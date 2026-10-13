# AppImage validation, 2026-10-13

AppImage support was built into the x86_64/glibc native-systemd desktop,
tested in disposable local VMs, then installed as signed offline APKs on
the physical device at `192.0.2.1`. The physical firmware was not reflashed
or rebooted.

## Source and build

The integration selects `openwrt-appimage`, FUSE 2 alongside the existing
FUSE 3, NSS/NSPR, the CUPS client library and `unshare`. Weston starts rootless
Xwayland on demand. Cairo gains XCB support; GLVND and the virtualization Mesa
provider gain X11/GLX while retaining Wayland EGL/GBM. The session imports
`DISPLAY` into the ordinary user's systemd manager and clears it on shutdown.
No downloaded application, printing daemon or application registration helper
is embedded.

Video-feed base: `288abd790da3944875ca0b714d64036773448b3d`.
Apply `patches/feeds/0005-video-appimage.patch` to that feed; provenance is in
`configs/appimage-feeds.json`. Main-tree and feed changes remain separate.
The validated image reports `r37224+49-0ad1348fb2`; concurrent main-tree
history updates were preserved.

Package builds, followed by `make -j4 V=s`, completed successfully. Every
entry in the target's `sha256sums` verified. The fresh boot used:

```text
bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
SHA256 49e53e8e1f7c8694e6e8a10edc4c460c3b12ed5efa865a2be9f638e0b035d6db
```

All 1,811 previously enabled `y`/`m` selections were retained; sixteen feature
selections were added. The existing unrelated `luci-app-weechat` Kconfig cycle
still affects normal `make defconfig`. A focused generated package menu
excluding that package passed `conf --fatalrecursive`. Shell syntax checks,
main/feed `git diff --check`, and the six Flatpak user-link tests passed.
Unrelated modified documentation and the packages-feed bison diff were
verified against their initial snapshots.

## VM evidence

The first VM exercised the bundle on the existing image. A second VM booted
the freshly built EFI squashfs image with KVM, virtio-vga-gl and EGL headless
display. Its LAN was isolated from the physical device.

| Check | Result |
| --- | --- |
| Legacy dynamic FUSE 2 and modern static Type 2 runtimes | Ordinary-user mounted launch passed |
| Arguments containing spaces, unmount cleanup | Passed for both runtimes |
| `--appimage-extract-and-run` | Passed, without a FUSE mount |
| GTK Wayland and X11/Xwayland | Both rendered and calculated `7 + 5 = 12` |
| Local QMP input and authenticated TLS VNC input | Both worked for each GTK backend |
| Clipboard | Wayland-to-X11 and X11 reads returned `appimage-probe-12` |
| GLX framebuffer | Pixel `17,204,51,255`; software and accelerated virgl paths passed |
| Fresh accelerated compositor | Weston EGL/GBM and GLX coexisted; virgl OpenGL 4.3, Mesa 26.2.2 |
| Existing Flatpak workflow | Flathub Calculator 51.1 on GNOME 51 displayed `7+5 = 12` |
| Normal reboot | systemd PID 1, desktop startup, FUSE permissions retained; no failed system units |
| Procd recovery entry | procd PID 1, ubus available, `/dev/fuse` mode 0666, both CLI suites passed |

After the recovery check, the VM returned to systemd PID 1 and its accelerated
desktop. Both disposable VM processes were then shut down and verified absent.

Official Joplin 3.7.21 launched as the VM's ordinary user and displayed its
welcome notes. The publisher's launcher probes `unshare -Ur true`; installing
the missing `unshare` utility prevented its global `--no-sandbox` fallback.
An actual renderer carried `--enable-sandbox`, seccomp mode 2, `NoNewPrivs=1`,
zero effective capabilities and a separate PID namespace. Joplin itself
chooses unsandboxed node-enabled UI renderers, so this is not a claim that
every renderer is sandboxed. AppImage execution itself provides no sandbox.

Runtime inputs were the AppImageKit legacy runtime and the 2026-09-28 Type 2
static runtime. Their SHA256 hashes were respectively:

```text
66f5b22f035022b8bdebb54c066aa6edc7b5db282fe6cdb372e7965f80772557
156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074
```

The official `Joplin-3.7.21.AppImage` SHA256 was
`5d202dcaca31e14206826aa3f04125e7c218dbc3dc3d98479d811efbd6b856c1`.
Controlled GTK/GLX payload source is in `scripts/tests/appimage-probe.c` and
`scripts/tests/appimage-glx-probe.c`; target compiler and target pkg-config
sysroot were used, rather than host libraries.

## Physical deployment

The 21 signed APKs total 27,203,008 bytes. The offline simulation and actual
transaction contained exactly fifteen additions and six desktop replacements:

```text
fuse-utils libfuse1 libcups-runtime libfontenc libXfont2 libxkbfile
libxcvt libxshmfence libXxf86vm nspr libnss xkbcomp xwayland unshare
openwrt-appimage
weston openwrt-desktop openwrt-flatpak libcairo libglvnd libmesa-virtualization
```

APK signatures were verified using the device's existing trusted keys, and
checksums were checked before installation. All frozen APK hashes match the
final image build. `scripts/create-appimage-bundle.py` reproduced those same
21 APKs. `/etc/config/desktop` retained the existing user, enabled setting,
port and GL renderer; APK's default `.apk-new` was left for review.

The restarted physical desktop passed both FUSE runtime suites, Wayland and
X11 GUI input over authenticated TLS VNC, and X11 clipboard readback, all as
`desktop-user` (UID 32769). GLX reported **Mesa Intel UHD Graphics (JSL)**, OpenGL 4.6,
and the exact expected framebuffer pixel. Both fusermount helpers were
root-owned mode 4755; `/dev/fuse` was mode 0666. Systemd reported no failed
system units. Test units were stopped and their temporary files removed.

The boot ID, libc/procd/systemd binary hashes, procd PID 1192, netifd PID 2644
and PPPoE default route matched the pre-install snapshot. This proves the
userspace installation left those core components running without a reboot.
Joplin and Flatpak Calculator acceptance was performed in the VM; physical
acceptance used the controlled AppImage probes. Audio, printing, every possible
AppImage and physical sysupgrade were not acceptance targets.

The bundle, six original desktop APKs and pre-install configuration/world
backup are retained on the device in `/root/appimage-deployment-20261013`.
Rollback requires an explicit offline downgrade transaction for those six
packages and removal of the new support package before removing its additions;
do not restore the APK database by copying files over it.

Detailed logs, fixture hashes, image hash, VM and physical screenshots,
package manifests and backups are outside the source tree at:

```text
/srv/openwrt-validation/appimage-validation-20261013-135902
```

Nonfatal GTK accessibility-bus warnings appeared in the probes. Joplin also
reported missing optional `xdg-settings` integration and libudev/ALSA symbol
version warnings. These did not prevent the tested launches or interactions.
