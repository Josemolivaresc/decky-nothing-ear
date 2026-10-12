#!/usr/bin/env bash
# Genera release/nothing-ear-deck.zip listo para instalar en Decky.
# Uso: scripts/package.sh   (desde la raíz del repositorio)
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=nothing-ear-deck
OUT=release
STAGE="$OUT/stage/$NAME"

pnpm install --frozen-lockfile
pnpm run build

rm -rf "$OUT"
mkdir -p "$STAGE"
cp -r dist main.py plugin.json package.json LICENSE NOTICE README.md README.es.md "$STAGE/"
mkdir -p "$STAGE/py_modules"
cp -r py_modules/nothing_ear "$STAGE/py_modules/"
python3 -m pip install --quiet --no-deps --target "$STAGE/py_modules" dbus-next==0.2.3
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$STAGE/py_modules/bin"

(cd "$OUT/stage" && zip -qr "../$NAME.zip" "$NAME")
rm -rf "$OUT/stage"
echo "Creado $OUT/$NAME.zip"
