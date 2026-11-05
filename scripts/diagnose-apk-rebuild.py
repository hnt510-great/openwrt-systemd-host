#!/usr/bin/env python3
"""Explain why a rebuilt APK differs from the published APK of the same version.

The publisher rejects a same-version rebuild whose bytes changed. This tool
compares the two packages from APK metadata down to the changed bytes and
classifies each difference:

  benign   build nondeterminism with no runtime effect (archive timestamps,
           .pyc source mtimes, BTF type order in BPF objects)
  change   a real content or metadata change; allocate a new release
  unknown  bytes differ in a way this tool cannot judge; inspect by hand

Usage:
  diagnose-apk-rebuild.py base/daed-2.1.1-r4.apk [...]   # paths as the publisher prints them
  diagnose-apk-rebuild.py OLD.apk NEW.apk                 # any two APK files
"""
import argparse
from collections import Counter
from dataclasses import dataclass, field, asdict
import difflib
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

TREE = Path(__file__).resolve().parent.parent
APK = TREE / 'staging_dir/host/bin/apk'
FEEDS_CONFIG = TREE / 'configs/lan-apk-feeds.json'
TARGET_PACKAGES = 'bin/systemd/targets/x86/64-glibc/packages'
PACKAGE_ROOT = 'bin/systemd/packages/x86_64'

BENIGN, CHANGE, UNKNOWN = 'benign', 'change', 'unknown'
MAX_DEPTH = 3
MAX_REGIONS = 8


@dataclass
class Finding:
    verdict: str
    path: str
    detail: str
    lines: list = field(default_factory=list)


@dataclass
class Report:
    old: str
    new: str
    identical: bool = False
    findings: list = field(default_factory=list)

    @property
    def verdict(self):
        verdicts = {f.verdict for f in self.findings}
        if self.identical:
            return 'identical'
        if CHANGE in verdicts:
            return CHANGE
        if UNKNOWN in verdicts or not verdicts:
            return UNKNOWN
        return BENIGN


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# APK metadata

def adbdump(apk, package):
    return json.loads(subprocess.check_output(
        [str(apk), 'adbdump', '--format', 'json', str(package)]))


def file_table(metadata):
    """Map every path in an adbdump to its directory or file attributes."""
    table = {}
    for directory in metadata.get('paths', []):
        name = directory.get('name', '')
        table[name + '/'] = {'acl': directory.get('acl')}
        for entry in directory.get('files', []):
            path = f'{name}/{entry["name"]}' if name else entry['name']
            table[path] = {k: v for k, v in entry.items() if k != 'name'}
    return table


def compare_metadata(old, new):
    """Return (findings, content-changed paths) for two adbdump results."""
    findings = []
    old_info = {k: v for k, v in old.get('info', {}).items() if k != 'hashes'}
    new_info = {k: v for k, v in new.get('info', {}).items() if k != 'hashes'}
    for key in sorted(set(old_info) | set(new_info)):
        if old_info.get(key) != new_info.get(key):
            if key == 'installed-size':
                # Follows file sizes; the file comparison explains it.
                continue
            findings.append(Finding(CHANGE, '(info)', f'{key}: {old_info.get(key)!r} -> '
                                    f'{new_info.get(key)!r}'))
    old_scripts, new_scripts = old.get('scripts', {}), new.get('scripts', {})
    for key in sorted(set(old_scripts) | set(new_scripts)):
        if old_scripts.get(key) != new_scripts.get(key):
            findings.append(Finding(CHANGE, f'(script {key})', 'install script changed',
                                    text_diff(old_scripts.get(key, ''), new_scripts.get(key, ''))))
    old_files, new_files = file_table(old), file_table(new)
    for path in sorted(set(old_files) - set(new_files)):
        findings.append(Finding(CHANGE, path, 'removed'))
    for path in sorted(set(new_files) - set(old_files)):
        findings.append(Finding(CHANGE, path, 'added'))
    changed = []
    for path in sorted(set(old_files) & set(new_files)):
        a, b = old_files[path], new_files[path]
        for key in sorted((set(a) | set(b)) - {'hash', 'size'}):
            if a.get(key) != b.get(key):
                verdict = BENIGN if key == 'mtime' else CHANGE
                findings.append(Finding(verdict, path, f'{key}: {a.get(key)!r} -> {b.get(key)!r}'))
        if a.get('hash') != b.get('hash'):
            changed.append(path)
    return findings, changed


# --------------------------------------------------------------------------
# ELF

def parse_elf(data, base=0):
    """Return ELF header facts and sections, or None if data is not an ELF image."""
    if data[base:base + 4] != b'\x7fELF' or len(data) < base + 52:
        return None
    klass, encoding = data[base + 4], data[base + 5]
    if klass not in (1, 2) or encoding not in (1, 2):
        return None
    end = '<' if encoding == 1 else '>'
    try:
        if klass == 2:
            shoff, = struct.unpack_from(end + 'Q', data, base + 0x28)
            shentsize, shnum, shstrndx = struct.unpack_from(end + 'HHH', data, base + 0x3a)
            phoff, = struct.unpack_from(end + 'Q', data, base + 0x20)
            phentsize, phnum = struct.unpack_from(end + 'HH', data, base + 0x36)
            layout = end + 'IIQQQQIIQQ'
        else:
            shoff, = struct.unpack_from(end + 'I', data, base + 0x20)
            shentsize, shnum, shstrndx = struct.unpack_from(end + 'HHH', data, base + 0x2e)
            phoff, = struct.unpack_from(end + 'I', data, base + 0x1c)
            phentsize, phnum = struct.unpack_from(end + 'HH', data, base + 0x2a)
            layout = end + 'IIIIIIIIII'
        if not shoff or not shnum or shentsize < struct.calcsize(layout):
            return None
        raw = []
        for i in range(shnum):
            fields = struct.unpack_from(layout, data, base + shoff + i * shentsize)
            name, kind = fields[0], fields[1]
            offset, size = fields[4], fields[5]
            raw.append((name, kind, offset, size))
        strtab = raw[shstrndx] if shstrndx < len(raw) else None
    except struct.error:
        return None
    sections = []
    for name, kind, offset, size in raw:
        label = ''
        if strtab:
            start = base + strtab[2] + name
            stop = data.find(b'\0', start)
            if 0 <= start < len(data) and stop > 0:
                label = data[start:stop].decode('latin-1')
        sections.append({'name': label, 'type': kind, 'offset': offset, 'size': size})
    extent = shoff + shnum * shentsize
    for section in sections:
        if section['type'] != 8:  # SHT_NOBITS occupies no file bytes
            extent = max(extent, section['offset'] + section['size'])
    extent = max(extent, phoff + phnum * phentsize)
    if base + extent > len(data):
        return None
    return {'endian': end, 'class': klass, 'size': extent, 'sections': sections}


def section_bytes(data, elf, section, base=0):
    if section['type'] == 8:
        return b''
    start = base + section['offset']
    return data[start:start + section['size']]


def diff_regions(a, b, gap=64):
    """Cluster differing byte offsets of equal-length buffers into [start, end)."""
    regions = []
    start = None
    last = None
    # Compare in chunks so large identical spans stay fast.
    chunk = 4096
    for offset in range(0, len(a), chunk):
        if a[offset:offset + chunk] == b[offset:offset + chunk]:
            continue
        for i in range(offset, min(offset + chunk, len(a))):
            if a[i] != b[i]:
                if start is None:
                    start = i
                elif i - last > gap:
                    regions.append((start, last + 1))
                    start = i
                last = i
    if start is not None:
        regions.append((start, last + 1))
    return regions


def find_embedded_elf(a, b, region):
    """Find an ELF image present at the same offset in both buffers covering region."""
    end = region[0] + 4
    while True:
        position = a.rfind(b'\x7fELF', 0, end)
        if position < 0:
            return None
        if b[position:position + 4] == b'\x7fELF':
            old, new = parse_elf(a, position), parse_elf(b, position)
            if old and new and position + old['size'] >= region[1]:
                return position, old['size'], new['size']
        end = position + 3


DERIVED_SECTIONS = {'.note.gnu.build-id', '.note.go.buildid', '.gnu_debuglink'}
ID_SECTIONS = {'.BTF.ext', '.rel.BTF', '.rel.BTF.ext'}


def analyze_elf(path, a, b, depth):
    old, new = parse_elf(a), parse_elf(b)
    findings = []
    old_sections = {s['name']: s for s in old['sections']}
    new_sections = {s['name']: s for s in new['sections']}
    if [s['name'] for s in old['sections']] != [s['name'] for s in new['sections']]:
        added = sorted(set(new_sections) - set(old_sections))
        removed = sorted(set(old_sections) - set(new_sections))
        findings.append(Finding(CHANGE, path, 'ELF section list changed',
                                [f'added: {", ".join(added) or "-"}',
                                 f'removed: {", ".join(removed) or "-"}']))
    differing = []
    for name, section in old_sections.items():
        other = new_sections.get(name)
        if not other:
            continue
        sa, sb = section_bytes(a, old, section), section_bytes(b, new, other)
        if sa != sb or section['size'] != other['size']:
            differing.append((name, section, other, sa, sb))
    if not differing:
        if not findings:
            findings.append(Finding(UNKNOWN, path, 'ELF headers or padding differ; sections '
                                    'are identical'))
        return findings
    btf_reordered = False
    for name, section, other, sa, sb in differing:
        if name == '.BTF':
            finding = analyze_btf(f'{path} [{name}]', sa, sb, old['endian'])
            btf_reordered = finding.verdict == BENIGN
            findings.append(finding)
    for name, section, other, sa, sb in differing:
        label = f'{path} [{name}]'
        if name == '.BTF':
            continue
        if name in DERIVED_SECTIONS:
            findings.append(Finding(BENIGN if len(differing) > 1 else UNKNOWN, label,
                                    'identifier derived from the other changed bytes'
                                    if len(differing) > 1 else 'only the build identifier differs'))
            continue
        if name in ID_SECTIONS and btf_reordered:
            findings.append(Finding(BENIGN, label, 'BTF type IDs renumbered with the type order'))
            continue
        if name == '.go.buildinfo':
            findings.append(go_buildinfo(label, a, b))
            continue
        if len(sa) != len(sb):
            findings.append(Finding(UNKNOWN, label, f'section size {len(sa)} -> {len(sb)} '
                                    'bytes; code or data changed'))
            continue
        findings.extend(analyze_regions(label, sa, sb, depth, section_name=name))
    return findings


def analyze_regions(label, a, b, depth, section_name=''):
    """Explain the differing regions of two equal-length buffers."""
    findings = []
    regions = diff_regions(a, b)
    explained = set()
    if depth < MAX_DEPTH:
        handled = []
        for region in regions:
            if any(s <= region[0] and region[1] <= s + n for s, n in handled):
                continue
            hit = find_embedded_elf(a, b, region)
            if not hit:
                continue
            start, size_old, size_new = hit
            handled.append((start, max(size_old, size_new)))
            inner = f'{label} embedded ELF @0x{start:x}'
            ia, ib = a[start:start + size_old], b[start:start + size_new]
            findings.extend(analyze_elf(inner, ia, ib, depth + 1))
        for region in regions:
            if any(s <= region[0] and region[1] <= s + n for s, n in handled):
                explained.add(region)
    rest = [r for r in regions if r not in explained]
    if rest:
        changed = sum(1 for s, e in rest for i in range(s, e) if a[i] != b[i])
        lines = [f'{len(rest)} region(s), {changed} differing byte(s)']
        for start, end in rest[:MAX_REGIONS]:
            lines.append(f'0x{start:x}-0x{end:x}: {context_strings(a, start, end)} -> '
                         f'{context_strings(b, start, end)}')
        hint = timestamp_hint(a, b, rest)
        if hint:
            lines.append(hint)
        where = f' in {section_name}' if section_name else ''
        findings.append(Finding(UNKNOWN, label, f'bytes differ{where}', lines))
    return findings


def context_strings(data, start, end, width=24):
    window = data[max(0, start - width):min(len(data), end + width)]
    text = re.sub(rb'[^\x20-\x7e]+', b'.', window).decode('ascii')
    return repr(text[:96])


TIMESTAMP = re.compile(rb'(19|20)\d\d[-/]?[01]\d[-/]?[0-3]\d|[0-2]\d:[0-5]\d:[0-5]\d|'
                       rb'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [ 0-3]\d')


def timestamp_hint(a, b, regions):
    for start, end in regions:
        lo, hi = max(0, start - 24), min(len(a), end + 24)
        if TIMESTAMP.search(a[lo:hi]) and TIMESTAMP.search(b[lo:hi]):
            return 'differing bytes sit next to date/time text: likely an embedded build timestamp'
    return ''


def go_buildinfo(label, a, b):
    go = next(iter(sorted(TREE.glob('staging_dir/hostpkg/lib/go-[0-9]*/bin/go'))), None)
    go = go or shutil.which('go')
    if not go:
        return Finding(UNKNOWN, label, 'Go build information differs (no go tool to decode it)')
    with tempfile.TemporaryDirectory() as temporary:
        outputs = []
        for name, data in (('old', a), ('new', b)):
            binary = Path(temporary) / name
            binary.write_bytes(data)
            result = subprocess.run([str(go), 'version', '-m', str(binary)],
                                    capture_output=True, text=True)
            outputs.append(result.stdout.replace(str(binary), name))
    return Finding(CHANGE, label, 'Go build information differs (toolchain, modules or '
                   'build settings)', text_diff(*outputs))


# --------------------------------------------------------------------------
# BTF

BTF_EXTRA = {1: lambda vlen: 4, 3: lambda vlen: 12, 4: lambda vlen: 12 * vlen,
             5: lambda vlen: 12 * vlen, 6: lambda vlen: 8 * vlen, 13: lambda vlen: 8 * vlen,
             14: lambda vlen: 4, 15: lambda vlen: 12 * vlen, 17: lambda vlen: 4,
             19: lambda vlen: 12 * vlen}
BTF_KINDS = {1: 'int', 2: 'ptr', 3: 'array', 4: 'struct', 5: 'union', 6: 'enum', 7: 'fwd',
             8: 'typedef', 9: 'volatile', 10: 'const', 11: 'restrict', 12: 'func',
             13: 'func_proto', 14: 'var', 15: 'datasec', 16: 'float', 17: 'decl_tag',
             18: 'type_tag', 19: 'enum64'}
NAMED_REFERENCES = {4, 5, 6, 7, 8, 12, 19}


def parse_btf(data):
    """Return BTF types as dicts with raw type-ID references, or None."""
    if data[:2] == b'\x9f\xeb':
        end = '<'
    elif data[:2] == b'\xeb\x9f':
        end = '>'
    else:
        return None
    _, _, _, header, type_off, type_len, str_off, str_len = struct.unpack_from(
        end + 'HBBIIIII', data, 0)
    types_blob = data[header + type_off:header + type_off + type_len]
    strings = data[header + str_off:header + str_off + str_len]

    def string(offset):
        stop = strings.find(b'\0', offset)
        return strings[offset:stop].decode('utf-8', 'replace') if stop >= 0 else '?'

    types = [None]
    i = 0
    while i < len(types_blob):
        name, info, size_or_type = struct.unpack_from(end + 'III', types_blob, i)
        i += 12
        kind, vlen, kflag = (info >> 24) & 0x1f, info & 0xffff, info >> 31
        extra = BTF_EXTRA.get(kind, lambda vlen: 0)(vlen)
        body = types_blob[i:i + extra]
        i += extra
        entry = {'kind': kind, 'name': string(name), 'kflag': kflag, 'vlen': vlen,
                 'value': size_or_type, 'refs': [], 'data': []}
        if kind in (2, 8, 9, 10, 11, 12, 14, 17, 18):
            entry['refs'].append(size_or_type)
            entry['value'] = None
        if kind == 1:
            entry['data'] = list(struct.unpack_from(end + 'I', body))
        elif kind == 3:
            elem, index, count = struct.unpack_from(end + 'III', body)
            entry['refs'] += [elem, index]
            entry['data'] = [count]
        elif kind in (4, 5):
            for j in range(vlen):
                member, ref, offset = struct.unpack_from(end + 'III', body, 12 * j)
                entry['data'].append((string(member), offset))
                entry['refs'].append(ref)
        elif kind == 6:
            entry['data'] = [(string(n), v) for n, v in
                             (struct.unpack_from(end + 'Ii', body, 8 * j) for j in range(vlen))]
        elif kind == 19:
            entry['data'] = [(string(n), lo, hi) for n, lo, hi in
                             (struct.unpack_from(end + 'III', body, 12 * j) for j in range(vlen))]
        elif kind == 13:
            entry['refs'].append(size_or_type)
            entry['value'] = None
            for j in range(vlen):
                param, ref = struct.unpack_from(end + 'II', body, 8 * j)
                entry['data'].append(string(param))
                entry['refs'].append(ref)
        elif kind == 14 or kind == 17:
            entry['data'] = list(struct.unpack_from(end + 'I', body))
        elif kind == 15:
            for j in range(vlen):
                ref, offset, size = struct.unpack_from(end + 'III', body, 12 * j)
                entry['data'].append((offset, size))
                entry['refs'].append(ref)
        types.append(entry)
    return types


def btf_signatures(types):
    """Describe every type without its numeric ID, following anonymous references."""
    cache = {}

    def reference(type_id, depth=0):
        if type_id == 0:
            return 'void'
        if type_id >= len(types):
            return f'<bad {type_id}>'
        entry = types[type_id]
        if entry['kind'] in NAMED_REFERENCES and entry['name']:
            return f'{BTF_KINDS.get(entry["kind"])} {entry["name"]}'
        if depth > 16:
            return '...'
        return describe(type_id, depth + 1)

    def describe(type_id, depth=0):
        if type_id in cache:
            return cache[type_id]
        entry = types[type_id]
        refs = ','.join(reference(ref, depth) for ref in entry['refs'])
        text = (f'{BTF_KINDS.get(entry["kind"], entry["kind"])} {entry["name"]!r} '
                f'k{entry["kflag"]} v{entry["value"]} [{refs}] {entry["data"]}')
        cache[type_id] = text
        return text

    return [describe(i) for i in range(1, len(types))]


def analyze_btf(label, a, b, endian):
    old, new = parse_btf(a), parse_btf(b)
    if old is None or new is None:
        return Finding(UNKNOWN, label, 'BTF differs and could not be decoded')
    old_sig, new_sig = btf_signatures(old), btf_signatures(new)
    if Counter(old_sig) == Counter(new_sig):
        moved = [s for s, t in zip(old_sig, new_sig) if s != t]
        names = []
        for i, (s, t) in enumerate(zip(old_sig, new_sig), 1):
            if s != t and old[i]['name'] and len(names) < 6:
                names.append(f'{BTF_KINDS.get(old[i]["kind"])} {old[i]["name"]}')
        return Finding(BENIGN, label, 'same BTF types in a different order (compiler '
                       'nondeterminism; the program is unaffected)',
                       [f'{len(moved)} of {len(old_sig)} type slots moved',
                        'first moved: ' + (', '.join(names) or '(anonymous types)')])
    removed = list((Counter(old_sig) - Counter(new_sig)).elements())
    added = list((Counter(new_sig) - Counter(old_sig)).elements())
    lines = [f'- {s[:160]}' for s in removed[:6]] + [f'+ {s[:160]}' for s in added[:6]]
    return Finding(CHANGE, label, f'BTF type definitions changed ({len(removed)} removed, '
                   f'{len(added)} added): the BPF program sees different types', lines)


# --------------------------------------------------------------------------
# Other formats

def text_diff(a, b, limit=24):
    lines = list(difflib.unified_diff(a.splitlines(), b.splitlines(), 'old', 'new',
                                      lineterm='', n=1))
    return lines[:limit] + (['...'] if len(lines) > limit else [])


def is_text(data):
    if b'\0' in data[:65536]:
        return False
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return True


def analyze_gzip(path, a, b, depth):
    try:
        ua, ub = gzip.decompress(a), gzip.decompress(b)
    except (OSError, EOFError):
        return [Finding(UNKNOWN, path, 'gzip stream differs and could not be decompressed')]
    if ua == ub:
        mtime_a, mtime_b = struct.unpack_from('<I', a, 4)[0], struct.unpack_from('<I', b, 4)[0]
        detail = (f'gzip header only (mtime {mtime_a} -> {mtime_b})' if mtime_a != mtime_b
                  else 'gzip compression bytes only; decompressed content is identical')
        return [Finding(BENIGN, path, detail)]
    return analyze_content(f'{path} (decompressed)', ua, ub, depth + 1)


def analyze_zip(path, a, b, depth):
    try:
        za, zb = zipfile.ZipFile(io.BytesIO(a)), zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile:
        return None
    findings = []
    names_a, names_b = set(za.namelist()), set(zb.namelist())
    for name in sorted(names_a ^ names_b):
        findings.append(Finding(CHANGE, f'{path}!{name}', 'added' if name in names_b
                                else 'removed'))
    for name in sorted(names_a & names_b):
        ca, cb = za.read(name), zb.read(name)
        if ca != cb:
            findings.extend(analyze_content(f'{path}!{name}', ca, cb, depth + 1))
    if not findings:
        findings.append(Finding(BENIGN, path, 'zip entry timestamps or order only; every '
                                'entry has identical content'))
    return findings


def analyze_pyc(path, a, b):
    if len(a) < 16 or len(b) < 16 or a[:4] != b[:4]:
        return None
    flags, = struct.unpack_from('<I', a, 4)
    if flags == 0 and a[:8] == b[:8] and a[16:] == b[16:]:
        return [Finding(BENIGN, path, 'pyc header records a different source mtime/size; '
                        'the bytecode is identical')]
    return None


def analyze_content(path, a, b, depth=0):
    if a == b:
        return []
    if parse_elf(a) and parse_elf(b):
        return analyze_elf(path, a, b, depth)
    if a[:2] == b[:2] == b'\x1f\x8b':
        return analyze_gzip(path, a, b, depth)
    if a[:4] == b[:4] == b'PK\x03\x04':
        result = analyze_zip(path, a, b, depth)
        if result is not None:
            return result
    if path.endswith('.pyc'):
        result = analyze_pyc(path, a, b)
        if result is not None:
            return result
    if is_text(a) and is_text(b):
        lines = text_diff(a.decode('utf-8'), b.decode('utf-8'))
        changed = [line[1:] for line in lines if line[:1] in '+-' and line[:3] not in ('+++', '---')]
        if changed and all(TIMESTAMP.search(line.encode()) for line in changed):
            return [Finding(BENIGN, path, 'text differs only on lines carrying dates/times '
                            '(likely a build timestamp)', lines)]
        return [Finding(CHANGE, path, 'text content changed', lines)]
    if len(a) != len(b):
        return [Finding(UNKNOWN, path, f'binary size {len(a)} -> {len(b)} bytes')]
    return analyze_regions(path, a, b, depth)


# --------------------------------------------------------------------------
# Packages

def extract(apk, package, destination):
    subprocess.run([str(apk), 'extract', '--allow-untrusted', '--no-chown',
                    '--destination', str(destination), str(package)],
                   check=True, capture_output=True)


def diagnose(old, new, apk=APK):
    old, new = Path(old), Path(new)
    report = Report(str(old), str(new))
    old_data, new_data = old.read_bytes(), new.read_bytes()
    if old_data == new_data:
        report.identical = True
        return report
    old_meta, new_meta = adbdump(apk, old), adbdump(apk, new)
    findings, changed = compare_metadata(old_meta, new_meta)
    report.findings.extend(findings)
    if changed:
        with tempfile.TemporaryDirectory(prefix='diagnose-apk-') as temporary:
            roots = Path(temporary) / 'old', Path(temporary) / 'new'
            for root, package in zip(roots, (old, new)):
                root.mkdir()
                extract(apk, package, root)
            for path in changed:
                a_path, b_path = roots[0] / path, roots[1] / path
                if a_path.is_symlink() or b_path.is_symlink():
                    report.findings.append(Finding(CHANGE, path, 'symlink target changed'))
                    continue
                report.findings.extend(
                    analyze_content(path, a_path.read_bytes(), b_path.read_bytes()))
    elif not findings:
        report.findings.append(Finding(UNKNOWN, '(package)', 'payload and metadata match; '
                                       'only the signature or archive framing differs'))
    return report


def resolve(feed_path, tree=TREE):
    """Map a publisher path such as base/daed-2.1.1-r4.apk to (published, rebuilt)."""
    repository, _, filename = feed_path.partition('/')
    if not filename:
        raise ValueError(f'Expected REPOSITORY/FILE.apk, got {feed_path}')
    destination = Path(json.loads(FEEDS_CONFIG.read_text())['destination'])
    snapshots = sorted((destination / 'public/snapshots').glob(f'*/{feed_path}'))
    if not snapshots:
        raise ValueError(f'{feed_path} is not in any published snapshot under {destination}')
    if repository == 'target':
        rebuilt = tree / TARGET_PACKAGES / filename
    elif repository == 'custom':
        candidates = sorted((tree / PACKAGE_ROOT).glob(f'*/{filename}'))
        rebuilt = candidates[0] if candidates else tree / PACKAGE_ROOT / 'custom' / filename
    else:
        rebuilt = tree / PACKAGE_ROOT / repository / filename
    if not rebuilt.exists():
        raise ValueError(f'No rebuilt {filename} at {rebuilt}')
    return snapshots[-1], rebuilt


SUMMARY = {
    'identical': 'identical bytes; nothing to do',
    BENIGN: 'build nondeterminism only; the content is equivalent. A new release would '
            'ship a no-op upgrade',
    CHANGE: 'real content change; allocate a new release (PKG_RELEASE or the ELF rebuild '
            'ledger)',
    UNKNOWN: 'unclassified difference; inspect the findings marked unknown',
}


def format_report(report, verbose=True, label=None):
    if label:
        lines = [f'{label}: {report.verdict}: {SUMMARY[report.verdict]}']
    else:
        lines = [f'old: {report.old}', f'new: {report.new}',
                 f'verdict: {report.verdict}: {SUMMARY[report.verdict]}']
    order = {CHANGE: 0, UNKNOWN: 1, BENIGN: 2}
    for finding in sorted(report.findings, key=lambda f: order[f.verdict]):
        lines.append(f'  [{finding.verdict}] {finding.path}: {finding.detail}')
        if verbose:
            lines.extend('      ' + line for line in finding.lines)
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('packages', nargs='+',
                        help='REPOSITORY/FILE.apk paths from the publisher, or OLD.apk NEW.apk')
    parser.add_argument('--json', action='store_true', help='print machine-readable reports')
    parser.add_argument('--brief', action='store_true', help='omit per-finding detail lines')
    args = parser.parse_args(argv)
    if not APK.exists():
        parser.error(f'{APK} is missing; build the host apk tool first')
    files = [Path(p) for p in args.packages]
    if len(files) == 2 and all(p.suffix == '.apk' and p.is_file() for p in files):
        pairs = [tuple(files)]
    else:
        pairs = [resolve(p) for p in args.packages]
    reports = [diagnose(old, new) for old, new in pairs]
    if args.json:
        print(json.dumps([dict(asdict(r), verdict=r.verdict) for r in reports], indent=2))
    else:
        print('\n\n'.join(format_report(r, not args.brief) for r in reports))
    worst = {'identical': 0, BENIGN: 0, UNKNOWN: 1, CHANGE: 2}
    return max(worst[r.verdict] for r in reports)


if __name__ == '__main__':
    sys.exit(main())
