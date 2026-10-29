# GNOME Tweaks deployment, 2026-10-29

Added the pinned upstream GNOME Tweaks 49.0 recipe, registered its update
source and included it in the GNOME profile and desktop package dependencies.
Its Python modules and generated paths use the target Python 3.14 site-packages
directory. Runtime dependencies include PyGObject, GTK4, libadwaita, GUdev,
Notify, GNOME Desktop and the desktop settings schemas.

Signed `gnome-tweaks-49.0-r1` and `openwrt-desktop-22` were published in
`/srv/openwrt-feeds/public/snapshots/20261028T183426.170903Z`, for ABI
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`. Publication changed only those two
packages, passed router/ELF upgrade preflight and had
`same_version_rebuilds=[]`; the kernel feed remained unchanged.

The physical router `192.0.2.1` installed **only GNOME Tweaks**. The existing
desktop package remains at 21 to avoid its service upgrade hooks restarting
the active session. APK world gained the unpinned `gnome-tweaks` selection;
all previous entries were retained. The payload matched the signed published
manifest, verified against existing router trust, and both offline simulations
contained exactly one installation with no dependency upgrades or removals.

`gnome-tweaks --version` returns 49.0. Normal launch and the installed desktop
entry work in the existing ordinary-user Wayland session. Actual FreeRDP
input dismissed the first-run notice and opened Fonts, Appearance, Keyboard,
Windows and Startup Applications. Screenshots show the real controls. The
application remains open on Fonts after the verification client exits.

All 11 recorded desktop-settings schemas and 19 protected configuration/trust/
pairing files are unchanged. Tweaks creates its own first-run notice setting.
The Shell PID, boot ID and kernel remain unchanged; WAN, WAN IPv6, LAN and
WireGuard stay up, `kernelctl check` passes, and only the two preexisting
hostname-sync units remain failed. The rollback timer was disarmed after
acceptance, and router APK indexes were refreshed.

Both package builds, 39 custom-updater tests, two APK source-version tests and
`git diff --check` pass. The original host `.config` was restored byte for
byte; feed repositories and unrelated edits were preserved. Existing metadata
warnings include the native-libudev Kconfig provider recursion; this is not a
new full-image or reboot validation. The optional upstream `--debug` invocation
was rejected by application argument handling; normal launch works. Libadwaita
also emitted a spin-row parent warning without a crash during the normal run.
The optional User Themes extension was not installed or changed.

Private evidence is under `bin/deployment/gnome-tweaks/20261029/`. No machine
or desktop restart, firmware flash, commit or Git push was performed in this
follow-up.
