"""Audit translation coverage of the extracted UVR modules.

Usage: py -3.9 tr_audit.py <module.pyc> [<module.pyc> ...]

Prints how many string constants already have a translation, which are
recoverable through a case-insensitive lookup, and which still look like
untranslated UI text.
"""
import json
import marshal
import re
import sys

CJK = re.compile(r'[\u4e00-\u9fff]')
WORDY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,:;!?()\[\]'\-\+/%.&]*$")
SKIP_EXT = re.compile(r'\.(py|pyc|dll|exe|json|onnx|pth|ckpt|ckptc|yaml|th|txt|log)$')
SKIP_SUB = re.compile(r'(^[#\d\s.,:%$+-]+$)')
# words that mark a string as logic/protocol rather than a UI label
SKIP_WORDS = (
    'utf-8', 'utf8', 'ascii', 'application/', 'text/', 'image/', 'audio/',
    'http', 'www.', '.com', 'numpy', 'torch', 'onnxruntime', 'cpu', 'cuda',
)


def load_code(path):
    """Load a code object from a .pyc, tolerating the extractor's 16-byte header."""
    with open(path, 'rb') as f:
        data = f.read()
    try:
        return marshal.loads(data)
    except Exception:
        return marshal.loads(data[16:])


def string_constants(code, out=None):
    if out is None:
        out = []
    for const in code.co_consts:
        if hasattr(const, 'co_code'):
            string_constants(const, out)
        elif isinstance(const, str):
            out.append(const)
    return out


def load_translations():
    zh = {}
    for name in ('tr_labels1.json', 'tr_labels2.json'):
        with open(name, encoding='utf-8') as f:
            zh.update(json.load(f))
    return zh


def case_insensitive_index(zh):
    """Upper-cased lookup with collision reporting."""
    index, collisions = {}, {}
    for key, value in zh.items():
        upper = key.upper()
        if upper in index and index[upper] != value:
            collisions[upper] = (index[upper], value)
        index[upper] = value
    return index, collisions


def ci_candidate(text):
    """Guard rails for case-insensitive fallback matching."""
    return len(text) >= 4 and re.search(r'[A-Za-z]', text) is not None


def looks_like_ui(text):
    if not (3 <= len(text) <= 90) or CJK.search(text):
        return False
    if not re.search(r'[A-Za-z]', text) or SKIP_SUB.match(text):
        return False
    if SKIP_EXT.search(text):
        return False
    if '/' in text or '\\' in text:
        return False
    if text.count('\n') > 1:
        return False
    low = text.lower()
    if any(w in low for w in SKIP_WORDS):
        return False
    return WORDY.match(text) is not None


def main():
    zh = load_translations()
    index, collisions = case_insensitive_index(zh)
    print(f'translation keys: {len(zh)}  case-insensitive collisions: {len(collisions)}')
    for key, pair in list(collisions.items())[:20]:
        print(f'   COLLISION {key!r}: {pair}')

    for path in sys.argv[1:]:
        strings = sorted(set(string_constants(load_code(path))))
        hits = [s for s in strings if s in zh]
        miss = [s for s in strings if s not in zh]
        ci_hits = [s for s in miss if ci_candidate(s) and s.upper() in index]
        bad_values = [s for s in hits if not CJK.search(str(zh[s])) and zh[s] != s]
        caps = [s for s in strings if len(s) >= 4 and s.upper() == s and re.search(r'[A-Z]', s)]
        caps_miss = [s for s in caps if s not in zh]

        print('=' * 72)
        print(path)
        print(f'  unique string constants      : {len(strings)}')
        print(f'  already translated (exact)   : {len(hits)}')
        print(f'  recoverable case-insensitively: {len(ci_hits)}')
        print(f'  ALL-CAPS still untranslated  : {len(caps_miss)}')
        print(f'  translated values not Chinese: {len(bad_values)}')
        for s in ci_hits:
            print(f'    CI   {s!r} -> {index[s.upper()]!r}')
        for s in caps_miss:
            print(f'    CAPS {s!r}')
        ui_miss = [s for s in miss if looks_like_ui(s)]
        print(f'  untranslated UI-looking strings: {len(ui_miss)}')
        for s in ui_miss:
            print(f'    MISS {s!r}')


if __name__ == '__main__':
    main()
