#!/usr/bin/env python3
"""Classify same-version APK rebuild differences."""
import gzip
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zipfile

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'

spec = importlib.util.spec_from_file_location('diagnose_apk_rebuild',
                                              TREE / 'scripts/diagnose-apk-rebuild.py')
diagnose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose)


def make_elf(sections):
    """Build a little-endian ELF64 relocatable object from (name, bytes) pairs."""
    names = b'\0'
    offsets = {}
    for name, _ in sections:
        offsets[name] = len(names)
        names += name.encode() + b'\0'
    names_offset = len(names)
    names += b'.shstrtab\0'
    body = b''
    headers = [b'\0' * 64]
    position = 64
    for name, data in sections + [('.shstrtab', names)]:
        name_offset = names_offset if name == '.shstrtab' else offsets[name]
        kind = 3 if name == '.shstrtab' else 1
        headers.append(struct.pack('<IIQQQQIIQQ', name_offset, kind, 0, 0, position,
                                   len(data), 0, 0, 1, 0))
        body += data
        position += len(data)
    shoff = position
    header = bytearray(64)
    header[:16] = b'\x7fELF\x02\x01\x01' + b'\0' * 9
    struct.pack_into('<HHIQQQIHHHHHH', header, 16, 1, 247, 1, 0, 0, shoff, 0, 64, 0, 0,
                     64, len(headers), len(headers) - 1)
    return bytes(header) + body + b''.join(headers)


def make_btf(types):
    """Build BTF from (kind, name, value, extra bytes) tuples."""
    strings = b'\0'
    blob = b''
    for kind, name, value, extra, vlen in types:
        offset = len(strings)
        strings += name.encode() + b'\0'
        blob += struct.pack('<III', offset if name else 0, (kind << 24) | vlen, value) + extra
    header = struct.pack('<HBBIIIII', 0xeb9f, 1, 0, 24, 0, len(blob), len(blob), len(strings))
    return header + blob + strings


FWD_A = (7, 'alpha', 0, b'', 0)
FWD_B = (7, 'beta', 0, b'', 0)


def bpf_object(btf, code=b'\x95' + b'\0' * 7):
    return make_elf([('kprobe/probe', code), ('.BTF', btf)])


class BtfTests(unittest.TestCase):
    def test_reordered_types_are_benign(self):
        old = make_btf([FWD_A, FWD_B, (2, '', 1, b'', 0)])
        new = make_btf([FWD_B, FWD_A, (2, '', 2, b'', 0)])
        finding = diagnose.analyze_btf('x', old, new, '<')
        self.assertEqual(finding.verdict, diagnose.BENIGN)
        self.assertIn('fwd alpha', finding.lines[1])

    def test_changed_struct_is_a_change(self):
        int_type = (1, 'int', 4, struct.pack('<I', 32), 0)
        old = make_btf([int_type, (4, 'thing', 4, struct.pack('<III', 0, 1, 0), 1)])
        new = make_btf([int_type, (4, 'thing', 8, struct.pack('<III', 0, 1, 0), 1)])
        finding = diagnose.analyze_btf('x', old, new, '<')
        self.assertEqual(finding.verdict, diagnose.CHANGE)


class ContentTests(unittest.TestCase):
    def test_embedded_bpf_with_reordered_btf(self):
        old_bpf = bpf_object(make_btf([FWD_A, FWD_B]))
        new_bpf = bpf_object(make_btf([FWD_B, FWD_A]))
        padding = b'\x11' * 300
        old = make_elf([('.text', b'\x90' * 64), ('.noptrdata', padding + old_bpf + padding)])
        new = make_elf([('.text', b'\x90' * 64), ('.noptrdata', padding + new_bpf + padding)])
        findings = diagnose.analyze_content('usr/bin/tool', old, new)
        self.assertEqual([f.verdict for f in findings], [diagnose.BENIGN])
        self.assertIn('.noptrdata] embedded ELF @0x12c [.BTF]', findings[0].path)

    def test_changed_code_is_not_called_benign(self):
        old = make_elf([('.text', b'\x90' * 64)])
        new = make_elf([('.text', b'\x90' * 32 + b'\xcc' + b'\x90' * 31)])
        findings = diagnose.analyze_content('usr/bin/tool', old, new)
        self.assertEqual([f.verdict for f in findings], [diagnose.UNKNOWN])
        self.assertIn('in .text', findings[0].detail)

    def test_section_size_change(self):
        old = make_elf([('.text', b'\x90' * 64)])
        new = make_elf([('.text', b'\x90' * 80)])
        findings = diagnose.analyze_content('usr/bin/tool', old, new)
        self.assertIn('section size 64 -> 80', findings[0].detail)

    def test_gzip_mtime_only(self):
        data = b'manual page\n' * 50
        old = gzip.compress(data, mtime=1)
        new = gzip.compress(data, mtime=2)
        findings = diagnose.analyze_content('usr/share/man/x.1.gz', old, new)
        self.assertEqual([f.verdict for f in findings], [diagnose.BENIGN])
        self.assertIn('mtime 1 -> 2', findings[0].detail)

    def test_gzip_content_change_is_explained_inside(self):
        old = gzip.compress(b'value=1\n', mtime=0)
        new = gzip.compress(b'value=2\n', mtime=0)
        findings = diagnose.analyze_content('etc/x.gz', old, new)
        self.assertEqual(findings[0].verdict, diagnose.CHANGE)
        self.assertEqual(findings[0].path, 'etc/x.gz (decompressed)')

    def test_zip_timestamps_only(self):
        def archive(date):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as handle:
                handle.writestr(zipfile.ZipInfo('a.txt', date), 'same')
            return buffer.getvalue()
        findings = diagnose.analyze_content('x.zip', archive((2020, 1, 1, 0, 0, 0)),
                                            archive((2021, 1, 1, 0, 0, 0)))
        self.assertEqual([f.verdict for f in findings], [diagnose.BENIGN])

    def test_pyc_source_mtime_only(self):
        code = b'\xe3' + b'\0' * 40
        old = b'\xcb\x0d\x0d\x0a' + struct.pack('<III', 0, 100, 10) + code
        new = b'\xcb\x0d\x0d\x0a' + struct.pack('<III', 0, 200, 10) + code
        findings = diagnose.analyze_content('usr/lib/python3/x.pyc', old, new)
        self.assertEqual([f.verdict for f in findings], [diagnose.BENIGN])

    def test_text_timestamp_and_text_change(self):
        stamp = diagnose.analyze_content('x.txt', b'built 2026-11-04\nkeep\n',
                                         b'built 2026-11-05\nkeep\n')
        self.assertEqual(stamp[0].verdict, diagnose.BENIGN)
        change = diagnose.analyze_content('x.txt', b'mode=a\n', b'mode=b\n')
        self.assertEqual(change[0].verdict, diagnose.CHANGE)
        self.assertIn('+mode=b', change[0].lines)


class MetadataTests(unittest.TestCase):
    def metadata(self, depends, mode=420, digest='aa'):
        return {'info': {'name': 'p', 'version': '1-r1', 'hashes': digest, 'depends': depends},
                'paths': [{'name': 'usr/bin', 'acl': {'mode': 493},
                           'files': [{'name': 'p', 'acl': {'mode': mode}, 'hash': digest,
                                      'size': 1}]}]}

    def test_dependency_and_mode_changes(self):
        findings, changed = diagnose.compare_metadata(self.metadata(['libc']),
                                                      self.metadata(['libc', 'libx'], 493, 'bb'))
        details = [f.detail for f in findings]
        self.assertTrue(any(d.startswith('depends:') for d in details))
        self.assertTrue(any(d.startswith('acl:') for d in details))
        self.assertEqual(changed, ['usr/bin/p'])


@unittest.skipUnless(APK.exists(), 'host apk tool is not built')
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def package(self, label, files, depends='libc'):
        payload = self.root / ('payload-' + label)
        for path, data in files.items():
            target = payload / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        output = self.root / f'{label}.apk'
        subprocess.run([str(APK), 'mkpkg', '--info', 'name:probe', '--info', 'version:1-r1',
                        '--info', 'arch:x86_64', '--info', 'license:MIT',
                        '--info', 'description:test', '--info', 'depends:' + depends,
                        '--files', str(payload), '--output', str(output)],
                       check=True, capture_output=True)
        return output

    def test_benign_rebuild(self):
        old_bpf = bpf_object(make_btf([FWD_A, FWD_B]))
        new_bpf = bpf_object(make_btf([FWD_B, FWD_A]))
        common = {'usr/share/probe/readme': b'same\n'}
        old = self.package('old', {**common, 'usr/bin/probe': make_elf([('.data', old_bpf)])})
        new = self.package('new', {**common, 'usr/bin/probe': make_elf([('.data', new_bpf)])})
        report = diagnose.diagnose(old, new, APK)
        self.assertEqual(report.verdict, diagnose.BENIGN)
        self.assertTrue(diagnose.format_report(report, label='base/probe-1-r1.apk')
                        .startswith('base/probe-1-r1.apk: benign: build nondeterminism'))
        self.assertEqual(diagnose.main([str(old), str(new), '--brief']), 0)

    def test_dependency_change(self):
        old = self.package('old', {'usr/share/probe/x': b'a\n'})
        new = self.package('new', {'usr/share/probe/x': b'a\n'}, depends='libc libextra')
        report = diagnose.diagnose(old, new, APK)
        self.assertEqual(report.verdict, diagnose.CHANGE)
        self.assertEqual(diagnose.main([str(old), str(new), '--brief']), 2)

    def test_identical(self):
        old = self.package('old', {'usr/share/probe/x': b'a\n'})
        self.assertTrue(diagnose.diagnose(old, old, APK).identical)


if __name__ == '__main__':
    unittest.main()
