"""Patch the string constants inside UVR's PyInstaller archive and rebuild the exe.

Usage:
    py -3.9 patch_build.py <out_exe> [language]

    language: zh_CN (Chinese, default) or en (English control build)
    With no language argument, language.json is consulted.

The original executable (SRC_EXE) is only ever read; the patched copy is written
to <out_exe> through a temporary file and renamed into place.

Translation tables map an English string to its replacement text:
    tr_labels1.json, tr_labels2.json, tr_labels3.json   (Chinese)
    tr_labels_en.json                                   (identity map, English)

A string that has no entry is left untouched. When a string is written entirely
in capitals - sections such as "CHOOSE PROCESS METHOD" are stored that way - the
table is consulted a second time in upper case, so an entry keyed as
"Choose Process Method" still matches. That fallback is skipped for identity
entries, which is why the English build keeps its original casing.

patch_targets.json lists the PYZ modules whose constants are rewritten.
"""
import json
import marshal
import os
import struct
import sys
import types
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
MAGIC = b'MEI\x0c\x0b\x0a\x0b\x0e'
COOKIE_SIZE = 88
SRC_EXE = 'E:/UVR5/UVR.exe'
PATCHED_ROOT_SCRIPT = 'UVR'          # CArchive root script entry name
TRANSLATION_FILES = ('tr_labels1.json', 'tr_labels2.json', 'tr_labels3.json')
ENGLISH_TABLE = 'tr_labels_en.json'
EXCLUDE_FILE = 'tr_exclude.json'      # entries that must stay in English (paths)
CI_MIN_LENGTH = 4                    # ignore very short all-caps strings
ZLIB_LEVEL = 9                       # same level PyInstaller uses


def path_in_workdir(name):
    return os.path.join(HERE, name)


# ---------------------------------------------------------------- CArchive ----


def load_carchive(data):
    """Parse the PyInstaller CArchive footer and table of contents."""
    cookie_pos = data.rfind(MAGIC)
    if cookie_pos == -1:
        raise SystemExit('PyInstaller cookie not found in %s' % SRC_EXE)
    magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack(
        '!8sIIii64s', data[cookie_pos:cookie_pos + COOKIE_SIZE])
    overlay_pos = cookie_pos + COOKIE_SIZE - pkg_len
    entries = []
    pos = overlay_pos + toc_off
    end = pos + toc_len
    while pos < end:
        (entry_size,) = struct.unpack('!i', data[pos:pos + 4])
        body = data[pos + 4:pos + entry_size]
        entry_pos, csize, usize, cflag, typ = struct.unpack('!IIIBc', body[:14])
        raw_name = body[14:]
        entries.append({
            'pos': overlay_pos + entry_pos,
            'csize': csize,
            'usize': usize,
            'flag': cflag,
            'type': typ,
            'raw_name': raw_name,
            'name': raw_name.rstrip(b'\x00').decode('utf-8'),
        })
        pos += entry_size
    return {
        'overlay_pos': overlay_pos,
        'cookie': (magic, pkg_len, toc_off, toc_len, pyver, pylib),
        'entries': entries,
        'tail': data[cookie_pos + COOKIE_SIZE:],
    }


def entry_blob(data, entry):
    blob = data[entry['pos']:entry['pos'] + entry['csize']]
    return zlib.decompress(blob) if entry['flag'] == 1 else blob


def compress(blob, flag):
    return zlib.compress(blob, ZLIB_LEVEL) if flag == 1 else blob


def rebuild_carchive(data, ca, replacements):
    """Lay the archive out again with the patched blobs.

    replacements maps a CArchive entry name to its new uncompressed content.
    Every entry keeps its position relative to the start of the overlay, and the
    cookie is written last so the bootloader finds it where it expects to.
    """
    overlay = bytearray()
    records = []
    for entry in ca['entries']:
        if entry['name'] in replacements:
            raw = replacements[entry['name']]
            blob = compress(raw, entry['flag'])
            usize = len(raw)
        else:
            blob = data[entry['pos']:entry['pos'] + entry['csize']]
            usize = entry['usize']
        records.append((len(overlay), len(blob), usize, entry['flag'],
                        entry['type'], entry['raw_name']))
        overlay += blob

    toc = bytearray()
    for pos, csize, usize, flag, typ, raw_name in records:
        body = struct.pack('!IIIBc', pos, csize, usize, flag, typ) + raw_name
        toc += struct.pack('!i', len(body) + 4) + body

    prefix = data[:ca['overlay_pos']]
    cookie = struct.pack('!8sIIii64s', MAGIC,
                         len(prefix) + len(overlay) + len(toc) + COOKIE_SIZE - len(prefix),
                         len(overlay), len(toc), ca['cookie'][4], ca['cookie'][5])
    return bytes(prefix) + bytes(overlay) + bytes(toc) + cookie + ca['tail']


# ---------------------------------------------------------- string patching ----


def load_excludes():
    """Entries detection found to be path components or identifiers."""
    path = path_in_workdir(EXCLUDE_FILE)
    if not os.path.exists(path):
        print(f'note: no {EXCLUDE_FILE}, translating everything in the tables')
        return {}
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def load_translation_tables():
    tables = {}
    for name in TRANSLATION_FILES:
        with open(path_in_workdir(name), encoding='utf-8') as handle:
            tables.update(json.load(handle))
    excluded = load_excludes()
    if excluded:
        print(f'{EXCLUDE_FILE}: keeping {len(excluded)} string(s) in English, e.g. '
              + ', '.join(repr(k) for k in sorted(excluded)[:5]))
        for key in excluded:
            tables.pop(key, None)
    return tables


def load_english_table():
    with open(path_in_workdir(ENGLISH_TABLE), encoding='utf-8') as handle:
        return json.load(handle)


def load_translations(language):
    if language == 'zh_CN':
        return load_translation_tables()
    if language == 'en':
        return load_english_table()
    raise SystemExit('unknown language %r' % language)


def make_lookup(translations):
    """Return (exact map, upper-case map) and report colliding keys."""
    uppercase, collisions = {}, {}
    for key, value in translations.items():
        if value == key:
            continue                       # identity entry: would only re-case
        if key.upper() in uppercase and uppercase[key.upper()] != value:
            collisions[key.upper()] = (uppercase[key.upper()], value)
        uppercase[key.upper()] = value
    return dict(translations), uppercase, collisions


def is_all_caps(text):
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def translate(text, exact, uppercase):
    if text in exact:
        return exact[text], 'exact'
    if len(text) >= CI_MIN_LENGTH and is_all_caps(text):
        hit = uppercase.get(text.upper())
        if hit is not None:
            return hit, 'caps'
    return None, None


def replace_strings(obj, lookup, stats, applied):
    exact, uppercase = lookup
    if isinstance(obj, str):
        new, how = translate(obj, exact, uppercase)
        if new is not None and new != obj:
            stats[how] += 1
            applied.append((obj, new))
            return new
        return obj
    if isinstance(obj, tuple):
        return tuple(replace_strings(x, lookup, stats, applied) for x in obj)
    if isinstance(obj, list):
        return [replace_strings(x, lookup, stats, applied) for x in obj]
    if isinstance(obj, (set, frozenset)):
        return type(obj)(replace_strings(x, lookup, stats, applied) for x in obj)
    if isinstance(obj, dict):
        return {k: replace_strings(v, lookup, stats, applied) for k, v in obj.items()}
    return obj


def patch_code(code, lookup, stats, applied):
    new_consts = []
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            new_consts.append(patch_code(const, lookup, stats, applied))
        else:
            new_consts.append(replace_strings(const, lookup, stats, applied))
    if tuple(new_consts) == code.co_consts:
        return code
    return code.replace(co_consts=tuple(new_consts))


def decode_root_blob(blob):
    """Unmarshal a root script blob, tolerating an old-style pyc header."""
    try:
        return marshal.loads(blob), b''
    except (ValueError, EOFError):
        if len(blob) > 16 and blob[2:4] == b'\r\n':
            return marshal.loads(blob[16:]), blob[:16]
        raise


# ------------------------------------------------------------------- build ----


def detect_runtime_language():
    lang_file = path_in_workdir('language.json')
    if not os.path.exists(lang_file):
        return 'zh_CN'
    try:
        with open(lang_file, encoding='utf-8') as handle:
            language = json.load(handle).get('language', 'zh_CN')
    except (ValueError, OSError):
        return 'zh_CN'
    return language if language in ('zh_CN', 'en') else 'zh_CN'


def build(out_exe, language):
    translations = load_translations(language)
    exact, uppercase, collisions = make_lookup(translations)
    lookup = (exact, uppercase)
    print(f'language: {language}   table entries: {len(translations)}   '
          f'case-insensitive keys: {len(uppercase)}')
    for key, pair in collisions.items():
        print(f'   WARNING colliding keys for {key!r}: {pair}')

    stats = {'exact': 0, 'caps': 0}
    applied = []
    data = open(SRC_EXE, 'rb').read()
    ca = load_carchive(data)
    print(f'source: {SRC_EXE}  {len(data)} bytes  '
          f'{len(ca["entries"])} CArchive entries')

    pyz_entry = next(e for e in ca['entries'] if e['name'].endswith('.pyz'))
    pyz = entry_blob(data, pyz_entry)
    if pyz[:4] != b'PYZ\x00':
        raise SystemExit('unexpected PYZ header %r' % pyz[:4])
    pymagic = pyz[4:8]
    (toc_off,) = struct.unpack('!i', pyz[8:12])
    pyz_toc = marshal.loads(pyz[toc_off:])
    toc_is_list = isinstance(pyz_toc, list)
    toc_items = pyz_toc if toc_is_list else list(pyz_toc.items())
    print(f'PYZ: {len(toc_items)} modules, toc stored as '
          f'{"list" if toc_is_list else "dict"}')

    targets = set(json.load(open(path_in_workdir('patch_targets.json'),
                                encoding='utf-8')))
    patched = {}
    per_module = []
    for name, (ispkg, pos, length) in toc_items:
        if name not in targets:
            continue
        before = stats['exact'] + stats['caps']
        code = marshal.loads(zlib.decompress(pyz[pos:pos + length]))
        code = patch_code(code, lookup, stats, applied)
        patched[name] = zlib.compress(marshal.dumps(code), ZLIB_LEVEL)
        per_module.append((name, stats['exact'] + stats['caps'] - before))
    print('patched PYZ modules: ' + ', '.join(f'{n} ({c})' for n, c in per_module))

    # Keep the original header up to the first module body: this build's PYZ
    # header is 12 bytes followed by 5 padding bytes, and module offsets start
    # after that padding. Re-packing from offset 8 would shift every body onto
    # the padding and corrupt the first entry.
    data_start = min(pos for _name, (_ispkg, pos, _length) in toc_items)
    out = bytearray(pyz[:data_start])
    new_toc = []
    for name, (ispkg, pos, length) in toc_items:
        blob = patched.get(name, pyz[pos:pos + length])
        new_toc.append((name, (ispkg, len(out), len(blob))))
        out += blob
    toc_offset = len(out)
    out[8:12] = struct.pack('!i', toc_offset)
    out += marshal.dumps(new_toc if toc_is_list else dict(new_toc))
    new_pyz = bytes(out)
    print(f'PYZ rebuilt: {len(pyz)} -> {len(new_pyz)} bytes')

    root = next((e for e in ca['entries'] if e['name'] == PATCHED_ROOT_SCRIPT), None)
    replacements = {pyz_entry['name']: new_pyz}
    if root is not None:
        code, header = decode_root_blob(entry_blob(data, root))
        before = stats['exact'] + stats['caps']
        code = patch_code(code, lookup, stats, applied)
        replacements[root['name']] = header + marshal.dumps(code)
        print(f'root script {root["name"]}: '
              f'{stats["exact"] + stats["caps"] - before} replacements')
    else:
        print(f'WARNING: root script entry {PATCHED_ROOT_SCRIPT!r} not found')

    rebuilt = rebuild_carchive(data, ca, replacements)
    tmp = out_exe + '.tmp'
    with open(tmp, 'wb') as handle:
        handle.write(rebuilt)
    os.replace(tmp, out_exe)

    check = load_carchive(rebuilt)
    names_before = [e['name'] for e in ca['entries']]
    names_after = [e['name'] for e in check['entries']]
    if names_before != names_after:
        raise SystemExit('rebuilt archive TOC does not match the original')
    if check['cookie'][4] != ca['cookie'][4]:
        raise SystemExit('rebuilt archive changed the python version field')

    report = {
        'output': os.path.abspath(out_exe),
        'language': language,
        'source': SRC_EXE,
        'replacements_exact': stats['exact'],
        'replacements_case_insensitive': stats['caps'],
        'replacements_total': stats['exact'] + stats['caps'],
        'per_module': [{'module': n, 'replacements': c} for n, c in per_module],
        'source_size': len(data),
        'output_size': len(rebuilt),
        'collisions': {k: list(v) for k, v in collisions.items()},
    }
    with open(path_in_workdir('patch_report_%s.json' % language), 'w',
              encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)

    print(f'replacements: {stats["exact"]} exact + {stats["caps"]} all-caps '
          f'= {stats["exact"] + stats["caps"]}')
    print(f'wrote {out_exe} ({len(rebuilt)} bytes)')
    return report


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out_exe = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else detect_runtime_language()
    if language not in ('zh_CN', 'en'):
        raise SystemExit('language must be zh_CN or en, got %r' % language)
    build(out_exe, language)
    return 0


if __name__ == '__main__':
    sys.exit(main())
