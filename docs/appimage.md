# AppImage applications on the systemd desktop

`openwrt-appimage` (`1-r7`) supports downloaded x86_64 AppImages on this
checkout's glibc/native-systemd desktop (both GNOME 51 and KDE Plasma 6.8.3).
It depends on `openwrt-desktop-base`, `xwayland`, and `glibc-distro-compat`,
and supplies FUSE 2 and FUSE 3, Mozilla NSS/NSPR, the CUPS client library and
the existing GTK/audio/font libraries. GNOME (Mutter) and KDE Plasma
(`kwin_wayland_wrapper --xwayland`) launch Xwayland on demand for X11
applications. The desktop Mesa provider (`libmesa-virtualization`) and GLVND
include GLX and Vulkan ICDs as well as Wayland EGL/GLES paths.

Merge `configs/appimage.config` into the existing configuration and run
`make defconfig` (the `appimage` component is also available in the offline
installer ISO, requiring either `gnome` or `plasma`). The selections are
retained in the desktop config. Build `package/custom/openwrt-appimage/compile`
first; a full firmware build or signed LAN APK feed publication packages it.

## Download and launch

The application runtime is embedded in each AppImage. No AppImage daemon or
automatic application installer is needed. As the ordinary desktop user,
download an application from its publisher, verify its published checksum or
signature, and run it from a desktop terminal (GNOME Terminal or Konsole):

```sh
mkdir -p ~/Applications
chmod +x ~/Applications/Application-x86_64.AppImage
~/Applications/Application-x86_64.AppImage
```

Replace an application file manually to update it. AppImage packaging does
not automatically sandbox applications; an Electron application's own sandbox
is separate and should remain enabled. Root execution and `--no-sandbox` are
not part of the supported desktop workflow. Native Wayland options differ by
application; X11 applications use the `DISPLAY` assigned by the desktop
session's Xwayland server.

Older Type 2 runtimes use the real FUSE 2 `libfuse.so.2` and `fusermount`.
Current static runtimes can use `fusermount3`. Both helpers must be owned by
root with mode 4755, and `/dev/fuse` must permit access by the desktop user;
`systemd-udevd` applies the package's `99-appimage-fuse.rules` permission rule
on x86_64 native-systemd boots.

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

## Installing on an existing device

Native-systemd images intentionally disable public OpenWrt snapshot feeds.
Use signed packages from the matching LAN APK feed (`docs/lan-apk-feeds.md`) or
select the `appimage` component in the offline installer ISO (`docs/installer-iso.md`),
not Alpine or public musl repositories:

```sh
sudo apk update
sudo apk add openwrt-appimage
```

No firmware reflash or device reboot is needed for these userspace packages.
Restarting the desktop to activate Xwayland closes its applications; router
services remain running. Open a new desktop terminal after the restart so
`DISPLAY` and `WAYLAND_DISPLAY` refer to the current session.

Application files and data under `/home` are excluded from config-only
`sysupgrade -b` archives (`files/lib/upgrade/keep.d/multiuser`), so keep
separate backups of downloaded AppImage files and user data before replacing
the disk image.

The support package also installs `unshare`. Some Electron AppImage launchers
probe `unshare -Ur true` and silently add `--no-sandbox` if the command is
missing, even when the kernel supports user namespaces. Check actual process
arguments and renderer seccomp state when validating an application's sandbox.

## Acceptance checks

`scripts/test-appimage.sh` runs on the target as an ordinary user with the
controlled legacy and modern probe images built from
`scripts/tests/appimage-probe.c`. It checks FUSE mounting, arguments containing
spaces, unmount cleanup and extraction fallback. GUI acceptance additionally
checks both GTK backends, local/RDP/Sunshine input, clipboard and an official
Electron AppImage with its sandbox enabled. See `appimage-validation.md` for
the historical build results and physical-device evidence.
