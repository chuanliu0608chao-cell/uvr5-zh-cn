"""Dump bytecode around every use of a given constant name.

Usage: py -3.9 dump_name_use.py <module.pyc> <NAME> [<NAME> ...]
"""
import dis
import marshal
import sys


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


import opcode

COND_JUMPS = {'POP_JUMP_IF_TRUE', 'POP_JUMP_IF_FALSE', 'POP_JUMP_FORWARD_IF_TRUE',
              'POP_JUMP_FORWARD_IF_FALSE', 'JUMP_IF_FALSE_OR_POP', 'POP_JUMP_IF_NONE',
              'POP_JUMP_IF_NOT_NONE'}


def main():
    path = sys.argv[1]
    targets = set(sys.argv[2:])
    for code in walk(load_code(path)):
        for target in targets:
            hits = [i for i, x in enumerate(dis.get_instructions(code))
                    if x.opname in ('LOAD_ATTR', 'LOAD_NAME', 'LOAD_GLOBAL')
                    and x.argval == target]
            if not hits:
                continue
            ins = list(dis.get_instructions(code))
            print(f'==== {target}  in {code.co_name}  ({len(hits)} use(s))')
            for h in hits:
                lo, hi = max(0, h - 14), min(len(ins), h + 10)
                print('   ----')
                for j in range(lo, hi):
                    mark = '>>' if j == h else '  '
                    x = ins[j]
                    print(f'   {mark} {j:5} {x.opname:26} {x.argval!r}')
            print()


if __name__ == '__main__':
    main()
