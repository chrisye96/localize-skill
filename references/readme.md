# READMEs and other Markdown documents

A README is not a string table, but every check of the main workflow still applies once it is split into segments. `md-split` does that and `md-build` puts the document back together. This reference was written from translating six READMEs into Simplified and Traditional Chinese; the lessons behind each rule are in brackets.

## 1. Set up

- Work on a new branch in its own worktree, cut from the default branch: `git worktree add <dir> -b docs/readme-<lang> origin/<default>`. The user's checkout may be on another branch with unpushed work, or in use by another session. [Three of five repositories were mid-work on `dev`.]
- Read the whole README and any existing translation first. An existing translation by the author is the best terminology reference you have, but the English stays the source of truth: where they disagree, follow the English and list the difference in your report. [Both existing zh-CN READMEs had drifted from their English in places.]
- Look in the project for its own terminology: a terms file (`tools/lightroom-terms.json`), the app's translation tables, the names its UI shows. They outrank any general vocabulary list. [Lightroom's real zh-TW names came from such a file.]
- Check every menu path, button and setting the README quotes from other software against that software's own text, not memory. Look in this order: the program's string files if it is installed (Lightroom Classic keeps them in `Resources/<lang>/TranslatedStrings_Lr_<locale>.txt`); the operating system's language files if that language pack is installed (search `C:\Windows\System32\<lang>\*.mui` for the string as UTF-16LE); then the vendor's own help pages in that locale (`support.microsoft.com/zh-tw`, `support.apple.com/zh-tw`). Report the names you could not confirm. [Two Lightroom names written from memory were wrong: 增效模組額外功能 is 增效模組額外資訊, and 已安裝並在執行中 is 已安裝且正在執行.]

## 2. Split, and prove the round trip

```
python scripts/l10n.py md-split README.md --out work
python scripts/l10n.py md-build work/skeleton.json --source work/source.json --target work/source.json --lang en --langs en,zh-CN,zh-TW -o work/en.md
```

Diff `work/en.md` against the README before translating anything. Only two differences are expected: the language line, and soft wrapped lines of one paragraph joined into one line (they render the same). Anything else is a segmenting problem to fix first. [The round trip caught CRLF line endings in a Windows checkout.]

What becomes a segment, keyed by its English text:

- Headings, paragraphs, list items, blockquotes and table cells.
- `alt` text of images and of HTML `<img>` (badges stay).
- Comments in code blocks (`# Install dependencies`), and the description column of a directory listing (`main.py      entry point`). The code itself stays.

What stays verbatim: code, HTML, badges, link definitions, rules, a cell or paragraph that is only code or a file name, and a whole code block that draws a box (`┌──┐`, `+---+`), since double width CJK characters would break its alignment.

Segments are keyed by their English, like an English-keyed table, so when the README changes later, `check` lists the new and removed paragraphs and `rekey` follows the edited ones. Repeated texts share one entry.

## 3. Glossary

Same as the main workflow, step 4, plus:

- Add the product, brand and tool names that stay in English as keep-as-is terms; they also silence the "identical to source" warnings for headings like `API` or `MIT`.
- A term with inflections takes a stem: `"reject*": "排除"` matches reject, rejects, rejected. A plain term matches the whole word only, and a hyphenated compound (`Double-click`) is not a match for `click`.
- Leave out words with two senses in the document (*support* as features and as donations, *script* as writing system and program), or give the accepted renderings as a list.
- A term that names a UI label must accept the label's on-screen wording too (see `chinese.md` for products whose UI is not in the target language).

## 4. Translate

Write `work/<lang>.json`, or a TSV file if JSON escaping gets in the way: `emit work/source.json --format tsv -o work/<lang>.tsv` gives `English<TAB>English` lines to overwrite in the second column. `check` and `md-build` read either. [Windows paths and `\|` in JSON went wrong by hand.]

- Translate for the README's readers, natural and concise, keeping its tone. A README is prose: the step 5 rules about button widths do not apply, but the placeholder and markup rules do.
- Keep code spans, link targets and URLs byte for byte; `check` fails any change. Link text is translated.
- When a code span holds UI text (a menu path such as `File > Plug-in Manager`), keep the span and put the localized name before it: 「增效模組管理員」（`File > Plug-in Manager`）. [The author's zh-CN translated inside the code span, which breaks the check and the copy-paste.]
- An in-page link `[CLI mode](#cli-mode)` must point at the translated heading's GitHub anchor: lowercase, punctuation dropped, spaces to hyphens, CJK kept (`## CLI 模式` → `#cli-模式`). `md-build` fails a link that matches no heading.
- Bold must still render. A closing `**` right after punctuation needs a space or punctuation after it, so `**完成。**然后` shows literal asterisks on GitHub: write `**完成**。然后`. `check` fails it.
- A list that ends in ", ..." in a sentence takes the language's own "etc." (等); only a short label must keep its ellipsis, and `check` only warns on long text.

## 5. Check, back-translate, build

Run `check` with the glossary until there are no errors, then the blind back-translation of step 6 with a different model. On a long README the drift scores are noisy; ask the back-translator to list the segments it found unclear or unnatural, with a reason, and read those. [That list found every real problem; the scores found synonyms.]

```
python scripts/l10n.py md-build work/skeleton.json --source work/source.json --target work/<lang>.json --lang <lang> --langs en,zh-CN,zh-TW -o README.<lang>.md
```

`md-build` writes the README's line endings, and the language line at the top: every language under its own name, the current one in bold (`[English](README.md) | **简体中文** | [繁體中文](README.zh-TW.md)`). Put the same line into `README.md` and into every existing translation by replacing their old line, not by rebuilding them, so their text and line wrapping stay as the author wrote them.

## 6. Record and hand over

A README has no status file of its own: add one line at the end of each new translation saying it is a machine translation not yet reviewed line by line by a native speaker, and that the English version prevails. Then commit on the branch, one commit per repository, and ask before pushing.
