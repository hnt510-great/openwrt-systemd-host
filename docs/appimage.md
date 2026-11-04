# AppImage applications on the systemd desktop

`openwrt-appimage` supports downloaded x86_64 AppImages on this checkout's
glibc/native-systemd GNOME desktop. It supplies FUSE 2 and FUSE 3, Mozilla
NSS/NSPR, the CUPS client library and the existing GTK/audio/font libraries.
GNOME supplies Xwayland for X11 applications; Mesa and GLVND provide the
configured graphics runtime.

Merge `configs/appimage.config` into the existing configuration and run
`make defconfig`. The new selections are also retained in the desktop config.
Build `package/custom/openwrt-appimage/compile` first; a full firmware build
embeds the packages. The video-feed changes must accompany the main tree;
their incremental patch and source revisions are recorded with this feature.

## Download and launch

The application runtime is embedded in each AppImage. No AppImage daemon or
automatic application installer is needed. As the ordinary desktop user,
download an application from its publisher, verify its published checksum or
signature, and run it from a GNOME terminal:

```sh
mkdir -p ~/Applications
chmod +x ~/Applications/Application-x86_64.AppImage
~/Applications/Application-x86_64.AppImage
```

Replace an application file manually to update it. AppImage packaging does
not automatically sandbox applications; an Electron application's own sandbox
is separate and should remain enabled. Root execution and `--no-sandbox` are
not part of the supported desktop workflow. Native Wayland options differ by
application; X11 applications use the `DISPLAY` supplied by the desktop session.

Older Type 2 runtimes use the real FUSE 2 `libfuse.so.2` and `fusermount`.
Current static runtimes can use `fusermount3`. Both helpers must be owned by
root with mode 4755, and `/dev/fuse` must permit access by the desktop user.
The package includes both systemd/udev and procd hotplug permission rules.

If mounting fails, a Type 2 image can normally be extracted and run:

```sh
~/Applications/Application-x86_64.AppImage --appimage-extract-and-run
```

Extraction consumes additional storage; `/tmp` is RAM-backed. For a persistent
extracted copy, run `--appimage-extract` in a dedicated application directory
and launch its `squashfs-root/AppRun`. This fallback does not fix missing
application libraries. Inspect ELF `NEEDED` entries with `readelf -d` and map
missing libraries to this build's APK packages. Bundles requiring a newer
glibc, different CPU architecture, unavailable desktop protocols, or extra
services need separate compatibility work.

## Install dependencies on an existing physical device

Native-systemd images intentionally disable public OpenWrt snapshot feeds.
Use signed packages from the matching `bin/systemd` build, not Alpine or
public musl/procd repositories. The AppImage bundle contains its dependency
packages and their matching desktop libraries and session integration.

Transfer the complete bundle and its checksums over SSH. As root, verify the
checksums and APK signatures, then simulate the offline transaction before
installing it. The transaction must contain only the reviewed additions and
desktop-library replacements; libc, kernel and router packages are excluded.
Keep the original desktop APKs and configuration backup for rollback.

Build and review the complete userspace dependency transaction for the current
GNOME image. Retain the existing trust configuration and use matching signed
packages. Package sets from earlier desktop integrations are not a dependency
closure for the current image.

No firmware reflash or device reboot is needed for these userspace packages.
Restarting the desktop to activate Xwayland closes its applications; router
services remain running. Open a new desktop terminal after the restart so
`DISPLAY` and `WAYLAND_DISPLAY` refer to the current session.

Application files and data under `/home` enter the existing upgrade backup
policy. Large AppImages can inflate that archive. Keep separate copies of
downloaded application files and review backup size before a sysupgrade;
this integration does not change the home backup policy.

The support package also installs `unshare`. Some Electron AppImage launchers
probe `unshare -Ur true` and silently add `--no-sandbox` if the command is
missing, even when the kernel supports user namespaces. Check actual process
arguments and renderer seccomp state when validating an application's sandbox.

## Acceptance checks

`scripts/test-appimage.sh` runs on the target as an ordinary user with the
controlled legacy and modern probe images built from
`scripts/tests/appimage-probe.c`. It checks FUSE mounting, arguments containing
spaces, unmount cleanup and extraction fallback. GUI acceptance additionally
checks both GTK backends, local/RDP input, clipboard and an official Electron
AppImage with its sandbox enabled. See `appimage-validation.md` for the exact
artifacts, build results and physical-device evidence.
