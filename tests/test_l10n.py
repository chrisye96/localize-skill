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
        po = 'msgid ""\nmsgstr ""\n\nmsgid "Hi %s"\nmsgstr "Hola %s"\n\nmsgid "A"\nmsgid_plural "As"\nmsgstr[0] "a"\n'
        self.assertEqual(l10n.read_po(po), {"Hi %s": "Hola %s"})
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

    def test_blind_hides_ids_and_unblind_restores_them(self):
        target = {"Play or pause": "Reproducir o pausar", "Quit": "Salir"}
        blinded = l10n.blind(target)
        self.assertEqual(blinded, {"1": "Reproducir o pausar", "2": "Salir"})
        self.assertEqual(l10n.unblind({"1": "Play or pause", "2": "Exit"}, target), {"Play or pause": "Play or pause", "Quit": "Exit"})

    def test_drift_ranks_worst_first(self):
        rows = l10n.drift({"a": "Play or pause", "b": "Quit"}, {"a": "Quit", "b": "Quit"}, 0.6)
        self.assertEqual([r[1] for r in rows], ["a"])


class ContextTest(unittest.TestCase):
    def test_short_ids_need_quotes_and_uses_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.js").write_text('const x = t("Up");\nlet Upload = 1;\n', encoding="utf-8")
            (root / "i18n.js").write_text('"Up": "上"', encoding="utf-8")
            result = l10n.usage_context(root, {"Up": "Up"})
            self.assertEqual(result["Up"]["uses"], ['app.js:1: const x = t("Up");'])


if __name__ == "__main__":
    unittest.main()
