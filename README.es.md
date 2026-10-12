# Nothing Ear para Decky

*[Read in English](README.md)*

> [!IMPORTANT]
> ### 🙏 Basado en BudsLink
> Este plugin existe gracias a **[BudsLink](https://github.com/maniacx/BudsLink)**, de **[maniacx](https://github.com/maniacx)**, la app de Linux para controlar auriculares Bluetooth cuya compatibilidad con Nothing y CMF ha hecho posible este plugin. El protocolo de control y la tabla de capacidades por modelo que usa este plugin están portados directamente de BudsLink.
>
> Si usas Linux en el escritorio, usa BudsLink: es compatible con muchas más marcas (Apple, Sony, Samsung, Nothing…) y está [disponible en Flathub](https://flathub.org/apps/io.github.maniacx.BudsLink). Dale una ⭐. El mérito de este trabajo es de su autor y de los proyectos en los que se apoya BudsLink, [ear-web](https://github.com/radiance-project/ear-web) y [earctl](https://github.com/DaanHessen/earctl).

> [!NOTE]
> **Escrito por IA.** Todo el código de este plugin lo ha escrito **Claude Opus 5.5** (el modelo de IA de Anthropic), bajo la dirección y las pruebas de Jose.

> [!WARNING]
> **Solo probado con los Nothing Ear (2024, modelo B171).** Los demás modelos Nothing y CMF están incluidos porque BudsLink los admite, pero **no se han probado** y puede que algunas opciones no funcionen. Si pruebas otro modelo, [abre una incidencia](../../issues).

Plugin de [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) para controlar auriculares Nothing y CMF desde el menú de acceso rápido de la Steam Deck, sin salir del modo Juego.

- Batería de cada auricular y del estuche, con indicador de carga
- Control de ruido (apagado, transparencia, cancelación) y nivel de cancelación
- Modo baja latencia y audio espacial
- Ecualizador (preajustes y personalizado de 3 bandas) y realce de graves
- Detección en el oído
- Hacer sonar cada auricular para encontrarlo (con doble confirmación de seguridad)
- Gestos de cada auricular
- Modelo, firmware y número de serie

Solo aparecen las opciones que admite tu modelo.

## Modelos compatibles

Los mismos modelos Nothing y CMF que [BudsLink](https://github.com/maniacx/BudsLink): Nothing Ear, Ear (1), Ear (2), Ear (3), Ear (a), Ear (Stick), Ear (open), Headphone (1), Headphone (a), CMF Buds, Buds 2, Buds 2a, Buds 2 Plus, Buds Neo, Buds Pro, Buds Pro 2, Headphone Pro y Neckband Pro.

✅ **Probado:** Nothing Ear (2024, B171).
⚠️ **Sin probar:** todos los demás. Usan los datos de BudsLink y deberían funcionar, pero nadie lo ha confirmado todavía.

## Instalación

Este plugin **no está en la tienda de Decky**, así que se instala a mano:

1. Empareja y conecta los auriculares desde los ajustes de Bluetooth de la Steam Deck.
2. En Decky, abre **Ajustes → General** y activa el **Modo desarrollador**.
3. Abre **Ajustes → Desarrollador → Instalar plugin desde URL** y pega:
   ```
   https://github.com/OWNER/decky-nothing-ear/releases/latest/download/nothing-ear-deck.zip
   ```
   O descarga el zip desde [Releases](../../releases) y usa **Instalar plugin desde ZIP**.

Para actualizar, repite el paso 3. Las actualizaciones no son automáticas.

## Problemas conocidos

- **Solo una app puede usar el canal de control a la vez.** Si BudsLink u otra app está conectada a los auriculares, ciérrala primero.
- Decky siempre muestra el plugin en su lista. Sin auriculares conectados, el panel solo muestra un aviso breve, y salta una notificación al conectarlos o desconectarlos.

## Cómo funciona

El Python que trae Decky no incluye `xml.etree`, que necesita `dbus-next`. Por eso el backend del plugin (`main.py`) lanza `py_modules/nothing_ear/helper.py` con el Python del sistema y se comunica con él por líneas JSON.

Ese proceso registra un perfil en BlueZ con el UUID del servicio de control de Nothing (`aeac4a03-dff5-498f-843a-34487cf133eb`). BlueZ encuentra el canal RFCOMM por SDP y le pasa el socket. A partir de ahí, el plugin habla el protocolo de Nothing: cabecera `55 60 01`, comando, longitud, número de secuencia, datos y CRC-16.

## Desarrollo

```sh
pnpm install
pnpm run build
pip install dbus-next==0.2.3
python3 tests/test_protocol.py
python3 tests/test_device.py
scripts/package.sh          # genera release/nothing-ear-deck.zip
```

Para publicar una versión, sube `version` en `package.json`, haz commit y sube un tag con el mismo número (por ejemplo `v0.3.2`). GitHub Actions pasa los tests, genera el zip y lo adjunta a la release.

## Créditos

- **[BudsLink](https://github.com/maniacx/BudsLink), de maniacx**: el proyecto original en el que se basa este plugin. De ahí se ha portado el protocolo de Nothing y la tabla de capacidades por modelo. ¡Gracias!
- [ear-web](https://github.com/radiance-project/ear-web) y [earctl](https://github.com/DaanHessen/earctl), a los que BudsLink da crédito.
- [ear2ctl](https://gitlab.com/bharadwaj-raju/ear2ctl): paquetes de referencia, incluida la detección en el oído.
- [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template), de Steam Deck Homebrew.

Sin relación ni respaldo de Nothing Technology.

## Licencia

[GPL-3.0 o posterior](LICENSE). Las licencias de terceros están en [NOTICE](NOTICE).
