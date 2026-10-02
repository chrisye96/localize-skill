---
name: localize
description: Translate and localize a website, web app, mobile app or desktop software into other languages, with checks that keep the translation accurate. Use this whenever the user wants to add a language, translate UI strings or i18n resource files (JSON, .po, .properties, .arb, Android strings.xml, iOS .strings, JS or Python string tables), localize an app for new markets, review or fix existing translations, or keep translations in sync after new strings were added, even if they only say "make it work in Spanish" or "translate the app". Not for translating a single document or message that is not part of a product UI.
---

# Localize

Accurate UI translation fails in predictable ways: a one word label translated without knowing where it appears, a product term translated three different ways, a placeholder broken so the app shows `{name}` or crashes, a plural that is wrong for Russian, a German label that no longer fits its button. This skill puts a check or a source of context in front of each of those, so you are not relying on the translation simply being good.

`scripts/l10n.py` (stdlib only, Python 3.8+) does the mechanical parts. Run it from the skill folder, or by absolute path.

## Workflow

### 1. Scope the job

Find where the strings live and which languages exist. Ask the user only what you cannot find out:

- **Target languages and locale variants.** "Spanish" is es-ES or es-419, "Portuguese" is pt-BR or pt-PT, "Chinese" is Simplified or Traditional. If unstated, pick the larger market and say which you picked.
- **Register.** Formal or informal address (tu/usted, du/Sie, 你/您). Pick one per language, note it in the glossary notes, and keep it consistent.
- **Critical copy.** Legal, payment and medical text, and the user's main markets, deserve a native reviewer (see step 8).

Detect the format from the files:

| Format | Notes |
|---|---|
| JSON, `.arb` | flat, or nested (use `--nested`; ids become dotted paths) |
| `.po` / `.pot` | plural entries are skipped with a note; translate those with a gettext tool |
| `.properties`, Android `strings.xml`, iOS `.strings` | one file per language |
| JS or Python tables such as `zh: { "English text": "..." }` | needs `--lang`; see `references/english-keyed-tables.md` |
| YAML, XLIFF, `.xcstrings`, others | convert to flat JSON yourself, or translate in place and still run `check` on the flat JSON |

### 2. Build the source file

```
python scripts/l10n.py export <source-file> [--lang xx] [--nested] [--identity] -o work/source.json
```

`work/source.json` is flat `{id: source text}`. For English-keyed tables use `--identity` on an existing complete language (the ids are the English text). To add a language to a project that already has others, export one of them as `work/ref.json` too: its values show what each string means and are the best disambiguation you have.

To translate only what is new in an existing language, run `check` (step 5) and take the `missing translation` lines.

### 3. Gather context

```
python scripts/l10n.py context <project-root> --source work/source.json -o work/context.json
```

This finds where each id is used. A short label is ambiguous without it: "Post" (verb or noun), "Order" (purchase or sort), "Back" (navigate or the body part), "Play" (media or game). Read the context for every string of five words or fewer, and for any string that looks like a button, menu item, tooltip or status. If an id has no hits, look at the neighbouring ids and at the UI itself before guessing.

### 4. Write the glossary

Create `work/glossary.json` as `{"source term": "required rendering"}`. Include:

- Product and brand names, kept as they are (`"Bilibili": "Bilibili"`).
- Terms that recur and must be translated one way (`"workspace": "espacio de trabajo"`).
- Terms the product uses as names for features, which are easy to translate inconsistently.

Propose it to the user for the first language and reuse it for every later one; extend it when you meet a new recurring term. `check` fails any string where a glossary term is in the source but not in the target, so the glossary is enforced and not just advice. Details that save time:

- The rendering can be a list of accepted forms, for languages with irregular plurals or inflection: `"window": ["نافذة", "نوافذ"]`. Otherwise a correct plural fails the check.
- A term that maps to itself is a "keep as is" term (a brand). Those are masked out of the source before the other terms are matched, so `Phone Remote` does not trigger a `phone` rule. Command line flags, `code spans` and placeholders are masked too.
- Matching is by whole word and by substring of the rendering, so give the stem (`vincul`) when a term appears in several grammatical forms.
- If one source word means different things in different places (the OS "Windows" and a "window" in the UI), use a separate glossary file for each set of strings.

### 5. Translate, then check

Translate in batches of 30 to 50 strings, with their context in view. Rules that prevent most defects:

- Keep every placeholder byte for byte: `{name}`, `{0}`, `{{name}}`, `%s`, `%d`, `%1$s`, `%@`, and ICU `{count, plural, ...}` arguments. Reorder them freely where the grammar needs it, but never rename, drop or add.
- Keep markup tags, line breaks, leading symbols (`+ Add`) and trailing ellipses.
- Do not make a string longer than it needs to be. German and Finnish run 30% or more longer than English; short labels sit in fixed-width buttons. Abbreviate rather than overflow.
- For languages with several plural forms (Russian, Polish, Arabic, Czech and others), text next to a number such as `{n} min left` cannot agree for every n. Rephrase to be number neutral (`Minutes left: {n}`), or use real plural forms if the project's i18n system supports them.
- Match the tone of the source. UI text is short, direct and consistent. Do not add politeness or explanations the source does not have.

Save as `work/<lang>.json`, then:

```
python scripts/l10n.py check --source work/source.json --target work/<lang>.json --lang <lang> --glossary work/glossary.json
```

Fix every `ERROR` (missing, empty, placeholder or markup changed, glossary violation). Read every `WARN` and either fix it or consciously accept it: a loanword identical to the source is fine, and so is an example address that should stay Latin inside right to left text; a string that is longer than its button is not. A warning asks you to look, it is not a verdict (`Volume {n}` triggers the plural warning because of `{n}`, but a volume level is not a counted noun). When a glossary error comes from a deliberate choice, change the glossary or the wording rather than ignoring the error, so the next run stays clean. Repeat until there are no errors.

### 6. Back-translate

The back-translation must not see the original English, otherwise it just echoes it. When the ids are English text (English-keyed tables) the ids themselves give the answer away, so renumber first:

```
python scripts/l10n.py blind work/<lang>.json -o work/<lang>.blind.json
```

Translate the values of `<lang>.blind.json` back to English, literally and even awkwardly (a smooth paraphrase hides errors), and keep the numeric ids: `work/<lang>.back.json`. Then:

```
python scripts/l10n.py backtrans --source work/source.json --back work/<lang>.back.json --target work/<lang>.json
```

If you can spawn a subagent, give it only the blinded file and the glossary: that is the only way to get a pass that has not seen the source. If you cannot, do it as a separate step; it still catches meaning errors, but not tone or fluency, and you should say it was not independent.

The most drifted strings are listed first. The score compares words, so it is noisy: a third of a typical list is just synonyms. Read the flagged ones and ask whether the back-translation lost or changed the meaning (fix the translation) or merely reworded it (leave it). In practice this pass finds ambiguous words, for example a media "rewind" that came back as "go back", or a "sleep timer" that came back as "stop timer".

### 7. Integrate and verify in the product

```
python scripts/l10n.py emit work/<lang>.json --format <json|js|py|properties|xml|strings|po> --lang <lang> [--source work/source.json] [-o out]
```

`js` and `py` print a table block to paste into the existing table (`--indent` matches the block to the surrounding code); the other formats write a whole new language file. Then wire the language in: register it where the project lists languages, add the language switcher entry, and handle the things a string table cannot:

- **RTL languages** (Arabic, Hebrew, Persian, Urdu): set `dir="rtl"` on the document and prefer CSS logical properties (`margin-inline-start`) over left and right. Look at the actual screens; layout cannot be checked from strings. Setting `dir` mirrors everything, including controls that should keep their order: playback controls (rewind, play, fast forward) and seek buttons, number pads, and anything tied to a physical direction. Platform guidelines mostly keep playback controls left to right, so decide per control and tell the user what you found.
- **Layout with real strings**: render the longest languages at the narrowest supported width. Wrapping to two lines in a button is usually fine; clipped text or a pushed-out layout is not. Compare with the English layout first, because overflow that already exists in English is not the translation's fault.
- **Fonts**: confirm the font stack has glyphs for the script (CJK, Arabic, Thai, Devanagari).
- **Formatting**: dates, numbers and currency should come from `Intl` or the platform formatter, not from translated strings.
- Run the project's own tests, and open the UI at a narrow width to look for overflow.

If the project has tests that tie translation tables to the code (some do), run them: they catch ids that stopped matching.

### 8. Report honestly

Say what was machine translated and not reviewed by a native speaker, list the warnings you accepted, and name the strings you were unsure about. For legal, payment and medical text and for the user's top markets, recommend a native reviewer; `work/<lang>.json` plus the glossary is the right handover. Do not claim a translation is "verified"; it passed mechanical checks and a back-translation, which is strong evidence and not proof.

## Keeping it up to date

When new strings are added, export the source again and run `check` against each existing language: new ids show up as `missing translation`, deleted ones as `id not in source`. Translate only the missing ones with the same glossary.

## References

- `references/english-keyed-tables.md`: projects whose translation tables use the English text as the key (JS and Python), with the integration points to touch when adding a language. Read it when the `export` of a `.js` or `.py` file is involved.
- `references/phone-remote.md`: the worked example this skill was built and tested on.
