import os, sys, asyncio, socket
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from nothing_ear import protocol as P
from nothing_ear.device import NothingEar

T = P.PayloadType


class FakeEarbud:
    """Auricular simulado con todo el estado que maneja BudsLink."""

    def __init__(self, model_bytes, anc=0x05):
        self.model_bytes = model_bytes
        self.anc, self.lat, self.pers, self.eq = anc, False, False, 0x00
        self.custom = P.custom_eq_payload(0, 0, 0)
        self.bass, self.inear, self.spatial = (False, 1), True, False
        self.gestures = {(2, 1, 2): 0x08, (3, 1, 2): 0x09, (2, 1, 7): 0x0A}
        self.rings = []

    def reply(self, m):
        p = m.payload
        t = m.payload_type
        if t == T.DEVICE_MODEL_GET:
            return [(0x401C, self.model_bytes)] if self.model_bytes else []
        if t == T.FIRMWARE_GET: return [(0x4042, b"3.1.2")]
        if t == T.SERIAL_GET: return [(0x4006, b"\x01" + b"1,4,SH12345678\n")]
        if t == T.BATTERY_GET: return [(0x4007, [3, 2, 90, 3, 0x80 | 88, 4, 55])]
        if t == T.ANC_SET: self.anc = p[1]; return [(0x700F, [])]
        if t == T.ANC_GET: return [(0x401E, [1, self.anc])]
        if t == T.LATENCY_SET: self.lat = p[0] == 1; return [(0x7040, [p[0], 0])]
        if t == T.LATENCY_GET: return [(0x4041, [1 if self.lat else 2])]
        if t == T.PERSONALIZED_ANC_SET: self.pers = bool(p[0]); return [(0x7011, [])]
        if t == T.PERSONALIZED_ANC_GET: return [(0x4020, [int(self.pers)])]
        if t == T.EQ_SET: self.eq = p[0]; return [(0x7010, [])]
        if t == T.EQ_GET: return [(0x401F, [self.eq])]
        if t == T.LISTENING_MODE_GET: return []
        if t == T.CUSTOM_EQ_SET: self.custom = p; return [(0x7041, [])]
        if t == T.CUSTOM_EQ_GET: return [(0x4044, self.custom)]
        if t == T.ENHANCED_BASS_SET: self.bass = (bool(p[0]), p[1] // 2); return [(0x7051, p)]
        if t == T.ENHANCED_BASS_GET: return [(0x404E, [int(self.bass[0]), self.bass[1] * 2])]
        if t == T.IN_EAR_SET: self.inear = bool(p[2]); return [(0x7004, [])]
        if t == T.IN_EAR_GET: return [(0x400E, [1, 1, int(self.inear)])]
        if t == T.SPATIAL_AUDIO_SET: self.spatial = bool(p[0]); return [(0x7052, [])]
        if t == T.SPATIAL_AUDIO_GET: return [(0x404F, [int(self.spatial)])]
        if t == T.RING_SET: self.rings.append(bytes(p)); return [(0x7002, [])]
        if t == T.GESTURES_SET:
            self.gestures[(p[1], p[2], p[3])] = p[4]; return [(0x7003, [])]
        if t == T.GESTURES_GET:
            out = [len(self.gestures)]
            for (d, b, ty), a in self.gestures.items(): out += [d, b, ty, a]
            return [(0x4018, out)]
        return []

    async def run(self, sock):
        loop = asyncio.get_event_loop()
        dec = P.Decoder()
        while True:
            data = await loop.sock_recv(sock, 4096)
            if not data: return
            for m in dec.feed(data):
                for t, p in self.reply(m):
                    await loop.sock_sendall(sock, P.encode(t, p, m.seq))


async def start(fake, name):
    async def on_state(s): pass
    ear = NothingEar(on_state)
    ear.state["name"] = name
    a, b = socket.socketpair(); b.setblocking(False)
    task = asyncio.create_task(fake.run(b))
    ear._on_new_connection("/org/bluez/hci0/dev_X", os.dup(a.fileno())); a.close()
    await ear._initialize()
    return ear, b, task


async def main():
    # ---- Nothing Ear (B171): todas sus funciones
    fake = FakeEarbud([0x71, 0xB1])
    ear, b, task = await start(fake, "Nothing Ear")
    s = ear.state; c = s["caps"]
    assert s["model_name"] == "Nothing Ear" and s["firmware"] == "3.1.2", s
    assert s["serial"] == "SH12345678", s["serial"]
    assert s["battery"]["case"] == {"level": 55, "charging": False}
    assert not c["personalized_anc"] and c["in_ear"] and c["bass_levels"] == 5 and c["ring"] == "dual"
    assert not c["spatial"]
    assert [p["value"] for p in c["eq_presets"]] == ["balanced", "voice", "more_treble", "more_bass", "custom"]
    assert s["eq_preset"] == "balanced" and s["in_ear"] is True and s["custom_eq"] == [0, 0, 0]
    assert s["bass"] == {"enabled": False, "level": 1}
    assert s["gestures"]["2-1-2"] == 0x08 and s["gestures"]["2-1-7"] == 0x0A

    await ear.set("anc", "high"); assert ear.state["anc"] == "high" and fake.anc == 0x01
    await ear.set("low_latency", True); assert ear.state["low_latency"] and fake.lat
    await ear.set("eq_preset", "more_bass"); assert ear.state["eq_preset"] == "more_bass" and fake.eq == 3
    await ear.set("eq_preset", "custom")
    await ear.set("custom_eq", [4, -2.5, 1]); assert ear.state["custom_eq"] == [4.0, -2.5, 1.0], ear.state["custom_eq"]
    await ear.set("bass", {"enabled": True}); assert ear.state["bass"] == {"enabled": True, "level": 1}
    await ear.set("bass", {"level": 9}); assert ear.state["bass"] == {"enabled": True, "level": 5} and fake.bass == (True, 5)
    await ear.set("in_ear", False); assert ear.state["in_ear"] is False and fake.inear is False
    await ear.set("ring", {"target": "left", "playing": True})
    await ear.set("ring", {"target": "right", "playing": True})
    await ear.set("ring", {"target": "left", "playing": False})
    assert fake.rings == [b"\x02\x01", b"\x03\x01", b"\x02\x00"], fake.rings
    assert ear.state["ring"] == {"left": False, "right": True, "single": False}
    await ear.set("gesture", {"id": "3-1-2", "action": 0x0B})
    assert ear.state["gestures"]["3-1-2"] == 0x0B and fake.gestures[(3, 1, 2)] == 0x0B
    await ear.set("gesture", {"id": "2-1-7", "action": 0x16}); assert fake.gestures[(2, 1, 7)] == 0x16
    for bad in [("personalized_anc", True), ("spatial", True), ("gesture", {"id": "2-1-2", "action": 0x12}), ("eq_preset", "rock")]:
        try:
            await ear.set(*bad); raise AssertionError(f"debería fallar: {bad}")
        except ValueError:
            pass
    b.close(); await asyncio.sleep(0.1); task.cancel()
    assert ear.state["connected"] is False

    # ---- Ear (Stick): modos distintos
    fake = FakeEarbud([0x57, 0xB1], anc=0x01)
    ear, b, task = await start(fake, "Ear (Stick)")
    assert ear.state["caps"]["anc_modes"] == ["off", "anc"] and ear.state["anc"] == "off"
    await ear.set("anc", "anc"); assert fake.anc == 0x04
    b.close(); task.cancel()

    # ---- Nothing ear (1): timbre "legacy" sin byte de auricular
    fake = FakeEarbud([0x81, 0xB1])
    ear, b, task = await start(fake, "Nothing ear (1)")
    await ear.set("ring", {"target": "left", "playing": True})
    assert fake.rings == [b"\x01"] and ear.state["ring"]["single"], fake.rings
    b.close(); task.cancel()

    # ---- Headphone (1): una batería, timbre 0x06, sin modelo -> por nombre
    fake = FakeEarbud(None)
    ear, b, task = await start(fake, "Nothing Headphone (1)")
    assert ear.state["model"] == "B170" and ear.state["caps"]["ring"] == "single"
    await ear.set("ring", {"target": "single", "playing": True}); assert fake.rings == [b"\x06\x01"]
    b.close(); task.cancel()

    # ---- Desconocido: conecta, sin opciones
    ear, b, task = await start(FakeEarbud(None), "Auriculares raros")
    assert ear.state["connected"] and ear.state["caps"]["anc_modes"] == [] and ear.state["battery"]
    b.close(); task.cancel()
    print("OK")

asyncio.run(main())
