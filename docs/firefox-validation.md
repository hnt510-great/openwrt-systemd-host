# Firefox ESR firmware validation

Validated on 2026-10-12 (Asia/Singapore) with an isolated 4 GiB QEMU/KVM VM.
No physical router was flashed.

## Delivered artifacts

- Firmware: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
- SHA256: `40e7b5d928944f7c4b7f1493511465362380abb1aaa094e3a7dfaa521d314f60`
- Compressed size: 492,869,716 bytes (470.0 MiB), an increase of 120.5 MiB
  over the initial image. The root partition remains 8 GiB.
- Browser APK: `bin/systemd/packages/x86_64/base/firefox-esr-bin-153.4.0-r1.apk`.
  Its upstream archive is Mozilla's official `153.4.0esr`, x86_64, zh-CN build.

APK signatures were verified with the public key embedded in the firmware.
The image checksum list and extracted final rootfs audit passed. Thirty
upstream browser ELF files remained byte-for-byte unchanged; the audit checked
87 ELF files including dependencies, finding no missing libraries or symbols.
Bundled NSS/NSPR remain in the browser's private application directory.
The existing enabled configuration and unrelated tracked changes were retained.

## Runtime results

| Check | Result |
| --- | --- |
| Narrow X.Org, Cairo, libepoxy, GTK3 and Firefox package builds | Passed |
| Complete native-systemd firmware build | Passed |
| Update-script default check and seven offline failure/upgrade cases | Passed |
| Ordinary-user panel launch and command-line launch | Passed; root launcher rejected |
| Native display protocol | Wayland |
| Rendering | WebRender (Software); hardware video decoding disabled |
| Content sandbox | Effective level 6; seccomp and user namespaces available |
| Content, socket and media process seccomp filters | Enabled |
| Browser application-update policy | DisableAppUpdate active |
| HTTPS without certificate override and local LuCI page | Passed |
| Chinese browser UI, web text and Noto CJK glyphs | Passed |
| Browser's complete upstream license document | Available through about:license |
| Copy/paste, local QEMU keyboard and TLS VNC keyboard | Passed |
| Native GTK file chooser, upload selection and download contents | Passed |
| 720p H.264, H.264 with AAC track, VP9 WebM | Video frames advanced for all three |
| Video pause, seek and native-input fullscreen | Passed |
| Certificate-verified TLS VNC and local/remote display comparison | Passed; initial comparison matched every pixel |
| Incorrect VNC password and root VNC login | Rejected |
| Terminal and virt-manager on the updated GTK3 stack | Passed; qemu:///system connected |
| Desktop restart and native reboot autostart | Passed |
| Profile settings and bookmark after native reboot | Retained |
| Signed APK release upgrade in the VM | Passed; settings/profile retained |
| Actual GRUB procd-recovery boot and Firefox panel launch | Passed |
| Actual retained-configuration firmware flash from procd | Returned to systemd |
| Profile marker, bookmark and VNC certificate after flashing | Retained |
| Home/profile directory owners and permissions | Preserved by the updated sysupgrade backup |
| Final image launcher and introspection metadata | 32-pixel icon and xlib-2.0 typelib present |
| Browser autostart | Disabled; browser opens only when requested |

The APK upgrade used a test-only signed `153.4.0-r2` metadata revision with
the same upstream executable payload, then the actual firmware upgrade
returned to the delivered `r1` package. This checks the APK release-upgrade
and data-preservation path; future upstream versions still require their own
dependency and runtime validation.

## Integration findings and limits

Enabling GTK3's X11 backend also required Cairo Xlib support, libepoxy GLX
interfaces and the `xlib-2.0` introspection metadata used by Python GTK clients.
The latter was added to the base gobject-introspection package after a
virt-manager regression exposed it.

A retained upgrade exposed the old file-only backup behavior: Firefox's files
survived, but its directories were recreated as root-owned and the ordinary user
could not write the bookmark database. Sysupgrade now includes parent directory
metadata for selected home files when GNU tar supports `--no-recursion`; the
desktop explicitly depends on GNU tar. Host tests ensure that unselected files
are not included. The repaired path was validated with an actual upgrade after
applying the updated upgrader to the running VM, including UID/GID and 0700/0710
directory mode checks. See the older-image migration note in [usage](firefox.md).

The packaged ESR uses `~/.config/mozilla/firefox/` for fresh Linux profiles.
Legacy/custom locations remain under Firefox's control. The existing `/home/`
upgrade retention preserves both locations; see [profile backups](firefox.md).

Audio services/output, protected streaming, screen sharing, GPU acceleration
and physical Intel display/USB/performance were outside this validation.
Video samples were muted. Temporary accounts, credentials and automation
flags existed only in the disposable VM, never in the delivered firmware.

Evidence and reproducible VM scripts are under
`/srv/openwrt-validation/firefox-validation-20261012/`, including
`final-image.json`, `final-rootfs-audit.json`, `browser-tests.json`,
`browser-support.json`, `desktop-regression.json`,
`apk-upgrade-result.json` and `retained-upgrade-persistence.json`.

[Usage and updates](firefox.md).
