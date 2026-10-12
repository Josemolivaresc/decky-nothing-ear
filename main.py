"""Backend del plugin.

El Python de Decky no trae todo lo que hace falta para hablar con BlueZ, así
que este archivo solo lanza py_modules/nothing_ear/helper.py con el Python del
sistema y hace de puente entre ese proceso y el frontend.
"""

import asyncio
import json
import os
import shutil

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(PLUGIN_DIR, "py_modules", "nothing_ear", "helper.py")
RESTART_DELAY = 5
REQUEST_TIMEOUT = 15

DISCONNECTED = {
    "connected": False, "name": None, "model": None, "model_name": None,
    "firmware": None, "serial": None, "error": None, "battery": {},
    "caps": {
        "anc_modes": [], "personalized_anc": False, "low_latency": False,
        "eq_presets": [], "custom_eq": False, "bass_levels": 0,
        "in_ear": False, "spatial": False, "ring": None, "gestures": [],
    },
    "anc": None, "personalized_anc": None, "low_latency": None,
    "eq_preset": None, "custom_eq": None, "bass": None, "in_ear": None,
    "spatial": None, "ring": {"left": False, "right": False, "single": False},
    "gestures": {},
}


def find_python() -> str | None:
    for candidate in ("/usr/bin/python3", shutil.which("python3")):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def clean_env() -> dict:
    # PyInstaller (Decky) mete rutas suyas que rompen el Python del sistema
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(key, None)
    orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    return env


class Plugin:
    async def _main(self):
        self.state = dict(DISCONNECTED)
        self.proc: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.next_id = 0
        self.running = True
        self.supervisor = asyncio.get_event_loop().create_task(self._supervise())
        decky.logger.info("Nothing Ear Deck iniciado")

    async def _supervise(self):
        python = find_python()
        if not python:
            self.state = dict(DISCONNECTED, error="No se encontró python3 en el sistema")
            decky.logger.error(self.state["error"])
            return
        while self.running:
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    python, "-I", HELPER,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=clean_env(),
                )
                decky.logger.info("Helper lanzado (pid %s) con %s", self.proc.pid, python)
                await asyncio.gather(self._read_stdout(), self._read_stderr())
                code = await self.proc.wait()
                decky.logger.warning("El helper terminó con código %s", code)
            except Exception:  # noqa: BLE001
                decky.logger.exception("No se pudo lanzar el helper")

            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("El proceso de Bluetooth se reinició"))
            self.pending.clear()
            self.state = dict(DISCONNECTED, error="Reiniciando el servicio de Bluetooth…")
            await decky.emit("state", self.state)
            if self.running:
                await asyncio.sleep(RESTART_DELAY)

    async def _read_stdout(self):
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                return
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                decky.logger.info("helper: %s", line.decode(errors="replace").rstrip())
                continue
            if msg.get("event") == "state":
                self.state = msg["state"]
                await decky.emit("state", self.state)
            elif "id" in msg:
                fut = self.pending.pop(msg["id"], None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(msg["error"]))
                    else:
                        self.state = msg["result"]
                        fut.set_result(msg["result"])

    async def _read_stderr(self):
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                return
            decky.logger.info("helper: %s", line.decode(errors="replace").rstrip())

    async def _call(self, cmd: str, *args):
        if not self.proc or self.proc.returncode is not None or not self.proc.stdin:
            raise RuntimeError("El servicio de Bluetooth no está en marcha")
        self.next_id += 1
        rid = self.next_id
        fut = asyncio.get_event_loop().create_future()
        self.pending[rid] = fut
        self.proc.stdin.write((json.dumps({"id": rid, "cmd": cmd, "args": list(args)}) + "\n").encode())
        await self.proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, REQUEST_TIMEOUT)
        finally:
            self.pending.pop(rid, None)

    async def _unload(self):
        self.running = False
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.stdin.close()  # el helper se cierra solo y libera BlueZ
                await asyncio.wait_for(self.proc.wait(), 3)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        self.supervisor.cancel()
        decky.logger.info("Nothing Ear Deck descargado")

    async def _uninstall(self):
        pass

    # ---- Llamadas desde el frontend ----

    async def get_state(self) -> dict:
        return self.state

    async def reconnect(self) -> dict:
        return await self._call("reconnect")

    async def set(self, key: str, value) -> dict:
        return await self._call("set", key, value)
