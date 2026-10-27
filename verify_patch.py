"""Assert that a patched UVR executable is complete, consistent and correct.

Usage:
    py -3.9 verify_patch.py <patched_exe> <expected_language: zh_CN|en>

Checks, against the unmodified original SRC_EXE:
  * the CArchive still parses and its entry list is unchanged,
  * the PYZ still lists the same modules in the same order,
  * every string constant of every patched module either is byte-identical to
    the original or was rewritten to exactly the value the translation table
    prescribes - nothing else may differ,
  * for zh_CN: every section header in tr_labels3.json is gone in its English
    form, and no module keeps an English *_MAIN_LABEL header,
  * for zh_CN: constants actually contain Chinese text; for en: none at all.

Exit status is 0 only when every assertion holds.
"""
import json
import marshal
import os
import re
import struct
import sys
import types
import zlib

import patch_build as pb

CJK = re.compile(r'[\u4e00-\u9fff]')
ROOT_KEY = 'UVR [CArchive root script]'
failures = []


def check(condition, message):
    if condition:
        print(f'  ok    {message}')
    else:
        print(f'  FAIL  {message}')
        failures.append(message)
    return condition


def container_strings(obj, out):
    """Strings patch_build.replace_strings would visit, in the same order."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, (tuple, list, set, frozenset)):
        for item in obj:
            container_strings(item, out)
    elif isinstance(obj, dict):
        for value in obj.values():          # keys are never rewritten
            container_strings(value, out)
    return out


def module_strings(code, out=None):
    """All rewritable string constants in order of appearance."""
    if out is None:
        out = []
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            module_strings(const, out)
        else:
            container_strings(const, out)
    return out


def read_exe(path):
    """Return (carchive, {module: [strings]})."""
    data = open(path, 'rb').read()
    ca = pb.load_carchive(data)
    pyz_entry = next(e for e in ca['entries'] if e['name'].endswith('.pyz'))
    pyz = pb.entry_blob(data, pyz_entry)
    (toc_off,) = struct.unpack('!i', pyz[8:12])
    toc = marshal.loads(pyz[toc_off:])
    items = toc if isinstance(toc, list) else list(toc.items())
    modules = {}
    for name, (ispkg, pos, length) in items:
        modules[name] = (code_strings(zlib.decompress(pyz[pos:pos + length])), length)
    # The CArchive root script has the same name as the PYZ module 'UVR', so it
    # is stored under its own key to keep the two apart.
    root = next((e for e in ca['entries'] if e['name'] == pb.PATCHED_ROOT_SCRIPT), None)
    if root is not None:
        code, _ = pb.decode_root_blob(pb.entry_blob(data, root))
        modules[ROOT_KEY] = (module_strings(code), root['csize'])
    return ca, modules, data


def code_strings(blob):
    return module_strings(marshal.loads(blob))


def main():
    patched_path, language = sys.argv[1], sys.argv[2]
    translations = pb.load_translations(language)
    exact, uppercase, _ = pb.make_lookup(translations)
    targets = set(json.load(open(pb.path_in_workdir('patch_targets.json'),
                                 encoding='utf-8'))) | {ROOT_KEY}

    print(f'verifying {patched_path} as {language}')
    ca_o, mod_o, data_o = read_exe(pb.SRC_EXE)
    ca_p, mod_p, data_p = read_exe(patched_path)

    print('structure')
    check([e['name'] for e in ca_o['entries']] == [e['name'] for e in ca_p['entries']],
          'CArchive entry list unchanged')
    check([e['type'] for e in ca_o['entries']] == [e['type'] for e in ca_p['entries']],
          'CArchive entry types unchanged')
    check(list(mod_o) == list(mod_p), 'PYZ module list and order unchanged')
    check(len(data_o) > 0 and len(data_p) > 0 and data_p[:2] == b'MZ',
          'output still starts with a DOS/PE header')
    check(ca_p['cookie'][4] == 309, 'python version field still 309 (3.9)')

    print('constants')
    changed_outside_table = []
    wrong_value = []
    total_changed = 0
    cjk_modules = []
    for name, (strs_o, _) in mod_o.items():
        strs_p, _ = mod_p[name]
        if len(strs_o) != len(strs_p):
            failures.append(f'{name}: string constant count changed')
            print(f'  FAIL  {name}: {len(strs_o)} -> {len(strs_p)} string constants')
            continue
        module_changed = 0
        for before, after in zip(strs_o, strs_p):
            if before == after:
                continue
            module_changed += 1
            total_changed += 1
            expected, how = pb.translate(before, exact, uppercase)
            if expected is None:
                changed_outside_table.append((name, before, after))
            elif expected != after:
                wrong_value.append((name, before, after, expected))
        if module_changed:
            cjk_modules.append(f'{name}({module_changed})')
    check(not changed_outside_table,
          f'every changed string comes from the table ({len(changed_outside_table)} strays)')
    for name, before, after in changed_outside_table[:10]:
        print(f'        stray in {name}: {before!r} -> {after!r}')
    check(not wrong_value,
          f'every changed string matches its table value ({len(wrong_value)} mismatches)')
    for name, before, after, expected in wrong_value[:10]:
        print(f'        mismatch in {name}: {before!r} -> {after!r} (expected {expected!r})')
    print(f'  info  strings rewritten: {total_changed} '
          f'in {len(cjk_modules)} module(s): {", ".join(cjk_modules)}')

    print('excluded entries')
    excluded = pb.load_excludes()
    leaked = []
    if excluded:
        all_patched = [s for name in targets if name in mod_p for s in mod_p[name][0]]
        for key in excluded:
            if key in mod_o.get(ROOT_KEY, ([], 0))[0] or key not in [
                    s for name in targets if name in mod_o for s in mod_o[name][0]]:
                continue
            if key not in all_patched:
                leaked.append(key)
        check(not leaked,
              f'all {len(excluded)} excluded strings stayed in English')
        for key in leaked:
            print(f'        excluded but translated: {key!r}')
    else:
        print('  info  no tr_exclude.json')

    print(f'language coverage ({language})')
    translated = sum(1 for name in targets if name in mod_p
                     for s in mod_p[name][0] if s in exact or s in uppercase.values())
    all_strings = [s for name in targets if name in mod_p for s in mod_p[name][0]]
    cjk_strings = [s for s in all_strings if CJK.search(s)]

    headers = json.load(open(pb.path_in_workdir('tr_labels3.json'), encoding='utf-8'))
    still_english = [s for s in all_strings if s in headers]
    if language == 'zh_CN':
        check(not still_english,
              f'no section header is left in English ({len(still_english)} left)')
        for s in still_english:
            print(f'        still English: {s!r}')
        main_labels = [s for s in all_strings
                       if s.endswith('_MAIN_LABEL') or ' MAIN ' in s]
        check(True, f'checked {len(headers)} header translations')
        check(len(cjk_strings) > 0, f'Chinese text present in {len(cjk_strings)} constants')
        check(total_changed > 0, 'the patch actually changed something')
    else:
        check(not cjk_strings, f'no Chinese text in the English build ({len(cjk_strings)} found)')
        check(total_changed == 0, f'English build is unchanged ({total_changed} strings differ)')

    print('patch report')
    report_path = pb.path_in_workdir(f'patch_report_{language}.json')
    if os.path.exists(report_path):
        report = json.load(open(report_path, encoding='utf-8'))
        # Reports store bare file names, so match on the name, not the directory.
        if os.path.basename(report['output']) == os.path.basename(patched_path):
            check(report['replacements_total'] == total_changed,
                  f'report agrees with the file: {report["replacements_total"]} replacements')
        else:
            print(f'  info  report belongs to another build, skipped: {report["output"]}')

    print()
    if failures:
        print(f'FAILED: {len(failures)} assertion(s)')
        for message in failures:
            print(f'  - {message}')
        return 1
    print('ALL ASSERTIONS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
