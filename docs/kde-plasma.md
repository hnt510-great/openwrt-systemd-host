# KDE Plasma 6.8.3 Desktop on OpenWrt x86_64 (Native systemd)

This tree supports **KDE Plasma 6.8.3 (Wayland)** alongside GNOME 51 on x86_64/glibc native-systemd OpenWrt, sharing the same PAM/logind VT7 session lifecycle, TPM2-sealed Secret Service keyring unlock (`openwrt-desktop-keyring`), PipeWire audio (`openwrt-desktop-audio`), Fcitx5 Chinese Pinyin IME (`openwrt-desktop-ime-plasma`), Sunshine/Moonlight streaming, and LuCI `Services → Desktop` session switcher (`luci-app-desktop`).

## Architecture & Package Layout

- **Qt 6.11.3 (`feeds/video/frameworks/qt6/*`, `package/custom/qt6*`)**:
  - Upgraded from 6.9.3 to 6.11.3. Following Qt 6.11's upstream Wayland consolidation, `qt6waylandclient` and `qt6waylandclient-dev` are built and packaged by `qt6base` (with `wayland/host` for `qtwaylandscanner`), while `package/custom/qt6wayland` provides optional `qt6wayland-extras`.
  - `qt6base-core` enables `-DFEATURE_glib=ON` (required by `pulseaudio-qt` / `plasma-pa`) and `qt6tools` packages `libQt6UiTools.so.*` (required by `aurorae` and `kwin`).
  - Added `qt65compat`, `qt6positioning`, `qt6location`, `polkit-qt6` (0.201.1), `qcoro6` (0.13.0), `qtkeychain-qt6` (0.18.0 with `libsecret`), `kirigami-addons` (1.16.1), and `pulseaudio-qt` (1.9.0).
- **KDE Frameworks 6.32.0 (`package/custom/extra-cmake-modules`, `package/custom/kf6-*`)**:
  - Upgraded all 35 existing KF6 recipes to 6.32.0 and added 20 new KF6 recipes (`kf6-kauth`, `kf6-kidletime`, `kf6-ksvg`, `kf6-krunner`, `kf6-kdeclarative`, `kf6-kded`, `kf6-kfilemetadata`, `kf6-kholidays`, `kf6-kitemmodels`, `kf6-kquickcharts`, `kf6-kstatusnotifieritem`, `kf6-kunitconversion`, `kf6-kwallet`, `kf6-syntax-highlighting`, `kf6-ktexteditor`, `kf6-prison`, `kf6-frameworkintegration`, `kf6-qqc2-desktop-style`, `kf6-kimageformats`, `kf6-kuserfeedback`).
  - `kf6-kwallet` builds only the client library (`-DBUILD_KSECRETD=OFF -DBUILD_KWALLETD=OFF -DBUILD_KWALLET_QUERY=OFF`) so KWallet never contends with `gnome-keyring-daemon` over `org.freedesktop.secrets`.
- **KDE Plasma 6.8.3 & Dolphin 26.08.3 (`package/custom/*`)**:
  - 32 Plasma 6.8.3 packages plus `dolphin` 26.08.3 and `konsole` 26.08.3 (`-r4`, decoupled from hardcoded `fcitx5-qt`).
  - `kwin` builds with `-DKWIN_BUILD_X11=ON` to provide XWayland support for `kwin_wayland_wrapper --xwayland`.
  - `plasma-workspace` builds with `-DWITH_X11=OFF -DBUILD_xembed-sni-proxy=OFF -DBUILD_GEOTIMEZONED=OFF` and optional Flatpak notification integration disabled (`001-disable-optional-flatpak.patch`) so pure Plasma never pulls unselected `flatpak`.
  - `kscreenlocker` ships `/etc/pam.d/kde` (`pam_unix.so`, without `pam_rootok`).
  - `krdp` 6.8.3 includes `001-add-rdpsnd-pipewire-playback.patch`, implementing an independent FreeRDP 3 RDPSND audio playback channel that captures PipeWire default sink monitor audio (`48kHz stereo S16 PCM`) and streams it to RDP clients.
- **OpenWrt Desktop Integration**:
  - `openwrt-desktop-plasma-core`: session plugin `/usr/libexec/openwrt-desktop/sessions.d/plasma`, `/usr/libexec/desktop-plasma-settings` (forces `startkderc` `systemdBoot=force` for native `plasma-workspace-wayland.target` user-unit boot, disables idle suspend, initializes Fcitx5), `/usr/libexec/desktop-plasma-remotes`, `openwrt-plasma-remotes.service`, and `/etc/xdg/xdg-desktop-portal/kde-portals.conf` (routes `org.freedesktop.impl.portal.Secret` to `gnome-keyring`).
  - `openwrt-desktop-plasma`: daily metapackage pulling `openwrt-desktop-plasma-core`, `systemsettings`, `kscreen`, `dolphin`, `konsole`, `openwrt-desktop-audio`, `plasma-pa`, and `openwrt-desktop-ime-plasma` (which ships `openwrt-fcitx5-plasma.service`).
  - `openwrt-desktop-plasma-rdp`: KRdp integration with `/usr/libexec/desktop-plasma-rdp-configure` (reads password from stdin into Secret Service under QtKeychain `KRDP` schema and writes `krdpserverrc`) and `/usr/libexec/desktop-krdp-wrapper` drop-in (`app-org.kde.krdpserver.service.d/openwrt.conf`) enforcing LAN IPv4 binding and active-session gating.

## Configuration Fragments

- `configs/plasma-packages.config`: builds Plasma 6.8.3, KRdp, Dolphin, and integration APKs as `=m` without preinstalling Plasma into the default GNOME base image.
- `configs/plasma.config`: selects Plasma packages as `=y` for Plasma-preinstalled images.
- `configs/installer-components.json`: registers the optional `plasma` component (`default: false`) alongside `gnome` (`default: true`), with `depends_any: ["gnome", "plasma"]` for `audio`, `ime`, `rdp`, `sunshine`, `flatpak`, and `appimage` (and conditional `virt-manager` installation under `virtualization` when a desktop is selected).

## On-Device Provisioning & Usage

```sh
# Provision desktop user & keyring (shared across GNOME and Plasma)
desktop-setup USER

# Switch between installed desktop sessions (or use LuCI Services -> Desktop)
desktop-ctl switch --session plasma
desktop-ctl switch --session gnome
desktop-ctl --json status

# Configure LAN-only RDP for Plasma (KRdp + PipeWire RDPSND audio)
desktop-rdp-setup USER --session plasma [--password-stdin]

# Configure Sunshine/Moonlight portal capture
sunshine-setup USER --capture=portal
```

## Offline Installer ISO

In the `openwrt-installer` TUI (or `--answers FILE`), select `plasma` (and optional `audio`, `ime`, `rdp`, `sunshine`). Answer files support `accounts.user.desktop_session` (`"gnome"` or `"plasma"`) and `accounts.user.desktop_autostart` (with backward compatibility for legacy `gnome_autostart`).
