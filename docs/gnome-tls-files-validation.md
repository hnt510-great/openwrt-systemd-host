# GNOME TLS and Files validation, 2026-10-29

Published signed packages and installed them on the physical router
`192.0.2.1`. The reviewed offline transaction made exactly these changes:

| Package | Before | After |
| --- | --- | --- |
| libgio-gnutls | absent | 2.80.1-r1 |
| gnome-shell | 51.1-r1 | 51.1-r2 |
| nautilus | 51.1-r1 | 51.1-r2 |

The signed userspace snapshot is
`/srv/openwrt-feeds/public/snapshots/20261028T181420.611471Z`, for ABI
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`. Publication changed only these
three packages, with `same_version_rebuilds=[]`, passing router upgrade and
ELF transition preflight. The kernel feed stayed unchanged. Router indexes
were refreshed and now expose `libgio-gnutls` in the matching packages feed.
Incoming payload hashes matched the published manifest, signatures verified
against existing router trust, and the repeated offline simulation matched
the reviewed three-package plan before installation.

## Diagnoses and changes

GIO initially selected its dummy TLS backend: the target GJS HTTPS check
failed with `GIO has no TLS backend`. The existing `glib-networking` recipe
produces `libgio-gnutls`; no new custom recipe is needed. Shell now depends
on that package and `ca-bundle`, and the GNOME profile selects both.

Nautilus was already installed, but crashed on an unconditional lookup of
the absent `org.freedesktop.Tracker3.Miner.Files` schema. The patch makes that
schema optional and returns no indexed locations when it is unavailable.
Basic browsing and filesystem search remain available; the optional
LocalSearch daemon and indexed content search are not added.

## Physical checks

- Target GJS loaded the real GNOME libraries, typelibs and schemas, and
  selected `GTlsBackendGnutls`.
- The ordinary user's libsoup/GIO requests downloaded Kimpanel metadata and
  its 26,311-byte ZIP over HTTPS. Both returned HTTP 200, with zero TLS
  certificate errors. This check did not install the extension.
- Shell's actual `InstallRemoteExtension` D-Bus method fetched metadata and
  displayed the installation confirmation over a real FreeRDP connection.
  Escape cancelled it and the method returned `('cancelled',)`. Existing
  extensions were not replaced.
- Through actual RDP keyboard input, Nautilus displayed a fixture directory,
  entered its subdirectory, and found `tls-fixed.txt` by filename search,
  with the LocalSearch schema still absent. It was then opened at the user's
  home directory.

Two desktop restarts were performed with user authorization. Shell's first
startup during installation still reported unavailable TLS; an explicit
restart after cache refresh and transaction completion selected GnuTLS and
passed the actual Shell confirmation test. No machine reboot was performed.

## Preservation and source checks

The installed-package comparison contains exactly the three changes above.
APK world and boot ID remain unchanged. Nineteen recorded configuration,
trust and pairing files retain their hashes; rotating Sunshine logs are
excluded from that configuration comparison. WAN, WAN IPv6, LAN and
WireGuard remain up. `kernelctl check` passes, and the only failed units
remain the two preexisting hostname-sync units. The independent rollback
timer was disarmed after acceptance; original signed packages and private
configuration backups remain available on the router.

The three package builds, 39 custom-updater tests, two APK source-version
tests, JavaScript syntax checks and `git diff --check` passed. Checkpatch was
run with kernel whitespace/brace rules excluded to retain upstream GNOME C
style. Temporary `make defconfig` emitted the existing native-libudev
provider-recursion diagnostic; this run does not establish a clean strict
Kconfig check or a new complete firmware/boot validation.

The original host `.config` was restored byte for byte. Feed repositories
and unrelated local edits were preserved. No commit or push was performed.
Private build, publication, simulation, runtime and RDP screenshot evidence
is under `bin/deployment/gnome-tls-files/20261029/`; it must not be published
as source. Task-created temporary files and the verification client were
removed, while the user's Nautilus home window remains open.
