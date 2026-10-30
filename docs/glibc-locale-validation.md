# UTF-8 locale alias validation, 2026-10-29

`glibc-locale-utf8-2.43_p2-r7` adds `en_us.utf8` as a relative symlink to
`en_US.utf8`. Target glibc normalizes the codeset in `en_us.utf-8` but retains
the language/territory case, so the alias supports that spelling without
copying locale data. The package remains pinned to `libc=2.43-r7`.

The package build, two APK source-version tests and scoped `git diff --check`
passed. Target-loader checks loaded UTF-8 character and numeric categories
for lowercase and canonical English spellings, C and Simplified Chinese.

The coordinated signed publisher passed router/ELF upgrade preflight with
`same_version_rebuilds=[]`. Publication changed only the locale package;
the kernel feed stayed unchanged. The active userspace snapshot is
`/srv/openwrt-feeds/public/snapshots/20261029T132253.933075Z` for ABI
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`.

The physical router at `192.0.2.1` verified the new and rollback APKs against
its existing signing trust. The installed payload matched the published
manifest SHA256 `db2739c3ba37c0d592272e555b2f1f68116c89bb8a840fc999f056b97c58a092`.
Offline simulations and the actual transaction upgraded only this package
from `2.43_p1-r7` to `2.43_p2-r7`. No dependencies were upgraded or removed.

Native Python on the router successfully loaded `en_us.utf-8`, `en_us.UTF-8`,
`en_US.UTF-8`, `en_US.utf8`, `C.UTF-8` and `zh_CN.UTF-8`, verified UTF-8 codesets,
and exercised numeric and collation data. All 20 recorded protected files,
APK world, boot ID, GNOME Shell PID, failed-unit list and network-interface
up/down states were unchanged. `kernelctl check` passed. Feed indexes were
refreshed and the independent rollback timer was disarmed after acceptance.
Signed rollback artifacts and configuration backups remain on the router.

Private execution evidence is under `bin/deployment/locale-utf8/20261029/`.
No reboot, firmware flash, desktop restart, default-language change, commit
or Git push was performed. This is package and physical-runtime validation;
no full-image or VM validation was performed for this update.
