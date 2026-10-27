"""Find translation-table entries that must NOT be translated.

Usage: py -3.9 path_risk.py

Three independent signals are combined, because the application builds some of
its paths out of constants that look exactly like display text:

1. literal passed to a path/filesystem call - the constant is loaded directly
   before a call such as os.path.join or os.makedirs (backwards scan);
2. module-level name whose value is used near a path API (indirect use);
3. the value is the name of an existing file or directory in the installation,
   which is ground truth that it is a real path component.

Anything flagged is written to tr_exclude.json; patch_build reads that file and
leaves those strings in their original form.
"""
import dis
import json
import marshal
import os
import re
import sys
from collections import defaultdict

IDENTIFIER = re.compile(r'^[A-Za-z0-9_\-]+$')

INSTALL_DIR = 'E:/UVR5'
BACKWARD = 8          # instructions to look back for the call target
ARG_WINDOW = 12       # instructions to look back over a call's arguments

# calls that consume or produce a filesystem path
PATH_CALLS = {
    'join', 'makedirs', 'mkdir', 'exists', 'isdir', 'isfile', 'dirname',
    'basename', 'abspath', 'normpath', 'realpath', 'listdir', 'glob', 'walk',
    'splitext', 'chdir', 'expanduser', 'startfile', 'remove', 'rmtree',
    'rename', 'copy', 'copyfile', 'move', 'replace', 'open', 'getsize',
    'isdir', 'samefile', 'disk_usage', 'link', 'symlink', 'getcwd',
}


def load_code(path):
    with open(path, 'rb') as handle:
        data = handle.read()
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


def real_prev(ins, index):
    j = index - 1
    while j >= 0 and ins[j].opname == 'EXTENDED_ARG':
        j -= 1
    return j


def container_values(obj, out=None):
    """Every string reachable inside a constant, in traversal order."""
    if out is None:
        out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, (tuple, list, set, frozenset)):
        for item in obj:
            container_values(item, out)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            container_values(key, out)
            container_values(value, out)
    return out


def table():
    merged = {}
    for name in ('tr_labels1.json', 'tr_labels2.json', 'tr_labels3.json'):
        with open(name, encoding='utf-8') as handle:
            merged.update(json.load(handle))
    return merged


def literal_path_args(modules):
    """Strings loaded as an argument to a path call."""
    hits = defaultdict(list)
    for module in modules:
        for code in walk(load_code(module)):
            ins = list(dis.get_instructions(code))
            for i, insn in enumerate(ins):
                if insn.opname != 'LOAD_CONST':
                    continue
                values = container_values(insn.argval) if not isinstance(insn.argval, str) \
                    else [insn.argval]
                if not values:
                    continue
                caller = None
                for j in range(i - 1, max(-1, i - 1 - BACKWARD), -1):
                    op = ins[j].opname
                    if op in ('LOAD_METHOD', 'LOAD_ATTR') and ins[j].argval in PATH_CALLS:
                        caller = ins[j].argval
                        break
                    if op in ('CALL_METHOD', 'CALL_FUNCTION', 'CALL_FUNCTION_KW',
                              'STORE_NAME', 'STORE_ATTR', 'RETURN_VALUE'):
                        break
                if caller:
                    for value in values:
                        hits[value].append(
                            f'{os.path.basename(module)}:{code.co_name}:{caller}')
    return hits


def assignments(module):
    pairs = defaultdict(set)
    for code in walk(load_code(module)):
        ins = list(dis.get_instructions(code))
        for i, insn in enumerate(ins):
            if insn.opname not in ('STORE_NAME', 'STORE_GLOBAL'):
                continue
            j = real_prev(ins, i)
            if j >= 0 and ins[j].opname == 'LOAD_CONST' and isinstance(ins[j].argval, str):
                pairs[ins[j].argval].add(insn.argval)
    return pairs


def name_path_args(modules, names):
    """Names loaded as arguments to a path call.

    Walks backwards from each path call over its argument pushes and stops at
    the previous completed call or store, so a name mentioned in an unrelated
    neighbouring statement is not mistaken for a path component.
    """
    found = defaultdict(list)
    for module in modules:
        for code in walk(load_code(module)):
            ins = list(dis.get_instructions(code))
            for i, insn in enumerate(ins):
                if insn.opname not in ('LOAD_METHOD', 'LOAD_ATTR') or \
                        insn.argval not in PATH_CALLS:
                    continue
                # backward pass over this call's arguments
                for j in range(i - 1, max(-1, i - 1 - ARG_WINDOW), -1):
                    op = ins[j].opname
                    if op in ('CALL_METHOD', 'CALL_FUNCTION', 'CALL_FUNCTION_KW',
                              'STORE_NAME', 'STORE_ATTR', 'STORE_FAST',
                              'RETURN_VALUE', 'POP_TOP'):
                        break
                    if op in ('LOAD_NAME', 'LOAD_GLOBAL') and ins[j].argval in names:
                        found[ins[j].argval].append(
                            f'{os.path.basename(module)}:{code.co_name}:{insn.argval}')
                if i + 1 < len(ins) and ins[i + 1].opname.startswith('CALL'):
                    continue
    return found


def filesystem_names(root=INSTALL_DIR, limit=60000):
    """Basenames of everything inside the installation, with and without suffix."""
    names, seen = set(), 0
    for dirpath, dirnames, filenames in os.walk(root):
        for entry in list(dirnames) + list(filenames):
            seen += 1
            if seen > limit:
                return names
            names.add(entry)
            stem, ext = os.path.splitext(entry)
            if ext:
                names.add(stem)
    return names


def main():
    translations = table()
    modules = ['UVR.exe_extracted/UVR.pyc', 'pyz_out/gui_data/constants.pyc']
    literal = literal_path_args(modules)
    names = assignments('pyz_out/gui_data/constants.pyc')
    name_hits = name_path_args(modules, {n for s in names.values() for n in s})
    on_disk = filesystem_names()

    exclude = {}
    for value, replacement in sorted(translations.items()):
        if value == replacement:
            continue
        reasons = []
        if value in literal:
            reasons.append('path-call argument: ' + '; '.join(sorted(set(literal[value]))[:4]))
        uses = [u for owner in names.get(value, ()) for u in name_hits.get(owner, ())]
        if uses:
            reasons.append('name used near path api: ' + '; '.join(sorted(set(uses))[:4]))
        if value in on_disk:
            reasons.append('matches a file/folder name in the installation')
        if '_' in value and IDENTIFIER.match(value):
            reasons.append('shape of an internal identifier, not display text')
        if reasons:
            exclude[value] = {'translation': replacement, 'reasons': reasons}

    print(f'table entries: {len(translations)}   excluded from translation: {len(exclude)}')
    for value, info in sorted(exclude.items()):
        print(f'   {value!r} -> {info["translation"]!r}')
        for reason in info['reasons']:
            print(f'        {reason}')
    with open('tr_exclude.json', 'w', encoding='utf-8') as handle:
        json.dump(exclude, handle, ensure_ascii=False, indent=1)
    print('wrote tr_exclude.json')


if __name__ == '__main__':
    sys.exit(main())
