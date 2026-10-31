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
