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

## Historical validation note (2026-10-15)

Initial build and physical-router JSON-RPC checks passed on `192.0.2.1`
(current recipe is `1.0.0-r4`), covering current/previous/all boots, unit and
priority filters, invalid argument rejection, and authenticated vs anonymous
access control. Interactive browser rendering and download were not tested.
