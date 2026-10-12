"""Conexión con los auriculares a través de BlueZ (D-Bus) y estado del dispositivo.

En vez de adivinar el canal RFCOMM, registramos un perfil Bluetooth con el
UUID de Nothing (igual que hace BudsLink). BlueZ busca el canal por SDP, abre
la conexión y nos pasa el descriptor del socket en NewConnection.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Awaitable, Callable

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, method

from . import protocol as P
from .models import MODELS

log = logging.getLogger("nothing_ear")

PROFILE_PATH = "/io/github/nothingeardeck/profile"
RESPONSE_TIMEOUT = 0.4  # segundos que esperamos respuesta a cada petición


class _Profile(ServiceInterface):
    def __init__(self, owner: "NothingEar") -> None:
        super().__init__("org.bluez.Profile1")
        self._owner = owner

    @method()
    def Release(self):
        log.info("Perfil liberado por BlueZ")

    @method()
    def NewConnection(self, device: "o", fd: "h", properties: "a{sv}"):
        # dbus-next no cierra el fd recibido: pasa a ser nuestro
        log.info("NewConnection %s fd=%s", device, fd)
        self._owner._on_new_connection(device, fd)

    @method()
    def RequestDisconnection(self, device: "o"):
        log.info("RequestDisconnection %s", device)
        self._owner._close_socket()



# ---- Textos y capacidades que ve el panel --------------------------------

EQ_LABELS = {
    "balanced": "Equilibrado",
    "voice": "Voz",
    "more_treble": "Más agudos",
    "more_bass": "Más graves",
    "dirac": "Dirac",
    "rock": "Rock",
    "electronic": "Electrónica",
    "pop": "Pop",
    "enhance_vocals": "Realzar voces",
    "classical": "Clásica",
    "custom": "Personalizado",
}

GESTURE_GROUPS = {
    "left": "Auricular izquierdo",
    "right": "Auricular derecho",
    "single": "Gestos",
    "roller": "Rueda",
    "slider": "Deslizador",
    "case-knob": "Rueda del estuche",
}

GESTURE_LABELS = {
    "double-pinch": "Doble pellizco",
    "triple-pinch": "Triple pellizco",
    "action-hold-pinch": "Pellizcar y mantener",
    "double-action-hold-pinch": "Doble pellizco y mantener",
    "double-tap": "Doble toque",
    "triple-tap": "Triple toque",
    "action-hold-tap": "Tocar y mantener",
    "double-action-hold-tap": "Doble toque y mantener",
    "single-press": "Pulsación",
    "double-press": "Doble pulsación",
    "triple-press": "Triple pulsación",
    "action-hold-press": "Pulsar y mantener",
    "double-action-hold-press": "Doble pulsación y mantener",
    "roller-action-hold-press": "Pulsar y mantener",
    "slider-single-slide": "Deslizar",
    "case-knob-single-press": "Pulsación",
    "case-knob-double-press": "Doble pulsación",
    "case-knob-triple-press": "Triple pulsación",
    "case-knob-action-hold-press": "Pulsar y mantener",
    "case-knob-double-action-hold-press": "Doble pulsación y mantener",
    "case-knob-rotate-rotate": "Girar",
}

ACTION_LABELS = {
    "play-pause": "Reproducir / pausar",
    "skip-back": "Pista anterior",
    "skip-forward": "Pista siguiente",
    "voice-assistant": "Asistente de voz",
    "volume-up": "Subir volumen",
    "volume-down": "Bajar volumen",
    "volume-control": "Control de volumen",
    "no-action": "Sin acción",
    "anc-type": "Tipo de cancelación",
    "case-game-mode": "Modo juego",
    "channel-hop": "Cambiar de canal",
    "eq-preset": "Cambiar ecualización",
    "essential-space": "Essential Space",
    "mic-on-off": "Silenciar micrófono",
    "news-description": "Noticias",
    "spatial-audio": "Audio espacial",
    "take-photo": "Hacer foto",
    "treble-enhance": "Realzar agudos",
    "ultra-bass": "Ultra Bass",
}

NOISE_CYCLE_LABELS = {
    0x0A: "Ruido: off · transp. · cancelación",
    0x14: "Ruido: off · cancelación",
    0x16: "Ruido: transp. · cancelación",
    0x15: "Ruido: off · transparencia",
}


def gesture_id(device: int, button: int, gtype: int) -> str:
    return f"{device}-{button}-{gtype}"


def _gesture_caps(model: dict) -> list[dict]:
    g = model.get("gestures")
    if not g:
        return []
    out = []
    for slot in g["slots"]:
        conf = g["gestures"].get(slot["type"])
        type_byte = g["types"].get(slot["type"])
        if not conf or type_byte is None:
            continue
        options = []
        for action in conf["actions"]:
            if action == "noise-control":
                options += [{"value": b, "label": t} for b, t in NOISE_CYCLE_LABELS.items()]
            elif action in g["actions"]:
                options.append({
                    "value": g["actions"][action][0],
                    "label": ACTION_LABELS.get(action, action),
                })
        out.append({
            "id": gesture_id(slot["device"], slot["buttonId"], type_byte),
            "device": slot["device"],
            "button": slot["buttonId"],
            "type": type_byte,
            "group": slot["group"],
            "group_label": GESTURE_GROUPS.get(slot["group"], slot["group"]),
            "label": GESTURE_LABELS.get(f"{slot['type']}-{conf['kind']}", slot["type"]),
            "options": options,
        })
    return out


def _caps(model: dict | None) -> dict:
    if model is None:
        return {
            "anc_modes": [], "personalized_anc": False, "low_latency": False,
            "eq_presets": [], "custom_eq": False, "bass_levels": 0,
            "in_ear": False, "spatial": False, "ring": None, "gestures": [],
        }
    presets = [
        {"value": k, "label": EQ_LABELS[k]}
        for k in model["eq_presets"] if k in EQ_LABELS
    ]
    if not model["ring"]:
        ring = None
    elif model["ring_legacy"]:
        ring = "legacy"
    elif model["single_battery"]:
        ring = "single"
    else:
        ring = "dual"
    return {
        "anc_modes": list(model["anc"].keys()),
        # Oculta: en los modelos actuales la cancelación se adapta sola al oído y
        # la app oficial no ofrece este interruptor (ver models.json si se recupera)
        "personalized_anc": False,
        "low_latency": model["low_latency"],
        "eq_presets": presets,
        "custom_eq": "custom" in model["eq_presets"],
        "bass_levels": model["bass_levels"],
        "in_ear": model["in_ear"],
        "spatial": model["spatial"],
        "ring": ring,
        "gestures": _gesture_caps(model),
    }


class NothingEar:
    def __init__(self, on_state: Callable[[dict], Awaitable[None]]) -> None:
        self._on_state = on_state
        self._bus: MessageBus | None = None
        self._profile_registered = False
        self._fd: int | None = None
        self._device_path: str | None = None
        self._decoder = P.Decoder()
        self._seq = 0
        self._lock = asyncio.Lock()
        self._pending: tuple[int, asyncio.Future] | None = None
        self._connected_event = asyncio.Event()
        self._model: dict | None = None
        self._anc_by_byte: dict[int, str] = {}
        self._eq_by_byte: dict[int, str] = {}
        self.state = self._empty_state()

    # ---------------------------------------------------------------- estado

    @staticmethod
    def _empty_state() -> dict:
        return {
            "connected": False,
            "name": None,
            "model": None,
            "model_name": None,
            "firmware": None,
            "serial": None,
            "error": None,
            "caps": _caps(None),
            "battery": {},
            "anc": None,
            "personalized_anc": None,
            "low_latency": None,
            "eq_preset": None,
            "custom_eq": None,
            "bass": None,          # {"enabled": bool, "level": int}
            "in_ear": None,
            "spatial": None,
            "ring": {"left": False, "right": False, "single": False},
            "gestures": {},        # id de gesto -> byte de acción
        }

    def _publish(self) -> None:
        asyncio.get_event_loop().create_task(self._on_state(dict(self.state)))

    # ------------------------------------------------------------------ dbus

    async def _ensure_bus(self) -> MessageBus:
        if self._bus is None or not self._bus.connected:
            self._bus = await MessageBus(
                bus_type=BusType.SYSTEM, negotiate_unix_fd=True
            ).connect()
            self._bus.export(PROFILE_PATH, _Profile(self))
            self._profile_registered = False
        if not self._profile_registered:
            intro = await self._bus.introspect("org.bluez", "/org/bluez")
            obj = self._bus.get_proxy_object("org.bluez", "/org/bluez", intro)
            mgr = obj.get_interface("org.bluez.ProfileManager1")
            try:
                await mgr.call_register_profile(
                    PROFILE_PATH,
                    P.NOTHING_UUID,
                    {
                        "Name": Variant("s", "Nothing Ear Deck"),
                        "Role": Variant("s", "client"),
                        "AutoConnect": Variant("b", False),
                    },
                )
            except DBusError as e:
                # Si ya está registrado por nosotros mismos, no pasa nada
                if "AlreadyExists" not in e.type:
                    raise
            self._profile_registered = True
        return self._bus

    async def _find_device(self) -> tuple[str, str] | None:
        bus = await self._ensure_bus()
        intro = await bus.introspect("org.bluez", "/")
        obj = bus.get_proxy_object("org.bluez", "/", intro)
        om = obj.get_interface("org.freedesktop.DBus.ObjectManager")
        objects = await om.call_get_managed_objects()
        for path, ifaces in objects.items():
            dev = ifaces.get("org.bluez.Device1")
            if not dev:
                continue
            uuids = [u.lower() for u in dev.get("UUIDs", Variant("as", [])).value]
            connected = dev.get("Connected", Variant("b", False)).value
            if connected and P.NOTHING_UUID in uuids:
                name = dev.get("Alias", dev.get("Name", Variant("s", "Nothing"))).value
                return path, name
        return None

    # -------------------------------------------------------------- conexión

    async def connect(self) -> dict:
        """Busca unos Nothing conectados y abre el canal de control."""
        if self.state["connected"]:
            return self.state
        try:
            found = await self._find_device()
        except Exception as e:  # noqa: BLE001
            log.exception("Error hablando con BlueZ")
            self.state["error"] = f"Error con BlueZ: {e}"
            self._publish()
            return self.state

        if not found:
            self.state = self._empty_state()
            self.state["error"] = "No hay auriculares Nothing conectados"
            self._publish()
            return self.state

        path, name = found
        self.state["name"] = name
        self._connected_event.clear()

        bus = await self._ensure_bus()
        intro = await bus.introspect("org.bluez", path)
        dev = bus.get_proxy_object("org.bluez", path, intro).get_interface(
            "org.bluez.Device1"
        )
        try:
            await dev.call_connect_profile(P.NOTHING_UUID)
        except DBusError as e:
            if "AlreadyConnected" in e.type or "InProgress" in e.type:
                self.state["error"] = (
                    "El canal de control ya lo está usando otra app "
                    "(¿BudsLink abierto?). Ciérrala y reconecta."
                )
            else:
                self.state["error"] = f"No se pudo abrir el canal: {e.text}"
            self._publish()
            return self.state

        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.state["error"] = "Los auriculares no respondieron"
            self._publish()
            return self.state

        await self._initialize()
        return self.state

    def _on_new_connection(self, device: str, fd: int) -> None:
        self._close_socket(publish=False)
        self._fd = fd
        self._device_path = device
        self._decoder = P.Decoder()
        os.set_blocking(fd, False)
        asyncio.get_event_loop().add_reader(fd, self._on_readable)
        self.state["connected"] = True
        self.state["error"] = None
        self._connected_event.set()

    def _close_socket(self, publish: bool = True) -> None:
        if self._fd is not None:
            try:
                asyncio.get_event_loop().remove_reader(self._fd)
            except Exception:  # noqa: BLE001
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        if self._pending:
            self._pending[1].cancel()
            self._pending = None
        if self.state["connected"]:
            name = self.state["name"]
            self.state = self._empty_state()
            self.state["name"] = name
            if publish:
                self._publish()

    async def disconnect(self) -> None:
        if self._device_path and self._bus:
            try:
                intro = await self._bus.introspect("org.bluez", self._device_path)
                dev = self._bus.get_proxy_object(
                    "org.bluez", self._device_path, intro
                ).get_interface("org.bluez.Device1")
                await dev.call_disconnect_profile(P.NOTHING_UUID)
            except Exception:  # noqa: BLE001
                pass
        self._close_socket()

    async def shutdown(self) -> None:
        await self.disconnect()
        if self._bus and self._bus.connected:
            if self._profile_registered:
                try:
                    intro = await self._bus.introspect("org.bluez", "/org/bluez")
                    mgr = self._bus.get_proxy_object(
                        "org.bluez", "/org/bluez", intro
                    ).get_interface("org.bluez.ProfileManager1")
                    await mgr.call_unregister_profile(PROFILE_PATH)
                except Exception:  # noqa: BLE001
                    pass
            self._bus.disconnect()
        self._bus = None
        self._profile_registered = False

    # ------------------------------------------------------------- lectura

    def _on_readable(self) -> None:
        if self._fd is None:
            return
        try:
            data = os.read(self._fd, 1024)
        except BlockingIOError:
            return
        except OSError as e:
            log.info("Socket cerrado: %s", e)
            self._close_socket()
            return
        if not data:
            log.info("Socket cerrado por el otro extremo")
            self._close_socket()
            return

        changed = False
        for msg in self._decoder.feed(data):
            if self._pending and self._pending[0] == msg.seq:
                fut = self._pending[1]
                if not fut.done():
                    fut.set_result(msg)
            changed |= self._handle(msg)
        if changed:
            self._publish()

    def _handle(self, msg: P.Message) -> bool:
        T = P.PayloadType
        t, p, st = msg.payload_type, msg.payload, self.state

        if t in (T.BATTERY_PRIMARY_NTFY, T.BATTERY_SECONDARY_NTFY):
            battery = P.parse_battery(p)
            if battery:
                st["battery"] = battery
                return True
        elif t in (T.ANC_PRIMARY_NTFY, T.ANC_SECONDARY_NTFY):
            mode = self._anc_by_byte.get(P.parse_anc(p))
            if mode:
                st["anc"] = mode
                return True
        elif t == T.PERSONALIZED_ANC_NTFY:
            value = P.parse_personalized_anc(p)
            if value is not None:
                st["personalized_anc"] = value
                return True
        elif t in (T.LATENCY_RET, T.LATENCY_NTFY):
            value = P.parse_latency(p)
            if value is not None:
                st["low_latency"] = value
                return True
        elif t in (T.EQ_NTFY, T.LISTENING_MODE_NTFY):
            preset = self._eq_by_byte.get(P.parse_eq_preset(p))
            if preset:
                st["eq_preset"] = preset
                return True
        elif t == T.CUSTOM_EQ_NTFY:
            levels = P.parse_custom_eq(p)
            if levels:
                st["custom_eq"] = levels
                return True
        elif t in (T.ENHANCED_BASS_RET, T.ENHANCED_BASS_NTFY):
            bass = P.parse_enhanced_bass(p)
            if bass:
                st["bass"] = {"enabled": bass[0], "level": bass[1]}
                return True
        elif t == T.IN_EAR_NTFY:
            value = P.parse_in_ear(p)
            if value is not None:
                st["in_ear"] = value
                return True
        elif t == T.SPATIAL_AUDIO_NTFY:
            value = P.parse_spatial(p)
            if value is not None:
                st["spatial"] = value
                return True
        elif t == T.GESTURES_NTFY:
            slots = P.parse_gestures(p)
            if slots:
                gestures = dict(st["gestures"])
                for s in slots:
                    gestures[gesture_id(s["device"], s["button"], s["type"])] = s["action"]
                st["gestures"] = gestures
                return True
        elif t == T.DEVICE_MODEL_RET:
            model_id = P.parse_model(p)
            if model_id and self._model is None:
                self._set_model(model_id, MODELS.get(model_id))
                return True
        elif t == T.FIRMWARE_NTFY:
            st["firmware"] = p.decode(errors="ignore").strip("\x00 ")
            return True
        elif t == T.SERIAL_RET:
            serial = P.parse_serial(p)
            if serial:
                st["serial"] = serial
                return True
        return False

    # ------------------------------------------------------------ escritura

    async def _request(self, payload_type: int, payload: bytes = b"") -> P.Message | None:
        """Envía un paquete y espera (como mucho RESPONSE_TIMEOUT) su respuesta."""
        async with self._lock:
            if self._fd is None:
                raise RuntimeError("No conectado")
            self._seq = 1 if self._seq >= 250 else self._seq + 1
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            self._pending = (self._seq, fut)
            try:
                os.write(self._fd, P.encode(payload_type, payload, self._seq))
            except OSError:
                self._pending = None
                self._close_socket()
                raise RuntimeError("Se perdió la conexión")
            try:
                return await asyncio.wait_for(fut, RESPONSE_TIMEOUT)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return None
            finally:
                self._pending = None

    def _set_model(self, model_id: str | None, model: dict | None) -> None:
        self._model = model
        self.state["model"] = model_id
        self.state["model_name"] = model["name"] if model else None
        self.state["caps"] = _caps(model)
        self._anc_by_byte = {b: m for m, b in model["anc"].items()} if model else {}
        self._eq_by_byte = (
            {b: k for k, b in model["eq_presets"].items()} if model else {}
        )

    def _model_from_name(self) -> None:
        """Si el auricular no dice su modelo, lo deducimos por el nombre (como BudsLink)."""
        name = self.state.get("name") or ""
        for model_id, model in MODELS.items():
            if model["pattern"] and re.search(model["pattern"], name):
                log.info("Modelo deducido por nombre: %s (%s)", model["name"], model_id)
                self._set_model(model_id, model)
                return
        log.info("Modelo desconocido para el nombre %r", name)

    async def _initialize(self) -> None:
        T = P.PayloadType
        self._model = None
        self._set_model(None, None)
        try:
            for t in (T.PROTOCOL_GET, T.PROTOCOL_SET, T.DEVICE_MODEL_GET):
                await self._request(t)
            if self._model is None:
                # Algunos modelos tardan en contestar el id: un reintento
                await self._request(T.DEVICE_MODEL_GET)
            if self._model is None:
                self._model_from_name()

            caps = self.state["caps"]
            gets = [T.FIRMWARE_GET, T.SERIAL_GET, T.BATTERY_GET]
            if caps["anc_modes"]:
                gets.append(T.ANC_GET)
            if caps["personalized_anc"]:
                gets.append(T.PERSONALIZED_ANC_GET)
            if caps["low_latency"]:
                gets.append(T.LATENCY_GET)
            if caps["eq_presets"]:
                # Según el modelo contesta a uno u otro: preguntamos por los dos
                gets += [T.EQ_GET, T.LISTENING_MODE_GET]
            if caps["bass_levels"]:
                gets.append(T.ENHANCED_BASS_GET)
            if caps["in_ear"]:
                gets.append(T.IN_EAR_GET)
            if caps["spatial"]:
                gets.append(T.SPATIAL_AUDIO_GET)
            if caps["gestures"]:
                gets.append(T.GESTURES_GET)
            for t in gets:
                await self._request(t)
            if caps["custom_eq"]:
                await self._request(T.CUSTOM_EQ_GET)
        except RuntimeError:
            return
        self._publish()

    async def refresh_battery(self) -> None:
        if self._fd is not None:
            try:
                await self._request(P.PayloadType.BATTERY_GET)
            except RuntimeError:
                pass

    # --------------------------------------------------- cambios del panel

    def _need(self, cap: str) -> dict:
        caps = self.state["caps"]
        if not caps.get(cap):
            raise ValueError("Este modelo no admite esta opción")
        return caps

    async def _set_and_check(self, set_type: int, payload: bytes, get_type: int | None) -> None:
        await self._request(set_type, payload)
        if get_type is not None:
            await self._request(get_type)

    async def set(self, key: str, value) -> dict:
        """Aplica un cambio desde el panel y devuelve el estado nuevo."""
        T, st = P.PayloadType, self.state
        if not st["connected"]:
            raise RuntimeError("Los auriculares no están conectados")

        if key == "anc":
            if not self._model or value not in self._model["anc"]:
                raise ValueError(f"Este modelo no admite el modo {value}")
            st["anc"] = value
            await self._set_and_check(
                T.ANC_SET, P.anc_set_payload(self._model["anc"][value]), T.ANC_GET
            )

        elif key == "personalized_anc":
            self._need("personalized_anc")
            st["personalized_anc"] = bool(value)
            await self._set_and_check(
                T.PERSONALIZED_ANC_SET, P.personalized_anc_payload(bool(value)),
                T.PERSONALIZED_ANC_GET,
            )

        elif key == "low_latency":
            self._need("low_latency")
            st["low_latency"] = bool(value)
            await self._set_and_check(
                T.LATENCY_SET, P.latency_set_payload(bool(value)), T.LATENCY_GET
            )

        elif key == "eq_preset":
            self._need("eq_presets")
            byte = self._model["eq_presets"].get(value) if self._model else None
            if byte is None:
                raise ValueError(f"Ecualización desconocida: {value}")
            st["eq_preset"] = value
            set_type = T.LISTENING_MODE_SET if self._model["eq_listening_mode"] else T.EQ_SET
            await self._request(set_type, P.eq_preset_payload(byte))
            if value == "custom":
                await self._request(T.CUSTOM_EQ_GET)

        elif key == "custom_eq":
            self._need("custom_eq")
            bass, mid, treble = (max(-6.0, min(6.0, float(v))) for v in value)
            st["custom_eq"] = [bass, mid, treble]
            await self._set_and_check(
                T.CUSTOM_EQ_SET, P.custom_eq_payload(bass, mid, treble), T.CUSTOM_EQ_GET
            )

        elif key == "bass":
            caps = self._need("bass_levels")
            current = st["bass"] or {"enabled": False, "level": 1}
            enabled = bool(value.get("enabled", current["enabled"]))
            level = int(value.get("level", current["level"]))
            level = max(1, min(caps["bass_levels"], level))
            st["bass"] = {"enabled": enabled, "level": level}
            await self._set_and_check(
                T.ENHANCED_BASS_SET, P.enhanced_bass_payload(enabled, level),
                T.ENHANCED_BASS_GET,
            )

        elif key == "in_ear":
            self._need("in_ear")
            st["in_ear"] = bool(value)
            await self._set_and_check(
                T.IN_EAR_SET, P.in_ear_payload(bool(value)), T.IN_EAR_GET
            )

        elif key == "spatial":
            self._need("spatial")
            st["spatial"] = bool(value)
            await self._set_and_check(
                T.SPATIAL_AUDIO_SET, P.spatial_payload(bool(value)), T.SPATIAL_AUDIO_GET
            )

        elif key == "ring":
            caps = self._need("ring")
            target, playing = value["target"], bool(value["playing"])
            if caps["ring"] == "legacy":
                byte, target = None, "single"
            elif caps["ring"] == "single":
                byte, target = 0x06, "single"
            else:
                byte = 0x02 if target == "left" else 0x03
            ring = dict(st["ring"])
            ring[target] = playing
            st["ring"] = ring
            await self._request(T.RING_SET, P.ring_payload(playing, byte))

        elif key == "gesture":
            caps = self._need("gestures")
            slot = next((g for g in caps["gestures"] if g["id"] == value["id"]), None)
            action = int(value["action"])
            if not slot or action not in {o["value"] for o in slot["options"]}:
                raise ValueError("Gesto o acción no válidos")
            gestures = dict(st["gestures"])
            gestures[slot["id"]] = action
            st["gestures"] = gestures
            await self._set_and_check(
                T.GESTURES_SET,
                P.gesture_payload(slot["device"], slot["button"], slot["type"], action),
                T.GESTURES_GET,
            )

        else:
            raise ValueError(f"Opción desconocida: {key}")

        self._publish()
        return self.state
