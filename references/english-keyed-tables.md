# English-keyed translation tables

Some projects skip string ids and use the English text as the key, in one table per language:

```js
const TABLES = {
  zh: {
    "Connecting…": "正在连接…",
    "Volume {n}": "音量 {n}",
  },
};
const t = (text) => table[text] || text;   // a missing entry simply stays English
```

```python
_TABLES = {
    "zh": {
        "Quit": "退出",
        "A long sentence that is "
        "split over two lines.": "...",
    },
}
```

The code stays readable and a missing translation degrades to English instead of showing an id. The cost is that rewording the English text silently stops its translations from applying, so projects like this usually have a test that every key is still used.

## How this skill reads them

`l10n.py export <file> --lang <block>` finds the `<block>: {` table in a `.js`, `.ts` or `.py` file and reads its string pairs. Comments, escaped quotes, strings split over lines and adjacent literals are handled. Nested braces outside strings are not (use a JSON file for those).

- Use `export --lang <existing> --identity` to get the source: ids and source text are the same string.
- Use `export --lang <existing>` without `--identity` to get a reference translation. Its values show what each string means, which is the best disambiguation available when you cannot see the UI.
- A project often has several tables, for example one for the web page and one for the desktop or server side. Treat each as its own run: own source file, own context, and possibly its own glossary.

## What the back-translator must not see

The ids are the English text, so a back-translator that is given the table sees the answer. Always go through `l10n.py blind` (see SKILL.md, step 6).

## Adding the language

1. `l10n.py emit work/<lang>.json --format js|py --lang <lang> --indent <n>` prints a block; paste it after the last language block, inside the table.
2. Register the language wherever the project lists them (a `LANGUAGES` map, a switcher, a settings validator, a tray menu).
3. Anything that tests for a specific language (a test that loads only `zh`, a script that checks `localStorage.lang === "zh"` to prevent a flash of English) needs generalizing so it covers every language.
4. If the project switches languages with a two state toggle, a third language needs a cycle or a picker.
5. For RTL languages, set `dir` where the language is applied.
