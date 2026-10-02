# Worked example: phone-remote

`chrisye96/phone-remote` is a Python desktop program with a phone web page that controls a computer. It already had English and Chinese. This skill was built and tested by adding Spanish (Latin American, informal) and Arabic (RTL, several plural forms) to a scratch copy of it. Use this file as the recipe for adding a language to that project.

## Where the strings are

| Table | File | Strings | Shown where |
|---|---|---|---|
| Phone page | `src/phone_remote/web/js/i18n.js`, block `zh` | 122 | the page on the phone |
| Computer side | `src/phone_remote/i18n.py`, `_TABLES["zh"]` | 23 | tray menu, QR page, console |

Both are English-keyed (see `english-keyed-tables.md`). Export both with `--lang zh --identity` for the source and `--lang zh` for the reference. Run `context <repo root>` on each; every key was found in the code.

## Glossary that worked (Spanish)

Keep as is: `Phone Remote`, `Bilibili`, `Danmaku`, `Wi-Fi`. Rendered one way: computer, phone, pair/pairing, shortcut, tab, QR code, window. Choose the variant first (`computadora` for Latin America, `teléfono` not `móvil`, `vincular` for pairing). A different glossary per table is not needed here, because the OS name "Windows" is only in the computer side table and is not a glossary term.

## Integration points (all of them)

1. `i18n.py`: add the block to `_TABLES` (`emit --format py --indent 4`) and the code and name to `LANGUAGES`. The tray language menu, the saved `config.json` validation and `set_language` all read `LANGUAGES`, so nothing else changes on the computer side.
2. `web/js/i18n.js`: add the block after `zh` (`emit --format js --indent 2`).
3. `web/js/i18n.js`, `initLanguage()`: the switcher toggles `en` and `zh` only. Change it to cycle through `["en", ...Object.keys(TABLES)]`.
4. `web/js/i18n.js`, `translatePage()`: for RTL languages set `document.documentElement.dir = "rtl"` (otherwise `"ltr"`).
5. `web/index.html`: the inline anti flash script tests `localStorage.lang === "zh"`; change it to `localStorage.lang && localStorage.lang !== "en"`. Add a `<span data-lang="xx">` label to the `#lang` button for each language.
6. `tests/test_i18n.py` only covers `zh`; the new language is covered by `l10n.py check` instead. Run the project's full test suite after integrating (79 tests at the time of testing, all passing).
7. `README.md` and `README.zh-CN.md` list the supported languages.

## What testing found

- `check` on the first Spanish pass: 0 errors. Warnings: `Next tab` 112 percent longer (kept, it sits under a "Tabs" heading but the glossary requires the word), `General` identical (a real Spanish word).
- Back-translation changed three Spanish strings (`Rewind` to `Rebobinar`, `Fast forward` to `Avance rápido`, `Start at login` to `Abrir al iniciar sesión`) and five Arabic ones (`Forward`, `Zoom in`, `Zoom out`, `Sleep timer`, `Start at login`). The word similarity score flagged about a quarter of all strings; most were synonyms.
- Arabic accepted warnings: `Enter` and the example address `192.168.1.5:8765/#code` stay Latin on purpose; `Volume {n}`, `{n} min left` and `Pausing in {n} min` use an abbreviated unit ("د") so the plural form of the unit never appears.
- In the browser at 375 px wide: Spanish and Arabic render without console errors. The status text in the header wraps to three lines when the phone is not paired; that is also true in English, so it is an existing layout limit, made slightly worse by two more labels in the language button. `Pausa programada` wraps to two lines inside its button, which fits.
- `dir="rtl"` also mirrors the playback row (rewind, play, fast forward) and the `Back 30s` and `Fwd 30s` pair. Decide whether those should keep their left to right order; this is a design decision, not a translation one.
- The glossary check needed three improvements discovered here: masking of brand names and `--reset-pairing` style flags, accepting a list of renderings (Arabic broken plurals), and a plural warning only for named counts (`{n}`), not `%d` (a port number).
