# SPICE GTK EGL build repair

## Physical diagnosis (2026-10-30)

On the physical OpenWrt host, `archlinux` was running with its guest agent
connected, SPICE GL enabled on `/dev/dri/renderD128`, and VirtIO 3D video.
QEMU logged `client does not support GL scanout`; the installed
`spice-gtk-0.43-r1` returned `False` for the default
`SpiceClientGLib.Session().get_property('gl-scanout')`.
The corresponding local build configuration contained `#undef HAVE_EGL`.
This identifies a client build limitation, despite a running guest.
The guest was later observed shut off; no guest power operation was issued
during diagnosis.

## Source repair

Explicitly enable Meson's `egl` feature alongside `auto_features=disabled`.
Advance the package release to `0.43-r2`. The monitor-ready redraw patch
must use `#ifdef HAVE_EGL`, because Meson defines this macro without a value.
The runtime smoke script now checks that GL scanout defaults to enabled.

## Validation

- `make package/custom/spice-gtk/compile -j3 V=s`: passed.
- A target-linked C probe run through `scripts/gi-target-runner` against
  the rebuilt library reported `SPICE default gl-scanout=true`.
- `python3 scripts/tests/test-apk-source-versions.py`: two tests passed.
- Runtime smoke script Python syntax and `git diff --check`: passed.
- Physical host `apk verify` accepted the rebuilt signed APK.
- Exact offline `apk add --simulate --no-network --repositories-file
  /dev/null` with that APK selected only `spice-gtk` (`0.43-r1` to `0.43-r2`).

Artifact: `bin/systemd/packages/x86_64/base/spice-gtk-0.43-r2.apk`.
SHA256: `a61f04b014ffca09d6f79f1e2d613871405ae76863df976ba05dbae433a8e205`.
Physical preflight copy: `/tmp/spice-gtk-egl-fix-0.43-r2.apk`.
Build log: `/tmp/spice-gtk-egl-build-20261030.log`.

## Authorized physical deployment and acceptance

After explicit user authorization, installed the same verified APK offline
on 2026-10-30. Only `spice-gtk` was upgraded to `0.43-r2`. Restored and
compared `/etc/apk/world` with its pre-install copy; it is unchanged.
Both installed client library hashes match the packaged build, and a new
Python process reports the default `gl-scanout` as `True`.

Reopened virt-manager in the existing desktop session and started
`archlinux`. Its SPICE viewer connected without the previous unsupported
GL scanout warning. No physical host reboot or desktop session restart
was performed; the host boot ID remained
`00000000-0000-4000-8000-000000000007`, with zero failed system units.
The user subsequently confirmed normal operation ("正常了"). This is
user-confirmed console acceptance; an automated desktop screenshot was
unavailable because GNOME denied the external screenshot request.

The backup of APK world and the VM XML is in
`/srv/libvirt/diagnostics/spice-egl-fix-20261030/` on the physical host.
The user's concurrent VM media, boot-order, and power operations were
preserved. No feed publication or full runtime smoke suite was performed.

## Installer GL reconnect follow-up — 2026-11-15

A local QEMU 11.1.2/SeaBIOS guest booted the existing installer from SATA
CD-ROM with VirtIO VGA GL. A Debian host SPICE client could reconnect to an
already idle installer and show a blank window until guest input caused a new
GL draw. QMP `screendump` returned `no surface` even when SPICE displayed the
guest correctly. This is a GL client rendering issue, not an optical boot test.

The existing r2 patch queues a render when monitor readiness changes. Release
r3 additionally queues a render after importing a scanout into an already-ready
widget, including the X11 drawing-area branch. Scanout notification itself does
not require a draw acknowledgement. Failed imports return without scheduling a
render of an invalid image.

`make package/custom/spice-gtk/compile -j3 V=s` passed. The patch was maintained
with quilt and `make package/custom/spice-gtk/refresh`. The new runtime helper is
`scripts/tests/spice-gl-console.py`. It captures the actual GTK GL framebuffer,
sends only Down/Up through SPICE, then reconnects twice without sending input,
resizing, or forcing a render. It rejects blank captures and unchanged input.

The rebuilt target r3 libraries passed that helper in a private client chroot:
three GL scanouts, two guest draw messages, and both passive reconnect images
identical to the final menu image. The chroot used target GTK/SPICE libraries
with a private copy of the host's Mesa graphics stack for the AMD render node;
the firmware's Intel/VirtIO Mesa selection does not supply a host radeonsi
driver. No host libraries or running applications were replaced.

On Fedora 45 (`spice-gtk3` `0.43-5.fc45`, QEMU `11.1.3-1.fc45`, AMD
`renderD128`), isolated `<listen type='none'/>` clones confirmed the same
client behavior against the live host stack: stock Fedora `spice-gtk3`
rendered normally when connected at boot, stayed blank on an idle-menu
connect until a `Down`/`Up` draw arrived, whereas the privately loaded r3
library rendered `initial`, `Down`/`Up`, and two passive reconnects without
extra input. Note separately that libvirt `<listen type='address'/>` on
QEMU 11.1 triggers `spice_remote_client = 1` and exports black `(0, 0, 0, 255)`
DMA-BUF textures regardless of client `spice-gtk3` version; see
[installer validation](installer-iso-validation.md).

Evidence: `/srv/openwrt-validation/installer-spice3d-validation-20261115/`, including
`spice-build.log`, `spice-r3-client.log`, `spice-r3/receipt.json` and its PNGs,
and `fedora/linux2024-verified/`.
The exact rebuilt ISO matrix is recorded in
[installer validation](installer-iso-validation.md). These are local and
isolated-remote VM/client checks. System host packages on Fedora were not
replaced, and an external host must update its own SPICE client to receive the
client-side idle-reconnect fix.
