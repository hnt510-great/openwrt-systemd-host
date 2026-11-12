# GitLab source synchronization validation (2026-11-12)

Integrated GitLab main updates after `b3731fd86a19df66b7c341c4cdc8eafa7f3e0b74`
through `b2a948f453ae4ac264307e26469f70279372bc49` onto the public tree.
The 63 non-merge source commits have individual provenance records
(`GitLab-source:` trailers). Original author names, email addresses, dates and
Signed-off-by / Co-Authored-By trailers were preserved and checked against
GitLab. Private GitLab history is not a merge parent.

Changes include Realtek r8125/r8126/r8127/r8168 driver updates, ppp 2.5.5,
ath79 PCI radio path migration, Linux 7.3.4 with the WireGuard p2p source address
fix, RealtimeKit and the desktop preemption baseline, libvirt UEFI/vTPM/passthrough/
network-filter support (OVMF, libtpms, swtpm), QEMU native AIO and io_uring,
needrestart chroot coverage, interrupted APK transaction recovery
(`apk-transaction-guard`), the Intel AX101 2.4 GHz access point, LuCI status
redraw, uci-history credential redaction, virtio-fs host sharing, FreeRDP 3.33.1,
and gnome-remote-desktop r7 preferring Opus playback (fixes RDP audio gaps with
FreeRDP 3.33.0 clients).

Three commits needed conflict resolution against public-only changes:
`ppp: update to 2.5.5` (taken as resolved by the GitLab merge),
`configs/gnome-desktop.config` (public desktop-setup block kept alongside the new
rtkit/preemption options), and `docs/virt-manager.md` (new UEFI/TPM, passthrough,
network-filter and socket content carried into the condensed public text).

Private LAN addresses, personal home/evidence paths, the build checkout path and
user account references use public/documentation examples (`192.0.2.x`,
`/srv/openwrt`, `/srv/openwrt-validation`, `router-admin`). No private keys,
credentials, or host-specific overlays were added. Agent instruction files remain
untracked.

| Check | Result |
| --- | --- |
| Author attribution | All 63 replayed commits match original author names, emails, dates and trailers |
| Personal marker scan | Added lines and messages across all 63 commits; zero private markers |
| Content parity | Every touched file equals the sanitized GitLab file, except 10 files that already differed publicly |
| Build and publish suite | 68 tests passed |
| Allocate rebuild releases | 9 tests passed |
| needrestart / LuCI needrestart | 102 + 7 tests passed; LuCI view assertions passed |
| uci-history / units / LuCI | 39 + 2 + 4 tests passed; LuCI view assertions passed |
| APK upgrade preflight | 37 tests passed |
| APK transaction journal | 9 tests skipped (need a target environment) |
| RealtimeKit desktop | 12 tests passed |
| gnome-remote-desktop audio latency / listener | 1 + 1 tests passed |
| libvirt secondary drivers | 7 failures, identical on the unmodified GitLab tree (live-host test; needs the OpenWrt libvirt build) |
| Whitespace | `git diff --check` reports only indentation inside a quoted diff in `docs/rtkit-preemption-plan.md`, identical to GitLab |

Scope: local source integration and host checks only. No package or full firmware
build, VM run, physical-device validation, feed publication or deployment was
performed here. Incoming build, VM, and router records describe historical
upstream work; those checks and actions were not repeated.
