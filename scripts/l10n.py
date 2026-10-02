#!/usr/bin/env python3
"""Helpers for the localize skill (stdlib only).

Everything is normalized to flat JSON: {id: text}. Ids are whatever the project uses as the key
(a dotted path, or the English text itself for English-keyed tables).

  export   read a translation file of any supported format into flat JSON
  context  find where each id is used in the code (so the translator sees the UI context)
  check    validate a translation against the source (placeholders, tags, glossary, length, ...)
  emit     write flat JSON back out as json / js / py / properties / xml / strings / po
  blind    renumber a translation so the back-translator cannot see the source
  backtrans  rank a back-translation by how far it drifted from the source
"""
import argparse
import ast
import difflib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- reading

def _tokens(text, i):
    """Strings and the punctuation { } : , of a JS or Python literal; comments are skipped."""
    n = len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while text[j] != c:
                j += 2 if text[j] == "\\" else 1
            yield "s", ast.literal_eval(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i) or c == "#":
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif c in "{}:,":
            yield "p", c
            i += 1
        else:
            i += 1


def read_block(text, lang):
    """The `lang: { "key": "value", ... }` table inside a .js / .ts / .py file."""
    m = re.search(r'(?m)^[ \t]*["\']?%s["\']?\s*:\s*\{' % re.escape(lang), text)
    if not m:
        raise SystemExit("no '%s' table found" % lang)
    table, key, parts = {}, None, []
    for kind, v in _tokens(text, m.end()):
        if kind == "s":
            parts.append(v)  # adjacent literals concatenate, as in Python
        elif v == ":":
            key, parts = "".join(parts), []
        elif v in ",}":
            if key is not None:
                table[key] = "".join(parts)
            key, parts = None, []
            if v == "}":
                return table
        else:
            raise SystemExit("nested braces outside strings are not supported in a table block")
    raise SystemExit("table block is not closed")


def _flatten(obj, prefix=""):
    for k, v in obj.items():
        if isinstance(v, dict):
            yield from _flatten(v, prefix + k + ".")
        elif isinstance(v, str):
            yield prefix + k, v


def _unflatten(flat):
    root = {}
    for key, value in flat.items():
        node = root
        *path, last = key.split(".")
        for part in path:
            node = node.setdefault(part, {})
        node[last] = value
    return root


def _unescape(s):
    return json.loads('"%s"' % s)  # .strings escapes (\" \n \\ \uXXXX) are JSON escapes


def read_properties(text):
    out, pending = {}, ""
    for raw in text.splitlines():
        line = pending + raw.strip()
        pending = ""
        if line.endswith("\\") and not line.endswith("\\\\"):
            pending = line[:-1]
            continue
        if not line or line[0] in "#!":
            continue
        m = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)", line)
        if m:
            out[m.group(1)] = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), m.group(2)).replace("\\n", "\n")
    return out


def read_po(text):
    out, skipped, msgid, msgstr, cur = {}, 0, None, None, None
    plural = False

    def flush():
        nonlocal skipped
        if msgid:
            if plural:
                skipped += 1
            else:
                out[msgid] = msgstr or ""

    for line in text.splitlines() + [""]:
        line = line.strip()
        m = re.match(r'(msgid|msgstr|msgid_plural)(?:\[\d+\])?\s+(".*")$', line)
        if line.startswith("msgid ") and not line.startswith("msgid_plural"):
            flush()
            msgid, msgstr, plural, cur = ast.literal_eval(m.group(2)), None, False, "id"
        elif m and m.group(1) == "msgid_plural":
            plural, cur = True, "plural"
        elif m and m.group(1) == "msgstr":
            msgstr, cur = ast.literal_eval(m.group(2)), "str"
        elif line.startswith('"') and cur in ("id", "str"):
            piece = ast.literal_eval(line)
            if cur == "id":
                msgid += piece
            else:
                msgstr += piece
    flush()
    if skipped:
        print("note: skipped %d plural entries (translate those with a gettext tool)" % skipped, file=sys.stderr)
    return out


def read_android(text):
    out = {}
    for el in ET.fromstring(text):
        if el.tag == "string":
            inner = (el.text or "") + "".join(ET.tostring(c, encoding="unicode") for c in el)
            out[el.get("name")] = inner.replace("\\'", "'").replace("\\n", "\n")
        else:
            print("note: skipped <%s name=%s> (plurals and arrays need manual handling)" % (el.tag, el.get("name")), file=sys.stderr)
    return out


def read_strings(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return {_unescape(k): _unescape(v) for k, v in re.findall(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', text)}


def load(path, lang=None, nested=False):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    ext = path.suffix.lower()
    if ext in (".json", ".arb"):
        data = json.loads(text)
        if lang and isinstance(data.get(lang), dict):
            data = data[lang]
        # .arb keeps metadata in @keys; they are not translatable
        return dict(_flatten(data)) if nested else {k: v for k, v in data.items() if isinstance(v, str) and not k.startswith("@")}
    if ext == ".properties":
        return read_properties(text)
    if ext in (".po", ".pot"):
        return read_po(text)
    if ext == ".xml":
        return read_android(text)
    if ext == ".strings":
        return read_strings(text)
    if ext in (".js", ".mjs", ".ts", ".py"):
        if not lang:
            raise SystemExit("--lang is required for %s tables" % ext)
        return read_block(text, lang)
    raise SystemExit("unsupported file type: %s (convert it to JSON first)" % ext)

# ---------------------------------------------------------------- writing

def _quote(s):
    return json.dumps(s, ensure_ascii=False)  # valid string literal in JSON, JS and Python


def _plain_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def emit(flat, fmt, lang, source=None, nested=False, indent=2):
    if fmt == "json":
        return json.dumps(_unflatten(flat) if nested else flat, ensure_ascii=False, indent=2) + "\n"
    if fmt in ("js", "py"):
        name = lang if fmt == "js" and re.fullmatch(r"[A-Za-z_]\w*", lang) else _quote(lang)
        pad = " " * indent  # block at `indent` spaces, entries at twice that, as in the tables this skill reads
        return "%s%s: {\n%s%s},\n" % (pad, name, "".join("%s%s: %s,\n" % (pad * 2, _quote(k), _quote(v)) for k, v in flat.items()), pad)
    if fmt == "properties":
        esc = lambda s: "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in s.replace("\\", "\\\\")).replace("\n", "\\n")
        return "".join("%s=%s\n" % (k, esc(v)) for k, v in flat.items())
    if fmt == "strings":
        return "".join('"%s" = "%s";\n' % (_plain_escape(k), _plain_escape(v)) for k, v in flat.items())
    if fmt == "po":
        if source is None:
            raise SystemExit("--source is required for po output (msgid is the source text)")
        head = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: %s\\n"\n\n' % lang
        return head + "".join("msgid %s\nmsgstr %s\n\n" % (_quote(source.get(k, k)), _quote(v)) for k, v in flat.items())
    if fmt == "xml":
        def esc(s):
            s = s.replace("'", "\\'").replace("\n", "\\n")
            return s if re.search(r"</?[a-zA-Z]", s) else s.replace("&", "&amp;").replace("<", "&lt;")
        rows = "".join('    <string name="%s">%s</string>\n' % (k, esc(v)) for k, v in flat.items())
        return '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n%s</resources>\n' % rows
    raise SystemExit("unknown format: " + fmt)

# ---------------------------------------------------------------- checking

# {name} {0} {{name}} %s %d %1$s %.2f %@ %ld %(name)s
PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}|\{\w+\}|%\(\w+\)[sdif]|%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?(?:ll|l|h)?[sdifuxXc@]")
ICU = re.compile(r"\{\s*(\w+)\s*,\s*(plural|select|selectordinal)\s*,")
TAG = re.compile(r"</?([a-zA-Z][\w-]*)[^<>]*>")
COUNT_NAME = re.compile(r"\{(?:n|count|num|number|total)\}")
# Languages whose plural rules have more than one/other, so "{n} items" style text can be wrong
COMPLEX_PLURAL = {"ru", "uk", "pl", "cs", "sk", "sl", "hr", "sr", "bs", "lt", "lv", "ar", "he", "ga", "cy", "ro", "mt"}
RTL = {"ar", "he", "fa", "ur", "ps", "yi"}
SCRIPTS = {
    "zh": "\u4e00-\u9fff", "ja": "\u3040-\u30ff\u4e00-\u9fff", "ko": "\uac00-\ud7af", "ar": "\u0600-\u06ff", "fa": "\u0600-\u06ff",
    "ur": "\u0600-\u06ff", "he": "\u0590-\u05ff", "ru": "\u0400-\u04ff", "uk": "\u0400-\u04ff", "bg": "\u0400-\u04ff",
    "el": "\u0370-\u03ff", "th": "\u0e00-\u0e7f", "hi": "\u0900-\u097f",
}


def _word(term):
    return r"(?<!\w)%s(?!\w)" % re.escape(term)


def check(source, target, lang, glossary=None, max_ratio=1.5):
    """Returns (errors, warnings), each a list of (id, message)."""
    errors, warnings = [], []
    base = lang.lower().replace("_", "-").split("-")[0]
    glossary = glossary or {}
    glossary = {term: [wanted] if isinstance(wanted, str) else list(wanted) for term, wanted in glossary.items()}
    keep = [term for term, wanted in glossary.items() if [term.lower()] == [w.lower() for w in wanted]]
    for k, src in source.items():
        if k not in target:
            errors.append((k, "missing translation"))
            continue
        tgt = target[k]
        if not tgt.strip():
            errors.append((k, "empty translation"))
            continue
        # Placeholders: ICU messages keep their argument and the mandatory `other` branch (languages differ in the rest)
        if ICU.search(src):
            if sorted(ICU.findall(src)) != sorted(ICU.findall(tgt)):
                errors.append((k, "ICU argument changed: %s -> %s" % (ICU.findall(src), ICU.findall(tgt))))
            if re.search(r"\bother\s*\{", src) and not re.search(r"\bother\s*\{", tgt):
                errors.append((k, "ICU message lost its `other` branch"))
        elif Counter(PLACEHOLDER.findall(src)) != Counter(PLACEHOLDER.findall(tgt)):
            errors.append((k, "placeholders differ: %s -> %s" % (PLACEHOLDER.findall(src), PLACEHOLDER.findall(tgt))))
        if Counter(TAG.findall(src)) != Counter(TAG.findall(tgt)):
            errors.append((k, "markup tags differ: %s -> %s" % (TAG.findall(src), TAG.findall(tgt))))
        if src.count("\n") != tgt.count("\n"):
            errors.append((k, "line break count differs"))
        # Terms kept as they are (brands) are masked first, so a brand like "Phone Remote" does not trigger the term "phone"
        # Command line flags, `code spans` and placeholders are never translated, so they are masked too
        masked = re.sub(r"--[\w-]+|`[^`]*`", " ", PLACEHOLDER.sub(" ", src))
        for term in keep:
            masked = re.sub(_word(term), " ", masked, flags=re.I)
        for term, wanted in glossary.items():
            if re.search(_word(term), src if term in keep else masked, re.I) and not any(w.lower() in tgt.lower() for w in wanted):
                errors.append((k, "glossary: '%s' must appear as %s" % (term, " or ".join("'%s'" % w for w in wanted))))
        words = PLACEHOLDER.sub("", src)
        if not re.search(r"[^\W\d_]", words):
            continue  # nothing to translate (only symbols or placeholders)
        if tgt == src and src.strip() not in glossary:
            warnings.append((k, "identical to source (fine for names and loanwords, otherwise untranslated)"))
        elif base in SCRIPTS and tgt != src and not re.search("[%s]" % SCRIPTS[base], tgt):
            warnings.append((k, "no %s characters in the translation" % base))
        if len(tgt) > max_ratio * len(src) + 4 and len(src) <= 60:
            warnings.append((k, "%d%% longer than source, check it fits the UI" % (100 * len(tgt) // max(len(src), 1) - 100)))
        if base in COMPLEX_PLURAL and COUNT_NAME.search(src):
            warnings.append((k, "text next to a number: %s has several plural forms, prefer number-neutral wording" % base))
    for k in target:
        if k not in source:
            warnings.append((k, "id not in source (stale or typo)"))
    return errors, warnings


def usage_context(root, source, skip_names=()):
    skip_dirs = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", "locales", "locale", "translations", "i18n", "lang"}
    exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".htm", ".kt", ".java", ".swift", ".m", ".dart", ".php", ".erb", ".xml"}
    files = []
    for p in Path(root).rglob("*"):
        rel = p.relative_to(root)
        if (p.suffix in exts and p.is_file() and not skip_dirs & set(rel.parts[:-1]) and not p.name.lower().startswith("i18n")
                and p.name not in skip_names and p.stat().st_size < 1_000_000):
            files.append((rel, p.read_text(encoding="utf-8", errors="replace").splitlines()))
    out = {}
    for k, text in source.items():
        # quoted forms keep short words like "Up" or "OK" from matching everywhere
        needles = ['"%s"' % k, "'%s'" % k, ">%s<" % k] + ([k[:50]] if len(k) >= 12 else [])
        hits = ["%s:%d: %s" % (rel.as_posix(), no, line.strip()[:160])
                for rel, lines in files for no, line in enumerate(lines, 1) if any(n in line for n in needles)]
        out[k] = {"text": text, "uses": hits[:3]}
    return out


def blind(target):
    """Target texts under numeric ids, so a back-translator cannot read the English when ids are English text."""
    return {str(i): text for i, text in enumerate(target.values(), 1)}


def unblind(back, target):
    return {k: back[str(i)] for i, k in enumerate(target, 1) if str(i) in back}


def drift(source, back, threshold):
    rows = []
    for k, src in source.items():
        if k in back:
            clean = lambda s: PLACEHOLDER.sub("", s).lower().strip()
            ratio = difflib.SequenceMatcher(None, clean(src), clean(back[k])).ratio()
            if ratio < threshold:
                rows.append((ratio, k, src, back[k]))
    return sorted(rows)

# ---------------------------------------------------------------- cli

def _dump(obj, out):
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export", help="read a translation file into flat JSON")
    p.add_argument("file")
    p.add_argument("--lang", help="language block name (needed for .js/.py tables)")
    p.add_argument("--nested", action="store_true", help="flatten nested JSON into dotted ids")
    p.add_argument("--identity", action="store_true", help="map every id to itself (source file for English-keyed tables)")
    p.add_argument("-o", "--out")

    p = sub.add_parser("context", help="where each id is used in the code")
    p.add_argument("root")
    p.add_argument("--source", required=True, help="flat JSON {id: source text}")
    p.add_argument("-o", "--out")

    p = sub.add_parser("check", help="validate a translation")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--glossary", help="JSON {source term: required rendering, or a list of accepted renderings}")
    p.add_argument("--max-ratio", type=float, default=1.5)

    p = sub.add_parser("emit", help="write flat JSON in a project format")
    p.add_argument("target", help="flat JSON {id: translation}")
    p.add_argument("--format", required=True, choices=["json", "js", "py", "properties", "xml", "strings", "po"])
    p.add_argument("--lang", required=True)
    p.add_argument("--source", help="flat JSON source (needed for po)")
    p.add_argument("--nested", action="store_true", help="json: rebuild nesting from dotted ids")
    p.add_argument("--indent", type=int, default=2, help="js/py: spaces before the language block (entries get twice as many)")
    p.add_argument("-o", "--out")

    p = sub.add_parser("blind", help="renumber a translation so the back-translator never sees the source ids")
    p.add_argument("target")
    p.add_argument("-o", "--out")

    p = sub.add_parser("backtrans", help="rank back-translations by drift from the source")
    p.add_argument("--source", required=True)
    p.add_argument("--back", required=True)
    p.add_argument("--target", help="the translation that was blinded; back keys are then numbers in its order")
    p.add_argument("--threshold", type=float, default=0.6)

    a = ap.parse_args(argv)
    if a.cmd == "export":
        data = load(a.file, a.lang, a.nested)
        _dump({k: k for k in data} if a.identity else data, a.out)
    elif a.cmd == "context":
        _dump(usage_context(a.root, load(a.source)), a.out)
    elif a.cmd == "check":
        glossary = json.loads(Path(a.glossary).read_text(encoding="utf-8")) if a.glossary else None
        errors, warnings = check(load(a.source), load(a.target), a.lang, glossary, a.max_ratio)
        for k, msg in errors:
            print("ERROR %s: %s" % (k, msg))
        for k, msg in warnings:
            print("WARN  %s: %s" % (k, msg))
        if a.lang.split("-")[0].lower() in RTL:
            print("NOTE  %s is right to left: set dir=rtl and check the layout by eye" % a.lang)
        print("%d errors, %d warnings" % (len(errors), len(warnings)))
        return 1 if errors else 0
    elif a.cmd == "emit":
        text = emit(load(a.target), a.format, a.lang, load(a.source) if a.source else None, a.nested, a.indent)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    elif a.cmd == "blind":
        _dump(blind(load(a.target)), a.out)
    elif a.cmd == "backtrans":
        back = load(a.back)
        rows = drift(load(a.source), unblind(back, load(a.target)) if a.target else back, a.threshold)
        for ratio, k, src, back in rows:
            print("%.2f  %s\n      source: %s\n      back:   %s" % (ratio, k, src, back))
        print("%d of the strings drifted below %.2f (a low score means review, not wrong)" % (len(rows), a.threshold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
