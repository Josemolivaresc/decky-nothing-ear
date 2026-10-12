# Nothing Ear for Decky

*[Leer en español](README.es.md)*

> [!IMPORTANT]
> ### 🙏 Built on BudsLink
> This plugin exists thanks to **[BudsLink](https://github.com/maniacx/BudsLink)** by **[maniacx](https://github.com/maniacx)**, the Linux app for controlling Bluetooth earbuds whose Nothing and CMF support made this plugin possible. The control protocol and the per-model capability table used here are ported directly from BudsLink.
>
> If you're on the Linux desktop, use BudsLink: it supports many more brands (Apple, Sony, Samsung, Nothing…) and is [available on Flathub](https://flathub.org/apps/io.github.maniacx.BudsLink). Go give it a ⭐. The credit for this work belongs to its author and to the projects BudsLink builds on, [ear-web](https://github.com/radiance-project/ear-web) and [earctl](https://github.com/DaanHessen/earctl).

> [!NOTE]
> **Written by AI.** All the code in this plugin was written by **Claude Opus 5.5** (Anthropic's AI model), directed and tested by Jose.

> [!WARNING]
> **Only tested with the Nothing Ear (2024, model B171).** Other Nothing and CMF models are included because BudsLink supports them, but they have **not been tested** and some options may not work. If you try another model, please [open an issue](../../issues).

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin to control Nothing and CMF earbuds and headphones from the Steam Deck Quick Access Menu, without leaving Game Mode.

- Battery for each earbud and the case, with charging indicator
- Noise control (off, transparency, noise cancellation) and cancellation level
- Low latency mode and spatial audio
- Equaliser (presets and 3-band custom EQ) and bass enhancement
- In-ear detection
- Ring each earbud to find it (with a double safety confirmation)
- Gesture customisation for each earbud
- Model, firmware and serial number

Only the options supported by your model are shown.

## Supported models

The same Nothing and CMF devices supported by [BudsLink](https://github.com/maniacx/BudsLink): Nothing Ear, Ear (1), Ear (2), Ear (3), Ear (a), Ear (Stick), Ear (open), Headphone (1), Headphone (a), CMF Buds, Buds 2, Buds 2a, Buds 2 Plus, Buds Neo, Buds Pro, Buds Pro 2, Headphone Pro and Neckband Pro.

✅ **Tested:** Nothing Ear (2024, B171).
⚠️ **Untested:** all other models. They use BudsLink's device data and should work, but nobody has confirmed it yet.

## Installation

This plugin is **not on the Decky Plugin Store**, so it's installed manually:

1. Pair and connect your earbuds in the Steam Deck Bluetooth settings.
2. In Decky, open **Settings → General** and enable **Developer mode**.
3. Open **Settings → Developer → Install Plugin from URL** and paste:
   ```
   https://github.com/OWNER/decky-nothing-ear/releases/latest/download/nothing-ear-deck.zip
   ```
   Or download the zip from [Releases](../../releases) and use **Install Plugin from ZIP**.

To update, repeat step 3. Updates are not automatic.

## Known issues

- **Only one app can use the control channel at a time.** If BudsLink or another app is connected to the earbuds, close it first.
- Decky always lists the plugin. When no earbuds are connected the panel just shows a short notice, and a notification appears when they connect or disconnect.

## How it works

Decky's bundled Python lacks `xml.etree`, which `dbus-next` needs, so the plugin backend (`main.py`) launches `py_modules/nothing_ear/helper.py` with the system Python and talks to it over JSON lines.

The helper registers a BlueZ profile for Nothing's control service UUID (`aeac4a03-dff5-498f-843a-34487cf133eb`). BlueZ finds the RFCOMM channel via SDP and hands over the socket. The plugin then speaks Nothing's protocol: a `55 60 01` header, command, length, sequence number, payload and CRC-16.

## Development

```sh
pnpm install
pnpm run build
pip install dbus-next==0.2.3
python3 tests/test_protocol.py
python3 tests/test_device.py
scripts/package.sh          # creates release/nothing-ear-deck.zip
```

To publish a release, bump `version` in `package.json`, commit, and push a matching tag (for example `v0.3.2`). GitHub Actions runs the tests, builds the zip and attaches it to the release.

## Credits

- **[BudsLink](https://github.com/maniacx/BudsLink) by maniacx**: the original project this plugin is based on. The Nothing protocol and per-model capability table were ported from it. Thank you!
- [ear-web](https://github.com/radiance-project/ear-web) and [earctl](https://github.com/DaanHessen/earctl), credited by BudsLink.
- [ear2ctl](https://gitlab.com/bharadwaj-raju/ear2ctl): reference packets, including in-ear detection.
- [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) by Steam Deck Homebrew.

Not affiliated with or endorsed by Nothing Technology.

## License

[GPL-3.0-or-later](LICENSE). See [NOTICE](NOTICE) for third-party licenses.
