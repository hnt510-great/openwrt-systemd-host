#!/usr/bin/env python3
"""Explain why a rebuilt APK differs from the published APK of the same version.

The publisher rejects a same-version rebuild whose bytes changed. This tool
compares the two packages from APK framing and metadata down to ELF dynamic
contracts and changed bytes, classifies each finding, and produces a versioned
release-action decision:

  benign   build nondeterminism with no runtime effect (archive timestamps,
           .pyc source mtimes, BTF type order in BPF objects)
  change   a real content or metadata change; allocate a new release
  unknown  bytes differ in a way this tool cannot judge; inspect by hand

Phase 1 policy (phase1-conservative-v1):
  * Identical complete ADB streams under trusted signatures -> reuse_published
  * Public shared library DT_NEEDED reordering or missing type ABI evidence ->
    review_before_allocate
  * Executable implementation-only changes without cold rebuild evidence ->
    review_before_allocate (conservative until Phase 2b)
  * Any mixed unknown/unresolved finding blocks automatic release allocation

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
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

try:
    from elftools.common.exceptions import ELFError
    from elftools.elf.dynamic import DynamicSegment
    from elftools.elf.elffile import ELFFile
    from elftools.elf.gnuversions import (
        GNUVerDefSection,
        GNUVerNeedSection,
        GNUVerSymSection,
    )
    from elftools.elf.sections import SymbolTableSection
    HAVE_ELFTOOLS = True
except ImportError:  # pragma: no cover - host python3 ships pyelftools
    ELFError = Exception
    HAVE_ELFTOOLS = False

TREE = Path(__file__).resolve().parent.parent
APK = TREE / 'staging_dir/host/bin/apk'
FEEDS_CONFIG = TREE / 'configs/lan-apk-feeds.json'
PUBLIC_KEY = TREE / 'public-key.pem'
TARGET_PACKAGES = 'bin/systemd/targets/x86/64-glibc/packages'
PACKAGE_ROOT = 'bin/systemd/packages/x86_64'

ANALYZER_VERSION = '2.1'
POLICY_VERSION = 'phase2-evidence-v1'

_type_abi_spec = importlib.util.spec_from_file_location(
    'diagnose_elf_type_abi', Path(__file__).with_name('elf-type-abi.py'))
ELF_TYPE_ABI = importlib.util.module_from_spec(_type_abi_spec)
_type_abi_spec.loader.exec_module(ELF_TYPE_ABI)

BENIGN, CHANGE, UNKNOWN = 'benign', 'change', 'unknown'
MAX_DEPTH = 3
MAX_REGIONS = 8

ACTION_KEEP_EXISTING = 'keep_existing'
ACTION_REUSE_PUBLISHED = 'reuse_published'
ACTION_ALLOCATE_RELEASE = 'allocate_release'
ACTION_REVIEW = 'review_before_allocate'
ACTION_BENIGN = 'benign_nondeterminism'
ACTION_REJECT = 'reject'

DF_1_PIE = 0x08000000

PUBLIC_LIB_DIRS = (
    'lib',
    'usr/lib',
    'lib64',
    'usr/lib64',
    'lib/x86_64-linux-gnu',
    'usr/lib/x86_64-linux-gnu',
)

PLUGIN_PATH_FRAGMENTS = (
    '/plugins/',
    '/modules/',
    '/ucode/',
    '/gio/modules/',
    '/gdk-pixbuf',
    '/gstreamer',
    '/gtk-',
    '/qt5/',
    '/qt6/',
    '/kf5/',
    '/kf6/',
    '/mozilla/',
    '/samba/',
    '/spa-0.2/',
    '/pipewire-0.3/',
    '/wireplumber-0.5/',
    '/xtables/',
    '/iptables/',
    '/ebtables/',
    '/security/',
    '/fcitx5/',
    '/libpeas',
    '/nautilus/',
)

KNOWN_TOP_LEVEL_KEYS = {'info', 'scripts', 'paths', 'triggers', 'replaces-priority'}


@dataclass
class Finding:
    verdict: str
    path: str
    detail: str
    lines: list = field(default_factory=list)
    code: str = ''


@dataclass
class Report:
    old: str
    new: str
    identical: bool = False
    findings: list = field(default_factory=list)
    old_sha256: str = ''
    new_sha256: str = ''
    adb_stream_identical: bool = False
    trust: dict = field(default_factory=dict)
    identity: dict = field(default_factory=dict)
    elf_summary: list = field(default_factory=list)
    type_abi: dict = field(default_factory=lambda: {'status': 'not_collected', 'phase': 'phase2a'})
    build_provenance: dict = field(default_factory=lambda: {'status': 'not_collected', 'phase': 'phase2b'})
    reproducibility: dict = field(default_factory=lambda: {'status': 'not_collected', 'phase': 'phase2b'})
    decision: dict = field(default_factory=dict)

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

    def effective_decision(self):
        return self.decision if self.decision else evaluate_decision(self)

    def to_dict(self):
        data = asdict(self)
        data['verdict'] = self.verdict
        data['decision'] = self.effective_decision()
        return data

    def report_sha256(self):
        payload = {
            'analyzer_version': ANALYZER_VERSION,
            'policy_version': POLICY_VERSION,
            'old_sha256': self.old_sha256,
            'new_sha256': self.new_sha256,
            'identical': self.identical,
            'adb_stream_identical': self.adb_stream_identical,
            'identity': self.identity,
            'findings': [asdict(f) for f in self.findings],
            'elf_summary': self.elf_summary,
            'decision': self.effective_decision(),
        }
        return sha256(json.dumps(payload, sort_keys=True).encode('utf-8'))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


# --------------------------------------------------------------------------
# APK framing & trust

def decompress_adb_stream(data):
    """Decompress an APK v3 ADB stream to raw uncompressed ADB bytes.

    Returns (bytes, format_name) on a complete, valid stream, or (None, reason)
    if the container framing is unsupported, truncated, or has trailing bytes.
    """
    if len(data) < 4:
        return None, 'truncated'
    magic = data[:4]
    if magic == b'ADB.':
        return data, 'adb-raw'
    if magic == b'ADBd':
        decompressor = zlib.decompressobj(-15)
        try:
            uncompressed = decompressor.decompress(data[4:]) + decompressor.flush()
        except zlib.error as error:
            return None, f'deflate-error:{error}'
        if not decompressor.eof or decompressor.unused_data:
            return None, 'incomplete-or-trailing-deflate-stream'
        if not uncompressed.startswith(b'ADB.'):
            return None, 'non-adb-inner-stream'
        return uncompressed, 'adb-deflate'
    return None, f'unsupported-magic:{magic!r}'


def adb_streams_identical(old_path, new_path):
    """True when both files decode cleanly to the exact same uncompressed ADB stream."""
    old_stream, _ = decompress_adb_stream(Path(old_path).read_bytes())
    if old_stream is None:
        return False
    new_stream, _ = decompress_adb_stream(Path(new_path).read_bytes())
    if new_stream is None:
        return False
    return old_stream == new_stream


def verify_package(apk, keys_dir, package):
    result = subprocess.run(
        [str(apk), 'verify', '--keys-dir', str(keys_dir), str(package)],
        capture_output=True, text=True)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def inspect_trust(apk, old, new, keys_dir=None):
    """Check APK signatures against keys_dir (or repository public-key.pem if present)."""
    if keys_dir is not None:
        keys = Path(keys_dir)
        key_files = sorted(p for p in keys.iterdir() if p.is_file()) if keys.is_dir() else []
        key_sha = sha256(b''.join(p.read_bytes() for p in key_files)) if key_files else ''
        old_ok, old_err = verify_package(apk, keys, old)
        new_ok, new_err = verify_package(apk, keys, new)
        errors = []
        if not old_ok:
            errors.append(f'old signature failed: {old_err}')
        if not new_ok:
            errors.append(f'new signature failed: {new_err}')
        return {
            'mode': 'keys_dir',
            'enforced': True,
            'verified': old_ok and new_ok,
            'old_verified': old_ok,
            'new_verified': new_ok,
            'key_sha256': key_sha,
            'errors': errors,
        }
    if PUBLIC_KEY.is_file():
        with tempfile.TemporaryDirectory(prefix='diagnose-keys-') as tmp:
            key_dest = Path(tmp) / 'public-key.pem'
            shutil.copyfile(PUBLIC_KEY, key_dest)
            old_ok, old_err = verify_package(apk, tmp, old)
            new_ok, new_err = verify_package(apk, tmp, new)
            errors = []
            if not old_ok:
                errors.append(f'old signature unverified: {old_err}')
            if not new_ok:
                errors.append(f'new signature unverified: {new_err}')
            return {
                'mode': 'repo_public_key',
                'enforced': False,
                'verified': old_ok and new_ok,
                'old_verified': old_ok,
                'new_verified': new_ok,
                'key_sha256': file_sha256(PUBLIC_KEY),
                'errors': errors,
            }
    return {
        'mode': 'untrusted',
        'enforced': False,
        'verified': False,
        'old_verified': False,
        'new_verified': False,
        'key_sha256': '',
        'errors': ['no trust keys configured'],
    }


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
        table[name + '/'] = {k: v for k, v in directory.items() if k not in ('name', 'files')}
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
                                    f'{new_info.get(key)!r}', code='info_changed'))

    old_scripts, new_scripts = old.get('scripts', {}), new.get('scripts', {})
    for key in sorted(set(old_scripts) | set(new_scripts)):
        if old_scripts.get(key) != new_scripts.get(key):
            findings.append(Finding(CHANGE, f'(script {key})', 'install script changed',
                                    text_diff(old_scripts.get(key, ''), new_scripts.get(key, '')),
                                    code='script_changed'))

    if old.get('triggers') != new.get('triggers'):
        findings.append(Finding(CHANGE, '(triggers)',
                                f'triggers: {old.get("triggers")!r} -> {new.get("triggers")!r}',
                                code='triggers_changed'))

    if old.get('replaces-priority') != new.get('replaces-priority'):
        findings.append(Finding(CHANGE, '(replaces-priority)',
                                f'replaces-priority: {old.get("replaces-priority")!r} -> '
                                f'{new.get("replaces-priority")!r}',
                                code='replaces_priority_changed'))

    extra_keys = (set(old.keys()) | set(new.keys())) - KNOWN_TOP_LEVEL_KEYS
    for key in sorted(extra_keys):
        if old.get(key) != new.get(key):
            findings.append(Finding(UNKNOWN, f'({key})',
                                    f'unrecognized top-level ADB field {key!r} changed: '
                                    f'{old.get(key)!r} -> {new.get(key)!r}',
                                    code='unknown_adb_field'))

    old_files, new_files = file_table(old), file_table(new)
    for path in sorted(set(old_files) - set(new_files)):
        findings.append(Finding(CHANGE, path, 'removed', code='file_removed'))
    for path in sorted(set(new_files) - set(old_files)):
        findings.append(Finding(CHANGE, path, 'added', code='file_added'))
    changed = []
    for path in sorted(set(old_files) & set(new_files)):
        a, b = old_files[path], new_files[path]
        for key in sorted((set(a) | set(b)) - {'hash', 'size'}):
            if a.get(key) != b.get(key):
                if key == 'mtime':
                    verdict, code = BENIGN, 'mtime_changed'
                elif key == 'target':
                    verdict, code = CHANGE, 'symlink_target_changed'
                else:
                    verdict, code = CHANGE, f'attr_{key}_changed'
                findings.append(Finding(verdict, path, f'{key}: {a.get(key)!r} -> {b.get(key)!r}',
                                        code=code))
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
            if phoff and phnum:
                extent = phoff + phnum * phentsize
                if base + extent <= len(data):
                    return {'endian': end, 'class': klass, 'size': len(data) - base,
                            'sections': [], 'missing_sections': True}
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
    return {'endian': end, 'class': klass, 'size': extent, 'sections': sections,
            'missing_sections': False}


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
            if old and new and not old.get('missing_sections') and not new.get('missing_sections'):
                if position + old['size'] >= region[1]:
                    return position, old['size'], new['size']
        end = position + 3


def classify_elf_role(path, facts):
    """Classify an ELF binary into executable, public_shared_lib, plugin, private_shared_lib, or other."""
    e_type = facts.get('e_type')
    if e_type == 'ET_REL':
        return 'relocatable'
    soname = facts.get('dt_soname')
    interp = facts.get('pt_interp')
    pie = bool(facts.get('dt_flags_1', 0) & DF_1_PIE)
    norm = '/' + path.lstrip('/')
    parent = str(Path(path).parent).lstrip('./')
    if (interp or pie or e_type == 'ET_EXEC') and not soname:
        return 'executable'
    if e_type == 'ET_DYN':
        if any(fragment in norm for fragment in PLUGIN_PATH_FRAGMENTS):
            return 'plugin'
        if soname and parent in PUBLIC_LIB_DIRS:
            return 'public_shared_lib'
        if not soname:
            return 'plugin'
        return 'private_shared_lib'
    return 'other'


def inspect_loadable_elf(path, data):
    """Extract ELF header, program headers, dynamic table, and versioned symbols."""
    if not HAVE_ELFTOOLS:
        return None
    try:
        ef = ELFFile(io.BytesIO(data))
        header = ef.header
        facts = {
            'sha256': sha256(data),
            'size': len(data),
            'e_type': str(header['e_type']),
            'e_machine': str(header['e_machine']),
            'ei_class': str(header['e_ident']['EI_CLASS']),
            'ei_data': str(header['e_ident']['EI_DATA']),
            'ei_osabi': str(header['e_ident']['EI_OSABI']),
            'e_flags': int(header['e_flags']),
            'missing_sections': ef.num_sections() == 0,
            'duplicate_sections': sorted(
                name for name, count in Counter(s.name for s in ef.iter_sections() if s.name).items()
                if count > 1),
            'pt_interp': None,
            'pt_load_flags': [],
            'pt_gnu_stack_flags': None,
            'pt_gnu_relro': False,
            'dt_needed': [],
            'dt_soname': None,
            'dt_rpath': [],
            'dt_runpath': [],
            'dt_flags': 0,
            'dt_flags_1': 0,
            'verneed': [],
            'verdef': [],
            'exported_symbols': {},
            'imported_symbols': {},
            'has_dynamic': False,
        }
        for segment in ef.iter_segments():
            p_type = segment['p_type']
            if p_type == 'PT_INTERP':
                facts['pt_interp'] = segment.get_interp_name()
            elif p_type == 'PT_LOAD':
                facts['pt_load_flags'].append(int(segment['p_flags']))
            elif p_type == 'PT_GNU_STACK':
                facts['pt_gnu_stack_flags'] = int(segment['p_flags'])
            elif p_type == 'PT_GNU_RELRO':
                facts['pt_gnu_relro'] = True
            elif isinstance(segment, DynamicSegment):
                facts['has_dynamic'] = True
                for tag in segment.iter_tags():
                    dt = tag.entry.d_tag
                    if dt == 'DT_NEEDED':
                        facts['dt_needed'].append(tag.needed)
                    elif dt == 'DT_SONAME':
                        facts['dt_soname'] = tag.soname
                    elif dt == 'DT_RPATH':
                        facts['dt_rpath'].extend(tag.rpath.split(':'))
                    elif dt == 'DT_RUNPATH':
                        facts['dt_runpath'].extend(tag.runpath.split(':'))
                    elif dt == 'DT_FLAGS':
                        facts['dt_flags'] |= int(tag.entry.d_val)
                    elif dt == 'DT_FLAGS_1':
                        facts['dt_flags_1'] |= int(tag.entry.d_val)

        # Parse GNU symbol versions semantically (by library/version name, not index).
        ver_by_index = {}
        verneed_entries = []
        verdef_entries = []
        versym_sec = None
        dynsym_sec = None
        for sec in ef.iter_sections():
            if isinstance(sec, GNUVerNeedSection):
                for verneed, vernaux_iter in sec.iter_versions():
                    lib = verneed.name
                    for aux in vernaux_iter:
                        idx = int(aux['vna_other']) & 0x7fff
                        ver_by_index[idx] = (lib, aux.name)
                        verneed_entries.append((lib, aux.name, int(aux['vna_flags'])))
            elif isinstance(sec, GNUVerDefSection):
                for verdef, verdaux_iter in sec.iter_versions():
                    aux_list = list(verdaux_iter)
                    if aux_list:
                        idx = int(verdef['vd_ndx']) & 0x7fff
                        ver_by_index[idx] = ('', aux_list[0].name)
                        verdef_entries.append((aux_list[0].name, int(verdef['vd_flags'])))
            elif isinstance(sec, GNUVerSymSection):
                versym_sec = sec
            elif isinstance(sec, SymbolTableSection) and sec.name == '.dynsym':
                dynsym_sec = sec
        facts['verneed'] = sorted(verneed_entries)
        facts['verdef'] = sorted(verdef_entries)

        if dynsym_sec is not None:
            for index, sym in enumerate(dynsym_sec.iter_symbols()):
                name = sym.name
                if not name:
                    continue
                st_info = sym['st_info']
                st_bind = str(st_info['bind'])
                st_type = str(st_info['type'])
                st_vis = str(sym['st_other']['visibility'])
                shndx = sym['st_shndx']
                ver_name = ''
                is_default = True
                if versym_sec is not None and index < versym_sec.num_symbols():
                    raw_ver = versym_sec.get_symbol(index)['ndx']
                    if raw_ver in ('VER_NDX_LOCAL', 'VER_NDX_GLOBAL', 0, 1):
                        ver_name = ''
                    elif isinstance(raw_ver, int):
                        is_default = not bool(raw_ver & 0x8000)
                        ver_idx = raw_ver & 0x7fff
                        info = ver_by_index.get(ver_idx)
                        ver_name = info[1] if info else f'<idx:{ver_idx}>'
                    else:
                        ver_name = str(raw_ver)
                key = f'{name}@@{ver_name}' if (ver_name and is_default) else (
                    f'{name}@{ver_name}' if ver_name else name)
                if shndx == 'SHN_UNDEF':
                    facts['imported_symbols'][key] = {
                        'type': st_type,
                        'bind': st_bind,
                        'visibility': st_vis,
                    }
                elif st_bind != 'STB_LOCAL' and st_vis in ('STV_DEFAULT', 'STV_PROTECTED'):
                    entry = {
                        'type': st_type,
                        'bind': st_bind,
                        'visibility': st_vis,
                    }
                    if st_type in ('STT_OBJECT', 'STT_TLS'):
                        entry['size'] = int(sym['st_size'])
                    facts['exported_symbols'][key] = entry
        facts['role'] = classify_elf_role(path, facts)
        return facts
    except (ELFError, OSError, ValueError, KeyError, IndexError, struct.error):
        return None


def dt_needed_diff_lines(old_list, new_list):
    lines = []
    max_len = max(len(old_list), len(new_list))
    for i in range(max_len):
        a = old_list[i] if i < len(old_list) else '<none>'
        b = new_list[i] if i < len(new_list) else '<none>'
        if a != b:
            lines.append(f'pos {i + 1}: {a} -> {b}')
    return lines


DERIVED_SECTIONS = {'.note.gnu.build-id', '.note.go.buildid', '.gnu_debuglink'}
ID_SECTIONS = {'.BTF.ext', '.rel.BTF', '.rel.BTF.ext'}
IMPL_DERIVED_SECTIONS = {'.gnu.version_r', '.gnu.version_d', '.gnu.version', '.dynstr', '.dynamic'}


def analyze_elf(path, a, b, depth, elf_summaries=None, abi_store=None, expected_abi_tool_version=None):
    old, new = parse_elf(a), parse_elf(b)
    if old is None or new is None:
        return [Finding(UNKNOWN, path, 'ELF header could not be parsed (truncated or malformed)',
                        code='elf_parse_error')]
    findings = []
    # Check loadable ELF dynamic/program-header contract at top level.
    load_old = inspect_loadable_elf(path, a) if depth == 0 else None
    load_new = inspect_loadable_elf(path, b) if depth == 0 else None
    loadable = (load_old is not None and load_new is not None
                and (load_old['has_dynamic'] or load_new['has_dynamic']
                     or load_old['e_type'] in ('ET_EXEC', 'ET_DYN')
                     or load_new['e_type'] in ('ET_EXEC', 'ET_DYN')))

    elf_record = None
    verneed_semantically_identical = False
    if loadable:
        role = load_new['role'] if load_old['role'] == load_new['role'] else f'{load_old["role"]}->{load_new["role"]}'
        contract_issues = []
        incompatible = False
        for field_name in ('e_machine', 'ei_class', 'ei_data', 'ei_osabi', 'e_type'):
            if load_old[field_name] != load_new[field_name]:
                incompatible = True
                contract_issues.append(f'{field_name}: {load_old[field_name]} -> {load_new[field_name]}')
                findings.append(Finding(
                    UNKNOWN, path,
                    f'ELF header {field_name} changed: {load_old[field_name]} -> {load_new[field_name]}',
                    code='elf_incompatible_header'))
        for field_name in ('e_flags', 'pt_interp', 'pt_load_flags', 'pt_gnu_stack_flags',
                           'pt_gnu_relro', 'dt_soname', 'dt_rpath', 'dt_runpath',
                           'dt_flags', 'dt_flags_1'):
            if load_old[field_name] != load_new[field_name]:
                contract_issues.append(f'{field_name}: {load_old[field_name]!r} -> {load_new[field_name]!r}')
                findings.append(Finding(
                    UNKNOWN, path,
                    f'ELF load contract {field_name} changed: {load_old[field_name]!r} -> {load_new[field_name]!r}',
                    code=f'elf_{field_name}_changed'))
        if load_old['missing_sections'] or load_new['missing_sections']:
            contract_issues.append('missing_section_headers')
            findings.append(Finding(
                UNKNOWN, path, 'ELF is missing section header table',
                code='elf_missing_sections'))
        if load_old['duplicate_sections'] or load_new['duplicate_sections']:
            dups = sorted(set(load_old['duplicate_sections']) | set(load_new['duplicate_sections']))
            contract_issues.append(f'duplicate_sections:{dups}')
            findings.append(Finding(
                UNKNOWN, path, f'ELF has duplicate section names: {", ".join(dups)}',
                code='elf_duplicate_sections'))

        dt_needed_status = 'identical'
        if load_old['dt_needed'] != load_new['dt_needed']:
            if Counter(load_old['dt_needed']) == Counter(load_new['dt_needed']):
                dt_needed_status = 'reordered'
                diff_lines = dt_needed_diff_lines(load_old['dt_needed'], load_new['dt_needed'])
                contract_issues.append('dt_needed_reordered')
                findings.append(Finding(
                    UNKNOWN, path,
                    f'DT_NEEDED load order changed ({len(load_old["dt_needed"])} entries, '
                    f'{len(diff_lines)} position(s) differ)',
                    diff_lines,
                    code='dt_needed_order_changed'))
            else:
                dt_needed_status = 'changed'
                old_c, new_c = Counter(load_old['dt_needed']), Counter(load_new['dt_needed'])
                removed = list((old_c - new_c).elements())
                added = list((new_c - old_c).elements())
                contract_issues.append('dt_needed_changed')
                findings.append(Finding(
                    CHANGE, path,
                    f'DT_NEEDED entries changed (removed={removed}, added={added})',
                    dt_needed_diff_lines(load_old['dt_needed'], load_new['dt_needed']),
                    code='dt_needed_changed'))

        verneed_semantically_identical = (load_old['verneed'] == load_new['verneed'])
        if not verneed_semantically_identical:
            old_v, new_v = set(load_old['verneed']), set(load_new['verneed'])
            contract_issues.append('verneed_changed')
            findings.append(Finding(
                UNKNOWN, path,
                f'GNU symbol version requirements changed '
                f'(removed={len(old_v - new_v)}, added={len(new_v - old_v)})',
                [f'- {x}' for x in sorted(old_v - new_v)[:8]] +
                [f'+ {x}' for x in sorted(new_v - old_v)[:8]],
                code='verneed_changed'))
        if load_old['verdef'] != load_new['verdef']:
            contract_issues.append('verdef_changed')
            findings.append(Finding(
                UNKNOWN, path, 'GNU symbol version definitions changed',
                code='verdef_changed'))

        exp_old, exp_new = load_old['exported_symbols'], load_new['exported_symbols']
        if exp_old != exp_new:
            removed = sorted(set(exp_old) - set(exp_new))
            added = sorted(set(exp_new) - set(exp_old))
            modified = sorted(k for k in set(exp_old) & set(exp_new) if exp_old[k] != exp_new[k])
            contract_issues.append('exported_symbols_changed')
            lines = ([f'- {k}' for k in removed[:8]] +
                     [f'+ {k}' for k in added[:8]] +
                     [f'~ {k}: {exp_old[k]} -> {exp_new[k]}' for k in modified[:8]])
            findings.append(Finding(
                UNKNOWN, path,
                f'exported dynamic symbols changed (removed={len(removed)}, '
                f'added={len(added)}, modified={len(modified)})',
                lines,
                code='exported_symbols_changed'))

        imp_old, imp_new = load_old['imported_symbols'], load_new['imported_symbols']
        if imp_old != imp_new:
            removed = sorted(set(imp_old) - set(imp_new))
            added = sorted(set(imp_new) - set(imp_old))
            modified = sorted(k for k in set(imp_old) & set(imp_new) if imp_old[k] != imp_new[k])
            contract_issues.append('imported_symbols_changed')
            lines = ([f'- {k}' for k in removed[:8]] +
                     [f'+ {k}' for k in added[:8]] +
                     [f'~ {k}: {imp_old[k]} -> {imp_new[k]}' for k in modified[:8]])
            findings.append(Finding(
                UNKNOWN, path,
                f'imported dynamic symbols changed (removed={len(removed)}, '
                f'added={len(added)}, modified={len(modified)})',
                lines,
                code='imported_symbols_changed'))

        elf_record = {
            'path': path,
            'role': role,
            'old_sha256': load_old['sha256'],
            'new_sha256': load_new['sha256'],
            'dt_soname': load_new['dt_soname'],
            'pt_interp': load_new['pt_interp'],
            'dt_needed_status': dt_needed_status,
            'old_dt_needed': load_old['dt_needed'],
            'new_dt_needed': load_new['dt_needed'],
            'verneed_identical': verneed_semantically_identical,
            'exported_symbol_count': len(exp_new),
            'exported_symbols_identical': exp_old == exp_new,
            'imported_symbols_identical': imp_old == imp_new,
            'old_exported_symbols': sorted(exp_old.keys()),
            'new_exported_symbols': sorted(exp_new.keys()),
            'incompatible': incompatible,
            'contract_issues': contract_issues,
            'changed_sections': [],
            'type_abi': {'status': 'not_collected', 'phase': 'phase2a'},
        }

    # Section-level comparison (when section headers exist).
    if old.get('missing_sections') or new.get('missing_sections'):
        if elf_record is not None and elf_summaries is not None:
            elf_summaries.append(elf_record)
        return findings

    old_sections = {s['name']: s for s in old['sections']}
    new_sections = {s['name']: s for s in new['sections']}
    if [s['name'] for s in old['sections']] != [s['name'] for s in new['sections']]:
        added = sorted(set(new_sections) - set(old_sections))
        removed = sorted(set(old_sections) - set(new_sections))
        findings.append(Finding(CHANGE, path, 'ELF section list changed',
                                [f'added: {", ".join(added) or "-"}',
                                 f'removed: {", ".join(removed) or "-"}'],
                                code='elf_section_list_changed'))
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
                                    'are identical', code='elf_header_or_padding_diff'))
        if elf_record is not None and elf_summaries is not None:
            elf_summaries.append(elf_record)
        return findings

    if elf_record is not None:
        elf_record['changed_sections'] = sorted(name for name, *_ in differing)

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
                                    if len(differing) > 1 else 'only the build identifier differs',
                                    code='derived_build_id'))
            continue
        if name in ID_SECTIONS and btf_reordered:
            findings.append(Finding(BENIGN, label, 'BTF type IDs renumbered with the type order',
                                    code='btf_id_renumber'))
            continue
        if name == '.gnu.version_r' and verneed_semantically_identical:
            findings.append(Finding(
                BENIGN, label,
                'raw .gnu.version_r layout changed but semantic version requirements are identical',
                code='verneed_layout_only'))
            continue
        if name == '.go.buildinfo':
            findings.append(go_buildinfo(label, a, b))
            continue
        if len(sa) != len(sb):
            findings.append(Finding(UNKNOWN, label, f'section size {len(sa)} -> {len(sb)} '
                                    'bytes; code or data changed', code='elf_section_size_diff'))
            continue
        findings.extend(analyze_regions(label, sa, sb, depth, section_name=name))

    if elf_record is not None:
        if elf_record['role'] == 'public_shared_lib':
            if abi_store is not None:
                abi_res = ELF_TYPE_ABI.compare_type_abi(
                    elf_record['old_sha256'], elf_record['new_sha256'],
                    elf_record['old_exported_symbols'], elf_record['new_exported_symbols'],
                    abi_store, expected_tool_version=expected_abi_tool_version)
                elf_record['type_abi'] = abi_res
                if abi_res['status'] == 'abi_incompatible_change':
                    elf_record['incompatible'] = True
                    elf_record['contract_issues'].append('type_abi_incompatible')
                    findings.append(Finding(
                        UNKNOWN, path,
                        f'public type ABI incompatible change detected '
                        f'({len(abi_res.get("changes", []))} change(s))',
                        [json.dumps(c, sort_keys=True)[:160] for c in abi_res.get('changes', [])[:6]],
                        code='type_abi_incompatible'))
                elif abi_res['status'] != 'verified_compatible':
                    findings.append(Finding(
                        UNKNOWN, path,
                        f'public shared library type ABI evidence insufficient '
                        f'({abi_res["status"]})',
                        code='missing_type_abi_evidence'))
            else:
                findings.append(Finding(
                    UNKNOWN, path,
                    'public shared library ELF changed without out-of-APK type ABI evidence (Phase 2a)',
                    code='missing_type_abi_evidence'))
        elif (elf_record['role'] == 'executable'
              and not elf_record['contract_issues']
              and elf_record['exported_symbol_count'] == 0
              and any(f.verdict == UNKNOWN for f in findings)):
            findings.append(Finding(
                UNKNOWN, path,
                'executable implementation bytes changed (no public ABI; load/import checks passed; '
                'requires review or isolated cold rebuild evidence before allocation)',
                code='executable_impl_changed_phase1_review'))
        elif elf_record['role'] in ('plugin', 'private_shared_lib') and any(
                f.verdict == UNKNOWN for f in findings):
            findings.append(Finding(
                UNKNOWN, path,
                f'{elf_record["role"]} ELF changed; external plugin/private contract is not verified',
                code='plugin_or_private_lib_review'))
        if elf_summaries is not None:
            elf_summaries.append(elf_record)
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
        findings.append(Finding(UNKNOWN, label, f'bytes differ{where}', lines,
                                code='binary_bytes_differ'))
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
        return Finding(UNKNOWN, label, 'Go build information differs (no go tool to decode it)',
                       code='go_buildinfo_no_tool')
    with tempfile.TemporaryDirectory() as temporary:
        outputs = []
        for name, data in (('old', a), ('new', b)):
            binary = Path(temporary) / name
            binary.write_bytes(data)
            result = subprocess.run([str(go), 'version', '-m', str(binary)],
                                    capture_output=True, text=True)
            outputs.append(result.stdout.replace(str(binary), name))
    return Finding(CHANGE, label, 'Go build information differs (toolchain, modules or '
                   'build settings)', text_diff(*outputs), code='go_buildinfo_changed')


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
        return Finding(UNKNOWN, label, 'BTF differs and could not be decoded', code='btf_decode_error')
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
                        'first moved: ' + (', '.join(names) or '(anonymous types)')],
                       code='btf_reordered')
    removed = list((Counter(old_sig) - Counter(new_sig)).elements())
    added = list((Counter(new_sig) - Counter(old_sig)).elements())
    lines = [f'- {s[:160]}' for s in removed[:6]] + [f'+ {s[:160]}' for s in added[:6]]
    return Finding(CHANGE, label, f'BTF type definitions changed ({len(removed)} removed, '
                   f'{len(added)} added): the BPF program sees different types', lines,
                   code='btf_types_changed')


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


def is_timestamp_only_text_diff(a_bytes, b_bytes):
    """True only when masking date/time substrings makes the entire texts byte-identical."""
    masked_a = TIMESTAMP.sub(b'<TIMESTAMP>', a_bytes)
    masked_b = TIMESTAMP.sub(b'<TIMESTAMP>', b_bytes)
    return masked_a == masked_b and masked_a != a_bytes and masked_b != b_bytes


def analyze_gzip(path, a, b, depth):
    try:
        ua, ub = gzip.decompress(a), gzip.decompress(b)
    except (OSError, EOFError):
        return [Finding(UNKNOWN, path, 'gzip stream differs and could not be decompressed',
                        code='gzip_decompress_error')]
    if ua == ub:
        mtime_a, mtime_b = struct.unpack_from('<I', a, 4)[0], struct.unpack_from('<I', b, 4)[0]
        detail = (f'gzip header only (mtime {mtime_a} -> {mtime_b})' if mtime_a != mtime_b
                  else 'gzip compression bytes only; decompressed content is identical')
        return [Finding(BENIGN, path, detail, code='gzip_header_only')]
    return analyze_content(f'{path} (decompressed)', ua, ub, depth + 1)


def analyze_zip(path, a, b, depth):
    try:
        za, zb = zipfile.ZipFile(io.BytesIO(a)), zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile:
        return None
    findings = []
    counts_a, counts_b = Counter(za.namelist()), Counter(zb.namelist())
    dups_a = sorted(n for n, c in counts_a.items() if c > 1)
    dups_b = sorted(n for n, c in counts_b.items() if c > 1)
    if dups_a or dups_b:
        findings.append(Finding(
            UNKNOWN, path,
            f'zip archive contains duplicate entries (old={dups_a}, new={dups_b})',
            code='zip_duplicate_entries'))
        return findings
    names_a, names_b = set(counts_a), set(counts_b)
    for name in sorted(names_a ^ names_b):
        findings.append(Finding(CHANGE, f'{path}!{name}', 'added' if name in names_b
                                else 'removed', code='zip_entry_membership'))
    for name in sorted(names_a & names_b):
        ia, ib = za.getinfo(name), zb.getinfo(name)
        mode_a, mode_b = (ia.external_attr >> 16) & 0xffff, (ib.external_attr >> 16) & 0xffff
        if mode_a != mode_b:
            findings.append(Finding(
                CHANGE, f'{path}!{name}',
                f'zip entry mode changed: 0o{mode_a:o} -> 0o{mode_b:o}',
                code='zip_entry_mode'))
        ca, cb = za.read(name), zb.read(name)
        if ca != cb:
            findings.extend(analyze_content(f'{path}!{name}', ca, cb, depth + 1))
    if not findings:
        findings.append(Finding(BENIGN, path, 'zip entry timestamps or order only; every '
                                'entry has identical content and permissions',
                                code='zip_timestamps_only'))
    return findings


def analyze_pyc(path, a, b):
    if len(a) < 16 or len(b) < 16 or a[:4] != b[:4]:
        return None
    flags, = struct.unpack_from('<I', a, 4)
    if flags == 0 and a[:8] == b[:8] and a[16:] == b[16:]:
        return [Finding(BENIGN, path, 'pyc header records a different source mtime/size; '
                        'the bytecode is identical', code='pyc_mtime_only')]
    return None


def analyze_content(path, a, b, depth=0, elf_summaries=None, abi_store=None,
                    expected_abi_tool_version=None):
    if a == b:
        return []
    if a[:4] == b'\x7fELF' or b[:4] == b'\x7fELF':
        if a[:4] == b[:4] == b'\x7fELF':
            return analyze_elf(path, a, b, depth, elf_summaries=elf_summaries,
                               abi_store=abi_store,
                               expected_abi_tool_version=expected_abi_tool_version)
        return [Finding(UNKNOWN, path, 'only one side is an ELF binary', code='elf_type_mismatch')]
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
        if is_timestamp_only_text_diff(a, b):
            return [Finding(BENIGN, path, 'text differs only in embedded date/time tokens '
                            '(likely a build timestamp)', lines, code='text_timestamp_only')]
        return [Finding(CHANGE, path, 'text content changed', lines, code='text_changed')]
    if len(a) != len(b):
        return [Finding(UNKNOWN, path, f'binary size {len(a)} -> {len(b)} bytes',
                        code='binary_size_changed')]
    return analyze_regions(path, a, b, depth)


# --------------------------------------------------------------------------
# Decision engine

IMPL_ONLY_CODES = {
    'binary_bytes_differ',
    'elf_section_size_diff',
    'executable_impl_changed_phase1_review',
    'elf_header_or_padding_diff',
}


def _elf_eligible_after_cold_rebuild(elf_record):
    if elf_record.get('incompatible') or elf_record.get('contract_issues'):
        return False
    if elf_record.get('role') == 'executable' and elf_record.get('exported_symbol_count') == 0:
        return True
    if (elf_record.get('role') == 'public_shared_lib'
            and isinstance(elf_record.get('type_abi'), dict)
            and elf_record['type_abi'].get('status') == 'verified_compatible'):
        return True
    return False


def evaluate_decision(report):
    """Compute the versioned release-action decision from all findings and evidence."""
    base = {
        'analyzer_version': ANALYZER_VERSION,
        'policy_version': POLICY_VERSION,
        'reasons': [],
        'blockers': [],
        'unresolved': [],
    }
    if report.identical:
        return {**base, 'action': ACTION_KEEP_EXISTING, 'reasons': ['identical_apk_bytes']}

    if report.trust.get('enforced') and not report.trust.get('verified'):
        errors = report.trust.get('errors') or ['signature verification failed']
        return {**base, 'action': ACTION_REJECT, 'reasons': ['untrusted_signature'],
                'blockers': list(errors)}

    if (isinstance(report.reproducibility, dict)
            and report.reproducibility.get('status') == 'payload_drift'):
        return {**base, 'action': ACTION_REJECT, 'reasons': ['cold_rebuild_payload_drift'],
                'blockers': [report.reproducibility.get('first_finding')
                             or 'isolated cold rebuild produced different payload bytes']}

    if (isinstance(report.reproducibility, dict)
            and report.reproducibility.get('status') == 'skipped_high_cost_recipe'):
        unresolved = [
            {'path': f.path, 'detail': f.detail, 'code': f.code or 'unknown'}
            for f in report.findings if f.verdict == UNKNOWN
        ]
        reasons = sorted({'high_cost_cold_rebuild_blocked', *(u['code'] for u in unresolved)})
        blockers = [report.reproducibility.get('reason')
                    or 'high-cost recipe blocked from automatic cold rebuild by default']
        blockers.extend(f'{u["path"]}: {u["detail"]}' for u in unresolved)
        return {**base, 'action': ACTION_REVIEW, 'reasons': reasons,
                'blockers': blockers, 'unresolved': unresolved}

    incompatible_elfs = [e for e in report.elf_summary if e.get('incompatible')]
    if incompatible_elfs:
        reasons = ['type_abi_incompatible' if any(
            'type_abi_incompatible' in e.get('contract_issues', []) for e in incompatible_elfs)
            else 'incompatible_elf_header']
        return {**base, 'action': ACTION_REJECT, 'reasons': reasons,
                'blockers': [f'{e["path"]}: {", ".join(e["contract_issues"])}'
                             for e in incompatible_elfs]}

    if report.adb_stream_identical and report.trust.get('verified') and not report.findings:
        return {**base, 'action': ACTION_REUSE_PUBLISHED,
                'reasons': ['identical_adb_stream_outer_framing_only']}

    unresolved = [
        {'path': f.path, 'detail': f.detail, 'code': f.code or 'unknown'}
        for f in report.findings if f.verdict == UNKNOWN
    ]
    if unresolved:
        # Phase 2: if an isolated cold rebuild reproduced the candidate AND every
        # unresolved finding is an implementation-only diff on an eligible ELF
        # (executable with no public ABI, or public_shared_lib with verified
        # compatible type ABI), allow automatic release allocation.
        cold_ok = (isinstance(report.reproducibility, dict)
                   and report.reproducibility.get('reproducible') is True)
        if (cold_ok and report.elf_summary
                and all(_elf_eligible_after_cold_rebuild(e) for e in report.elf_summary)
                and all(u['code'] in IMPL_ONLY_CODES for u in unresolved)):
            elf_paths = tuple(e['path'] for e in report.elf_summary)
            if all(u['path'] in elf_paths or u['path'].startswith(tuple(p + ' [' for p in elf_paths))
                   for u in unresolved):
                reason = ('public_lib_impl_reproduced_abi_verified'
                          if any(e['role'] == 'public_shared_lib' for e in report.elf_summary)
                          else 'executable_impl_reproduced')
                return {**base, 'action': ACTION_ALLOCATE_RELEASE, 'reasons': [reason]}

        reasons = sorted({u['code'] for u in unresolved})
        return {**base, 'action': ACTION_REVIEW, 'reasons': reasons,
                'blockers': [f'{u["path"]}: {u["detail"]}' for u in unresolved],
                'unresolved': unresolved}

    verdicts = {f.verdict for f in report.findings}
    if not verdicts:
        return {**base, 'action': ACTION_REVIEW, 'reasons': ['unexplained_difference'],
                'blockers': ['APK bytes differ with no classified findings']}
    if verdicts == {BENIGN}:
        return {**base, 'action': ACTION_BENIGN, 'reasons': ['benign_nondeterminism_only']}
    if CHANGE in verdicts:
        return {**base, 'action': ACTION_ALLOCATE_RELEASE,
                'reasons': sorted({f.code or 'content_changed' for f in report.findings
                                   if f.verdict == CHANGE})}
    return {**base, 'action': ACTION_REVIEW, 'reasons': ['unclassified']}


# --------------------------------------------------------------------------
# Packages

def extract(apk, package, destination, keys_dir=None):
    cmd = [str(apk), 'extract', '--no-chown', '--destination', str(destination)]
    if keys_dir is not None:
        cmd.extend(['--keys-dir', str(keys_dir)])
    else:
        cmd.append('--allow-untrusted')
    cmd.append(str(package))
    subprocess.run(cmd, check=True, capture_output=True)


def diagnose(old, new, apk=APK, keys_dir=None, context=None, abi_store=None,
             expected_abi_tool_version=None, cold_evidence=None):
    old, new = Path(old), Path(new)
    old_data, new_data = old.read_bytes(), new.read_bytes()
    old_digest, new_digest = sha256(old_data), sha256(new_data)
    trust = inspect_trust(apk, old, new, keys_dir=keys_dir)
    report = Report(
        str(old), str(new),
        old_sha256=old_digest,
        new_sha256=new_digest,
        trust=trust,
        identity=dict(context) if context else {},
    )
    if cold_evidence is not None:
        report.reproducibility = dict(cold_evidence)
        if 'input_sha256' in cold_evidence:
            report.build_provenance = {
                'status': 'collected',
                'input_sha256': cold_evidence['input_sha256'],
                'inputs_stable': cold_evidence.get('inputs_stable', True),
            }
    if old_data == new_data:
        report.identical = True
        report.adb_stream_identical = True
        report.decision = evaluate_decision(report)
        return report

    if trust.get('enforced') and not trust.get('verified'):
        report.findings.append(Finding(
            UNKNOWN, '(signature)', '; '.join(trust.get('errors') or ['signature check failed']),
            code='signature_verification_failed'))
        report.decision = evaluate_decision(report)
        return report

    old_stream, old_fmt = decompress_adb_stream(old_data)
    new_stream, new_fmt = decompress_adb_stream(new_data)
    if old_stream is not None and new_stream is not None and old_stream == new_stream:
        report.adb_stream_identical = True

    old_meta, new_meta = adbdump(apk, old), adbdump(apk, new)
    old_info, new_info = old_meta.get('info', {}), new_meta.get('info', {})
    report.identity.setdefault('name', new_info.get('name') or old_info.get('name'))
    report.identity.setdefault('old_version', old_info.get('version'))
    report.identity.setdefault('new_version', new_info.get('version'))
    report.identity.setdefault('arch', new_info.get('arch') or old_info.get('arch'))

    if report.adb_stream_identical and trust.get('verified'):
        report.decision = evaluate_decision(report)
        return report

    findings, changed = compare_metadata(old_meta, new_meta)
    report.findings.extend(findings)
    if changed:
        with tempfile.TemporaryDirectory(prefix='diagnose-apk-') as temporary:
            roots = Path(temporary) / 'old', Path(temporary) / 'new'
            extract_keys = keys_dir if trust.get('verified') and keys_dir is not None else None
            for root, package in zip(roots, (old, new)):
                root.mkdir()
                extract(apk, package, root, keys_dir=extract_keys)
            for path in changed:
                a_path, b_path = roots[0] / path, roots[1] / path
                if a_path.is_symlink() or b_path.is_symlink():
                    a_target = os.readlink(a_path) if a_path.is_symlink() else '<not-symlink>'
                    b_target = os.readlink(b_path) if b_path.is_symlink() else '<not-symlink>'
                    report.findings.append(Finding(
                        CHANGE, path, f'symlink target changed: {a_target!r} -> {b_target!r}',
                        code='symlink_target_changed'))
                    continue
                report.findings.extend(
                    analyze_content(path, a_path.read_bytes(), b_path.read_bytes(),
                                    elf_summaries=report.elf_summary,
                                    abi_store=abi_store,
                                    expected_abi_tool_version=expected_abi_tool_version))
        if abi_store is not None and report.elf_summary:
            pub_abis = [e['type_abi'] for e in report.elf_summary
                        if e.get('role') == 'public_shared_lib' and isinstance(e.get('type_abi'), dict)]
            if pub_abis:
                statuses = [a.get('status') for a in pub_abis]
                overall = (
                    'abi_incompatible_change' if 'abi_incompatible_change' in statuses else
                    'verified_compatible' if all(s == 'verified_compatible' for s in statuses) else
                    statuses[0])
                report.type_abi = {'status': overall, 'objects': pub_abis}
    elif not findings:
        if report.adb_stream_identical and not trust.get('verified'):
            report.findings.append(Finding(
                UNKNOWN, '(package)',
                'uncompressed ADB stream matches, but signatures are not verified under trusted keys',
                code='untrusted_framing_diff'))
        else:
            detail = ('payload and metadata match; only the signature or archive framing differs '
                      f'(old={old_fmt}, new={new_fmt})')
            report.findings.append(Finding(UNKNOWN, '(package)', detail, code='framing_or_signature_diff'))
    report.decision = evaluate_decision(report)
    return report


def resolve(feed_path, tree=TREE, destination=None):
    """Map a publisher path such as base/daed-2.1.1-r4.apk to (published, rebuilt)."""
    repository, _, filename = feed_path.partition('/')
    if not filename:
        raise ValueError(f'Expected REPOSITORY/FILE.apk, got {feed_path}')
    dest = Path(destination) if destination else Path(json.loads(FEEDS_CONFIG.read_text())['destination'])
    snapshots = sorted((dest / 'public/snapshots').glob(f'*/{feed_path}'))
    if not snapshots:
        raise ValueError(f'{feed_path} is not in any published snapshot under {dest}')
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

ACTION_SUMMARY = {
    ACTION_KEEP_EXISTING: 'keep existing published identity',
    ACTION_REUSE_PUBLISHED: 'reuse published APK (identical uncompressed ADB stream)',
    ACTION_ALLOCATE_RELEASE: 'eligible for automatic release allocation',
    ACTION_REVIEW: 'review before writing release ledger',
    ACTION_BENIGN: 'benign nondeterminism only; do not allocate a new release',
    ACTION_REJECT: 'reject candidate',
}


def format_report(report, verbose=True, label=None):
    decision = report.effective_decision()
    action = decision['action']
    if label:
        lines = [f'{label}: {report.verdict}: {SUMMARY[report.verdict]} [action: {action}]']
    else:
        lines = [f'old: {report.old}', f'new: {report.new}',
                 f'verdict: {report.verdict}: {SUMMARY[report.verdict]}',
                 f'action: {action}: {ACTION_SUMMARY.get(action, action)}']
    if report.trust:
        lines.append(f'  trust: verified={report.trust.get("verified")} ({report.trust.get("mode")})')
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
    parser.add_argument('--keys-dir', type=Path, help='verify and extract APKs using this keys directory')
    parser.add_argument('--abi-store', type=Path, help='out-of-APK type ABI evidence directory (Phase 2a)')
    parser.add_argument('--destination', type=Path, help='feed destination for REPOSITORY/FILE.apk lookup')
    args = parser.parse_args(argv)
    if not APK.exists():
        parser.error(f'{APK} is missing; build the host apk tool first')
    files = [Path(p) for p in args.packages]
    if len(files) == 2 and all(p.suffix == '.apk' and p.is_file() for p in files):
        pairs = [tuple(files)]
    else:
        pairs = [resolve(p, destination=args.destination) for p in args.packages]
    reports = [diagnose(old, new, keys_dir=args.keys_dir, abi_store=args.abi_store)
               for old, new in pairs]
    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        print('\n\n'.join(format_report(r, not args.brief) for r in reports))
    worst = {'identical': 0, BENIGN: 0, UNKNOWN: 1, CHANGE: 2}
    return max(worst[r.verdict] for r in reports)


if __name__ == '__main__':
    sys.exit(main())
