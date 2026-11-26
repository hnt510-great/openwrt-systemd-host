#!/usr/bin/env python3
"""Read-only runner and inventory guard for host-runnable tests in scripts/tests/.

Invokes existing test scripts as unmodified subprocesses from the repository
root. Never executes KVM/VM drivers or target-only router checks.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import subprocess
import sys
import time

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parents[1]

HOST_SUITES = {
    'publish': [
        'test-allocate-rebuild-releases.py',
        'test-apk-rebuild-phase2.py',
        'test-apk-release-repack.py',
        'test-apk-source-versions.py',
        'test-apk-transaction-journal.py',
        'test-apk-upgrade-preflight.py',
        'test-build-and-publish.py',
        'test-custom-package-updates.py',
        'test-diagnose-apk-rebuild.py',
        'test-elf-abi.py',
        'test-firefox-updater.py',
        'test-kernel-apk-policy.py',
        'test-kernel-build-inputs.py',
        'test-kernel-bundle.py',
        'test-kernel-upgrade.py',
        'test-lan-apk-client.py',
        'test-lan-apk-nginx.py',
        'test-lan-apk-publisher.py',
        'test-mainline-kernel-updates.py',
        'test-package-metadata-kconfig.py',
        'test-parallel-build-staging.py',
        'test-scheduled-maintenance.py',
        'test-ucode-abi.py',
    ],
    'systemd': [
        'test-alternatives.sh',
        'test-auxiliary-systemd.py',
        'test-boot-readiness.py',
        'test-home-backup-metadata.py',
        'test-irqbalance-netdev-cpus.py',
        'test-logd-journal.py',
        'test-merge-usr.py',
        'test-nas-systemd.py',
        'test-needrestart.py',
        'test-network-wait-online.py',
        'test-preinit-handoff.py',
        'test-procd-units.py',
        'test-samba4-systemd.py',
        'test-sshd-systemd.py',
        'test-systemd-backup-cli.py',
        'test-systemd-router-decoupling.py',
        'test-systemd-service-bridge.py',
        'test-systemd-udev-boundary.py',
        'test-udev-hotplug-migration.py',
    ],
    'desktop': [
        'desktop-rdp-config.py',
        'test-desktop-audio.py',
        'test-desktop-gpu-coldplug.py',
        'test-desktop-icon-theme-hook.py',
        'test-desktop-ime.py',
        'test-desktop-sessions.py',
        'test-desktop-setup.py',
        'test-flatpak-user-link.py',
        'test-gnome-keyring.py',
        'test-gnome-rdp-audio-latency.py',
        'test-gnome-rdp-listener.py',
        'test-libvirt-audio.py',
        'test-podman-native-storage.py',
        'test-rtkit-desktop.py',
        'test-sunshine-gnome.py',
    ],
    'luci': [
        'test-luci-daed-view.js',
        'test-luci-desktop-setup.js',
        'test-luci-desktop-view.js',
        'test-luci-desktop.py',
        'test-luci-firewall-fullcone.js',
        'test-luci-journal-view.js',
        'test-luci-journal.py',
        'test-luci-needrestart.js',
        'test-luci-needrestart.py',
        'test-luci-podman-runtime.py',
        'test-luci-podman-view.js',
        'test-luci-podman.py',
        'test-luci-qemu-view.js',
        'test-luci-qemu.py',
        'test-luci-status-redraw.js',
        'test-luci-uci-history-view.js',
        'test-luci-uci-history.py',
        'test-sshd-startup-view.js',
    ],
    'installer': [
        'test-installer-components.py',
        'test-installer-optical.py',
        'test-openwrt-installer.py',
    ],
    'audit': [
        'test-router-audit-config.py',
        'test-router-audit-connections.py',
        'test-router-audit.py',
        'test-uci-history-units.py',
        'test-uci-history-vm-console.py',
        'test-uci-history.py',
    ],
    'staged': [
        'test-custom-branch-upgrade.py',
    ],
    'legacy': [
        'test-desktop-launcher.py',
        'test-weston-terminal-sgr.py',
    ],
}

ACTIVE_SUITES = ('publish', 'systemd', 'desktop', 'luci', 'installer', 'audit')

NON_HOST_TESTS = {
    'vm': [
        'test-apk-transaction-vm.py',
        'test-daed-client-features-vm.py',
        'test-daed-vm.py',
        'test-input-hotplug.py',
        'test-installer-components-vm.py',
        'test-installer-iso-vm.py',
        'test-kde-plasma-vm.py',
        'test-systemd-router-pppoe-vm.py',
        'test-uci-history-vm.py',
    ],
    'target': [
        'test-libvirt-secondary-drivers.py',
    ],
}


def verify_inventory() -> list[str]:
    errors = []
    seen = {}
    for group_kind, mapping in (('host', HOST_SUITES), ('non-host', NON_HOST_TESTS)):
        for suite, names in mapping.items():
            for name in names:
                if name in seen:
                    errors.append(f'Duplicate classification for {name}: {seen[name]} and {group_kind}:{suite}')
                seen[name] = f'{group_kind}:{suite}'
                if not (TESTS_DIR / name).is_file():
                    errors.append(f'Missing file listed in {group_kind}:{suite}: {name}')
    on_disk = sorted(
        p.name for p in TESTS_DIR.iterdir()
        if p.is_file() and p.name.startswith('test-') and p.suffix in ('.py', '.js', '.sh')
    )
    for name in on_disk:
        if name not in seen:
            errors.append(f'Unclassified test-* file in scripts/tests/: {name}')
    return errors


def command_for(name: str) -> list[str]:
    path = str(TESTS_DIR / name)
    if name.endswith('.py'):
        return [sys.executable, '-B', path]
    if name.endswith('.js'):
        return ['node', path]
    if name.endswith('.sh'):
        return ['sh', path]
    raise ValueError(f'Unsupported test extension: {name}')


def run_one(suite: str, name: str, timeout: int) -> dict:
    cmd = command_for(name)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
        )
        returncode = proc.returncode
        output = (proc.stdout + proc.stderr).decode(errors='replace').strip()
        status = 'FAIL' if returncode else 'PASS'
        if not returncode and name.endswith('.py'):
            report = proc.stderr.decode(errors='replace')
            summary = re.search(r'^Ran (\d+) tests? in [^\n]+\n\s*OK \(skipped=(\d+)\)\s*\Z',
                                report, re.MULTILINE)
            if summary:
                ran, skipped = map(int, summary.groups())
                # setUpClass skips can add to "skipped" without adding to "Ran".
                passed_case = re.search(r'^[.sx]*[.x][.sx]*$| \.\.\. (?:ok|expected failure)$',
                                        report, re.MULTILINE)
                status = 'PARTIAL' if ran > skipped or passed_case else 'SKIP'
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        status = 'FAIL'
        captured = (exc.stdout or b'') + (exc.stderr or b'')
        output = f'TIMEOUT after {timeout}s\n' + captured.decode(errors='replace').strip()
    except OSError as exc:
        returncode = 1
        status = 'FAIL'
        output = str(exc)
    return dict(suite=suite, name=name, status=status, returncode=returncode,
                duration=time.monotonic() - start, output=output)


def resolve_suites(selected: list[str], include_legacy: bool) -> list[str]:
    if not selected:
        suites = list(ACTIVE_SUITES)
    else:
        suites = []
        for item in selected:
            for part in item.split(','):
                part = part.strip()
                if not part:
                    continue
                if part == 'all':
                    suites.extend(ACTIVE_SUITES)
                elif part in HOST_SUITES:
                    suites.append(part)
                else:
                    valid = ', '.join(('all', *HOST_SUITES))
                    raise SystemExit(f'Unknown suite {part!r}; expected one of: {valid}')
    if include_legacy and 'legacy' not in suites:
        suites.append('legacy')
    # Preserve order while deduplicating.
    return list(dict.fromkeys(suites))


def run_plan(plan, jobs, timeout):
    if jobs == 1:
        for suite, name in plan:
            yield run_one(suite, name, timeout)
        return
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, suite, name, timeout) for suite, name in plan]
        for future in as_completed(futures):
            yield future.result()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--suite',
        action='append',
        default=[],
        help='Suite(s) to run or list: all (active suites), ' + ', '.join(HOST_SUITES),
    )
    parser.add_argument(
        '--include-legacy',
        action='store_true',
        help='Also include disabled legacy-recipe tests (legacy suite)',
    )
    parser.add_argument('--list', action='store_true', help='List selected suites and exit without running tests')
    parser.add_argument(
        '--verify-inventory',
        action='store_true',
        help='Verify every test-*.{py,js,sh} in scripts/tests/ is classified and present',
    )
    parser.add_argument('-j', '--jobs', type=int, default=1, help='Maximum parallel test processes (default: 1)')
    parser.add_argument('--timeout', type=int, default=300, help='Per-test timeout in seconds (default: 300)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Print test output even on pass/skip')
    args = parser.parse_args()

    errors = verify_inventory()
    if errors:
        for err in errors:
            print(f'INVENTORY ERROR: {err}', file=sys.stderr)
        if args.verify_inventory or not args.list:
            return 2

    suites = resolve_suites(args.suite, args.include_legacy)
    if args.list:
        total = 0
        for suite in suites:
            names = HOST_SUITES[suite]
            total += len(names)
            print(f'[{suite}] ({len(names)})')
            for name in names:
                print(f'  {name}')
        print(f'\nTotal selected host tests: {total}')
        if args.verify_inventory:
            print('Inventory verification: OK')
        return 0

    if args.verify_inventory and not args.suite and not args.include_legacy:
        print('Inventory verification: OK')
        return 0

    plan = [(suite, name) for suite in suites for name in HOST_SUITES[suite]]
    jobs = max(1, args.jobs)
    results = []
    start_all = time.monotonic()

    for res in run_plan(plan, jobs, args.timeout):
        results.append(res)
        print(f"[{res['status']}] {res['suite']:9s} {res['name']} ({res['duration']:.2f}s)", flush=True)
        if res['output'] and (args.verbose or res['status'] == 'FAIL'):
            print(res['output'], flush=True)

    elapsed = time.monotonic() - start_all
    passed = sum(1 for r in results if r['status'] == 'PASS')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    skipped = sum(1 for r in results if r['status'] == 'SKIP')
    failed = [r for r in results if r['status'] == 'FAIL']
    print(f'\nSummary: {passed} passed, {partial} passed with skips, {skipped} skipped, '
          f'{len(failed)} failed ({len(results)} scripts in {elapsed:.1f}s)')
    if failed:
        print('Failed tests:')
        for r in failed:
            print(f"  - [{r['suite']}] {r['name']} (rc={r['returncode']})")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
