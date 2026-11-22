#!/usr/bin/env python3
"""Out-of-APK public library type ABI evidence capture and comparison (Phase 2a).

Stores type ABI evidence outside APK archives, bound to the final stripped
ELF SHA-256, source package metadata, and tool version.

Supports two verification backends:
  1. libabigail (abidw / abidiff) when installed, checking all exit status bits
     (ABIDIFF_ERROR=1, ABIDIFF_USAGE_ERROR=2, ABIDIFF_ABI_CHANGE=4,
     ABIDIFF_ABI_INCOMPATIBLE_CHANGE=8) in addition to DWARF symbol coverage.
  2. Native DWARF type-signature & struct-layout comparison via pyelftools,
     verifying exported function parameter/return types and reachable
     struct/union/enum sizes and member offsets directly from .debug_info.

Never treats missing DWARF or exit-code-0 without symbol coverage as proof of
ABI compatibility: insufficient coverage always returns 'insufficient_coverage'
so the caller falls back to review_before_allocate.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from elftools.common.exceptions import ELFError
from elftools.elf.dynamic import DynamicSegment
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

SCHEMA_VERSION = 1

ABIDIFF_OK = 0
ABIDIFF_ERROR = 1
ABIDIFF_USAGE_ERROR = 2
ABIDIFF_ABI_CHANGE = 4
ABIDIFF_ABI_INCOMPATIBLE_CHANGE = 8


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False,
                                     prefix='.' + path.name + '.tmp-') as stream:
        tmp = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def detect_libabigail():
    """Return dict with abidw/abidiff paths and pinned version, or None if absent."""
    abidw = shutil.which('abidw')
    abidiff = shutil.which('abidiff')
    if not (abidw and abidiff):
        return None
    try:
        out = subprocess.check_output([abidiff, '--version'], text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return {'abidw': abidw, 'abidiff': abidiff, 'version': out}


def inspect_elf_identity(path):
    """Extract machine, SONAME, ordered DT_NEEDED, and exported dynamic symbol names."""
    data = Path(path).read_bytes()
    ef = ELFFile(io.BytesIO(data))
    info = {
        'sha256': hashlib.sha256(data).hexdigest(),
        'e_machine': str(ef.header['e_machine']),
        'ei_class': str(ef.header['e_ident']['EI_CLASS']),
        'ei_data': str(ef.header['e_ident']['EI_DATA']),
        'dt_soname': None,
        'dt_needed': [],
        'exported_symbols': [],
        'has_dwarf': ef.get_section_by_name('.debug_info') is not None,
    }
    for seg in ef.iter_segments():
        if isinstance(seg, DynamicSegment):
            for tag in seg.iter_tags():
                if tag.entry.d_tag == 'DT_SONAME':
                    info['dt_soname'] = tag.soname
                elif tag.entry.d_tag == 'DT_NEEDED':
                    info['dt_needed'].append(tag.needed)
    exported = set()
    for sec in ef.iter_sections():
        if isinstance(sec, SymbolTableSection) and sec.name == '.dynsym':
            for sym in sec.iter_symbols():
                if not sym.name:
                    continue
                if (sym['st_shndx'] != 'SHN_UNDEF'
                        and str(sym['st_info']['bind']) != 'STB_LOCAL'
                        and str(sym['st_other']['visibility']) in ('STV_DEFAULT', 'STV_PROTECTED')):
                    exported.add(sym.name)
    info['exported_symbols'] = sorted(exported)
    return info


def _die_name(die):
    attr = die.attributes.get('DW_AT_name')
    if attr is None:
        return ''
    val = attr.value
    return val.decode('utf-8', 'replace') if isinstance(val, bytes) else str(val)


def _die_int(die, attr_name, default=None):
    attr = die.attributes.get(attr_name)
    if attr is None:
        return default
    val = attr.value
    return int(val) if isinstance(val, int) else default


def _member_offset(die):
    attr = die.attributes.get('DW_AT_data_member_location')
    if attr is None:
        return None
    val = attr.value
    if isinstance(val, int):
        return val
    # DWARF expression list: e.g. [DW_OP_plus_uconst, offset]
    if isinstance(val, (list, bytes)) and len(val) >= 2 and val[0] == 0x23:
        return int(val[1])
    return str(val)


def extract_dwarf_abi(elf_path, exported_symbols):
    """Extract canonical DWARF signatures for exported symbols and reachable types."""
    data = Path(elf_path).read_bytes()
    try:
        ef = ELFFile(io.BytesIO(data))
    except ELFError as error:
        return {'has_dwarf': False, 'error': str(error), 'symbols': {}, 'types': {}}
    if ef.get_section_by_name('.debug_info') is None:
        return {'has_dwarf': False, 'symbols': {}, 'types': {}}

    dwarf = ef.get_dwarf_info()
    target_names = set(exported_symbols)
    symbols = {}
    recorded_types = {}

    for cu in dwarf.iter_CUs():
        die_by_offset = {}
        for die in cu.iter_DIEs():
            die_by_offset[die.offset] = die

        def ref_die(die, attr_name='DW_AT_type'):
            attr = die.attributes.get(attr_name)
            if attr is None:
                return None
            if attr.form == 'DW_FORM_ref_addr':
                return die_by_offset.get(attr.value)
            if isinstance(attr.value, int):
                return die_by_offset.get(cu.cu_offset + attr.value)
            return None

        def describe_type(die, depth=0, visiting=None):
            if die is None:
                return 'void'
            if depth > 12:
                return '<depth-limit>'
            visiting = set() if visiting is None else visiting
            if die.offset in visiting:
                name = _die_name(die)
                return f'{die.tag}:{name or hex(die.offset)}'
            visiting = visiting | {die.offset}
            tag = die.tag
            name = _die_name(die)
            size = _die_int(die, 'DW_AT_byte_size')
            if tag == 'DW_TAG_base_type':
                enc = _die_int(die, 'DW_AT_encoding')
                return f'base({name},size={size},enc={enc})'
            if tag == 'DW_TAG_pointer_type':
                return f'ptr({describe_type(ref_die(die), depth + 1, visiting)},size={size})'
            if tag == 'DW_TAG_const_type':
                return f'const({describe_type(ref_die(die), depth + 1, visiting)})'
            if tag == 'DW_TAG_volatile_type':
                return f'volatile({describe_type(ref_die(die), depth + 1, visiting)})'
            if tag == 'DW_TAG_restrict_type':
                return f'restrict({describe_type(ref_die(die), depth + 1, visiting)})'
            if tag == 'DW_TAG_typedef':
                target = describe_type(ref_die(die), depth + 1, visiting)
                return f'typedef({name}->{target})'
            if tag == 'DW_TAG_array_type':
                elem = describe_type(ref_die(die), depth + 1, visiting)
                bounds = []
                for child in die.iter_children():
                    if child.tag == 'DW_TAG_subrange_type':
                        upper = _die_int(child, 'DW_AT_upper_bound')
                        count = _die_int(child, 'DW_AT_count')
                        bounds.append(count if count is not None else (upper + 1 if upper is not None else None))
                return f'array({elem},{bounds})'
            if tag in ('DW_TAG_structure_type', 'DW_TAG_union_type', 'DW_TAG_class_type'):
                kind = {'DW_TAG_structure_type': 'struct',
                        'DW_TAG_union_type': 'union',
                        'DW_TAG_class_type': 'class'}[tag]
                is_decl = bool(_die_int(die, 'DW_AT_declaration', 0))
                if is_decl:
                    return f'{kind}({name},forward)'
                members = []
                for child in die.iter_children():
                    if child.tag == 'DW_TAG_member':
                        m_name = _die_name(child)
                        m_off = _member_offset(child)
                        m_type = describe_type(ref_die(child), depth + 1, visiting)
                        members.append({'name': m_name, 'offset': m_off, 'type': m_type})
                layout = {'kind': kind, 'name': name, 'size': size, 'members': members}
                if name:
                    recorded_types[f'{kind} {name}'] = layout
                return f'{kind}({name},size={size},members={len(members)})'
            if tag == 'DW_TAG_enumeration_type':
                enumerators = []
                for child in die.iter_children():
                    if child.tag == 'DW_TAG_enumerator':
                        enumerators.append((_die_name(child), _die_int(child, 'DW_AT_const_value')))
                layout = {'kind': 'enum', 'name': name, 'size': size, 'values': enumerators}
                if name:
                    recorded_types[f'enum {name}'] = layout
                return f'enum({name},size={size},values={enumerators})'
            if tag == 'DW_TAG_subroutine_type':
                ret = describe_type(ref_die(die), depth + 1, visiting)
                params = [describe_type(ref_die(c), depth + 1, visiting)
                          for c in die.iter_children() if c.tag == 'DW_TAG_formal_parameter']
                return f'fn({",".join(params)})->{ret}'
            return f'{tag}({name},size={size})'

        for die in cu.iter_DIEs():
            if die.tag == 'DW_TAG_subprogram':
                name = _die_name(die)
                linkage = die.attributes.get('DW_AT_linkage_name')
                sym_name = (linkage.value.decode('utf-8', 'replace')
                            if linkage and isinstance(linkage.value, bytes) else name)
                matched = sym_name if sym_name in target_names else (name if name in target_names else None)
                if not matched:
                    continue
                if _die_int(die, 'DW_AT_declaration', 0) and matched in symbols:
                    continue
                ret = describe_type(ref_die(die))
                params = []
                variadic = False
                for child in die.iter_children():
                    if child.tag == 'DW_TAG_formal_parameter':
                        params.append({
                            'name': _die_name(child),
                            'type': describe_type(ref_die(child)),
                        })
                    elif child.tag == 'DW_TAG_unspecified_parameters':
                        variadic = True
                symbols[matched] = {
                    'kind': 'function',
                    'return_type': ret,
                    'params': params,
                    'variadic': variadic,
                }
            elif die.tag == 'DW_TAG_variable':
                name = _die_name(die)
                if name not in target_names:
                    continue
                if _die_int(die, 'DW_AT_declaration', 0) and name in symbols:
                    continue
                symbols[name] = {
                    'kind': 'variable',
                    'type': describe_type(ref_die(die)),
                }

    return {
        'has_dwarf': True,
        'symbols': symbols,
        'types': recorded_types,
    }


def evidence_path(store_dir, elf_sha256):
    return Path(store_dir) / f'{elf_sha256}.abi.json'


def capture_evidence(unstripped_elf, stripped_elf, store_dir, *, package='', version='', path=''):
    """Bind out-of-APK DWARF / libabigail ABI evidence to stripped_elf's SHA-256."""
    unstripped_info = inspect_elf_identity(unstripped_elf)
    stripped_info = inspect_elf_identity(stripped_elf)

    # Ensure unstripped ELF genuinely matches the final stripped ELF.
    for key in ('e_machine', 'ei_class', 'ei_data', 'dt_soname', 'dt_needed', 'exported_symbols'):
        if unstripped_info[key] != stripped_info[key]:
            raise ValueError(
                f'Unstripped ELF does not match stripped ELF on {key}: '
                f'{unstripped_info[key]!r} != {stripped_info[key]!r}')

    exported = stripped_info['exported_symbols']
    dwarf_abi = extract_dwarf_abi(unstripped_elf, exported)
    covered = sorted(set(exported) & set(dwarf_abi['symbols']))
    uncovered = sorted(set(exported) - set(dwarf_abi['symbols']))

    abigail = detect_libabigail()
    abixml_file = None
    tool_info = {'name': 'pyelftools-dwarf', 'version': '1.0', 'args': ['extract_dwarf_abi']}
    if abigail and dwarf_abi['has_dwarf']:
        abixml_target = Path(store_dir) / f'{stripped_info["sha256"]}.abixml'
        abixml_target.parent.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            [abigail['abidw'], '--no-corpus-path', '--out-file', str(abixml_target),
             str(unstripped_elf)],
            capture_output=True, text=True)
        if res.returncode == 0 and abixml_target.is_file():
            abixml_file = abixml_target.name
            tool_info = {
                'name': 'libabigail+pyelftools-dwarf',
                'version': abigail['version'],
                'args': ['abidw', '--no-corpus-path'],
            }

    record = {
        'schema': SCHEMA_VERSION,
        'elf_sha256': stripped_info['sha256'],
        'unstripped_sha256': unstripped_info['sha256'],
        'package': package,
        'version': version,
        'path': path,
        'dt_soname': stripped_info['dt_soname'],
        'tool': tool_info,
        'has_dwarf': dwarf_abi['has_dwarf'],
        'exported_symbol_count': len(exported),
        'covered_symbol_count': len(covered),
        'uncovered_symbols': uncovered,
        'dwarf_abi': {
            'symbols': dwarf_abi['symbols'],
            'types': dwarf_abi['types'],
        },
        'abixml': abixml_file,
    }
    out = evidence_path(store_dir, stripped_info['sha256'])
    atomic_write_text(out, json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def decode_abidiff_exit(code):
    return {
        'raw_code': code,
        'error': bool(code & ABIDIFF_ERROR),
        'usage_error': bool(code & ABIDIFF_USAGE_ERROR),
        'abi_change': bool(code & ABIDIFF_ABI_CHANGE),
        'abi_incompatible_change': bool(code & ABIDIFF_ABI_INCOMPATIBLE_CHANGE),
    }


def compare_type_abi(old_elf_sha256, new_elf_sha256, old_exported, new_exported, store_dir,
                     expected_tool_version=None):
    """Compare out-of-APK type ABI evidence for two versions of a public shared library."""
    store = Path(store_dir)
    old_file = evidence_path(store, old_elf_sha256)
    new_file = evidence_path(store, new_elf_sha256)
    if not old_file.is_file() or not new_file.is_file():
        missing = []
        if not old_file.is_file():
            missing.append(f'old:{old_elf_sha256}')
        if not new_file.is_file():
            missing.append(f'new:{new_elf_sha256}')
        return {
            'status': 'missing_evidence',
            'compatible': None,
            'missing': missing,
            'changes': [],
        }

    try:
        old_rec = json.loads(old_file.read_text())
        new_rec = json.loads(new_file.read_text())
    except (OSError, ValueError) as error:
        return {'status': 'evidence_parse_error', 'compatible': None, 'error': str(error), 'changes': []}

    if old_rec.get('elf_sha256') != old_elf_sha256 or new_rec.get('elf_sha256') != new_elf_sha256:
        return {'status': 'evidence_digest_mismatch', 'compatible': None, 'changes': []}

    if expected_tool_version:
        for side, rec in (('old', old_rec), ('new', new_rec)):
            if (rec.get('tool') or {}).get('version') != expected_tool_version:
                return {
                    'status': 'tool_version_mismatch',
                    'compatible': None,
                    'detail': f'{side} tool version {(rec.get("tool") or {}).get("version")!r} '
                              f'!= expected {expected_tool_version!r}',
                    'changes': [],
                }

    if not old_rec.get('has_dwarf') or not new_rec.get('has_dwarf'):
        return {
            'status': 'insufficient_coverage',
            'compatible': None,
            'detail': 'DWARF debug information is missing on one or both sides',
            'changes': [],
        }

    # Verify full coverage of every exported symbol on both sides.
    old_syms = (old_rec.get('dwarf_abi') or {}).get('symbols', {})
    new_syms = (new_rec.get('dwarf_abi') or {}).get('symbols', {})
    # Strip symbol version suffixes (foo@@VER -> foo) when matching DWARF names.
    old_plain = sorted({s.split('@', 1)[0] for s in old_exported})
    new_plain = sorted({s.split('@', 1)[0] for s in new_exported})
    uncovered_old = sorted(set(old_plain) - set(old_syms))
    uncovered_new = sorted(set(new_plain) - set(new_syms))
    if uncovered_old or uncovered_new:
        return {
            'status': 'insufficient_coverage',
            'compatible': None,
            'detail': 'not all exported dynamic symbols are covered by type evidence',
            'uncovered_old': uncovered_old,
            'uncovered_new': uncovered_new,
            'changes': [],
        }

    changes = []
    # Optional libabigail check when both abixml files and abidiff are present.
    abigail = detect_libabigail()
    if abigail and old_rec.get('abixml') and new_rec.get('abixml'):
        old_xml = store / old_rec['abixml']
        new_xml = store / new_rec['abixml']
        if old_xml.is_file() and new_xml.is_file():
            res = subprocess.run([abigail['abidiff'], str(old_xml), str(new_xml)],
                                 capture_output=True, text=True)
            bits = decode_abidiff_exit(res.returncode)
            if bits['error'] or bits['usage_error']:
                return {
                    'status': 'abidiff_error',
                    'compatible': None,
                    'abidiff': bits,
                    'detail': (res.stderr or res.stdout).strip()[:1000],
                    'changes': [],
                }
            if bits['abi_change'] or bits['abi_incompatible_change']:
                changes.append({
                    'source': 'abidiff',
                    'abidiff': bits,
                    'detail': (res.stdout or res.stderr).strip()[:2000],
                })

    # Native DWARF exported symbol signature comparison.
    for name in sorted(set(old_syms) | set(new_syms)):
        a = old_syms.get(name)
        b = new_syms.get(name)
        if a != b:
            changes.append({
                'source': 'dwarf_symbol',
                'symbol': name,
                'old': a,
                'new': b,
            })

    # Native DWARF public struct/union/enum layout comparison.
    old_types = (old_rec.get('dwarf_abi') or {}).get('types', {})
    new_types = (new_rec.get('dwarf_abi') or {}).get('types', {})
    for tname in sorted(set(old_types) | set(new_types)):
        a = old_types.get(tname)
        b = new_types.get(tname)
        if a != b:
            changes.append({
                'source': 'dwarf_type_layout',
                'type': tname,
                'old': a,
                'new': b,
            })

    if changes:
        return {
            'status': 'abi_incompatible_change',
            'compatible': False,
            'changes': changes,
            'covered_symbols': len(new_plain),
            'total_symbols': len(new_plain),
            'tool': new_rec.get('tool'),
        }

    return {
        'status': 'verified_compatible',
        'compatible': True,
        'changes': [],
        'covered_symbols': len(new_plain),
        'total_symbols': len(new_plain),
        'tool': new_rec.get('tool'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    cap = sub.add_parser('capture', help='Capture out-of-APK type ABI evidence for a library')
    cap.add_argument('--unstripped', type=Path, required=True)
    cap.add_argument('--stripped', type=Path, required=True)
    cap.add_argument('--store', type=Path, required=True)
    cap.add_argument('--package', default='')
    cap.add_argument('--version', default='')
    cap.add_argument('--path', default='')

    cmp_p = sub.add_parser('compare', help='Compare two stripped ELFs using stored type ABI evidence')
    cmp_p.add_argument('--old', type=Path, required=True)
    cmp_p.add_argument('--new', type=Path, required=True)
    cmp_p.add_argument('--store', type=Path, required=True)
    cmp_p.add_argument('--expected-tool-version')

    args = parser.parse_args(argv)
    if args.command == 'capture':
        rec = capture_evidence(args.unstripped, args.stripped, args.store,
                               package=args.package, version=args.version, path=args.path)
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0
    old_id = inspect_elf_identity(args.old)
    new_id = inspect_elf_identity(args.new)
    res = compare_type_abi(old_id['sha256'], new_id['sha256'],
                           old_id['exported_symbols'], new_id['exported_symbols'],
                           args.store, expected_tool_version=args.expected_tool_version)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0 if res.get('status') == 'verified_compatible' else 1


if __name__ == '__main__':
    sys.exit(main())
