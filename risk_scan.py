"""Classify string constants by how they are used, to tell UI text from logic values.

Usage: py -3.9 risk_scan.py <module.pyc> [<module.pyc> ...]

For every string constant found in the module (including nested code objects)
it reports whether the string is used as a dict key, a subscript key, a
comparison operand, or a call argument. Strings used as keys/operands are
logic values: translating them is unsafe.
"""
import dis
import json
import marshal
import sys
from collections import defaultdict

PRECEDERS = {'LOAD_CONST', 'LOAD_NAME', 'LOAD_GLOBAL', 'LOAD_FAST', 'LOAD_ATTR',
             'LOAD_METHOD', 'LOAD_DEREF', 'EXTENDED_ARG'}
LOGIC_CALLS = ('encode', 'decode', 'open', 'get', 'join', 'format', 'startswith',
               'endswith', 'lower', 'upper', 'strip', 'replace', 'split',
               'import_module', 'find_spec', '__import__', 'exec', 'eval',
               'getattr', 'setattr', 'hasattr', 'loads', 'dumps')


def load_code(path):
    with open(path, 'rb') as f:
        data = f.read()
    try:
        return marshal.loads(data)
    except Exception:
        return marshal.loads(data[16:])


def walk(code, name='<module>', out=None):
    if out is None:
        out = []
    out.append((name, code))
    for const in code.co_consts:
        if hasattr(const, 'co_code'):
            walk(const, const.co_name, out)
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
    uses = defaultdict(set)
    for scope, code in walk(load_code(path)):
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
            if nxtop in ('BINARY_SUBSCR', 'DELETE_SUBSCR') or \
               (nxtop == 'LOAD_CONST' and nxt < len(ins) and
                    ins[next_real(ins, nxt)].opname in ('BINARY_SUBSCR', 'STORE_SUBSCR')):
                uses[s].add('subscript-key')
            if nxtop == 'COMPARE_OP' or x.opname == 'COMPARE_OP':
                uses[s].add('compared')
            if nxtop == 'CONTAINS_OP':
                uses[s].add('contains')
            if nxtop == 'BUILD_CONST_KEY_MAP':
                uses[s].add('dict-key')
            if nxtop == 'CALL_FUNCTION' and i >= 1:
                uses[s].add('call-arg')
            if nxtop == 'LOAD_ATTR':
                attr = ins[nxt].argval
                uses[s].add(f'attr:{attr}')
                if attr in LOGIC_CALLS:
                    uses[s].add(f'logic:{attr}')
            if nxtop in ('STORE_ATTR', 'STORE_NAME', 'STORE_FAST', 'STORE_GLOBAL'):
                uses[s].add('stored')
    return uses


def main():
    zh = {}
    for name in ('tr_labels1.json', 'tr_labels2.json'):
        with open(name, encoding='utf-8') as f:
            zh.update(json.load(f))
    merged = defaultdict(set)
    for path in sys.argv[1:]:
        for s, kinds in analyse(path).items():
            merged[s] |= kinds

    risky = {s: sorted(k) for s, k in merged.items()
             if k & {'dict-key', 'subscript-key', 'compared', 'contains'} or
             any(x.startswith('logic:') for x in k)}
    print(f'strings seen: {len(merged)}   logic-risky: {len(risky)}')
    with open('risk_scan.json', 'w', encoding='utf-8') as f:
        json.dump({'all': {s: sorted(k) for s, k in merged.items()},
                   'risky': risky}, f, ensure_ascii=False, indent=1)
    for s in sorted(risky):
        mark = 'TRANSLATED' if s in zh else 'untranslated'
        print(f'   {mark:12} {s!r:60} {risky[s]}')


if __name__ == '__main__':
    main()
