# localize

A Claude skill for localizing websites, web apps, mobile apps and desktop software into other languages, with checks that keep the translation accurate.

Accurate UI translation fails in predictable ways: a one word label translated without its context, a product term translated three ways, a broken `{placeholder}`, a plural that is wrong for Russian or Arabic, a German label that no longer fits its button. The skill puts a source of context or a check in front of each:

| Risk | What the skill does |
|---|---|
| Ambiguous short labels | `context` finds where every string is used in the code |
| Inconsistent terms | a glossary that `check` enforces (with masking for brands and flags, and lists of accepted forms) |
| Broken placeholders and markup | `check` compares `{x}`, `{{x}}`, `%s`, `%1$s`, `%@`, ICU arguments, HTML tags and line breaks |
| Meaning drift | `blind` and `backtrans`: a blind back-translation, ranked by drift |
| Plural, length and script problems | warnings for languages with several plural forms, overlong strings, text not in the target script |
| RTL and layout | a checklist in the workflow; the UI has to be looked at |
| Reliability claims | the report states what was machine translated and recommends a native reviewer for legal, payment and medical text |

## Formats

JSON (flat or nested) and `.arb`, `.po`, `.properties`, Android `strings.xml`, iOS `.strings`, and JS or Python tables keyed by the English text. Anything else can be converted to flat JSON first; the checks work on `{id: text}`.

## Install

Clone into your skills folder:

```bash
git clone https://github.com/chrisye96/localize-skill ~/.claude/skills/localize
```

Then ask Claude to add a language to a project ("translate this app into Spanish"). The script needs only Python 3.8+ and the standard library:

```bash
python scripts/l10n.py --help
```

## Layout

```
SKILL.md                              the workflow Claude follows
scripts/l10n.py                       export, context, check, emit, blind, backtrans
references/english-keyed-tables.md    projects that use the English text as the key
references/phone-remote.md            worked example this skill was built and tested on
tests/test_l10n.py                    python -m unittest discover -s tests
```

## Tested on

Adding Spanish and Arabic to [phone-remote](https://github.com/chrisye96/phone-remote) in a scratch copy: all checks passed, the project's own 79 tests passed, and both languages were inspected in a browser at phone width. See `references/phone-remote.md` for what the run found.
