#!/usr/bin/env python3
"""Hermetic CLI and storage regression tests; no host service/config mutations."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[2] / 'package/custom/uci-history/files/uci-history'
loader = importlib.machinery.SourceFileLoader('uci_history', str(CLI))
spec = importlib.util.spec_from_loader(loader.name, loader)
H = importlib.util.module_from_spec(spec)
with patch.object(sys, 'dont_write_bytecode', True):
    loader.exec_module(H)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.write('etc/config/network', "config interface 'lan'\n option ipaddr '192.0.2.1'\n option password 'sensitive-original'\n")
        self.write('etc/config/system', "config system\n option hostname 'router'\n")
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('systemd-run', 'systemctl', 'reload_config', 'ubus'):
            f = self.bin / name
            f.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(self.root / 'calls') + '"\n')
            f.chmod(0o755)
        self.env = patch.dict(os.environ, {'PATH': str(self.bin) + ':' + os.environ['PATH'], 'SSH_CONNECTION': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.h = H.History(self.root)
        self.addCleanup(self.h.lock.close)

    def write(self, name, value):
        f = self.root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(value)
        return f

    def change(self, value='192.0.2.2'):
        f = self.root / 'etc/config/network'
        f.write_text(f.read_text().replace('192.0.2.1', value))

    def test_snapshot_noop_monotonic(self):
        self.assertEqual(self.h.snapshot()['revision'], 1)
        self.assertFalse(self.h.snapshot()['changed'])
        self.change()
        self.assertEqual(self.h.snapshot()['revision'], 2)
        self.h.restore(1)
        self.assertEqual(self.h.revisions()[0]['revision'], 3)
        self.assertFalse(self.h.status()['drift'])
        self.assertEqual((self.root / 'etc/uci-history').stat().st_mode & 0o777, 0o700)

    def test_parser(self):
        p = H.parse_uci("config wifi 'named'\n option text 'it'\\''s okay'\n list dns 'a b'\n list dns c\nconfig wifi\n option p \"a#b\" # comment\n")
        self.assertEqual(p['named']['options']['text'], "it's okay")
        self.assertEqual(p['named']['options']['dns'], ['a b', 'c'])
        self.assertEqual(p['@wifi[1]']['options']['p'], 'a#b')

    def test_masking(self):
        self.h.snapshot()
        f = self.root / 'etc/config/network'
        f.write_text(f.read_text().replace('sensitive-original', 'sensitive-new'))
        rows = self.h.diff()['changes']
        self.assertEqual(rows[0]['old'], 'changed')
        self.assertNotIn('sensitive', json.dumps(self.h.diff(format='unified')))
        self.assertIn('sensitive-new', json.dumps(self.h.diff(show=True)))
        self.assertNotIn('sensitive', H.masked(f.read_text()))
        for key in ('key', 'wifi_psk', 'api_token', 'private_key', 'pin'):
            self.assertTrue(H.SECRET.search(key))
        self.assertFalse(H.SECRET.search('monkey'))

    def test_partial_mode_delete_and_atomic(self):
        f = self.root / 'etc/config/network'
        f.chmod(0o640)
        self.h.snapshot()
        self.change()
        self.write('etc/config/system', "config system\n option hostname changed\n")
        self.write('etc/config/new', 'config test\n')
        self.h.restore(1, configs=['network'], no_reload=True)
        self.assertEqual(f.stat().st_mode & 0o777, 0o640)
        self.assertIn('192.0.2.1', f.read_text())
        self.assertIn('changed', (self.root / 'etc/config/system').read_text())
        self.assertFalse(list(f.parent.glob('.network.*')))
        self.h.restore(1)
        self.assertFalse((self.root / 'etc/config/new').exists())

    def test_selected_creation_and_deletion(self):
        self.h.snapshot()
        self.write('etc/config/created', 'config test\n')
        self.h.restore(1, configs=['created'])
        self.assertFalse((self.root / 'etc/config/created').exists())
        (self.root / 'etc/config/network').unlink()
        self.h.restore(1, configs=['network'])
        self.assertTrue((self.root / 'etc/config/network').exists())

    def test_staged(self):
        self.h.snapshot()
        self.change()
        delta = self.write('var/run/rpcd/uci-session/network', 'delta')
        with self.assertRaises(H.Error) as e:
            self.h.restore(1)
        self.assertEqual(e.exception.code, 3)
        self.h.restore(1, discard=True)
        self.assertFalse(delta.exists())

    def test_ssh_gate_dry_run(self):
        self.h.snapshot()
        self.change()
        with patch.dict(os.environ, SSH_CONNECTION='remote'):
            with self.assertRaises(H.Error):
                self.h.restore(1)
            self.assertTrue(self.h.restore(1, timeout=60, dry=True)['dry_run'])
            self.assertIsNone(self.h.txn())
            self.h.restore(1, timeout=60)
        self.assertIsNotNone(self.h.txn())
        self.h.finish('abort')
        self.assertIn('192.0.2.2', (self.root / 'etc/config/network').read_text())

    def test_transactions_confirm_abort(self):
        tx = self.h.arm(60, 'agent', 'reason')['transaction']
        self.change()
        snap = self.h.snapshot(auto=True)
        self.assertTrue(snap['changed'])
        rev = self.h.revisions()[0]
        self.assertEqual((rev['actor'], rev['transaction']), ('agent', tx['id']))
        self.h.finish('confirm')
        self.assertIsNone(self.h.txn())
        self.h.arm(60)
        self.write('etc/config/network', 'config interface\n')
        self.h.finish('abort')
        self.assertIn('192.0.2.2', (self.root / 'etc/config/network').read_text())
        self.assertEqual(self.h.revisions()[0]['source'], 'txn-revert')

    def test_timeout_late_confirm(self):
        self.h.arm(5)
        self.change()
        tx = self.h.txn()
        tx['deadline'] = time.time() - 1
        self.h.save(self.h.txfile, tx)
        with self.assertRaises(H.Error) as e:
            self.h.finish('confirm')
        self.assertEqual(e.exception.code, 10)
        self.assertIn('192.0.2.1', (self.root / 'etc/config/network').read_text())
        with self.assertRaises(H.Error) as e:
            self.h.finish('confirm')
        self.assertEqual(e.exception.code, 10)

    def test_stale_timer_cannot_revert_new_transaction(self):
        self.h.arm(60)
        self.change()
        self.assertFalse(self.h.finish('revert', 'old-id')['changed'])
        self.assertIn('192.0.2.2', (self.root / 'etc/config/network').read_text())

    def test_pending_conflicts(self):
        self.write('var/run/rpcd/snapshot-files/network', 'snapshot')
        self.assertTrue(self.h.status()['rpcd_rollback'])
        for action in (lambda: self.h.arm(60), lambda: self.h.restore(1)):
            with self.assertRaises(H.Error) as e:
                action()
            self.assertEqual(e.exception.code, 3)

    def test_hints(self):
        self.h.snapshot()
        for event, data, expected in [
            ('uci.apply', dict(configs=['network'], username='alice'), 'luci'),
            ('uci.rollback', dict(configs=['network']), 'rpcd-rollback'),
            ('apk', {}, 'apk')]:
            self.h.hint(event, data)
            f = self.root / 'etc/config/network'
            f.write_text(f.read_text() + '\n# new\n')
            self.assertEqual(self.h.snapshot(auto=True)['source'], expected)
        hints = self.root / 'run/uci-history/hints'
        for f in hints.iterdir():
            data = json.loads(f.read_text())
            data['time'] -= 31
            f.write_text(json.dumps(data))
        self.change()
        self.assertEqual(self.h.snapshot(source='external', auto=True)['source'], 'external')

    def test_prune(self):
        self.h.snapshot()
        self.change()
        self.h.snapshot()
        self.write('etc/config/system', 'config system\n')
        self.h.snapshot()
        self.h.prune(2)
        self.assertEqual([r['revision'] for r in self.h.revisions()], [3, 2])
        with self.assertRaises(H.Error):
            self.h.revision(1)
        self.change('192.0.2.3')
        f = self.root / 'etc/config/network'
        f.write_text(f.read_text() + '# next\n')
        self.assertEqual(self.h.snapshot()['revision'], 4)

    def test_hidden_extra_files_are_captured(self):
        extra = self.write('etc/nftables.d/.managed', 'original-extra-secret')
        self.write('etc/config/.uci-temporary', 'not a committed config')
        self.h.snapshot()
        files = self.h.files_at(1)
        self.assertIn('etc/nftables.d/.managed', files)
        self.assertNotIn('etc/config/.uci-temporary', files)
        extra.write_text('changed-extra-secret')
        self.h.restore(1, paths=['/etc/nftables.d'])
        self.assertEqual(extra.read_text(), 'original-extra-secret')

    def test_report_actual_reload_events(self):
        self.h.snapshot()
        self.change()
        hashes = self.write('var/run/config.md5',
                            '0' * 32 + '  /var/run/config.check/network\n' +
                            '0' * 32 + '  /var/run/config.check/system\n' +
                            '0' * 32 + '  /var/run/config.check/removed\n')
        after = ('1' * 32 + '  /var/run/config.check/network\n' +
                 '0' * 32 + '  /var/run/config.check/system\n')
        (self.bin / 'reload_config').write_text('#!/bin/sh\nprintf %s ' + shlex.quote(after) + ' > ' + shlex.quote(str(hashes)) + '\n')
        result = self.h.restore(1, configs=['network'])
        self.assertEqual(result['configs'], ['network'])
        self.assertEqual(result['triggered_configs'], ['network', 'removed'])

    def test_restore_signals_packages_reload_config_skips(self):
        # An init-script reload leaves reload_config's baseline at the old
        # content, so restoring that content changes no checksum.
        self.h.snapshot()
        self.write('var/run/config.md5', '0' * 32 + '  /var/run/config.check/network\n')
        self.change()
        self.h.snapshot()
        result = self.h.restore(1, configs=['network'])
        self.assertEqual(result['triggered_configs'], ['network'])
        calls = (self.root / 'calls').read_text()
        self.assertIn('call service event {"type": "config.change", "data": {"package": "network"}}', calls)

    def test_hint_is_consumed_by_one_capture(self):
        self.h.snapshot()
        self.h.hint('uci.apply', dict(configs=['network'], username='alice'))
        self.change()
        self.assertEqual(self.h.snapshot(source='external', auto=True)['source'], 'luci')
        self.write('etc/config/system', "config system\n option hostname 'other'\n")
        self.h.hint('uci.apply', dict(configs=['system'], username='alice'))
        self.h.snapshot(source='external', auto=True)
        f = self.root / 'etc/config/system'
        f.write_text(f.read_text() + '# edited\n')
        self.assertEqual(self.h.snapshot(source='external', auto=True)['source'], 'external')

    def test_apk_sidecars_and_nested_backup_files(self):
        self.write('etc/config/network.apk-new', "config interface lan\n option password 'sidecar-secret'\n")
        self.write('etc/config/backups/network', 'backup-secret')
        self.h.snapshot(source='apk')
        self.assertNotIn('network.apk-new', self.h.status()['configs'])
        self.assertFalse(self.h.snapshot()['changed'])
        self.write('etc/config/network.apk-new', 'modified-secret')
        self.assertFalse(self.h.diff()['changes'])
        self.assertNotIn('secret', self.h.diff(format='unified')['diff'])
        restored = self.h.restore(1)
        self.assertIn('/etc/config/network.apk-new', restored['paths'])
        self.assertFalse(restored['reload'])
        self.assertIn('sidecar-secret', (self.root / 'etc/config/network.apk-new').read_text())

    def test_explicit_empty_extra_scope(self):
        self.write('etc/config/uci-history', 'config history main\n option enabled 1\n')
        self.write('etc/nftables.d/custom', 'not selected')
        self.h.refresh_settings()
        self.assertEqual(self.h.settings['extras'], [])
        self.assertNotIn('etc/nftables.d/custom', self.h.collect())

    def test_extra_paths_deny_and_symlinks(self):
        for p in ('/etc', '/tmp/x', '/etc/shadow', '/etc/uci-history/repo', '/etc/../tmp/x', '/etc/apk', '/etc/ssl/private/key', '/etc/a.key'):
            with self.assertRaises(H.Error, msg=p):
                self.h.validate_path(p)
        self.write('etc/nftables.d/custom', 'private arbitrary content')
        self.h.snapshot()
        self.write('etc/nftables.d/custom', 'changed')
        self.h.restore(1, paths=['/etc/nftables.d'])
        self.assertEqual((self.root / 'etc/nftables.d/custom').read_text(), 'private arbitrary content')
        self.assertFalse((self.root / 'calls').exists())
        (self.root / 'etc/config/link').symlink_to('/etc/passwd')
        with self.assertRaises(H.Error):
            self.h.collect()

    def test_boot_missing_timer_and_invalid_settings(self):
        self.h.arm(60)
        self.change()
        self.write('etc/config/uci-history', "config history\n option enabled 'unterminated\n")
        (self.bin / 'systemctl').write_text('#!/bin/sh\n[ "$1" = stop ] && exit 5\necho not-found\n')
        self.h.lock.close()
        recovered = H.History(self.root)
        try:
            recovered.finish('revert')
            self.assertIsNone(recovered.txn())
            self.assertIn('192.0.2.1', (self.root / 'etc/config/network').read_text())
            self.assertFalse((self.root / 'etc/config/uci-history').exists())
        finally:
            recovered.lock.close()

    def test_revert_retries_failed_reload(self):
        self.h.arm(60)
        self.change()
        reload = self.bin / 'reload_config'
        reload.write_text('#!/bin/sh\nexit 1\n')
        with self.assertRaises(H.Error):
            self.h.finish('abort')
        self.assertIsNotNone(self.h.txn())
        reload.write_text('#!/bin/sh\nexit 0\n')
        self.h.finish('abort')
        self.assertIsNone(self.h.txn())
        self.assertIn('192.0.2.1', (self.root / 'etc/config/network').read_text())

    def test_multiline_secret_and_fail_closed(self):
        data = "config test\n option password 'top\nmiddle\nbottom'\n option description 'two\nlines'\n"
        self.assertEqual(H.parse_uci(data)['@test[0]']['options']['description'], 'two\nlines')
        self.assertNotIn('middle', H.masked(data))
        self.assertNotIn('sensitive', H.masked("option password 'sensitive\nmore"))

    def test_listener(self):
        self.h.lock.close()
        fake = self.bin / 'ubus'
        fake.write_text('#!/bin/sh\ncat <<EOF\n{\n "uci.apply": {"configs":["network"],"username":"operator"}\n}\nEOF\n')
        fake.chmod(0o755)
        H.listen(str(self.root))
        self.h = H.History(self.root)
        self.addCleanup(self.h.lock.close)
        self.h.snapshot()
        self.change()
        self.assertEqual(self.h.snapshot(auto=True)['source'], 'luci')
        self.assertEqual(self.h.revisions()[0]['actor'], 'operator')

    def test_timer_failure_is_atomic(self):
        (self.bin / 'systemd-run').write_text('#!/bin/sh\nexit 1\n')
        with self.assertRaises(H.Error):
            self.h.arm(60)
        self.assertIsNone(self.h.txn())

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = H.main(['--json', '--root', str(self.root), *args])
        data = json.loads(out.getvalue())
        self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['ok'], rc == 0)
        return rc, data

    def test_cli_schema_and_commands(self):
        root_mock = patch.object(os, 'geteuid', return_value=0)
        root_mock.start()
        self.addCleanup(root_mock.stop)
        # Release the in-process lock before invoking a second History.
        self.h.lock.close()
        for args in [('commands',), ('guide',), ('status',), ('snapshot',), ('log',), ('show', '1'),
                     ('diff', '1', '1'), ('restore', '1', '--dry-run'), ('prune', '--keep', '1'),
                     ('hint', '--event', 'apk'), ('boot',), ('revert', '--id', 'stale')]:
            self.assertEqual(self.cli(*args)[0], 0, args)
        self.assertEqual(self.cli('show', '999')[0], 4)
        self.assertEqual(self.cli('confirm')[0], 3)
        self.assertEqual(self.cli('prune', '--keep', '0')[0], 2)
        with patch.object(os, 'geteuid', return_value=1000):
            self.assertEqual(self.cli('status')[0], 77)
        self.assertEqual(self.cli('begin', '--timeout', '60')[0], 0)
        self.change()
        self.assertEqual(self.cli('boot')[0], 0)
        self.assertEqual(self.cli('confirm')[0], 10)
        self.assertEqual(self.cli('begin', '--timeout', '60')[0], 0)
        self.assertEqual(self.cli('abort')[0], 0)
        self.assertEqual(self.cli('begin', '--timeout', '60')[0], 0)
        self.assertEqual(self.cli('confirm')[0], 0)



# Shims that model the mechanism behind the revert bug. Each service keeps the
# configuration it last applied in run/applied/PKG. It changes only when a
# config.change event reaches it, or when the test runs an "init script reload".
# reload_config fires events only for packages whose content differs from its
# own previous run, as in package/system/procd/files/reload_config.
RELOAD_CONFIG = r"""#!/usr/bin/env python3
import hashlib, pathlib, shutil
root = pathlib.Path(%(root)r)
md5 = root / 'var/run/config.md5'
current = {f.name: hashlib.md5(f.read_bytes()).hexdigest()
           for f in sorted((root / 'etc/config').iterdir())
           if f.is_file() and not f.name.startswith('.')}
if md5.exists():
    for line in md5.read_text().splitlines():
        checksum, name = line.split(None, 1)
        name = pathlib.Path(name).name
        if current.get(name) != checksum:
            with open(root / 'events', 'a') as log:
                log.write(name + '\n')
            applied = root / 'run/applied' / name
            source = root / 'etc/config' / name
            if source.exists():
                shutil.copyfile(source, applied)
            else:
                applied.unlink(missing_ok=True)
md5.parent.mkdir(parents=True, exist_ok=True)
md5.write_text(''.join('%%s  /var/run/config.check/%%s\n' %% (v, k) for k, v in current.items()))
"""

UBUS = r"""#!/usr/bin/env python3
import json, pathlib, shutil, sys
root = pathlib.Path(%(root)r)
if pathlib.Path(root / 'ubus-fails').exists():
    sys.exit(1)
if sys.argv[1:4] != ['call', 'service', 'event']:
    sys.exit(0)
event = json.loads(sys.argv[4])
assert event['type'] == 'config.change'
name = event['data']['package']
with open(root / 'events', 'a') as log:
    log.write(name + '\n')
source = root / 'etc/config' / name
applied = root / 'run/applied' / name
if source.exists():
    shutil.copyfile(source, applied)
else:
    applied.unlink(missing_ok=True)
"""

LAN = "config interface 'lan'\n option ipaddr '192.0.2.1'\n"
BROKEN = "config interface 'lan'\n option ipaddr '192.0.2.9'\n"
FIREWALL = "config zone 'lan'\n option input 'ACCEPT'\n"
LOCKED = "config zone 'lan'\n option input 'REJECT'\n"


class RunningServiceRevertTest(unittest.TestCase):
    """Revert must restore what services run, not only the files on disk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        for name, text in [('network', LAN), ('firewall', FIREWALL), ('system', "config system\n")]:
            self.write('etc/config/' + name, text)
        self.write('etc/nftables.d/10-custom.nft', 'original\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name, text in [('reload_config', RELOAD_CONFIG), ('ubus', UBUS),
                           ('systemd-run', '#!/bin/sh\n'), ('systemctl', '#!/bin/sh\n')]:
            f = self.bin / name
            f.write_text(text % dict(root=str(self.root)) if '%(root)' in text else text)
            f.chmod(0o755)
        self.env = patch.dict(os.environ, {'PATH': str(self.bin) + ':' + os.environ['PATH'], 'SSH_CONNECTION': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Boot: every service applies its configuration, then /etc/init.d/boot
        # runs reload_config once to record the baseline.
        (self.root / 'run/applied').mkdir(parents=True)
        for name in ('network', 'firewall', 'system'):
            self.init_reload(name)
        subprocess.run(['reload_config'], check=True)
        self.h = H.History(self.root)
        self.addCleanup(self.h.lock.close)
        self.h.snapshot()

    def write(self, name, value):
        f = self.root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(value)
        return f

    def init_reload(self, name):
        # /etc/init.d/NAME reload: the service applies the file on disk, but
        # reload_config's checksum baseline is not updated.
        (self.root / 'run/applied' / name).write_text((self.root / 'etc/config' / name).read_text())

    def running(self, name):
        return (self.root / 'run/applied' / name).read_text()

    def events(self):
        f = self.root / 'events'
        lines = f.read_text().splitlines() if f.exists() else []
        f.unlink(missing_ok=True)
        return sorted(lines)

    def break_lan_with_init_reload(self):
        self.write('etc/config/network', BROKEN)
        self.init_reload('network')
        self.assertEqual(self.running('network'), BROKEN)
        self.events()

    def test_abort_after_init_script_reload_restores_running_service(self):
        # The reported bug: the file reverted, the service kept 192.0.2.9.
        self.h.arm(60)
        self.break_lan_with_init_reload()
        self.h.finish('abort')
        self.assertEqual((self.root / 'etc/config/network').read_text(), LAN)
        self.assertEqual(self.running('network'), LAN)
        self.assertEqual(self.events(), ['network'])

    def test_timer_revert_after_init_script_reload(self):
        tx = self.h.arm(60)['transaction']
        self.break_lan_with_init_reload()
        self.h.finish('revert', tx['id'])
        self.assertEqual(self.running('network'), LAN)
        self.assertEqual(self.h.revisions()[0]['source'], 'txn-revert')

    def test_boot_revert_after_init_script_reload(self):
        self.h.arm(60)
        self.break_lan_with_init_reload()
        self.h.finish('revert')
        self.assertEqual(self.running('network'), LAN)

    def test_revert_after_reload_config_signals_once(self):
        # The path that already worked must not reload the service twice.
        self.h.arm(60)
        self.write('etc/config/network', BROKEN)
        subprocess.run(['reload_config'], check=True)
        self.assertEqual((self.events(), self.running('network')), (['network'], BROKEN))
        self.h.finish('abort')
        self.assertEqual(self.running('network'), LAN)
        self.assertEqual(self.events(), ['network'])

    def test_mixed_apply_methods_each_signalled_once(self):
        self.h.arm(60)
        self.break_lan_with_init_reload()
        self.write('etc/config/firewall', LOCKED)
        subprocess.run(['reload_config'], check=True)
        self.events()
        self.h.finish('abort')
        self.assertEqual((self.running('network'), self.running('firewall')), (LAN, FIREWALL))
        self.assertEqual(self.events(), ['firewall', 'network'])

    def test_unapplied_commit_revert_keeps_service_on_checkpoint(self):
        # Committed but never applied: an extra event is harmless; the service
        # must end on the checkpoint either way.
        self.h.arm(60)
        self.write('etc/config/network', BROKEN)
        self.h.finish('abort')
        self.assertEqual(self.running('network'), LAN)
        self.assertLessEqual(self.events().count('network'), 1)

    def test_restore_after_init_script_reload(self):
        self.break_lan_with_init_reload()
        self.h.snapshot()
        result = self.h.restore(1, configs=['network'])
        self.assertEqual(self.running('network'), LAN)
        self.assertEqual(result['triggered_configs'], ['network'])

    def test_missing_reload_baseline_still_signals(self):
        (self.root / 'var/run/config.md5').unlink()
        self.h.arm(60)
        self.break_lan_with_init_reload()
        self.h.finish('abort')
        self.assertEqual(self.running('network'), LAN)

    def test_unchanged_packages_and_extras_are_not_signalled(self):
        self.h.arm(60)
        self.write('etc/nftables.d/10-custom.nft', 'changed\n')
        self.h.finish('abort')
        self.assertEqual((self.root / 'etc/nftables.d/10-custom.nft').read_text(), 'original\n')
        self.assertEqual(self.events(), [])

    def test_no_reload_sends_no_events(self):
        self.break_lan_with_init_reload()
        self.h.snapshot()
        self.h.restore(1, configs=['network'], no_reload=True)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.running('network'), BROKEN)

    def test_failed_signal_keeps_transaction_for_retry(self):
        self.h.arm(60)
        self.break_lan_with_init_reload()
        (self.root / 'ubus-fails').touch()
        with self.assertRaises(H.Error):
            self.h.finish('abort')
        self.assertIsNotNone(self.h.txn())
        (self.root / 'ubus-fails').unlink()
        self.h.finish('abort')
        self.assertIsNone(self.h.txn())
        self.assertEqual(self.running('network'), LAN)

    def test_scenario_fails_without_the_fix(self):
        # Mutation check: the reload code from before the fix leaves the service
        # broken in this scenario, so the tests above can detect a regression.
        def old_reload(history, affected=()):
            before = history.reload_hashes()
            history.run(['reload_config'])
            after = history.reload_hashes()
            return sorted({Path(n).name for n, c in before.items() if after.get(n) != c})
        self.h.arm(60)
        self.break_lan_with_init_reload()
        with patch.object(H.History, 'reload', old_reload):
            self.h.finish('abort')
        self.assertEqual((self.root / 'etc/config/network').read_text(), LAN)
        self.assertEqual(self.running('network'), BROKEN)
        self.assertEqual(self.events(), [])

if __name__ == '__main__':
    unittest.main()
