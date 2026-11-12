# Review status

What a chat message says about a translation is gone by the next release. Write it into the project instead, so the next person (or the next run of this skill) knows which strings a native speaker has seen and which nobody has.

## Where

If the project already has a place for this (a credits file, a `TRANSLATIONS.md`, a section in the i18n README), add to it. Otherwise propose a `TRANSLATIONS.md` next to the translation files, and ask before adding a new file to the user's repository.

## Levels

Use these words and no others, so two rows are comparable. A row can name more than one native level when more than one happened.

| Level | Means |
|---|---|
| `machine` | machine translated; passed `check` |
| `back-translated` | machine translated; passed `check` and a back-translation, and the flagged strings were read and fixed |
| `native-skimmed` | a native speaker looked through it; not every string was read |
| `native-terminology` | a native speaker reviewed the glossary and the core terms |
| `native-in-app` | a native speaker used it in the running product |
| `native-line-by-line` | a native speaker read every string in the row |

A review by you, or by another model, is not a native review: it stays `machine` or `back-translated`, however careful it was. Never write a level the user has not confirmed happened.

## Rows

One row per language and batch of strings. When new strings are added later, add a row for that batch; do not fold them into an older row, because a `native-line-by-line` row would then claim strings no one has read.

```markdown
# Translation status

| Language | Strings | Translated by | Review | Date | Notes |
|---|---|---|---|---|---|
| es (es-419, tú) | all 214 at 3f2a9c1 | Claude Code (Opus 5.5) | back-translated | 2026-11-11 | 3 loanwords accepted as warnings |
| es (es-419, tú) | 18 added at 9b07e44 | Claude Code (Opus 5.5) | machine | 2026-12-02 | |
| ar | all 214 at 3f2a9c1 | Claude Code (Opus 5.5); reviewed by Layla (native) | back-translated, native-terminology | 2026-11-12 | RTL layout checked at 375px |
```

- **Strings**: which strings, and the commit or version they came from, so a later reader can tell which strings came after.
- **Translated by**: the tool and model, plus every person involved and what they did. Write people's names only as the user gives them.
- **Notes**: the register chosen, warnings accepted, strings you were unsure about, what was checked by eye (RTL, layout width).
