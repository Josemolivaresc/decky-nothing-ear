"""Capacidades de cada modelo Nothing / CMF.

Los datos están en models.json, generado a partir de las configuraciones de
BudsLink (src/lib/devices/nothingBuds/deviceConfigs). No editar a mano.
"""

import json
import os

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.json")) as f:
    MODELS: dict = json.load(f)
