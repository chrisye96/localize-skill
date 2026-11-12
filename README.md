# localize

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

An [Agent Skills](https://agentskills.io) skill (works in Claude Code, Codex, Gemini CLI, OpenCode and other agents that support the format) for localizing websites, web apps, mobile apps and desktop software into other languages, with checks that keep the translation accurate.

Accurate UI translation fails in predictable ways: a one word label translated without its context, a product term translated three ways, a broken `{placeholder}`, a plural that is wrong for Russian or Arabic, a German label that no longer fits its button. The skill puts a source of context or a check in front of each:

| Risk | What the skill does |
|---|---|
| Ambiguous short labels | `context` finds where every string is used in the code |
| Inconsistent terms | a glossary that `check` enforces (with masking for brands and flags, and lists of accepted forms) |
| Broken placeholders and markup | `check` compares `{x}`, `{{x}}`, `%s`, `%1$s`, `%@`, ICU arguments, HTML tags and line breaks |
| Meaning drift | `blind` and `backtrans`: a blind back-translation, ranked by drift |
| Plurals | `check` knows which plural forms 75 languages need, and fails an ICU plural, i18next `_one`/`_few` group, gettext `msgstr[i]` set or Android `<plurals>` that lacks one |
| Length and script problems | warnings for overlong strings and text not in the target script; a dropped or added trailing `…` is an error |
| Edited English | `rekey` carries translations across case, punctuation and spacing edits, and lists every other edit with the old translation |
| Over-eager reviews | the workflow separates corrections from preferences, and `diff` lists every change for the reviewer |
| Regional variants | `regional` keeps only the rows es-MX changes from es, and refuses script variants |
| RTL and layout | a checklist in the workflow; the UI has to be looked at |
| Reliability claims | a review status record in the project, with fixed levels from `machine` to `native-line-by-line`; legal, payment and medical text gets a native reviewer |
| READMEs and docs | `md-split` and `md-build` turn Markdown into segments (code comments and image alt text included) and back, and fail a changed code span, link or URL, a broken in-page anchor, or bold that would not render |
| Simplified and Traditional Chinese | a warning for characters of the wrong script, and a guide to the vocabulary and typography zh-TW uses |

## Formats

JSON (flat or nested) and `.arb`, `.po`/`.pot`, `.properties`, Android `strings.xml`, iOS `.strings`, `.tsv`, JS or Python tables keyed by the English text, and Markdown documents such as a README. Plural entries are read as one id per form. Anything else can be converted to flat JSON first; the checks work on `{id: text}`.

## Install

Clone into the skills folder your agent reads: `~/.agents/skills/` for Codex, Gemini CLI, OpenCode and most others, `~/.claude/skills/` for Claude Code.

```bash
git clone https://github.com/chrisye96/localize-skill ~/.agents/skills/localize
```

Then ask your agent to add a language to a project ("translate this app into Spanish"). The script needs only Python 3.8+ and the standard library:

```bash
python scripts/l10n.py --help
```

## Layout

```
SKILL.md                              the workflow the agent follows
scripts/l10n.py                       export, context, check, emit, md-split, md-build, rekey, regional, diff, blind, backtrans
references/english-keyed-tables.md    projects that use the English text as the key
references/readme.md                  translating a README or other Markdown document
references/chinese.md                 Simplified and Traditional Chinese: vocabulary, typography, quoting a UI
references/review-status.md           the review status record: levels and template
references/phone-remote.md            worked example this skill was built and tested on
tests/test_l10n.py                    python -m unittest discover -s tests
```

## Tested on

Adding Spanish and Arabic to [phone-remote](https://github.com/chrisye96/phone-remote) in a scratch copy: all checks passed, the project's own 79 tests passed, and both languages were inspected in a browser at phone width. See `references/phone-remote.md` for what the run found.
