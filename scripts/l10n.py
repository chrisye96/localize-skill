#!/usr/bin/env python3
"""Helpers for the localize skill (stdlib only).

Everything is normalized to flat JSON: {id: text}. Ids are whatever the project uses as the key
(a dotted path, or the English text itself for English-keyed tables).

  export   read a translation file of any supported format into flat JSON
  context  find where each id is used in the code (so the translator sees the UI context)
  check    validate a translation against the source (placeholders, tags, glossary, length, ...)
  emit     write flat JSON back out as json / js / py / properties / xml / strings / po
  md-split a Markdown document (README, docs) as segments plus a skeleton that keeps code, HTML and layout
  md-build rebuild it from a translation, with the language links line; checks links, code and #anchors
  rekey    carry translations across cosmetic edits of the English; list the rest for review
  regional keep only the rows of a regional variant (es-MX) that differ from its base language (es)
  diff     what changed between two versions of a translation (for a review report)
  blind    renumber a translation so the back-translator cannot see the source
  backtrans  rank a back-translation by how far it drifted from the source
"""
import argparse
import ast
import difflib
import json
import re
import sys
import unicodedata
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


def read_po(text, template=False):
    """msgid -> msgstr. A plural entry becomes one id per form: `msgid#0`, `msgid#1`, ... (msgstr[i]).
    A template (.pot) gives the English instead: msgid, and msgid_plural as `#1`."""
    out, entry, field = {}, {}, None

    def flush():
        mid = entry.get("msgid")
        if mid:  # the header has an empty msgid
            if "msgid_plural" in entry:
                if template:
                    out[mid + "#0"], out[mid + "#1"] = mid, entry["msgid_plural"]
                else:
                    for key, val in entry.items():
                        if key.startswith("msgstr["):
                            out["%s#%s" % (mid, key[7:-1])] = val
            else:
                out[mid] = mid if template else entry.get("msgstr", "")
        entry.clear()

    for line in text.splitlines() + [""]:
        line = line.strip()
        m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(".*")$', line)
        if m:
            field = m.group(1)
            if field in ("msgctxt", "msgid") and "msgid" in entry:
                flush()
            entry[field] = ast.literal_eval(m.group(2))
        elif line.startswith('"') and field in entry:
            entry[field] += ast.literal_eval(line)
    flush()
    return out


def _android_text(el):
    inner = (el.text or "") + "".join(ET.tostring(c, encoding="unicode") for c in el)
    return inner.replace("\\'", "'").replace("\\n", "\n")


def read_android(text):
    """<string name="x"> -> x, and each <item quantity="q"> of <plurals name="x"> -> x#q."""
    out = {}
    for el in ET.fromstring(text):
        if el.tag == "string":
            out[el.get("name")] = _android_text(el)
        elif el.tag == "plurals":
            for item in el:
                out["%s#%s" % (el.get("name"), item.get("quantity"))] = _android_text(item)
        else:
            print("note: skipped <%s name=%s> (arrays need manual handling)" % (el.tag, el.get("name")), file=sys.stderr)
    return out


def read_strings(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return {_unescape(k): _unescape(v) for k, v in re.findall(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', text)}


def _tsv_unescape(s):
    return re.sub(r"\\([nt\\])", lambda m: {"n": "\n", "t": "\t", "\\": "\\"}[m.group(1)], s)


def read_tsv(text):
    """id<TAB>text per line, with \\n \\t \\\\ escapes: easier to write by hand than JSON, whose escaping of
    Windows paths and backslashes goes wrong. Blank lines are skipped."""
    out = {}
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.strip():
            key, _, value = line.partition("\t")
            out[_tsv_unescape(key)] = _tsv_unescape(value)
    return out


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
    if ext == ".tsv":
        return read_tsv(text)
    if ext in (".po", ".pot"):
        return read_po(text, template=ext == ".pot")
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


def _grouped(flat, split):
    """Entries in file order: (id, None) for a plain string, (base, [(form, text), ...]) once per plural group.
    `split(id)` returns (base, form) for an id that is a plural form, else something falsy."""
    done = set()
    for k in flat:
        parts = split(k)
        if not parts:
            yield k, None
        elif parts[0] not in done:
            done.add(parts[0])
            yield parts[0], [(split(x)[1], y) for x, y in flat.items() if split(x) and split(x)[0] == parts[0]]


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
    if fmt == "tsv":
        esc = lambda s: s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
        return "".join("%s\t%s\n" % (esc(k), esc(v)) for k, v in flat.items())
    if fmt == "strings":
        return "".join('"%s" = "%s";\n' % (_plain_escape(k), _plain_escape(v)) for k, v in flat.items())
    if fmt == "po":
        if source is None:
            raise SystemExit("--source is required for po output (msgid is the source text)")
        rule = plural_rule(lang)
        head = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: %s\\n"\n' % lang
        if rule:
            head += '"Plural-Forms: nplurals=%d; plural=(%s);\\n"\n' % (len(rule[0]), rule[1])
        groups, body = plural_groups(source), []

        def po_form(k):  # (msgid, index) for `msgid#i` of a gettext plural group in the source
            m = re.match(r"(.+)#(\d+)$", k)
            return m and groups.get(m.group(1)) == ("idx", "#") and m.groups()

        for base, forms in _grouped(flat, po_form):
            if forms is None:
                body.append("msgid %s\nmsgstr %s\n\n" % (_quote(source.get(base, base)), _quote(flat[base])))
            else:
                strs = "".join("msgstr[%s] %s\n" % (i, _quote(v)) for i, v in sorted(forms, key=lambda f: int(f[0])))
                body.append("msgid %s\nmsgid_plural %s\n%s\n" % (_quote(source[base + "#0"]), _quote(source[base + "#1"]), strs))
        return head + "\n" + "".join(body)
    if fmt == "xml":
        def esc(s):
            s = s.replace("'", "\\'").replace("\n", "\\n")
            return s if re.search(r"</?[a-zA-Z]", s) else s.replace("&", "&amp;").replace("<", "&lt;")
        rows = []

        def xml_form(k):  # (name, quantity) for `name#quantity`; Android names never contain `#`
            m = re.match(r"(.+)#(%s)$" % "|".join(CATEGORIES), k)
            return m and m.groups()

        for base, forms in _grouped(flat, xml_form):
            if forms is None:
                rows.append('    <string name="%s">%s</string>\n' % (base, esc(flat[base])))
            else:
                items = sorted(forms, key=lambda f: CATEGORIES.index(f[0]))
                rows.append('    <plurals name="%s">\n%s    </plurals>\n' % (base, "".join('        <item quantity="%s">%s</item>\n' % (q, esc(v)) for q, v in items)))
        return '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n%s</resources>\n' % "".join(rows)
    raise SystemExit("unknown format: " + fmt)

# ---------------------------------------------------------------- checking

# {name} {0} {{name}} %s %d %1$s %.2f %@ %ld %(name)s
PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}|\{\w+\}|%\(\w+\)[sdif]|%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?(?:ll|l|h)?[sdifuxXc@]")
ICU = re.compile(r"\{\s*(\w+)\s*,\s*(plural|select|selectordinal)\s*,")
TAG = re.compile(r"</?([a-zA-Z][\w-]*)[^<>]*>")
COUNT_NAME = re.compile(r"\{(?:n|count|num|number|total)\}")

# CLDR plural categories, in CLDR order. For each language: the categories whole numbers 0 to 1000 reach
# (a gettext catalog has one msgstr per category, in this order), and the gettext expression that picks
# the index. Fractions can reach more categories (Russian `other`, French `many` for a million), which is
# why CLDR based formats (ICU, i18next, Android) always need `other` as well.
CATEGORIES = ("zero", "one", "two", "few", "many", "other")
_ONE_OTHER, _ONE_FEW_OTHER = ("one", "other"), ("one", "few", "other")
_SLAVIC = "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2"
_PLURAL_GROUPS = [
    ("af az bg ca da de el en eo es et eu fi gl hu it ka kk ml mn mr nb nl nn no pt-pt sq sv sw ta te tr ur uz",
     _ONE_OTHER, "n != 1"),
    ("am as bn fa fr gu hi hy kn pt zu", _ONE_OTHER, "n > 1"),  # `one` is 0 and 1
    ("is mk", _ONE_OTHER, "n%10 != 1 || n%100 == 11"),
    ("id ja km ko lo ms my th vi zh", ("other",), "0"),
    ("ru uk be", ("one", "few", "many"), _SLAVIC),
    ("pl", ("one", "few", "many"), "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2"),
    ("hr sr bs", _ONE_FEW_OTHER, _SLAVIC),
    ("cs sk", _ONE_FEW_OTHER, "n==1 ? 0 : n>=2 && n<=4 ? 1 : 2"),
    ("lt", _ONE_FEW_OTHER, "n%10==1 && (n%100<11 || n%100>19) ? 0 : n%10>=2 && (n%100<11 || n%100>19) ? 1 : 2"),
    ("ro", _ONE_FEW_OTHER, "n==1 ? 0 : n==0 || (n%100>=1 && n%100<=19) ? 1 : 2"),
    ("lv", ("zero", "one", "other"), "n%10==0 || (n%100>=11 && n%100<=19) ? 0 : n%10==1 && n%100!=11 ? 1 : 2"),
    ("he", ("one", "two", "other"), "n==1 ? 0 : n==2 ? 1 : 2"),
    ("sl", ("one", "two", "few", "other"), "n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3"),
    ("ga", ("one", "two", "few", "many", "other"), "n==1 ? 0 : n==2 ? 1 : n>=3 && n<=6 ? 2 : n>=7 && n<=10 ? 3 : 4"),
    ("mt", ("one", "two", "few", "many", "other"),
     "n==1 ? 0 : n==2 ? 1 : n==0 || (n%100>=3 && n%100<=10) ? 2 : n%100>=11 && n%100<=19 ? 3 : 4"),
    ("ar", ("zero", "one", "two", "few", "many", "other"),
     "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5"),
    ("cy", ("zero", "one", "two", "few", "many", "other"), "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n==3 ? 3 : n==6 ? 4 : 5"),
]
PLURALS = {lang: (cats, expr) for langs, cats, expr in _PLURAL_GROUPS for lang in langs.split()}
# Languages whose plural rules have more than one/other, so "{n} items" style text can be wrong
COMPLEX_PLURAL = {lang for lang, (cats, _) in PLURALS.items() if len(cats) > 2}
# `file_one` / `file_other` (i18next), `file#one` (Android plurals as read here), `msgid#0` (gettext plurals)
PLURAL_KEY = re.compile(r"^(.+?)([#_])(%s)$|^(.+)#(\d+)$" % "|".join(CATEGORIES))


def plural_rule(lang):
    """(categories, gettext expression) for a language tag such as `pt-BR` or `zh_Hant`, or None."""
    lang = lang.lower().replace("_", "-")
    return PLURALS.get(lang) or PLURALS.get(lang.split("-")[0])


def plural_groups(keys):
    """{base: ("cat", separator) or ("idx", "#")} for the ids in `keys` that form a plural group.
    A category group needs its `other` form and an indexed one `#0` and `#1`, so `step_one` alone is just a string."""
    keys, groups = set(keys), {}
    for k in keys:
        m = PLURAL_KEY.match(k)
        if m and m.group(1) and m.group(1) + m.group(2) + "other" in keys:
            groups[m.group(1)] = ("cat", m.group(2))
        elif m and m.group(4) and {m.group(4) + "#0", m.group(4) + "#1"} <= keys:  # not a lone "Item #1"
            groups[m.group(4)] = ("idx", "#")
    return groups


def _plural_member(k, groups):
    """(base, form) when id `k` is a form of one of `groups`, else None."""
    m = PLURAL_KEY.match(k)
    if m and m.group(1) and groups.get(m.group(1)) == ("cat", m.group(2)):
        return m.group(1), m.group(3)
    if m and m.group(4) and groups.get(m.group(4)) == ("idx", "#"):
        return m.group(4), int(m.group(5))
    return None


def icu_plural_selectors(text):
    """The selectors (`one`, `few`, `=0`, ...) of every plural in an ICU message, nested ones included."""
    found = []
    for m in re.finditer(r"\{\s*\w+\s*,\s*plural\s*,", text):
        i, sels, n = m.end(), [], len(text)
        while i < n:
            while i < n and text[i].isspace():
                i += 1
            if i >= n or text[i] == "}":
                break
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{}":
                j += 1
            token, i = text[i:j], j
            while i < n and text[i].isspace():
                i += 1
            if i < n and text[i] == "{":
                depth = 0
                while i < n:
                    depth += {"{": 1, "}": -1}.get(text[i], 0)
                    i += 1
                    if depth == 0:
                        break
                sels.append(token)
        found.append(sels)
    return found


RTL = {"ar", "he", "fa", "ur", "ps", "yi"}
SCRIPTS = {
    "zh": "\u4e00-\u9fff", "ja": "\u3040-\u30ff\u4e00-\u9fff", "ko": "\uac00-\ud7af", "ar": "\u0600-\u06ff", "fa": "\u0600-\u06ff",
    "ur": "\u0600-\u06ff", "he": "\u0590-\u05ff", "ru": "\u0400-\u04ff", "uk": "\u0400-\u04ff", "bg": "\u0400-\u04ff",
    "el": "\u0370-\u03ff", "th": "\u0e00-\u0e7f", "hi": "\u0900-\u097f",
}


def _word(term):
    """A glossary term as a whole word; `reject*` matches every word starting with `reject` (rejects, rejected)."""
    # a hyphen joins words: "click" is not a match inside "Double-click"
    if term.endswith("*"):
        return r"(?<![\w-])%s[\w-]*" % re.escape(term[:-1])
    return r"(?<![\w-])%s(?![\w-])" % re.escape(term)


# Code spans, link targets and bare URLs carry over unchanged. An in-page #anchor follows its translated
# heading instead (md-build checks those against the headings).
URL = re.compile(r"https?://[^\s)>\]\"'，。、；：）」』]+")


def _literals(text):
    links = [t for t in re.findall(r"\]\(([^)\s]+)[^)]*\)", text) if not t.startswith("#")]
    return Counter(re.findall(r"`[^`]+`", text)) + Counter(links) + Counter(URL.findall(text))


def _prose(text):
    """The words of a text that are translated: placeholders, command line flags, code spans, link targets,
    URLs and file names removed ("phone-remote" in a link is not the term "remote", icons.svg not "icons")."""
    text = URL.sub(" ", PLACEHOLDER.sub(" ", text))
    return re.sub(r"--[\w-]+|`[^`]*`|\]\([^)]*\)|[\w/-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}(?![\w.])", " ", text)


def _md_punct(c):
    return c == "" or unicodedata.category(c)[0] in "PS"


def _bold_problems(text):
    """`**` pairs that Markdown will not render as bold, CommonMark's flanking rules: an opening `**` before
    punctuation needs whitespace or punctuation in front, a closing one after punctuation needs it behind.
    Chinese hits this all the time: `**完成。**然后` stays literal asterisks."""
    problems, runs = [], [m.start() for m in re.finditer(r"(?<!\*)\*\*(?!\*)", text)]
    for n, i in enumerate(runs):
        before, after = text[i - 1:i] if i else "", text[i + 2:i + 3]
        opening = n % 2 == 0
        if opening:
            ok = after and not after.isspace() and (not _md_punct(after) or before == "" or before.isspace() or _md_punct(before))
        else:
            ok = before and not before.isspace() and (not _md_punct(before) or after == "" or after.isspace() or _md_punct(after))
        if not ok:
            problems.append(text[max(0, i - 6):i + 8])
    return problems


# Common characters written differently in Simplified and Traditional Chinese, as (Simplified, Traditional)
# pairs. Only characters that exist in one of the two scripts are listed (no 后/後, 里/裡, 干/乾).
ZH_PAIRS = ("这這们們个個为為说說时時发發项項译譯检檢测測试試语語术術词詞复複数數据據库庫码碼软軟开開关關页頁"
            "网網络絡显顯单單标標记記换換题題区區变變审審释釋链鏈应應写寫读讀规規则則浏瀏览覽机機图圖层層义義"
            "与與么麼样樣还還进進过過对對从從级級识識别別确確认認组組档檔态態录錄资資夹夾构構绍紹盘盤错錯误誤"
            "隐隱给給让讓将將线線类類实實场場处處间間设設计計门門转轉颜顏导導务務动動线線书書长長车車东東")
SIMPLIFIED, TRADITIONAL = set(ZH_PAIRS[0::2]), set(ZH_PAIRS[1::2])


def zh_script(lang):
    """"hans" or "hant" for a Chinese tag (zh-TW, zh-HK and zh-MO are Traditional), else None."""
    parts = lang.lower().replace("_", "-").split("-")
    if parts[0] != "zh":
        return None
    return "hant" if "hant" in parts or set(parts) & {"tw", "hk", "mo"} else "hans"


def _check_text(src, tgt, base, rule, glossary, keep, max_ratio, form=None, group_placeholders=None, zh=None):
    """(errors, warnings) for one translated text, as messages. `form` is set for one form of a plural group:
    its placeholders may be fewer than the source's (Arabic `zero` needs no number) but never others."""
    errors, warnings = [], []
    if not tgt.strip():
        return ["empty translation"], []
    # Placeholders: ICU messages keep their argument and the mandatory `other` branch (languages differ in the rest)
    if ICU.search(src):
        if sorted(ICU.findall(src)) != sorted(ICU.findall(tgt)):
            errors.append("ICU argument changed: %s -> %s" % (ICU.findall(src), ICU.findall(tgt)))
        if re.search(r"\bother\s*\{", src) and not re.search(r"\bother\s*\{", tgt):
            errors.append("ICU message lost its `other` branch")
        elif rule:
            need = [c for c in rule[0] if c != "other"]
            lacking = sorted({c for sels in icu_plural_selectors(tgt) for c in need if c not in sels}, key=CATEGORIES.index)
            if lacking:
                errors.append("ICU plural lacks forms %s needs: %s" % (base, ", ".join(lacking)))
    elif form is None:
        if Counter(PLACEHOLDER.findall(src)) != Counter(PLACEHOLDER.findall(tgt)):
            errors.append("placeholders differ: %s -> %s" % (PLACEHOLDER.findall(src), PLACEHOLDER.findall(tgt)))
    else:
        have, want = Counter(PLACEHOLDER.findall(tgt)), Counter(PLACEHOLDER.findall(src))
        added = sorted(set(have) - set(group_placeholders))
        if added:
            errors.append("plural form '%s' adds placeholders: %s" % (form, added))
        elif want - have and form in ("other", rule[0][-1]):
            errors.append("placeholders differ: %s -> %s" % (PLACEHOLDER.findall(src), PLACEHOLDER.findall(tgt)))
        elif want - have:
            warnings.append("plural form '%s' drops %s: fine only if this form is used for a single number"
                            % (form, sorted(want - have)))
    if Counter(TAG.findall(src)) != Counter(TAG.findall(tgt)):
        errors.append("markup tags differ: %s -> %s" % (TAG.findall(src), TAG.findall(tgt)))
    have, want = _literals(tgt), _literals(src)
    if have != want:
        errors.append("code, links or URLs changed: lost %s, added %s" % (sorted((want - have).elements()), sorted((have - want).elements())))
    if src.count("\n") != tgt.count("\n"):
        errors.append("line break count differs")
    # A closing ellipsis says the control opens a dialog or needs more input before it acts. Word order may move
    # one that is part of an example ("https://..."), so only a dropped or added one is an error
    src_dots, tgt_dots = (bool(re.search(r"(\.\.\.|\u2026)\s*$", s)) for s in (src, tgt))
    dots = lambda s: len(re.findall(r"\.\.\.|\u2026+", s))
    if src_dots != tgt_dots and dots(src) != dots(tgt):
        message = "trailing ellipsis: the %s ends with one, the %s does not" % (("source", "translation") if src_dots else ("translation", "source"))
        # a control label needs it; in a sentence ("Gemini, Claude, ...") the language's own "etc." is right
        (errors if len(src) <= 60 else warnings).append(message)
    # Terms kept as they are (brands) are masked first, so a brand like "Phone Remote" does not trigger the term "phone"
    # Command line flags, `code spans` and placeholders are never translated, so they are masked too
    masked = _prose(src)
    for term in keep:
        masked = re.sub(_word(term), " ", masked, flags=re.I)
    # Longest terms first, each masked once matched: "back-translation" then never triggers the rule for "translation"
    for term, wanted in sorted(glossary.items(), key=lambda t: -len(t[0])):
        found = re.search(_word(term), src if term in keep else masked, re.I)
        if found:
            # the English kept as it is passes: a UI label the product only shows in English (**Profile**)
            if not any(w.lower() in tgt.lower() for w in wanted) and found.group(0) not in tgt:
                errors.append("glossary: '%s' must appear as %s" % (term, " or ".join("'%s'" % w for w in wanted)))
            masked = re.sub(_word(term), " ", masked, flags=re.I)
    bold_src, bold_tgt = _bold_problems(src), _bold_problems(tgt)
    if bold_tgt and not bold_src:
        errors.append("bold will not render: %s (a closing ** after punctuation needs a space or punctuation next)" % bold_tgt[0])
    elif src.count("**") != tgt.count("**"):
        warnings.append("bold markers %d -> %d" % (src.count("**"), tgt.count("**")))
    if not re.search(r"[^\W\d_]", _prose(src)):
        return errors, warnings  # nothing to translate (only symbols, placeholders, code, URLs or file names)
    if tgt == src and src.strip() not in glossary:
        warnings.append("identical to source (fine for names and loanwords, otherwise untranslated)")
    elif base in SCRIPTS and tgt != src and not re.search("[%s]" % SCRIPTS[base], tgt):
        warnings.append("no %s characters in the translation" % base)
    if zh:  # code spans, URLs and file names may hold the other script on purpose
        wrong = sorted(set(_prose(tgt)) & (SIMPLIFIED if zh == "hant" else TRADITIONAL))
        if wrong:
            names = ("Simplified", "Traditional") if zh == "hant" else ("Traditional", "Simplified")
            warnings.append("%s characters in a %s Chinese translation: %s" % (names[0], names[1], "".join(wrong)))
    if len(tgt) > max_ratio * len(src) + 4 and len(src) <= 60:
        warnings.append("%d%% longer than source, check it fits the UI" % (100 * len(tgt) // max(len(src), 1) - 100))
    if form is None and base in COMPLEX_PLURAL and COUNT_NAME.search(src):
        warnings.append("text next to a number: %s has several plural forms, use real plural forms or number-neutral wording" % base)
    return errors, warnings


def _check_plural_group(gid, kind, sep, source, target, rule, lang, check_text):
    """Problems of one plural group: forms the language needs that are missing, then each form's text."""
    if kind == "cat":
        cats = list(rule[0]) + ([] if "other" in rule[0] else ["other"])
        ids = {c: gid + sep + c for c in cats}
        src_of = lambda c: source.get(gid + sep + c, source[gid + sep + "other"])
        present = [c for c in cats if ids[c] in target]
        problem = "plural forms missing for %s: %s" % (lang, ", ".join(c for c in cats if c not in present))
    else:
        cats = list(rule[0])
        ids = {c: "%s#%d" % (gid, i) for i, c in enumerate(cats)}
        src_of = lambda c: source[gid + ("#0" if c == "one" else "#1")]
        present = [c for c in cats if ids[c] in target]
        found = sorted(int(k.rsplit("#", 1)[1]) for k in target if _plural_member(k, {gid: ("idx", "#")}))
        problem = "%s takes %d plural forms (%s), found msgstr%s" % (lang, len(cats), ", ".join(cats), found)
        if found and found != list(range(len(cats))):
            return [problem], []
    if not present:
        return ["missing translation"], []
    errors, warnings = ([problem] if len(present) < len(cats) else []), []
    members = [k for k in source if _plural_member(k, {gid: (kind, sep)})]
    group_placeholders = set(PLACEHOLDER.findall(" ".join(source[k] for k in members)))
    for c in present:
        e, w = check_text(src_of(c), target[ids[c]], form=c, group_placeholders=group_placeholders)
        errors += ["'%s': %s" % (c, m) if not m.startswith("plural form") else m for m in e]
        warnings += ["'%s': %s" % (c, m) if not m.startswith("plural form") else m for m in w]
    return errors, warnings


def check(source, target, lang, glossary=None, max_ratio=1.5):
    """Returns (errors, warnings), each a list of (id, message). A plural group is reported under its base id."""
    errors, warnings = [], []
    base = lang.lower().replace("_", "-").split("-")[0]
    rule = plural_rule(lang)
    glossary = glossary or {}
    glossary = {term: [wanted] if isinstance(wanted, str) else list(wanted) for term, wanted in glossary.items()}
    keep = [term for term, wanted in glossary.items() if [term.lower()] == [w.lower() for w in wanted]]
    zh = zh_script(lang)
    check_text = lambda src, tgt, **kw: _check_text(src, tgt, base, rule, glossary, keep, max_ratio, zh=zh, **kw)
    groups = plural_groups(source)
    for k, src in source.items():
        if _plural_member(k, groups):
            continue
        if k not in target:
            errors.append((k, "missing translation"))
            continue
        e, w = check_text(src, target[k])
        errors += [(k, m) for m in e]
        warnings += [(k, m) for m in w]
    for gid, (kind, sep) in groups.items():
        if not rule:
            warnings.append((gid, "no plural rules for %s here: check its plural forms by hand" % lang))
            continue
        e, w = _check_plural_group(gid, kind, sep, source, target, rule, lang, check_text)
        errors += [(gid, m) for m in e]
        warnings += [(gid, m) for m in w]
    for k in target:
        if k not in source and not _plural_member(k, groups):
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
    out, groups = {}, plural_groups(source)
    for k, text in source.items():
        # the code names a plural group by its base id: t("file", {count}), not file_one
        name = (_plural_member(k, groups) or (k,))[0]
        # quoted forms keep short words like "Up" or "OK" from matching everywhere
        needles = ['"%s"' % name, "'%s'" % name, ">%s<" % name] + ([name[:50]] if len(name) >= 12 else [])
        hits = ["%s:%d: %s" % (rel.as_posix(), no, line.strip()[:160])
                for rel, lines in files for no, line in enumerate(lines, 1) if any(n in line for n in needles)]
        out[k] = {"text": text, "uses": hits[:3]}
    return out


def blind(target):
    """Target texts under numeric ids, so a back-translator cannot read the English when ids are English text."""
    return {str(i): text for i, text in enumerate(target.values(), 1)}


def unblind(back, target):
    return {k: back[str(i)] for i, k in enumerate(target, 1) if str(i) in back}


def _shape(text):
    """What a translation has to mirror: placeholders, tags, line breaks and the closing punctuation."""
    end = re.search(r"(\.\.\.|[\u2026:?!.])\s*$", text)
    closing = end and end.group(1).replace("...", "\u2026")
    return Counter(PLACEHOLDER.findall(text)), Counter(TAG.findall(text)), text.count("\n"), closing


def _loose(text):
    return " ".join(re.sub(r"[^\w\s]", "", text.replace("\u2026", "...").casefold()).split())


def is_cosmetic_edit(old, new):
    """True when the English changed only in case, punctuation or spacing, so its translation still fits.
    A changed closing ellipsis, ":" or "?" is not cosmetic: the translation needs the same change."""
    return _loose(old) == _loose(new) and _shape(old) == _shape(new)


def rekey(source, target, old_source=None, threshold=0.5):
    """Follow edits of the English without losing translations. Returns (new target, carried, review).

    English-keyed tables: a target id no longer in the source is paired with the most similar new id.
    With `old_source` (id-keyed files), an id whose English changed is compared with its old English too.
    Cosmetic edits are carried as they are (`carried`: (new id, old id)). Any other similar pair goes to
    `review` as (new id, old id, old English, new English, old translation, similarity) and is left out of
    the new target, so `check` reports it as missing until it is translated again or the old text reused."""
    old_text = lambda k: (old_source or {}).get(k, k)
    carried, review, drop, rename = [], [], set(), {}
    for k in target:
        if k in source and old_source and k in old_source and old_source[k] != source[k]:
            if is_cosmetic_edit(old_source[k], source[k]):
                carried.append((k, k))
            else:
                review.append((k, k, old_source[k], source[k], target[k], 0.0))
                drop.add(k)
    stale = [k for k in target if k not in source]
    missing = [k for k in source if k not in target]
    pairs = sorted(((difflib.SequenceMatcher(None, _loose(old_text(s)), _loose(source[m])).ratio(), m, s)
                    for m in missing for s in stale), reverse=True)
    used = set()
    for ratio, m, s in pairs:
        if ratio < threshold or m in used or s in used:
            continue
        used.update((m, s))
        if is_cosmetic_edit(old_text(s), source[m]):
            carried.append((m, s))
            rename[s] = m
        else:
            review.append((m, s, old_text(s), source[m], target[s], round(ratio, 2)))
            drop.add(s)
    new = {rename.get(k, k): v for k, v in target.items() if k not in drop}
    return new, carried, review


def regional(target, base, lang):
    """Rows of a regional variant (es-MX) that differ from its base language (es). Returns (kept, dropped ids).
    Only for a runtime that falls back from region to base; never for a script variant, which shows other letters."""
    parts = lang.replace("_", "-").split("-")
    if len(parts) < 2 or not re.fullmatch(r"[A-Za-z]{2}|\d{3}", parts[-1]):
        raise SystemExit("%s has no region subtag: only a regional variant (es-MX, pt-BR, es-419) falls back to its base" % lang)
    if parts[0].lower() == "zh" and len(parts) == 2 and parts[1].upper() in ("TW", "HK", "MO"):
        raise SystemExit("%s is Traditional Chinese: falling back to zh would show Simplified, keep every row" % lang)
    groups, kept, dropped = plural_groups(target), {}, []
    same = lambda k: k in base and base[k] == target[k]
    for k, v in target.items():
        member = _plural_member(k, groups)
        forms = [x for x in target if _plural_member(x, groups) and _plural_member(x, groups)[0] == member[0]] if member else [k]
        if all(same(x) for x in forms):
            dropped.append(k)
        else:
            kept[k] = v
    return kept, dropped


def diff(old, new):
    """What changed between two versions of one translation, for the review report."""
    return {"changed": [(k, old[k], new[k]) for k in new if k in old and old[k] != new[k]],
            "added": [(k, new[k]) for k in new if k not in old],
            "removed": [(k, old[k]) for k in old if k not in new]}


def drift(source, back, threshold):
    rows = []
    for k, src in source.items():
        if k in back:
            clean = lambda s: PLACEHOLDER.sub("", s).lower().strip()
            ratio = difflib.SequenceMatcher(None, clean(src), clean(back[k])).ratio()
            if ratio < threshold:
                rows.append((ratio, k, src, back[k]))
    return sorted(rows)

# ---------------------------------------------------------------- markdown (README and docs)

MD_LIST = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?)(.*)$")
MD_HEADING = re.compile(r"^(#{1,6}\s+)(.*?)(\s*#*\s*)$")
MD_QUOTE = re.compile(r"^(\s*>\s?)(.*)$")
MD_IMAGE = re.compile(r"(!\[)([^\]]*)(\]\(([^)]*)\))")
MD_ONLY_MEDIA = re.compile(r"^\s*(\[?!\[[^\]]*\]\([^)]*\)\]?(\([^)]*\))?\s*)+$")
# Lines that are HTML blocks, not text that merely starts with an inline tag such as <kbd>
MD_BLOCK_HTML = re.compile(r"^<(/?(p|div|picture|source|img|table|tr|td|th|br|hr|h[1-6]|a)\b|!--)", re.I)
MD_CLOSE_HTML = re.compile(r"</(p|div|picture|table)>\s*$|-->\s*$", re.I)
MD_ALT = re.compile(r'(alt=")([^"]*[A-Za-z][^"]*)(")')
# A line of links to the README's languages, such as **English** | [中文](README.zh-CN.md)
MD_LANGLINE = re.compile(r"\]\(\.?/?README(\.[\w-]+)?\.md\)")
HASH_COMMENT_LANGS = {"", "bash", "sh", "shell", "console", "zsh", "ini", "toml", "yaml", "yml", "python", "py",
                      "powershell", "ps1", "text", "txt", "conf", "dockerfile", "make", "r"}
SLASH_COMMENT_LANGS = {"js", "javascript", "ts", "typescript", "jsx", "tsx", "jsonc", "c", "cpp", "cs", "java", "go",
                       "rust", "swift", "kotlin", "dart", "php"}
MD_BOX = re.compile(r"[│┐┘┤║╗╝]\s*$")  # a box drawing ends on its border; a tree line does not
# "path/or.file   what it is": the description column of a directory listing without comment markers
MD_LAYOUT = re.compile(r"^([\s│├└─]*[\w.\\/@-]*[./\\][\w.\\/@-]*\s{2,})(\S.*[A-Za-z]{2}.*)$")
ENDONYMS = {"en": "English", "zh-cn": "简体中文", "zh-hans": "简体中文", "zh-tw": "繁體中文", "zh-hant": "繁體中文",
            "zh-hk": "繁體中文（香港）", "ja": "日本語", "ko": "한국어", "es": "Español", "fr": "Français", "de": "Deutsch",
            "it": "Italiano", "pt-br": "Português (Brasil)", "pt": "Português", "ru": "Русский", "uk": "Українська",
            "ar": "العربية", "he": "עברית", "tr": "Türkçe", "vi": "Tiếng Việt", "th": "ไทย", "id": "Bahasa Indonesia",
            "pl": "Polski", "nl": "Nederlands"}


def md_split(text):
    """A Markdown document as ({English: English}, skeleton). The segments are keyed by their English text,
    like an English-keyed table: an edited README then shows new and removed paragraphs in `check` and edited
    ones in `rekey`, where numbered ids would shift after the first inserted paragraph. The skeleton keeps
    everything else verbatim: code (but its comments), HTML (but its alt text), badges, link definitions and
    rules, with a numbered slot per segment; the language links line becomes {{LANGLINE}}, added under the
    title when there is none."""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    source, slots, skel, buf = {}, {}, [], []  # buf: (prefix, text) lines of the current paragraph, item or quote
    st = {"fence": None, "lang": "", "html": False, "box": False}

    def seg(text, kind="s"):  # kind: s for prose, c for a comment in code
        if not re.search(r"[^\W\d_]", _prose(text)):
            return text  # only code, a URL or a file name: nothing to translate, so not a segment
        slot = "%s%03d" % (kind, len(slots) + 1)
        slots[slot] = source[text] = text
        return "{{%s}}" % slot

    def flush():
        if not buf:
            return
        if any(t.endswith("  ") or t.endswith("\\") for _, t in buf[:-1]):  # hard line breaks: a segment per line
            skel.extend(p + seg(t.rstrip(" \\")) + t[len(t.rstrip(" \\")):] for p, t in buf)
        else:  # soft wrapped lines render as one paragraph, so they are one segment
            skel.append(buf[0][0] + seg(" ".join(t.strip() for _, t in buf)))
        buf.clear()

    def images(line):  # alt text of a picture is read aloud and shown when it fails to load; badges stay
        return MD_IMAGE.sub(lambda m: m.group(0) if "shields.io" in m.group(4) or "badge" in m.group(4) or not re.search(r"[A-Za-z]{2}", m.group(2))
                            else m.group(1) + seg(m.group(2)) + m.group(3), line)

    for n, line in enumerate(lines):
        s = line.strip()
        if st["fence"]:
            if s.startswith(st["fence"]):
                st["fence"] = None
                skel.append(line)
                continue
            if st["box"]:  # a box drawing stays whole: double width CJK characters would break its alignment
                skel.append(line)
                continue
            # a comment in code is prose the reader needs; the code stays. A box drawing stays whole, since
            # double width CJK characters would break its alignment
            marker = "//" if st["lang"] in SLASH_COMMENT_LANGS else "#" if st["lang"] in HASH_COMMENT_LANGS else None
            c = marker and not MD_BOX.search(line) and not s.startswith("#!") and re.match(r"^(|.*?\s)(%s\s+)(.*[A-Za-z]{2}.*)$" % re.escape(marker), line)
            layout = not c and st["lang"] in ("", "text", "txt") and not MD_BOX.search(line) and MD_LAYOUT.match(line)
            if layout and not re.search(r"(?<![\w./\\])[A-Za-z]{3,}(?![\w./\\])", layout.group(2)):
                layout = None  # "input.py  media.py": more file names, not a description
            skel.append(c.group(1) + c.group(2) + seg(c.group(3), "c") if c else layout.group(1) + seg(layout.group(2), "c") if layout else line)
            continue
        m = re.match(r"^\s*(```+|~~~+)\s*([^\s{]*)", line)
        if m:
            flush()
            st["fence"], st["lang"] = m.group(1), m.group(2).lower()
            block = []
            for later in lines[n + 1:]:
                if later.strip().startswith(m.group(1)):
                    break
                block.append(later)
            # top and right corners mark a box drawing; a directory tree only uses ├ └ │ ─
            st["box"] = bool(re.search("[┌┐┘╔╗╝+]-{3,}|[┌┐┘╔╗╝]", "\n".join(block)))
            skel.append(line)
        elif st["html"] or MD_BLOCK_HTML.match(s):
            flush()
            skel.append(MD_ALT.sub(lambda a: a.group(1) + seg(a.group(2)) + a.group(3), line))
            st["html"] = not MD_CLOSE_HTML.search(s) if st["html"] or re.match(r"<(p|div|picture|table|!--)\b", s) else False
        elif not s:
            flush()
            skel.append(line)
        elif MD_LANGLINE.search(line) and "|" in line:
            flush()
            skel.append("{{LANGLINE}}")
        elif MD_ONLY_MEDIA.match(line):
            flush()
            skel.append(images(line))
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s) or re.match(r"^\s*\[[^\]]+\]:\s*\S", line):
            flush()
            skel.append(line)
        elif MD_HEADING.match(line):
            flush()
            h = MD_HEADING.match(line)
            skel.append(h.group(1) + seg(h.group(2)) + h.group(3))
        elif s.startswith("|"):
            flush()
            if re.fullmatch(r"\|?[\s:|-]+\|?", s):
                skel.append(line)
            else:
                cells = re.split(r"(?<!\\)\|", s.strip("|"))
                skel.append("| " + " | ".join(seg(c.strip()) if re.search(r"[A-Za-z]", c) else c.strip() for c in cells) + " |")
        elif MD_LIST.match(line):
            flush()
            m = MD_LIST.match(line)
            buf.append((m.group(1), m.group(2)))
        elif MD_QUOTE.match(line):
            m = MD_QUOTE.match(line)
            if buf and not buf[0][0].lstrip().startswith(">"):
                flush()
            buf.append((m.group(1), m.group(2)))
        elif line.startswith("    ") and not buf:
            skel.append(line)  # indented code
        else:
            buf.append((buf[0][0] if buf else "", line))
    flush()
    if "{{LANGLINE}}" not in skel:
        h1 = next((i for i, l in enumerate(skel) if l.startswith("# ")), None)
        if h1 is not None:
            skel[h1 + 1:h1 + 1] = ["", "{{LANGLINE}}"]
    return source, {"eol": eol, "slots": slots, "lines": skel}


def md_slug(heading):
    """GitHub's anchor for a heading: link markup dropped, lowercased, punctuation removed, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def md_langline(langs, lang):
    """`**English** | [简体中文](README.zh-CN.md) | ...`: every language by its own name, the current one in bold.
    The first language is the source and owns README.md."""
    names = [ENDONYMS.get(l.lower(), ENDONYMS.get(l.lower().split("-")[0], l)) for l in langs]
    files = ["README.md"] + ["README.%s.md" % l for l in langs[1:]]
    return " | ".join("**%s**" % n if l == lang else "[%s](%s)" % (n, f) for l, n, f in zip(langs, names, files))


def md_build(skeleton, source, target, lang, langs):
    """(document, problems). Problems: a missing segment, a changed code span, link target or URL, and an
    in-page #anchor that matches no heading of the translation."""
    problems = ["missing translation: %s" % k[:80] for k in source if k not in target]
    problems += ["code, links or URLs changed: %s" % k[:80] for k in source if k in target and _literals(source[k]) != _literals(target[k])]
    slots = skeleton["slots"]
    fill = lambda m: md_langline(langs, lang) if m.group(1) == "LANGLINE" else target.get(slots[m.group(1)], slots[m.group(1)])
    text = "\n".join(re.sub(r"\{\{([sc]\d+|LANGLINE)\}\}", fill, line) for line in skeleton["lines"])
    slugs = {md_slug(h) for h in re.findall(r"^#{1,6}\s+(.*?)\s*#*\s*$", text, re.M)}
    problems += ["#%s matches no heading: point it at the translated heading's anchor" % a
                 for a in re.findall(r"\]\(#([^)]+)\)", text) if a not in slugs]
    return text.replace("\n", skeleton["eol"]), problems

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
    p.add_argument("--format", required=True, choices=["json", "js", "py", "properties", "xml", "strings", "po", "tsv"])
    p.add_argument("--lang", required=True)
    p.add_argument("--source", help="flat JSON source (needed for po)")
    p.add_argument("--nested", action="store_true", help="json: rebuild nesting from dotted ids")
    p.add_argument("--indent", type=int, default=2, help="js/py: spaces before the language block (entries get twice as many)")
    p.add_argument("-o", "--out")

    p = sub.add_parser("md-split", help="a Markdown document (README, docs page) as source.json and skeleton.json")
    p.add_argument("file")
    p.add_argument("--out", required=True, help="work directory for source.json and skeleton.json")

    p = sub.add_parser("md-build", help="rebuild a Markdown document from the skeleton and a translation")
    p.add_argument("skeleton")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True, help="the translation (the source itself to rebuild the original)")
    p.add_argument("--lang", required=True)
    p.add_argument("--langs", required=True, help="every language of the document, source first: en,zh-CN,zh-TW")
    p.add_argument("-o", "--out", required=True)

    p = sub.add_parser("rekey", help="carry translations across edits of the English source (case, punctuation, spacing)")
    p.add_argument("--source", required=True, help="the current source")
    p.add_argument("--target", required=True)
    p.add_argument("--old-source", help="the source the target was translated from (needed when ids are not the English)")
    p.add_argument("--threshold", type=float, default=0.5, help="similarity below which a stale id is not paired")
    p.add_argument("-o", "--out", help="write the updated target here")

    p = sub.add_parser("regional", help="keep only the rows of a regional variant that differ from its base language")
    p.add_argument("target", help="the regional variant, complete (es-MX)")
    p.add_argument("--base", required=True, help="the base language it falls back to (es)")
    p.add_argument("--lang", required=True, help="the regional tag, such as es-MX")
    p.add_argument("-o", "--out")

    p = sub.add_parser("diff", help="what changed between two versions of a translation (for a review report)")
    p.add_argument("old")
    p.add_argument("new")

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
    elif a.cmd == "md-split":
        source, skeleton = md_split(Path(a.file).read_bytes().decode("utf-8"))  # bytes keep \r\n line endings
        Path(a.out).mkdir(parents=True, exist_ok=True)
        _dump(source, str(Path(a.out, "source.json")))
        _dump(skeleton, str(Path(a.out, "skeleton.json")))
        comments = sum(s.startswith("c") for s in skeleton["slots"])
        print("%d segments, %d of them comments in code (repeated texts share one entry)" % (len(source), comments))
    elif a.cmd == "md-build":
        skeleton = json.loads(Path(a.skeleton).read_text(encoding="utf-8"))
        text, problems = md_build(skeleton, load(a.source), load(a.target), a.lang, a.langs.split(","))
        for p in problems:
            print("ERROR %s" % p)
        if problems:
            return 1
        Path(a.out).write_bytes(text.encode("utf-8"))
        print("wrote %s" % a.out)
    elif a.cmd == "rekey":
        new, carried, review = rekey(load(a.source), load(a.target), load(a.old_source) if a.old_source else None, a.threshold)
        for k, old in carried:
            print("CARRIED %s" % k + ("" if k == old else "  <- %s" % old))
        for k, old, before, after, text, ratio in review:
            print("REVIEW  %s\n      old English: %s\n      new English: %s\n      old translation: %s"
                  % (k, before, after, text) + ("" if k == old else "\n      (was id %s, similarity %.2f)" % (old, ratio)))
        print("%d carried, %d to review: reuse an old translation only if the meaning did not change" % (len(carried), len(review)))
        if a.out:
            _dump(new, a.out)
    elif a.cmd == "regional":
        kept, dropped = regional(load(a.target), load(a.base), a.lang)
        print("%d rows differ from the base, %d identical rows dropped" % (len(kept), len(dropped)), file=sys.stderr)
        _dump(kept, a.out)
    elif a.cmd == "diff":
        d = diff(load(a.old), load(a.new))
        for k, before, after in d["changed"]:
            print("CHANGED %s\n      old: %s\n      new: %s" % (k, before, after))
        for k, text in d["added"]:
            print("ADDED   %s: %s" % (k, text))
        for k, text in d["removed"]:
            print("REMOVED %s: %s" % (k, text))
        print("%d changed, %d added, %d removed" % (len(d["changed"]), len(d["added"]), len(d["removed"])))
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
