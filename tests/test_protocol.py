import sys; sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "py_modules"))
from nothing_ear import protocol as P

# Paquetes reales capturados en ear2ctl (Ear (2)), mismo formato de trama
def h(s): return bytes(int(x,16) for x in s.split())
assert P.encode(0xC01E, [0x03], 0x0c) == h("55 60 01 1e c0 01 00 0c 03 98 19")
assert P.encode(0xF040, P.latency_set_payload(True), 0x27) == h("55 60 01 40 f0 02 00 27 01 00 97 f7")
assert P.encode(0xF040, P.latency_set_payload(False), 0x28)[:10] == h("55 60 01 40 f0 02 00 28 02 00")
assert P.encode(0xC042, [], 0x03) == h("55 60 01 42 c0 00 00 03 e0 d1")
assert P.encode(0xC018, [], 0x51) == h("55 60 01 18 c0 00 00 51 39 21")
# ANC set con ear2ctl: modo transparencia
pkt = P.encode(0xF00F, P.anc_set_payload(0x07), 0xcd)
assert pkt[:11] == h("55 60 01 0f f0 03 00 cd 01 07 00")

# Decoder: dos mensajes pegados + basura + mensaje partido
bat = P.encode(0x4007, [3, 0x02, 0x50, 0x03, 0xD5, 0x04, 0x40], 1)
anc = P.encode(0xE003, [0x01, 0x04, 0x00], 2)
d = P.Decoder()
msgs = d.feed(b"\x00\x01" + bat + anc[:5])
assert len(msgs) == 1 and msgs[0].payload_type == 0x4007
msgs += d.feed(anc[5:])
assert len(msgs) == 2 and msgs[1].seq == 2
b = P.parse_battery(msgs[0].payload)
assert b == {"left": {"level": 80, "charging": False}, "right": {"level": 85, "charging": True}, "case": {"level": 64, "charging": False}}, b
assert P.parse_anc(msgs[1].payload) == 0x04
assert P.parse_latency(bytes([1, 0])) is True and P.parse_latency(bytes([2, 0])) is False
assert P.parse_model(bytes([0x71, 0xB1])) == "B171"
# Detección en el oído: paquetes reales de ear2ctl
assert P.encode(0xF004, P.in_ear_payload(True), 0x26) == h("55 60 01 04 f0 03 00 26 01 01 01 73 10")
assert P.encode(0xF004, P.in_ear_payload(False), 0x25) == h("55 60 01 04 f0 03 00 25 01 01 00 b2 94")
print("OK")
