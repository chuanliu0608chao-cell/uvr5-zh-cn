"""Build the list of untranslated strings still safe to translate.

A string qualifies when, across the analysed modules, it is
  * not already translated,
  * never used as a dict/subscript key, comparison or containment operand,
  * not a docstring, and
  * shaped like user-facing text.
Writes candidates.json and prints them with the reason for inclusion.
"""
import dis
import json
import marshal
import re
import sys
from collections import defaultdict

RISKY_KINDS = {'dict-key', 'subscript-key', 'compared', 'contains'}
CJK = re.compile(r'[\u4e00-\u9fff]')
WORDY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,:;!?()\[\]'\-\+/%.&«»]*$")
# brand, model, format and credit names that must stay as-is
KEEP = {
    'MDX-Net', 'Matchering', 'WAV', 'FLAC', 'MP3', 'FFmpeg', 'Demucs', 'VR',
    'AudioTools', 'MVSep', 'Ensembler', 'MainWindow', 'Listbox',
    'Century Gothic', 'GOTHIC.ttf', 'GUI-Icon.ico', 'GUI-Icon.png',
    'Adefossez & Demucs', 'Bas Curtiz', 'Kuielab & Woosung Choi', 'DilanBoskan',
    'Is Linux', 'Doubles', 'FLOAT', 'DOUBLE', 'UTF-8', 'WM_DELETE_WINDOW',
    'Montserrat', 'centurygothic', 'fonts', 'Rubber Band Library',
    'Tsurumeso', 'X-Minus AI', '320k', 'data.pkl', 'sample.wav',
    'ThreadSafeConsole.clear', 'ThreadSafeConsole.write',
    'ToolTip.hidetip', 'ToolTip.showtip', 'TButton', 'TCheckbutton', 'TCombobox',
    'TEntry', 'TLabel', 'TMenubutton', 'TRadiobutton', 'xdg-open', 'arrow',
    'black', 'bold', 'both', 'break', 'center', 'command', 'cpu', 'current',
    'dark', 'disabled', 'dotbox', 'drop', 'end', 'exit', 'file', 'font',
    'frozen', 'hand2', 'highlight', 'horizontal', 'img', 'insert', 'key',
    'left', 'mirroring', 'nsew', 'open', 'padx', 'pady', 'ridge', 'sel',
    'sel.first', 'sel.last', 'text', 'textvariable', 'tmp', 'true', 'underline',
    'white', 'wraplength', 'write', 'instrum', 'changemodeldefault',
    'deletesetting', 'demucsmdxdownload', 'demucspre', 'gpudevice',
    'mdxdownload', 'menuchoose', 'modelparams', 'models', 'name', 'normal',
    'savedensembles', 'savedsettings', 'setvocaldeverb', 'setvocalsplit',
    'vrdownload', 'missing', 'present', 'other',
    'ComboBoxMenu', 'ComboBoxEditableMenu', 'MainWindow.restart',
    'ComboBoxEditableMenu.focusin', 'ComboBoxMenu.focusin', 'ListboxBatchFrame',
    '32-bit Float', '64-bit Float', 'arm', 'dual', 'file1', 'file2',
    'privateuseone', 'readonly', 'fourstem', 'kara check', 'ensemble check',
}


def load_code(path):
    with open(path, 'rb') as f:
        data = f.read()
    try:
        return marshal.loads(data)
    except Exception:
        return marshal.loads(data[16:])


def walk(code, out=None):
    if out is None:
        out = []
    out.append(code)
    for const in code.co_consts:
        if hasattr(const, 'co_code'):
            walk(const, out)
    return out


def prev_real(ins, i):
    j = i - 1
    while j >= 0 and ins[j].opname == 'EXTENDED_ARG':
        j -= 1
    return j


def next_real(ins, i):
    j = i + 1
    while j < len(ins) and ins[j].opname == 'EXTENDED_ARG':
        j += 1
    return j


def analyse(path):
    """Return (risky_strings, docstrings, all_strings)."""
    risky, docstrings, strings = set(), set(), set()
    for code in walk(load_code(path)):
        if code.co_consts and isinstance(code.co_consts[0], str):
            docstrings.add(code.co_consts[0])
        for const in code.co_consts:
            if isinstance(const, str):
                strings.add(const)
        try:
            ins = list(dis.get_instructions(code))
        except Exception:
            continue
        for i, x in enumerate(ins):
            if x.opname != 'LOAD_CONST' or not isinstance(x.argval, str):
                continue
            s = x.argval
            nxt = next_real(ins, i)
            nxtop = ins[nxt].opname if nxt < len(ins) else None
            if nxtop in ('BINARY_SUBSCR', 'DELETE_SUBSCR', 'COMPARE_OP', 'CONTAINS_OP',
                         'BUILD_CONST_KEY_MAP'):
                risky.add(s)
            if nxtop == 'LOAD_ATTR' and ins[nxt].argval in (
                    'encode', 'decode', 'get', 'join', 'format', 'startswith',
                    'endswith', 'import_module', 'find_spec', 'loads', 'insert'):
                risky.add(s)
        # members of a tuple/list that is compared or used with 'in'
        for i, x in enumerate(ins):
            if x.opname != 'LOAD_CONST' or not isinstance(x.argval, (tuple, list)):
                continue
            nxtop = ins[next_real(ins, i)].opname if next_real(ins, i) < len(ins) else None
            if nxtop in ('COMPARE_OP', 'CONTAINS_OP'):
                for member in x.argval:
                    if isinstance(member, str):
                        risky.add(member)
    return risky, docstrings, strings


def looks_like_ui(text):
    if not (3 <= len(text) <= 90) or CJK.search(text):
        return False
    if not re.search(r'[A-Za-z]', text) or text in KEEP:
        return False
    if text.count('\n') > 1 or '/' in text or '\\' in text:
        return False
    if re.search(r'\.(py|pyc|dll|exe|json|onnx|pth|ckpt|ckptc|yaml|th|txt|ttf|ico|png)$', text):
        return False
    if re.search(r'utf-?8|http|www\.|\.com|numpy|torch|onnx|cuda|numba|ffmpeg', text, re.I):
        return False
    return WORDY.match(text) is not None


def is_all_caps_label(text):
    letters = [c for c in text if c.isalpha()]
    return len(text) >= 4 and letters and all(c.isupper() for c in letters)


def main():
    zh = {}
    for name in ('tr_labels1.json', 'tr_labels2.json'):
        with open(name, encoding='utf-8') as f:
            zh.update(json.load(f))

    risky, docstrings, strings = set(), set(), set()
    for path in sys.argv[1:]:
        r, d, s = analyse(path)
        risky |= r
        docstrings |= d
        strings |= s
    # a string that is a docstring anywhere is a docstring
    risky |= (strings & docstrings)

    candidates = {'caps_labels': [], 'other': []}
    for s in sorted(strings):
        if s in zh or not looks_like_ui(s):
            continue
        if s in risky:
            continue
        (candidates['caps_labels'] if is_all_caps_label(s) else candidates['other']).append(s)

    print(f'analysed strings: {len(strings)}  risky: {len(risky)}  translated: {len(zh)}')
    print(f'ALL-CAPS label candidates: {len(candidates["caps_labels"])}')
    for s in candidates['caps_labels']:
        print(f'   {s!r}')
    print(f'other candidates: {len(candidates["other"])}')
    for s in candidates['other']:
        print(f'   {s!r}')
    with open('candidates_new.json', 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
