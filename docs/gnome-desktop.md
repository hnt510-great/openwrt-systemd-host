# GNOME desktop for native systemd

This profile runs the shared GNOME desktop. Local display, GNOME
Remote Desktop's RDP screen sharing, and Sunshine/Moonlight use one ordinary
user's Wayland session. There is no VNC backend or separate RDP login session.
The first validation milestone is a disposable VM; publication and installation
on the physical router are separate operations.

The RDP server is `gnome-remote-desktop`, using FreeRDP libraries internally.
`xfreerdp3` is the validation client. This profile does not use xrdp.

## Configuration and build

Preserve `.config` before merging `configs/gnome-desktop.config`, then run
`make defconfig`. The fragment requires x86_64, glibc and native systemd.
`CONFIG_PACKAGE_libudev-zero`, seatd and the old desktop launcher must
be absent from the resulting profile. Keep GTK-VNC if virt-manager needs it;
that library does not provide a desktop VNC listener.

Select `libmesa-virtualization` as the Mesa provider and leave
`libmesa-softpipe` disabled. The virtualization variant includes Intel,
VirtIO and software rendering with GLVND support. The standalone softpipe
variant supplies EGL/GLES libraries that conflict with `libglvnd`, which
Xwayland requires; selecting both prevents APK rootfs installation.

GNOME Shell/Mutter/session/settings use the 51 series. GTK4, libadwaita, GJS
and SpiderMonkey are built from pinned upstream archives. Build tools are
staged separately; Cargo dependencies are locked and compilation runs offline
after preparation. Every custom recipe is registered in
`configs/custom-package-updates.json`. Feed changes in `feeds/packages` and
`feeds/video` belong to their own repository histories.

GTK4 includes Wayland and X11 backends for GNOME's Xwayland frame helper and
applications. Character conversion modules come from the target glibc
toolchain and require its exact libc release. GNOME audio clients use the
optional PulseAudio GLib main-loop adapter with PipeWire's Pulse server.
Blueprint uses staged host PyGObject and shared GLib libraries; target
introspection generators run through the matching target loader.
The selected `glibc-locale-utf8` package supplies `C.UTF-8`, `en_US.UTF-8`
and `zh_CN.UTF-8`. It also accepts `en_us.utf-8` through a directory alias
to the English locale, without duplicating its data. Select it for a process
with `LANG=en_US.UTF-8` (or `LANG=en_us.utf-8`); installing locale data does
not change the system or user language preference.
First-boot cache initialization registers the SVG image loader as well as
schemas, GIO modules and input modules, so GNOME application icons can load.

GNOME Shell depends on `libgio-gnutls` (built by the `glib-networking`
recipe) and `ca-bundle` for HTTPS extension downloads. Extension Manager
delegates installation to Shell, so installing a TLS-capable browser alone
does not provide this backend. After adding it to a running system, refresh
the GIO cache with `/usr/libexec/glib2-cache-update` and restart the desktop
session if Shell has already cached the unavailable TLS backend.

GNOME Files (`nautilus`) is included. LocalSearch's indexer is optional in
this profile; Nautilus handles its missing settings schema and retains basic
file browsing and filesystem search without indexed content search.
Nautilus depends on a minimal `gvfs` build that supplies the Trash, Recent,
Network, Computer, FTP and SFTP backends and the metadata daemon; without it
the Trash and Network sidebar entries fail with "Operation not supported" and
"volume doesn't implement mount". Backends needing absent services are
disabled: removable-media mounting (no `udisksd`), SMB/DNS-SD, MTP/gphoto2,
WebDAV, FUSE and keyring integration.
See the [physical TLS and Files validation](gnome-tls-files-validation.md)
for the signed deployment and actual Shell/RDP checks.

GNOME Tweaks (`gnome-tweaks`) is included for additional appearance, font,
keyboard, mouse, startup-application and window preferences. Its Python
modules install into the target Python site-packages directory, with explicit
PyGObject, GTK4, libadwaita, GUdev, Notify and desktop-schema dependencies.
See the [physical Tweaks validation](gnome-tweaks-validation.md) for the
signed deployment and application checks.

The desktop ships DejaVu Sans/Sans Mono as primary fonts and
`noto-sans-symbols2` (Noto Sans Symbols 2, OFL-1.1) as a fontconfig fallback.
DejaVu lacks several Miscellaneous Technical and pictograph code points, such
as U+23F5 used by terminal UIs like Claude Code's `⏵⏵` mode line; without
the fallback, GTK terminals render them as hex boxes (`23F5`). Check coverage
on the device with `fc-list :charset=23f5 family`.

Full systemd libudev and udevd provide device tags for logind seats. The udev
package installs device-identification, seat and access rules, not networking
renaming, firmware or module-loading rules. udevd is the only receiver of
device events; it forwards events with `/etc/hotplug.d` handlers to procd (see
[systemd supervision](systemd-native-supervision.md)). netifd, firewall and
router service configuration are unchanged. A coldplug unit identifies
DRM/input/audio devices before starting the desktop. PCI GPUs with an already
bound driver are left alone, including built-in bochs DRM in installer VMs;
only unbound display controllers need a module probe.
The native library also provides the legacy `libudev-zero` virtual name and
excludes the old implementation. An existing unpinned `libudev-zero` world
selection therefore migrates to native libudev in one APK transaction.

GNOME Settings includes display, keyboard, mouse, sound, background,
multitasking, notifications, power, applications, privacy, search,
accessibility, wellbeing and system settings. This profile omits network,
WWAN, Bluetooth, Wacom, online-account, printer and color panels. Configure
router networking through LuCI/netifd. The UDisks client library supports
Settings queries without introducing a disk-management daemon.

## Provisioning

Create an ordinary user with a nonempty login password and a writable home,
then run as root:

```sh
desktop-setup USER
desktop-rdp-setup USER
sunshine-setup USER --capture=portal
```

Sunshine enrollment also enables desktop audio. For an RDP-only setup, run
`desktop-audio-setup USER` to enable playback and microphone access.

`desktop-setup` creates or preserves TLS credentials, provisions unattended
GNOME keyring unlock, enables the desktop service and starts the user's
session on VT7 through native PAM/logind. An existing login keyring prompts
for its current passphrase; a new keyring receives a random passphrase.
The bootstrap secret is stored root-only under `/etc/desktop/gnome/` and
passed to the transient session through systemd `LoadCredential`. The
bootstrap unlock addresses the existing keyring daemon's control socket;
it does not launch another daemon with `gnome-keyring-daemon --unlock`.
RDP's separate password is read without terminal echo or through
`desktop-rdp-setup USER --password-stdin`, then sent to `grdctl` through a
pipe. Do not embed user passwords or bootstrap credentials in firmware.

A reboot starts the configured session without a local login. Keyring
availability is a startup condition, not an assumption based on an active
RDP service. Root-only configuration and user keyring files must be retained
across upgrades. Changing the login-keyring passphrase requires running
`desktop-setup USER --refresh-keyring` to update its bootstrap credential
before testing reboot persistence. An invalid replacement leaves the existing
credential file intact.

The local session can start before LAN readiness. A user supervisor waits for
Mutter and starts remote listeners only when the root service has supplied a
LAN address. LAN changes replace the listener environment and restart remote
services without replacing GNOME. RDP does not negotiate another port or bind
a wildcard address. The default is TCP 3389 on LAN IPv4 only.

RDP shares the local monitor, so changing its mode or scale in Settings >
Displays during a session closes Mutter's screen-cast stream. The server
creates a new stream, resets the RDP graphics pipeline, and the client follows
the new desktop size without reconnecting. Each new stream renegotiates its
buffers right after it starts. Upstream 51.0 kept only PipeWire's borrowed
dma-buf fd. If PipeWire closed it while a frame was still queued, the import
used a dead or reused fd. The log then shows
`Failed to import DMA buffer as EGL image: 12291` followed by
`ERRINFO_GRAPHICS_SUBSYSTEM_FAILED`, and the client disconnects. Patch 007
(`gnome-remote-desktop` 51.0-r8) keeps the server's own duplicate of each
dma-buf fd for the buffer's lifetime. See the
[r8 validation](gnome-desktop-validation.md#rdp-mode-changes-during-a-session--2026-11-12).

Sunshine retains its user's configuration, pairing state, PipeWire audio,
uinput enrollment and the Intel 8086:4e61 H.264-only encoder workaround.
Portal capture may require an initial screen-selection permission in GNOME;
reboot persistence of that permission is an acceptance check. Explicit
`sunshine-setup USER --enable-kms` selects KMS and grants the enrolled binary
its capture capability. Portal enrollment removes that capability. Configure
Sunshine Web UI credentials and pair Moonlight on its LAN endpoint.

Fcitx5 remains the input daemon. Its IBus compatibility frontend serves GNOME's
native text-input path; the pinned GNOME 51 Kimpanel extension supplies
candidate popups. GTK3/GTK4 modules support other clients. Provisioning does
not overwrite existing Fcitx profiles, dictionaries or shortcuts. A global
GTK input-module override is not imposed on native Wayland or Flatpak clients.
New profiles use Ctrl+Space as the primary input-method shortcut. Fcitx is
supervised for the lifetime of the GNOME session and also recovers after a
clean process exit; an explicit service/session stop still stops it.

## Realtime scheduling and kernel preemption

`openwrt-desktop` and `openwrt-desktop-audio` depend on RealtimeKit (`rtkit`
0.14 from `gitlab.freedesktop.org/pipewire/rtkit`). `rtkit-daemon.service` is
D-Bus activated as `org.freedesktop.RealtimeKit1`, runs as the `rtkit` system
user (UID/GID 193), chroots into `/proc` and keeps only `CAP_SYS_NICE` and
`CAP_DAC_READ_SEARCH`. A drop-in pins its system bus address to
`/run/dbus/system_bus_socket`. Mutter 51 and PipeWire 1.6 do not change their
own scheduling; both request it from RealtimeKit over D-Bus:

| Thread | Request | Expected `ps -eLo cls,rtprio,ni` |
|---|---|---|
| `rtkit-daemon` watchdog | built in | `RR`, priority 99 |
| gnome-shell `KMS thread` (default) | `MakeThreadHighPriority(-15)` | `TS`, nice -15 |
| gnome-shell `KMS thread` (`realtime`) | `MakeThreadRealtime(20)` | `RR`, priority 20 |
| PipeWire/WirePlumber `data-loop.0` | `MakeThreadRealtime(20)` (clamped from 88) | `RR`, priority 20 |
| PipeWire main thread | `MakeThreadHighPriority(-11)` | `TS`, nice -11 |

The upstream polkit action allows active and inactive local sessions. The
`/usr/share/polkit-1/rules.d/20-openwrt-rtkit.rules` rule also authorizes
members of `audio` (from `desktop-audio-setup`) and `video` (from
`desktop-setup`), which covers user services in RDP-only, headless and VM
sessions without a `seat0` session. `render` is deliberately excluded because
`libvirt-qemu` belongs to it. RealtimeKit's own limits (`MaxRealtimePriority`
20, `RLIMIT_RTTIME` 200 ms and its canary watchdog) apply to every caller.

`/etc/config/desktop` selects the Mutter KMS thread policy:

| Option | Values | Default | Effect |
|---|---|---|---|
| `kms_scheduling` | `high-priority`, `realtime`, `normal` | `high-priority` | Mutter's upstream nice -15 policy, `SCHED_RR` 20, or no elevation. `high-priority` and `realtime` enable Mutter's KMS deadline timer. |

```sh
uci set desktop.main.kms_scheduling='realtime'
uci commit desktop
/etc/init.d/desktop restart
```

The init script rejects other values. Non-default modes are passed to Mutter
as `MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY`; the session clears that variable
from a surviving user manager first, so returning to `high-priority` takes
effect on the next desktop restart.

Desktop kernels (`configs/gnome-desktop.config`) are built with
`CONFIG_PREEMPT_DYNAMIC=y` defaulting to `preempt=full`, `CONFIG_HZ_1000=y`
and `CONFIG_RT_GROUP_SCHED_DEFAULT_DISABLED=y`. With RT group scheduling
active, cgroup v2 slices have no realtime runtime, so `sched_setscheduler()`
returns `EPERM` for `rtkit-daemon`, PipeWire and gnome-shell even with
`CAP_SYS_NICE`. The x86_64 target configuration carries `HZ=1000` and
`PREEMPT_DYNAMIC`; the preemption model and the RT group default come from
the top-level `CONFIG_KERNEL_PREEMPT` and
`CONFIG_KERNEL_RT_GROUP_SCHED_DEFAULT_DISABLED`, which the fragment selects
(`include/kernel-defaults.mk` appends top-level `CONFIG_KERNEL_*` values after
the target configuration). These change the kernel ABI and need a new
reserved kernel generation.

Boot-time controls, no rebuild required:

- `rt_group_sched=0` enables realtime grants on a kernel built before this
  baseline; `rt_group_sched=1` restores RT group scheduling on a new kernel.
  `kernelctl` preserves `rt_group_sched=` from the running command line.
- `preempt=lazy`, `preempt=voluntary` or `preempt=none` select another model;
  with debugfs mounted, `/sys/kernel/debug/sched/preempt` shows and changes it.
- `kernelctl rollback` returns to the previous kernel generation.

Check the result in a running session:

```sh
zcat /proc/config.gz | grep -E 'CONFIG_(PREEMPT|HZ|RT_GROUP_SCHED)'
cat /sys/kernel/debug/sched/preempt
systemctl status rtkit-daemon.service
ps -eLo pid,tid,cls,rtprio,ni,comm | grep -E 'rtkit|KMS thread|pipewire|data-loop'
journalctl -b _UID=$(id -u USER) | grep "KMS thread"
```

gnome-shell logs `Failed to make thread 'KMS thread' high priority` when the
request is refused. See the [RealtimeKit validation](rtkit-validation.md).

## Validation boundary

Use [GNOME validation](gnome-desktop-validation.md) for the required build,
VM, session, audio, input and persistence checks. Package builds alone do not
establish a working graphical session. VM rendering/encoding results do not
establish physical GPU stability or target streaming performance.
