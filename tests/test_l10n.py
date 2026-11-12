import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import l10n  # noqa: E402

JS = '''
export const TABLES = {
  zh: {
    // header
    "Remote": "遥控器",
    "Volume {n}": "音量 {n}",
    "It's here": "在这里",
    "Long text":
      "第一行",
  },
  de: { "Remote": "Fernbedienung" },
};
'''
PY = '''
_TABLES = {
    "zh": {
        # tray
        "Quit": "退出",
        "A long sentence that is "
        "split over two lines.": "分成两行的长句子。",
        "Port %d is busy": "端口 %d 被占用",
    },
}
'''


class ReadTest(unittest.TestCase):
    def test_js_block_handles_comments_quotes_and_continuations(self):
        table = l10n.read_block(JS, "zh")
        self.assertEqual(table["Remote"], "遥控器")
        self.assertEqual(table["It's here"], "在这里")
        self.assertEqual(table["Long text"], "第一行")
        self.assertEqual(len(table), 4)
        self.assertEqual(l10n.read_block(JS, "de"), {"Remote": "Fernbedienung"})

    def test_py_block_joins_adjacent_string_literals(self):
        table = l10n.read_block(PY, "zh")
        self.assertEqual(table["A long sentence that is split over two lines."], "分成两行的长句子。")
        self.assertEqual(table["Port %d is busy"], "端口 %d 被占用")

    def test_other_formats(self):
        self.assertEqual(l10n.read_properties("# c\na.b=Hello \\u00e9\nc: x\\\n  y\n"), {"a.b": "Hello é", "c": "xy"})
        po = 'msgid ""\nmsgstr ""\n\nmsgid "Hi %s"\nmsgstr "Hola %s"\n\nmsgid "A"\nmsgid_plural "As"\nmsgstr[0] "a"\nmsgstr[1] "as"\n'
        self.assertEqual(l10n.read_po(po), {"Hi %s": "Hola %s", "A#0": "a", "A#1": "as"})
        # a template gives the English, so it can be the source file as it is
        pot = 'msgid "Hi %s"\nmsgstr ""\n\nmsgid "{n} file"\nmsgid_plural "{n} files"\nmsgstr[0] ""\nmsgstr[1] ""\n'
        self.assertEqual(l10n.read_po(pot, template=True), {"Hi %s": "Hi %s", "{n} file#0": "{n} file", "{n} file#1": "{n} files"})
        xml = '<resources><plurals name="files"><item quantity="one">%d file</item><item quantity="other">%d files</item></plurals></resources>'
        self.assertEqual(l10n.read_android(xml), {"files#one": "%d file", "files#other": "%d files"})
        self.assertEqual(l10n.read_android('<resources><string name="a">It\\\'s <b>ok</b></string></resources>'), {"a": "It's <b>ok</b>"})
        self.assertEqual(l10n.read_strings('/* c */\n"a" = "b \\"q\\"";'), {"a": 'b "q"'})


class RoundTripTest(unittest.TestCase):
    flat = {"Remote": "Fernbedienung", "It's {n} \"x\"": "Es ist {n} \"x\"", "Two\nlines": "Zwei\nZeilen"}

    def test_every_writer_reads_back_the_same(self):
        for fmt, ext in [("json", "json"), ("properties", "properties"), ("strings", "strings"), ("po", "po"), ("xml", "xml")]:
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                # properties and xml keys are identifiers, so they get id style keys and the same hard values
                flat = {"a_b": "Es ist 'x' & y {n}", "c": "Zwei\nZeilen"} if fmt in ("xml", "properties") else self.flat
                path = Path(d) / ("t." + ext)
                path.write_text(l10n.emit(flat, fmt, "de", source={k: k for k in flat}), encoding="utf-8")
                loaded = l10n.load(path)
                self.assertEqual(loaded, flat)

    def test_plural_groups_survive_po_and_xml(self):
        source = {"Hi": "Hi", "{n} file#0": "{n} file", "{n} file#1": "{n} files"}
        ru = {"Hi": "Привет", "{n} file#0": "{n} файл", "{n} file#1": "{n} файла", "{n} file#2": "{n} файлов"}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ru.po"
            text = l10n.emit(ru, "po", "ru", source=source)
            self.assertIn("nplurals=3;", text)
            self.assertIn('msgid_plural "{n} files"', text)
            path.write_text(text, encoding="utf-8")
            self.assertEqual(l10n.load(path), ru)
            ar = {"a": "x", "files#zero": "لا ملفات", "files#one": "ملف", "files#other": "%d ملف"}
            path = Path(d) / "strings.xml"
            path.write_text(l10n.emit(ar, "xml", "ar"), encoding="utf-8")
            self.assertEqual(l10n.load(path), ar)

    def test_js_and_py_blocks_read_back(self):
        for fmt in ("js", "py"):
            with self.subTest(fmt=fmt):
                self.assertEqual(l10n.read_block("X = {\n%s}" % l10n.emit(self.flat, fmt, "de"), "de"), self.flat)

    def test_block_indent_matches_the_surrounding_table(self):
        self.assertEqual(l10n.emit({"a": "b"}, "py", "de", indent=4), '    "de": {\n        "a": "b",\n    },\n')
        self.assertEqual(l10n.emit({"a": "b"}, "js", "de"), '  de: {\n    "a": "b",\n  },\n')

    def test_nested_json(self):
        flat = {"home.title": "Hallo", "home.sub": "Welt", "x": "y"}
        self.assertEqual(dict(l10n._flatten(l10n._unflatten(flat))), flat)


class CheckTest(unittest.TestCase):
    def run_check(self, source, target, lang="es", glossary=None):
        return l10n.check(source, target, lang, glossary)

    def test_clean_translation_has_no_errors(self):
        errors, _ = self.run_check({"Volume {n}": "Volume {n}"}, {"Volume {n}": "Volumen {n}"})
        self.assertEqual(errors, [])

    def test_missing_empty_and_placeholder_problems_are_errors(self):
        source = {"a": "Hi {name}", "b": "Total %d items", "c": "Press %@", "d": "x", "e": "<b>Bold</b> text", "f": "Hi {{who}}"}
        target = {"a": "Hola {nombre}", "b": "Total %s", "c": "Presiona %@", "d": " ", "e": "Negrita", "f": "Hola {{who}}"}
        errors = dict(self.run_check(source, target)[0])
        self.assertIn("placeholders differ", errors["a"])
        self.assertIn("placeholders differ", errors["b"])
        self.assertNotIn("c", errors)
        self.assertEqual(errors["d"], "empty translation")
        self.assertIn("markup tags", errors["e"])
        self.assertNotIn("f", errors)
        self.assertEqual(dict(self.run_check({"z": "Z"}, {})[0])["z"], "missing translation")

    def test_icu_needs_same_argument_and_other_branch(self):
        src = "{count, plural, one {# file} other {# files}}"
        ok = "{count, plural, one {# archivo} other {# archivos}}"
        bad_arg = "{n, plural, one {# archivo} other {# archivos}}"
        no_other = "{count, plural, one {# archivo}}"
        self.assertEqual(self.run_check({"k": src}, {"k": ok})[0], [])
        self.assertEqual(len(self.run_check({"k": src}, {"k": bad_arg})[0]), 1)
        self.assertEqual(len(self.run_check({"k": src}, {"k": no_other})[0]), 1)

    def test_glossary_is_enforced_as_a_whole_word(self):
        glossary = {"workspace": "espacio de trabajo"}
        self.assertEqual(self.run_check({"k": "Open workspace"}, {"k": "Abrir espacio de trabajo"}, glossary=glossary)[0], [])
        self.assertEqual(len(self.run_check({"k": "Open workspace"}, {"k": "Abrir área"}, glossary=glossary)[0]), 1)
        self.assertEqual(self.run_check({"k": "Workspaces"}, {"k": "Áreas"}, glossary=glossary)[0], [])

    def test_brand_containing_a_glossary_word_does_not_trigger_that_word(self):
        glossary = {"Phone Remote": "Phone Remote", "phone": "teléfono"}
        self.assertEqual(self.run_check({"k": "Phone Remote"}, {"k": "Phone Remote"}, glossary=glossary)[0], [])
        self.assertEqual(len(self.run_check({"k": "Phone Remote"}, {"k": "Control remoto"}, glossary=glossary)[0]), 1)
        self.assertEqual(len(self.run_check({"k": "Use your phone"}, {"k": "Usa tu móvil"}, glossary=glossary)[0]), 1)

    def test_glossary_accepts_a_list_of_renderings_for_plurals_and_inflections(self):
        glossary = {"window": ["نافذة", "نوافذ"]}
        self.assertEqual(self.run_check({"k": "No open windows"}, {"k": "لا توجد نوافذ مفتوحة"}, "ar", glossary)[0], [])
        self.assertEqual(self.run_check({"k": "Current window"}, {"k": "النافذة الحالية"}, "ar", glossary)[0], [])
        self.assertEqual(len(self.run_check({"k": "Current window"}, {"k": "الشاشة الحالية"}, "ar", glossary)[0]), 1)

    def test_plural_warning_only_for_named_count_placeholders(self):
        self.assertEqual(l10n.check({"k": "Port %d is busy"}, {"k": "Порт %d занят"}, "ru")[1], [])
        self.assertEqual(len(l10n.check({"k": "{count} files"}, {"k": "{count} файлов"}, "ru")[1]), 1)

    def test_flags_and_placeholders_are_not_glossary_matches(self):
        glossary = {"pairing": "vincul", "window": "ventana"}
        self.assertEqual(self.run_check({"k": "Restart with --reset-pairing {window}"}, {"k": "Reinicia con --reset-pairing {window}"}, glossary=glossary)[0], [])

    def test_warnings(self):
        _, warns = self.run_check({"a": "Settings", "b": "OK", "c": "Hi"}, {"a": "Settings", "b": "OK", "c": "Hola amigo mío querido"})
        text = " ".join(m for _, m in warns)
        self.assertIn("identical", text)
        self.assertIn("longer than source", text)
        _, warns = l10n.check({"a": "Back"}, {"a": "Back"}, "ar")
        self.assertTrue(any("identical" in m for _, m in warns))
        _, warns = l10n.check({"a": "Back"}, {"a": "Return"}, "ru")
        self.assertTrue(any("no ru characters" in m for _, m in warns))
        _, warns = l10n.check({"a": "{n} min left"}, {"a": "осталось {n} мин"}, "ru")
        self.assertTrue(any("plural" in m for _, m in warns))
        _, warns = l10n.check({}, {"stale": "x"}, "es")
        self.assertTrue(any("not in source" in m for _, m in warns))

    def test_icu_plural_needs_every_form_the_language_uses(self):
        src = {"k": "{count, plural, one {# file} other {# files}}"}
        two = {"k": "{count, plural, one {# файл} other {# файла}}"}
        four = {"k": "{count, plural, one {# файл} few {# файла} many {# файлов} other {# файла}}"}
        errors = dict(l10n.check(src, two, "ru")[0])
        self.assertIn("few, many", errors["k"])
        self.assertEqual(l10n.check(src, four, "ru")[0], [])
        self.assertEqual(l10n.check(src, {"k": "{count, plural, other {# 个文件}}"}, "zh-Hans")[0], [])
        # French "many" (a million) is allowed but not required; nested plurals are checked too
        self.assertEqual(l10n.check(src, {"k": "{count, plural, one {# fichier} other {# fichiers}}"}, "fr")[0], [])
        nested = {"k": "{g, select, male {{count, plural, one {# a} other {# b}}} other {{count, plural, one {# a} few {# c} many {# d} other {# b}}}}"}
        self.assertEqual(len(l10n.check({"k": nested["k"]}, nested, "ru")[0]), 1)

    def test_suffix_plural_groups_by_category(self):
        source = {"file_one": "{{count}} file", "file_other": "{{count}} files", "step_one": "Step one"}
        ru = {"file_one": "{{count}} файл", "file_few": "{{count}} файла", "file_many": "{{count}} файлов",
              "file_other": "{{count}} файла", "step_one": "Шаг первый"}
        self.assertEqual(l10n.check(source, ru, "ru"), ([], []))
        errors = dict(l10n.check(source, {k: v for k, v in ru.items() if k != "file_many"}, "ru")[0])
        self.assertIn("many", errors["file"])
        # Japanese has one form only: no missing `file_one`
        self.assertEqual(l10n.check(source, {"file_other": "{{count}} 件", "step_one": "ステップ1"}, "ja")[0], [])
        # `step_one` has no `step_other`, so it is an ordinary string
        self.assertIn("step_one", dict(l10n.check(source, {"file_other": "x {{count}}"}, "ja")[0]))

    def test_plural_forms_placeholders(self):
        source = {"f#one": "One file", "f#other": "{n} files"}
        errors, warns = l10n.check(source, {"f#zero": "لا ملفات", "f#one": "ملف واحد", "f#two": "ملفان", "f#few": "{n} ملفات",
                                            "f#many": "{n} ملفًا", "f#other": "{n} ملف"}, "ar")
        self.assertEqual(errors, [])
        self.assertTrue(all("drops" in m for _, m in warns))  # zero/one/two may drop {n}: a warning, not an error
        errors, _ = l10n.check(source, {"f#one": "{n} file {x}", "f#other": "files"}, "en")
        self.assertEqual(len(errors), 2)  # one added {x}, other lost {n}

    def test_indexed_plural_forms_need_the_language_count(self):
        source = {"{n} file#0": "{n} file", "{n} file#1": "{n} files"}
        ok = {"{n} file#0": "{n} файл", "{n} file#1": "{n} файла", "{n} file#2": "{n} файлов"}
        self.assertEqual(l10n.check(source, ok, "ru"), ([], []))
        errors = dict(l10n.check(source, {"{n} file#0": "{n} файл", "{n} file#1": "{n} файлов"}, "ru")[0])
        self.assertIn("3 plural forms", errors["{n} file"])
        self.assertEqual(l10n.check(source, {"{n} file#0": "{n} 个文件"}, "zh")[0], [])
        self.assertEqual(dict(l10n.check(source, {}, "ru")[0])["{n} file"], "missing translation")

    def test_plural_expressions_index_the_categories(self):
        def index(expr, n):
            parts = re.split(r"\s*\?\s*|\s*:\s*", expr.replace("&&", " and ").replace("||", " or "))
            for cond, value in zip(parts[:-1:2], parts[1::2]):
                if eval(cond, {"n": n}):
                    return int(value)
            return int(eval(parts[-1], {"n": n}))
        for lang, (cats, expr) in l10n.PLURALS.items():
            with self.subTest(lang=lang):
                self.assertEqual({index(expr, n) for n in range(1001)}, set(range(len(cats))))
        spot = {"ru": {1: 0, 2: 1, 5: 2, 11: 2, 12: 2, 21: 0, 22: 1, 111: 2}, "pl": {1: 0, 21: 2, 22: 1},
                "fr": {0: 0, 1: 0, 2: 1}, "lv": {0: 0, 1: 1, 11: 0, 21: 1, 2: 2}, "ar": {0: 0, 1: 1, 2: 2, 3: 3, 11: 4, 100: 5},
                "lt": {1: 0, 11: 2, 2: 1, 10: 2}, "cy": {3: 3, 6: 4, 4: 5}}
        for lang, cases in spot.items():
            for n, want in cases.items():
                self.assertEqual(index(l10n.PLURALS[lang][1], n), want, (lang, n))

    def test_trailing_ellipsis_must_match(self):
        errors = dict(self.run_check({"a": "Save as…", "b": "Loading", "c": "Open...", "d": "Export…"},
                                     {"a": "Guardar como", "b": "Cargando…", "c": "Abrir…", "d": "Exportar... "})[0])
        self.assertIn("ellipsis", errors["a"])
        self.assertIn("ellipsis", errors["b"])
        self.assertNotIn("c", errors)  # "..." and "…" are the same thing
        self.assertNotIn("d", errors)
        self.assertEqual(l10n.check({"a": "Save as…"}, {"a": "另存为……"}, "zh")[0], [])
        # word order may move an ellipsis that is part of an example (found in phone-remote)
        moved = {"a": "Can't save: the address should look like bilibili.com or https://…"}
        self.assertEqual(l10n.check(moved, {"a": "保存不了：网址要像 bilibili.com 或 https://… 这样"}, "zh")[0], [])

    def test_regional_keeps_only_what_differs_from_the_base(self):
        mx = {"a": "Computadora", "b": "Guardar", "f#0": "{n} archivo", "f#1": "{n} archivos", "new": "Nuevo"}
        es = {"a": "Ordenador", "b": "Guardar", "f#0": "{n} archivo", "f#1": "{n} ficheros"}
        kept, dropped = l10n.regional(mx, es, "es-MX")
        self.assertEqual(kept, {"a": "Computadora", "f#0": "{n} archivo", "f#1": "{n} archivos", "new": "Nuevo"})
        self.assertEqual(dropped, ["b"])  # a plural group is kept whole when one form differs
        self.assertEqual(l10n.regional({"a": "x"}, {"a": "x"}, "es-419")[1], ["a"])
        for tag in ("zh-Hant", "sr-Latn", "zh-TW", "pt"):
            with self.subTest(tag=tag), self.assertRaises(SystemExit):
                l10n.regional({"a": "x"}, {"a": "x"}, tag)

    def test_diff_lists_changed_added_and_removed(self):
        old, new = {"a": "x", "b": "y", "c": "z"}, {"a": "x", "b": "Y", "d": "w"}
        self.assertEqual(l10n.diff(old, new), {"changed": [("b", "y", "Y")], "added": [("d", "w")], "removed": [("c", "z")]})

    def test_rekey_english_keyed_carries_only_cosmetic_edits(self):
        source = {k: k for k in ["Log in", "Receive files", "Connecting…", "Save…", "Brand new"]}
        target = {"Log In": "登录", "Recieve files": "接收文件", "Connecting...": "连接中…", "Save": "保存", "Old thing": "旧"}
        new, carried, review = l10n.rekey(source, target)
        self.assertEqual(sorted(carried), [("Connecting…", "Connecting..."), ("Log in", "Log In")])
        self.assertEqual(sorted((r[0], r[1], r[4]) for r in review),
                         [("Receive files", "Recieve files", "接收文件"), ("Save…", "Save", "保存")])  # "Save…" now opens a dialog
        self.assertEqual(new, {"Log in": "登录", "Connecting…": "连接中…", "Old thing": "旧"})

    def test_rekey_id_keyed_compares_the_old_english(self):
        old = {"a": "Delete File", "b": "Sign in", "c": "Help"}
        source = {"a": "Delete file", "b": "Sign out", "c": "Help"}
        target = {"a": "Eliminar archivo", "b": "Iniciar sesión", "c": "Ayuda"}
        new, carried, review = l10n.rekey(source, target, old_source=old)
        self.assertEqual(carried, [("a", "a")])
        self.assertEqual([(r[0], r[2], r[3], r[4]) for r in review], [("b", "Sign in", "Sign out", "Iniciar sesión")])
        self.assertEqual(new, {"a": "Eliminar archivo", "c": "Ayuda"})  # b now shows up as missing in check

    def test_blind_hides_ids_and_unblind_restores_them(self):
        target = {"Play or pause": "Reproducir o pausar", "Quit": "Salir"}
        blinded = l10n.blind(target)
        self.assertEqual(blinded, {"1": "Reproducir o pausar", "2": "Salir"})
        self.assertEqual(l10n.unblind({"1": "Play or pause", "2": "Exit"}, target), {"Play or pause": "Play or pause", "Quit": "Exit"})

    def test_drift_ranks_worst_first(self):
        rows = l10n.drift({"a": "Play or pause", "b": "Quit"}, {"a": "Quit", "b": "Quit"}, 0.6)
        self.assertEqual([r[1] for r in rows], ["a"])


README = """<p align="center"><img src="logo.svg" alt="Tool logo"></p>

# Tool

**English** | [中文](README.zh-CN.md)

[![CI](https://img.shields.io/badge/ci-passing-green)](https://example.com/ci)

> **Fast.** Works offline.

Run it once. See [CLI mode](#cli-mode) and `--help`.

![The main screen](docs/screen.png)

- **Sync**: copies files to https://example.com/drop
- Pick `config.json`

| Key | Does |
|---|---|
| `P` | Pick a photo |

## CLI mode

```bash
tool --sync   # copy everything
```

```
src/
  main.py      entry point
  io/          input.py  output.py
```

```
+--------+
| Box ok |   # stays
+--------+
```

[docs]: https://example.com/docs

---
"""


class MarkdownTest(unittest.TestCase):
    langs = ["en", "zh-CN", "zh-TW"]

    def test_split_finds_prose_comments_and_alt_text_and_rebuilds_the_original(self):
        source, skel = l10n.md_split(README)
        for text in ["Tool logo", "**Fast.** Works offline.", "Run it once. See [CLI mode](#cli-mode) and `--help`.",
                     "The main screen", "**Sync**: copies files to https://example.com/drop", "Pick a photo", "CLI mode",
                     "copy everything", "entry point", "Key", "Does"]:
            self.assertIn(text, source)
        for kept in ["CI", "input.py  output.py", "Box ok", "stays", "`P`"]:
            self.assertNotIn(kept, source)  # badges, file name rows, box drawings and code-only cells stay as they are
        text, problems = l10n.md_build(skel, source, source, "en", self.langs)
        self.assertEqual(problems, [])
        expected = README.replace("**English** | [中文](README.zh-CN.md)", "**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)")
        self.assertEqual(text, expected)

    def test_crlf_survives_and_a_missing_language_line_is_added_under_the_title(self):
        source, skel = l10n.md_split("# Tool\r\n\r\nHello.\r\n")
        text, _ = l10n.md_build(skel, source, {"Tool": "工具", "Hello.": "你好。"}, "zh-CN", self.langs)
        self.assertEqual(text, "# 工具\r\n\r\n[English](README.md) | **简体中文** | [繁體中文](README.zh-TW.md)\r\n\r\n你好。\r\n")

    def test_segments_are_keyed_by_their_english_so_an_inserted_paragraph_shifts_nothing(self):
        source, _ = l10n.md_split("# T\n\nOne.\n\nTwo.\n")
        target = {"T": "T", "One.": "一。", "Two.": "二。"}
        source2, skel2 = l10n.md_split("# T\n\nNew.\n\nOne.\n\nTwo.\n")
        self.assertEqual(l10n.check(source2, target, "zh-CN")[0], [("New.", "missing translation")])
        text, problems = l10n.md_build(skel2, source2, dict(target, **{"New.": "新。"}), "zh-CN", self.langs)
        self.assertIn("新。\n\n一。\n\n二。", text)

    def test_anchors_must_follow_the_translated_heading(self):
        source, skel = l10n.md_split("# T\n\nSee [CLI mode](#cli-mode).\n\n## CLI mode\n")
        stale = {"T": "T", "CLI mode": "CLI 模式", "See [CLI mode](#cli-mode).": "见 [CLI 模式](#cli-mode)。"}
        self.assertTrue(any("#cli-mode" in p for p in l10n.md_build(skel, source, stale, "zh-CN", self.langs)[1]))
        fixed = dict(stale, **{"See [CLI mode](#cli-mode).": "见 [CLI 模式](#cli-模式)。"})
        self.assertEqual(l10n.md_build(skel, source, fixed, "zh-CN", self.langs)[1], [])
        self.assertEqual(l10n.md_slug("Install & run `tool` (Windows)"), "install--run-tool-windows")

    def test_language_line_names_every_language_in_its_own_language(self):
        self.assertEqual(l10n.md_langline(self.langs, "zh-TW"), "[English](README.md) | [简体中文](README.zh-CN.md) | **繁體中文**")


class ReadmeCheckTest(unittest.TestCase):
    def test_code_links_and_urls_must_survive(self):
        src = {"a": "Run `tool --sync` or see [docs](https://x.dev/docs) and https://x.dev/faq"}
        self.assertEqual(l10n.check(src, {"a": "运行 `tool --sync`，或参阅[文档](https://x.dev/docs)和 https://x.dev/faq"}, "zh-CN")[0], [])
        errors = dict(l10n.check(src, {"a": "运行 `tool`，或参阅[文档](https://x.dev/zh/docs)和 https://x.dev/faq"}, "zh-CN")[0])
        self.assertIn("code, links or URLs changed", errors["a"])

    def test_bold_that_markdown_would_not_render_is_an_error(self):
        src = {"a": "**Done.** Next step"}
        self.assertIn("bold will not render", dict(l10n.check(src, {"a": "**完成。**下一步"}, "zh-CN")[0])["a"])
        self.assertEqual(l10n.check(src, {"a": "**完成**。下一步"}, "zh-CN")[0], [])
        self.assertEqual(l10n.check(src, {"a": "**完成。** 下一步"}, "zh-CN")[0], [])
        self.assertIn("bold will not render", dict(l10n.check({"a": "Press **[OK]** now"}, {"a": "按**「確定」**鍵"}, "zh-TW")[0])["a"])

    def test_wrong_chinese_script_is_a_warning(self):
        self.assertTrue(any("Simplified" in m for _, m in l10n.check({"a": "Open the file"}, {"a": "開啟这个檔案"}, "zh-TW")[1]))
        self.assertTrue(any("Traditional" in m for _, m in l10n.check({"a": "Open the file"}, {"a": "打開這个文件"}, "zh-CN")[1]))
        self.assertEqual(l10n.zh_script("zh-Hant-HK"), "hant")
        self.assertEqual(l10n.zh_script("zh-SG"), "hans")
        self.assertEqual(len(l10n.ZH_PAIRS) % 2, 0)

    def test_a_longer_glossary_term_shadows_the_shorter_one_inside_it(self):
        glossary = {"translation": "翻译", "back-translation": "回译"}
        self.assertEqual(l10n.check({"a": "a blind back-translation"}, {"a": "盲回译"}, "zh-CN", glossary)[0], [])
        self.assertEqual(len(l10n.check({"a": "a translation"}, {"a": "回译"}, "zh-CN", glossary)[0]), 1)

    def test_glossary_ignores_urls_and_file_names_and_takes_stems(self):
        glossary = {"remote": "遥控器", "icons": "图示", "reject*": "排除"}
        src = {"a": "Get the [release](https://github.com/x/phone-remote/releases) with icons.svg"}
        self.assertEqual(l10n.check(src, {"a": "下载[发布版](https://github.com/x/phone-remote/releases)和 icons.svg"}, "zh-CN", glossary)[0], [])
        self.assertEqual(len(l10n.check({"a": "Show rejected photos"}, {"a": "显示被拒的照片"}, "zh-CN", glossary)[0]), 1)
        self.assertEqual(l10n.check({"a": "Show rejected photos"}, {"a": "显示排除的照片"}, "zh-CN", glossary)[0], [])

    def test_readme_sentences_are_not_ui_labels(self):
        # a long sentence may end its list with the language's own "etc.", a short label keeps its ellipsis
        long_src = {"a": "Pick any of the providers, including Gemini, ChatGPT, Claude, Grok, Mistral, ..."}
        errors, warns = l10n.check(long_src, {"a": "可选任意供应商，包括 Gemini、ChatGPT、Claude、Grok、Mistral 等"}, "zh-CN")
        self.assertEqual(errors, [])
        self.assertTrue(any("ellipsis" in m for _, m in warns))
        # an English UI label kept as it is passes the glossary; a hyphenated compound is not the term
        glossary = {"profile": "个人档案", "click": "点击"}
        self.assertEqual(l10n.check({"a": "Open **Profile**"}, {"a": "打开 **Profile**"}, "zh-CN", glossary)[0], [])
        self.assertEqual(l10n.check({"a": "Double-click the icon"}, {"a": "双击图标"}, "zh-CN", glossary)[0], [])
        # the other script inside code is on purpose
        self.assertEqual(l10n.check({"a": "Type `[09:00] 开会`"}, {"a": "輸入 `[09:00] 开会`"}, "zh-TW")[1], [])

    def test_tsv_round_trip_keeps_tabs_newlines_and_backslashes(self):
        flat = {"C:\\Users\\x": "路径 C:\\Users\\x", "a\tb": "一\n二"}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "zh.tsv"
            path.write_text(l10n.emit(flat, "tsv", "zh"), encoding="utf-8")
            self.assertEqual(l10n.load(path), flat)

    def test_code_only_segments_do_not_warn_as_identical(self):
        self.assertEqual(l10n.check({"a": "`touchpad`", "b": "api.ts"}, {"a": "`touchpad`", "b": "api.ts"}, "zh-TW")[1], [])


class ContextTest(unittest.TestCase):
    def test_short_ids_need_quotes_and_uses_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.js").write_text('const x = t("Up");\nlet Upload = 1;\n', encoding="utf-8")
            (root / "i18n.js").write_text('"Up": "上"', encoding="utf-8")
            result = l10n.usage_context(root, {"Up": "Up"})
            self.assertEqual(result["Up"]["uses"], ['app.js:1: const x = t("Up");'])
            (root / "list.js").write_text('t("files", { count })\n', encoding="utf-8")
            result = l10n.usage_context(root, {"files_one": "{{count}} file", "files_other": "{{count}} files"})
            self.assertEqual(result["files_one"]["uses"], ['list.js:1: t("files", { count })'])


if __name__ == "__main__":
    unittest.main()
