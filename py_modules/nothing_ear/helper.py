"""Proceso auxiliar que habla con los auriculares.

El Python que trae Decky viene recortado (sin xml.etree, que necesita dbus-next),
así que el plugin lanza este script con el Python del sistema y se comunican
por líneas JSON:

  stdin  -> {"id": 1, "cmd": "set_anc", "args": ["adaptive"]}
  stdout <- {"id": 1, "result": {...estado...}}  o  {"id": 1, "error": "..."}
  stdout <- {"event": "state", "state": {...}}   (cambios espontáneos)

Los logs salen por stderr.
"""

import asyncio
import json
import logging
import os
import sys

# Nuestros módulos (y dbus-next) van por delante de los del sistema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nothing_ear.device import NothingEar  # noqa: E402

POLL_SECONDS = 15        # cada cuánto buscamos auriculares si no hay conexión
BATTERY_SECONDS = 60     # cada cuánto pedimos la batería estando conectados

log = logging.getLogger("nothing_ear")


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


async def on_state(state: dict) -> None:
    send({"event": "state", "state": state})


async def poll_loop(ear: NothingEar) -> None:
    tick = 0
    while True:
        try:
            if not ear.state["connected"]:
                await ear.connect()
            elif tick % (BATTERY_SECONDS // POLL_SECONDS) == 0:
                await ear.refresh_battery()
        except Exception:  # noqa: BLE001
            log.exception("Error en el bucle")
        tick += 1
        await asyncio.sleep(POLL_SECONDS)


async def handle(ear: NothingEar, req: dict) -> None:
    cmd, args, rid = req.get("cmd"), req.get("args", []), req.get("id")
    try:
        if cmd == "get_state":
            result = ear.state
        elif cmd == "reconnect":
            await ear.disconnect()
            result = await ear.connect()
        elif cmd == "set":
            result = await ear.set(*args)
        else:
            raise ValueError(f"Comando desconocido: {cmd}")
        send({"id": rid, "result": result})
    except Exception as e:  # noqa: BLE001
        log.exception("Error en %s", cmd)
        send({"id": rid, "error": str(e)})


async def main() -> None:
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s"
    )
    loop = asyncio.get_running_loop()
    ear = NothingEar(on_state)
    poll = loop.create_task(poll_loop(ear))

    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )
    log.info("Helper iniciado con %s", sys.executable)
    try:
        while True:
            line = await reader.readline()
            if not line:  # el plugin se ha cerrado
                break
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            loop.create_task(handle(ear, req))
    finally:
        poll.cancel()
        await ear.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
