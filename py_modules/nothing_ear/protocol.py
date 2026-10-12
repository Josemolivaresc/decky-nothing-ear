"""Protocolo de los auriculares Nothing / CMF sobre RFCOMM.

Portado del código de BudsLink (GPL-3.0), que a su vez se basa en
ear-web (radiance-project) y earctl (DaanHessen).

Formato de un paquete:

    55 60 01 | tipo (LE, 2 bytes) | longitud (LE, 2 bytes) | seq | payload | crc16 (LE)
"""

from __future__ import annotations

from dataclasses import dataclass

HEADER_MAGIC = bytes([0x55, 0x60, 0x01])
HEADER_LEN = 8
CRC_LEN = 2

# UUID del servicio RFCOMM de Nothing
NOTHING_UUID = "aeac4a03-dff5-498f-843a-34487cf133eb"


class PayloadType:
    PROTOCOL_GET = 0xC001
    PROTOCOL_SET = 0xF001

    FIRMWARE_GET = 0xC042
    FIRMWARE_NTFY = 0x4042

    DEVICE_MODEL_GET = 0xC01C
    DEVICE_MODEL_RET = 0x401C

    BATTERY_GET = 0xC007
    BATTERY_PRIMARY_NTFY = 0xE001
    BATTERY_SECONDARY_NTFY = 0x4007

    ANC_GET = 0xC01E
    ANC_SET = 0xF00F
    ANC_PRIMARY_NTFY = 0xE003
    ANC_SECONDARY_NTFY = 0x401E

    LATENCY_GET = 0xC041
    LATENCY_SET = 0xF040
    LATENCY_RET = 0x4041
    LATENCY_NTFY = 0x7040

    SERIAL_GET = 0xC006
    SERIAL_RET = 0x4006

    UTC_TIME_SET = 0xF00A

    GESTURES_GET = 0xC018
    GESTURES_SET = 0xF003
    GESTURES_NTFY = 0x4018

    PERSONALIZED_ANC_GET = 0xC020
    PERSONALIZED_ANC_SET = 0xF011
    PERSONALIZED_ANC_NTFY = 0x4020

    EQ_GET = 0xC01F
    EQ_SET = 0xF010
    EQ_NTFY = 0x401F

    CUSTOM_EQ_GET = 0xC044
    CUSTOM_EQ_SET = 0xF041
    CUSTOM_EQ_NTFY = 0x4044

    ENHANCED_BASS_GET = 0xC04E
    ENHANCED_BASS_SET = 0xF051
    ENHANCED_BASS_RET = 0x404E
    ENHANCED_BASS_NTFY = 0x7051

    LISTENING_MODE_GET = 0xC050
    LISTENING_MODE_SET = 0xF01D
    LISTENING_MODE_NTFY = 0x4050

    SPATIAL_AUDIO_GET = 0xC04F
    SPATIAL_AUDIO_SET = 0xF052
    SPATIAL_AUDIO_NTFY = 0x404F

    IN_EAR_GET = 0xC00E
    IN_EAR_SET = 0xF004
    IN_EAR_NTFY = 0x400E

    RING_SET = 0xF002


class BatteryType:
    LEFT = 0x02
    RIGHT = 0x03
    CASE = 0x04
    SINGLE = 0x06



def _make_crc_table() -> list[int]:
    # CRC-16/ANSI (poly 0xA001 reflejado), idéntico a la tabla de BudsLink
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_CRC_TABLE = _make_crc_table()


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = _CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc & 0xFFFF


def encode(payload_type: int, payload: bytes | list[int], seq: int) -> bytes:
    payload = bytes(payload)
    header = HEADER_MAGIC + bytes([
        payload_type & 0xFF,
        (payload_type >> 8) & 0xFF,
        len(payload) & 0xFF,
        (len(payload) >> 8) & 0xFF,
        seq & 0xFF,
    ])
    packet = header + payload
    crc = crc16(packet)
    return packet + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


@dataclass
class Message:
    payload_type: int
    payload: bytes
    seq: int


class Decoder:
    """Va acumulando bytes y saca mensajes completos."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Message]:
        self._buf.extend(data)
        out: list[Message] = []
        while True:
            msg = self._extract()
            if msg is None:
                break
            out.append(msg)
        return out

    def _extract(self) -> Message | None:
        buf = self._buf
        start = buf.find(HEADER_MAGIC[0])
        if start < 0:
            buf.clear()
            return None
        if start > 0:
            del buf[:start]
        if len(buf) < HEADER_LEN:
            return None

        control = buf[1] | (buf[2] << 8)
        has_crc = (control & 0x20) != 0
        payload_len = buf[5] | (buf[6] << 8)
        total = HEADER_LEN + payload_len + (CRC_LEN if has_crc else 0)

        if total > 600:
            # Cabecera basura: descarta el byte y sigue buscando
            del buf[:1]
            return self._extract()
        if len(buf) < total:
            return None

        raw = bytes(buf[:total])
        del buf[:total]
        return Message(
            payload_type=raw[3] | (raw[4] << 8),
            payload=raw[HEADER_LEN:HEADER_LEN + payload_len],
            seq=raw[7],
        )


# ---- Parsers -------------------------------------------------------------

def parse_battery(payload: bytes) -> dict:
    result: dict = {}
    if not payload:
        return result
    count = payload[0]
    names = {
        BatteryType.LEFT: "left",
        BatteryType.RIGHT: "right",
        BatteryType.CASE: "case",
        BatteryType.SINGLE: "single",
    }
    for i in range(count):
        idx = 1 + i * 2
        if idx + 1 >= len(payload):
            break
        name = names.get(payload[idx])
        if name is None:
            continue
        level_byte = payload[idx + 1]
        result[name] = {
            "level": level_byte & 0x7F,
            "charging": bool(level_byte & 0x80),
        }
    return result


def parse_anc(payload: bytes) -> int | None:
    """Devuelve el byte del modo; cada modelo lo interpreta con su tabla."""
    if len(payload) < 2:
        return None
    return payload[1]


def parse_latency(payload: bytes) -> bool | None:
    if len(payload) < 1:
        return None
    return payload[0] == 0x01


def parse_model(payload: bytes) -> str | None:
    if len(payload) < 2:
        return None
    return format(payload[1] << 8 | payload[0], "X")


# ---- Payloads de escritura ----------------------------------------------

def anc_set_payload(mode_byte: int) -> bytes:
    return bytes([0x01, mode_byte, 0x00])


def latency_set_payload(enabled: bool) -> bytes:
    return bytes([0x01 if enabled else 0x02, 0x00])


# ---- Resto de funciones (portadas de BudsLink) ---------------------------

import struct  # noqa: E402

# Acción de gesto "control de ruido": qué modos recorre (bit0 off, bit1
# transparencia, bit2 cancelación) -> byte de acción
NC_CYCLE_TO_BYTE = {0b101: 0x14, 0b110: 0x16, 0b111: 0x0A, 0b011: 0x15}
NC_BYTE_TO_CYCLE = {v: k for k, v in NC_CYCLE_TO_BYTE.items()}


def bool_from_byte(b: int) -> bool | None:
    return {0: False, 1: True}.get(b)


def parse_personalized_anc(payload: bytes) -> bool | None:
    return bool_from_byte(payload[0]) if payload else None


def personalized_anc_payload(enabled: bool) -> bytes:
    return bytes([1 if enabled else 0])


def parse_eq_preset(payload: bytes) -> int | None:
    return payload[0] if payload else None


def eq_preset_payload(byte: int) -> bytes:
    return bytes([byte, 0x00])


def parse_enhanced_bass(payload: bytes) -> tuple[bool, int] | None:
    if len(payload) < 2:
        return None
    enabled = bool_from_byte(payload[0])
    if enabled is None:
        return None
    return enabled, payload[1] // 2


def enhanced_bass_payload(enabled: bool, level: int) -> bytes:
    return bytes([1 if enabled else 0, level * 2])


def parse_in_ear(payload: bytes) -> bool | None:
    return bool_from_byte(payload[2]) if len(payload) >= 3 else None


def in_ear_payload(enabled: bool) -> bytes:
    # BudsLink envía 00 00 estado y el auricular lo ignora; ear2ctl (probado
    # con hardware real) envía 01 01 estado, que es lo que funciona.
    return bytes([0x01, 0x01, 1 if enabled else 0])


def parse_spatial(payload: bytes) -> bool | None:
    return payload[0] == 0x01 if payload else None


def spatial_payload(enabled: bool) -> bytes:
    return bytes([1 if enabled else 0])


def ring_payload(playing: bool, target: int | None) -> bytes:
    """target: 0x02 izquierdo, 0x03 derecho, 0x06 diadema; None en modelos antiguos."""
    out = [] if target is None else [target]
    out.append(1 if playing else 0)
    return bytes(out)


def parse_gestures(payload: bytes) -> list[dict]:
    if not payload:
        return []
    slots, offset = [], 1
    for _ in range(payload[0]):
        if offset + 3 >= len(payload):
            break
        slots.append({
            "device": payload[offset],
            "button": payload[offset + 1],
            "type": payload[offset + 2],
            "action": payload[offset + 3],
        })
        offset += 4
    return slots


def gesture_payload(device: int, button: int, gtype: int, action: int) -> bytes:
    return bytes([0x01, device & 0xFF, button & 0xFF, gtype & 0xFF, action & 0xFF])


def parse_serial(payload: bytes) -> str | None:
    if len(payload) < 2:
        return None
    text = payload[1:].decode(errors="ignore")
    for line in text.strip().split("\n"):
        parts = line.split(",")
        if len(parts) == 3 and parts[1].strip() == "4" and parts[2]:
            return parts[2].strip()
    return None


# Ecualizador personalizado: 3 bandas (graves, medios, agudos) en ±6 dB.
# Los valores van como float32 con un "signo" propio para valores diminutos.

def _decode_eq_float(b: bytes) -> float:
    be = bytes([b[3], b[2], b[1], b[0]])
    if be[0] == 0 and be[1] == 0 and be[2] == 0 and be[3] & 0x80:
        return -struct.unpack(">f", be[:3] + bytes([be[3] & 0x7F]))[0]
    return struct.unpack(">f", be)[0]


def _encode_eq_float(value: float, total: bool = False) -> bytes:
    if total and value >= 0.0:
        return bytes([0x00, 0x00, 0x00, 0x80])
    be = bytearray(struct.pack(">f", value))
    if value != 0.0 and be[0] == 0 and be[1] == 0 and be[2] == 0:
        be[3] |= 0x80
    return bytes([be[3], be[2], be[1], be[0]])


def parse_custom_eq(payload: bytes) -> list[float] | None:
    if len(payload) < 45:
        return None
    levels = [_decode_eq_float(payload[6 + band * 13: 10 + band * 13]) for band in range(3)]

    def clamp(v: float) -> float:
        return round(max(-6.0, min(6.0, v)), 1)

    # El auricular guarda (medios, agudos, graves); devolvemos (graves, medios, agudos)
    return [clamp(levels[2]), clamp(levels[0]), clamp(levels[1])]


_CUSTOM_EQ_TEMPLATE = bytes([
    0x03, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x75, 0x44,
    0xc3, 0xf5, 0x28, 0x3f, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0xc0, 0x5a, 0x45, 0x00,
    0x00, 0x80, 0x3f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0c, 0x43, 0xcd, 0xcc,
    0x4c, 0x3f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


def custom_eq_payload(bass: float, mid: float, treble: float) -> bytes:
    out = bytearray(_CUSTOM_EQ_TEMPLATE)
    values = [mid, treble, bass]
    highest = max(abs(v) for v in values)
    out[1:5] = _encode_eq_float(-highest, True)
    for i, v in enumerate(values):
        out[6 + i * 13: 10 + i * 13] = _encode_eq_float(float(v))
    return bytes(out)
