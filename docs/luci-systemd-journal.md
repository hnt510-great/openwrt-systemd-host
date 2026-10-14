# LuCI systemd journal viewer

`luci-app-systemd-journal` adds **Status → System Log → Systemd Journal**
at `/cgi-bin/luci/admin/status/logs/journal`. It is a separate package under
`package/custom/` and is selected in `.config` and
`configs/x86-64-systemd-desktop.config` for native systemd builds.

The page reads the current boot, previous boot, or all retained boots. It
supports an exact systemd unit name, a maximum numeric priority (the selected
severity and higher), and the latest 100, 300, or 1000 journal entries. Empty
unit names include every unit. Search performs a case-insensitive literal
filter on the returned lines. Automatic refresh runs every five seconds and
can be paused; automatic scrolling can also be disabled. Download exports
the displayed text to `systemd-journal.txt`.

The `luci.journal.read` RPC grants read access only. It invokes a fixed
`journalctl` command with validated and shell-quoted arguments, a four-second
timeout, and a 256 KiB output limit. Logs are displayed as textarea values.
Journal retention, service management, and journal deletion are outside the
package's interface.

Build and local checks:

```sh
make defconfig
make -j4 package/custom/luci-app-systemd-journal/compile V=s
python3 scripts/tests/test-luci-journal.py
node scripts/tests/test-luci-journal-view.js
```

On 2026-10-15, `luci-app-systemd-journal-1.0.0-r2.apk` was built and its
signature verified with the firmware's APK keys. Seven backend tests passed,
covering typed RPC declarations, command arguments, boot selection, invalid
inputs, output limits, command failure, and timeout. The JavaScript checks
passed for safe text rendering, search, paused polling, stale responses,
and failed RPC requests.

Full-tree strict Kconfig checking still encounters the existing unrelated
`luci-app-weechat` / WeeChat dependency cycle. Focused `conf --fatalrecursive`
validation using a temporary package Kconfig that excludes `luci-app-weechat`
passed. Configuration comparison retained all existing selections and added
only `CONFIG_PACKAGE_luci-app-systemd-journal=y`.

The signed APK was installed offline on `192.0.2.1` after transaction
simulation. Initial runtime checking found that the line-count argument
needed a numeric example in rpcd's ucode declaration; release 2 corrects
that declaration and was rebuilt and installed. The final installed package
set differs from the baseline by this package alone. The kernel packages,
boot ID, and `/etc/config/{network,firewall,dhcp}` hashes were unchanged;
procd and journald remained active.

Physical-router validation passed for HTTPS JSON-RPC journal reads with
current, previous, and all boots, unit and priority filters, an unknown unit,
and invalid arguments. Anonymous and ungranted sessions were denied.
The authenticated LuCI route rendered the new view, and its installed
JavaScript was served successfully. Temporary test sessions were destroyed.
Browser rendering and interactive download were not visually tested because
no browser was available. No firmware image was rebuilt, flashed, or rebooted.

Build/test logs and before/after snapshots are in
`/tmp/luci-journal-validation-20261015/` on the build host. The router retains
the configuration/package-state backup and signed APKs under
`/root/luci-journal-deployment-20261015/`.
