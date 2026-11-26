# Firefox ESR on the systemd desktop

The x86_64/glibc image includes Mozilla's official Simplified Chinese Firefox
ESR build as `firefox-esr-bin`. It runs directly on Wayland as an ordinary user
in both GNOME 51 and KDE Plasma 6.8.3 sessions.
After creating a user, setting a password and running `desktop-setup USER`,
launch Firefox from the desktop application launcher (GNOME Application Grid or
KDE Plasma Application Launcher). The browser does not start
automatically. From the desktop terminal, run:

```sh
firefox-esr
firefox-esr https://example.com/
```

`firefox` is an alias for the same launcher. Root launches are rejected.
Each user has a private profile in Firefox's default location. This ESR uses
`~/.config/mozilla/firefox/` for a fresh Linux account; existing legacy profiles
may remain under `~/.mozilla/firefox/`. Custom `XDG_CONFIG_HOME` values are also
honored. Use `about:profiles` to see the active root directory. The package does
not create users, embed profiles or change the user's default-browser choice.

The browser detects EGL/WebRender and VA-API automatically, falling back to
software when acceleration is unavailable. The Intel iHD driver is included for
the N5105/Jasper Lake desktop. H.264 uses the target FFmpeg libraries; VP9 can
use bundled FFVPX. Both use libva for hardware decoding, and codecs unsupported
by the GPU retain software decoding. Noto Sans CJK provides Simplified Chinese
glyphs. X11 client
libraries and GTK's X11 backend satisfy the official binary's link requirements;
the browser uses Wayland and needs no Xorg or Xwayland server.

This integration covers browsing, downloads and basic video pictures.
Protected streaming and screen sharing are outside this integration. Hardware
video decoding is validated separately from audio and remote-display transport;
remote display and browser audio are carried over LAN RDP (`gnome-remote-desktop`
or `krdp`) and Sunshine/Moonlight via PipeWire (see [desktop-audio.md](desktop-audio.md)).

## VA-API video decoding

Firefox selects FFmpeg's `FFMPEG_VAAPI` build option, libva, `libigdgmm` and
`intel-media-driver`. The Firefox configuration fragment also selects
`libva-utils`, which provides `vainfo`. The driver uses Intel's upstream
full-feature build with prebuilt media shaders; its license notices are installed
under `/usr/share/licenses/intel-media-driver/`.

The desktop user must have read/write access to `/dev/dri/renderD128` (or the
actual Intel render node). Existing `desktop-setup` enrolls the user in `render`
and `video`; no additional privilege or sandbox bypass is required. From the
ordinary user's terminal:

```sh
vainfo --display drm --device /dev/dri/renderD128
firefox-esr
```

In `about:support`, check Wayland, the compositor, and the codec support table.
A hardware-available entry alone does not prove that a playing video uses VA-API.
For diagnosis, start a separate temporary profile with
`MOZ_LOG=timestamp,PlatformDecoderModule:4,FFmpegVideo:5` and check for a successful VA-API decoder
initialization while frames advance; correlate with the Intel Video engine.
N5105 hardware does not decode AV1, which must continue through software.

The packaged defaults enable hardware decoding and leave WebRender selection to
Firefox. Existing user overrides are preserved. If a profile explicitly disables
hardware decoding or forces software WebRender, reset
`media.hardware-video-decoding.enabled` and `gfx.webrender.software` in
`about:config`, then restart that browser. ESR 153 no longer uses the older
`media.ffmpeg.vaapi.enabled` preference. Do not disable the RDD sandbox or force
hardware decoding past Firefox's driver checks.

`sh scripts/tests/firefox-smoke.sh` checks libraries and FFmpeg VA-API codec
configurations without requiring a GPU. Add `--vaapi` on real hardware to also
check driver initialization with `vainfo`. See the VA-API section in the
[validation record](firefox-validation.md) for measured results.

## Updates and profile backups

Browser application updates are disabled with Mozilla's `DisableAppUpdate`
policy. Update the signed APK together with its dependencies, or install a new
firmware image. Extension updates retain Firefox's normal behavior.
Do not manually overwrite the APK-owned application directory.

On the build host, `firefox-esr-bin` is registered in
`configs/custom-package-updates.json` (`provider: firefox`, `policy: major`), so
`./scripts/feeds update -a` or the custom updater tracks new ESR releases
(including new ESR major branches):

```sh
python3 scripts/update-custom-packages.py --check --package firefox-esr-bin
python3 scripts/update-custom-packages.py --update --package firefox-esr-bin
make package/custom/firefox-esr-bin/compile V=s
```

The updater verifies the official archive's SHA-256, updates version/hash
metadata, and resets `PKG_RELEASE`. Publish updated APKs through the gated LAN
feed workflow (`scripts/build-and-publish.sh` or `scripts/publish-changed-feeds.sh`)
and install on the router with `apk upgrade`.

Close Firefox before backing up its profile. As the desktop user:

```sh
tar -czf "$HOME/firefox-profile-backup.tar.gz" -C "$HOME" .config/mozilla/firefox
```

For a legacy or custom profile, substitute the root directory shown by
`about:profiles`. Store a copy outside the router: `/home` is excluded from
config-only `sysupgrade -b` archives (`files/lib/upgrade/keep.d/multiuser`), so
browser profiles and downloads must be backed up separately before replacing the
disk image via installation media or offline imaging. Keep a matching profile
backup if rolling back to an older Firefox version; profiles updated by newer
versions are not guaranteed to work after a downgrade.

## Build and runtime checks

Feed changes for `video` and `packages` are already committed in the feed
checkouts and mirrored via the cumulative snapshots in
`configs/feed-mirrors-snapshot.json` (`patches/feeds/0058-video-local-snapshot.patch`
and `patches/feeds/0056-packages-local-snapshot.patch`). See
[local build instructions](local-build.md) for snapshot replay; do not reapply
patches to a checkout that already contains those commits. New driver recipes
live in the main tree and are registered in the custom updater registry.

Merge the Firefox configuration fragment into the existing desktop profile:

```sh
./scripts/kconfig.pl + .config configs/firefox-esr.config > .config.firefox
mv .config.firefox .config
make defconfig
```

This preserves the other selected firmware options. `CONFIG_BUILD_PATENTED`
allows the required H.264/AAC codecs, and `libffmpeg` selects the full default
variant. The ignored local `.config` and generated firmware stay outside Git.

Build the X.Org client libraries, Cairo and GTK3 before Firefox, then build the
complete firmware. Target staging must contain no host-library paths or ABI
substitutions. Bundled NSS/NSPR stay private under `/usr/lib/firefox-esr/`.

Run `python3 scripts/tests/test-firefox-updater.py` on the build host.
Run `scripts/tests/firefox-smoke.sh` on the target after copying the script.
Fresh-image VM checks cover Wayland, sandbox status, HTTPS, LuCI, Chinese text,
clipboard, file selection/downloads, MP4/WebM playback, profile persistence,
APK reinstall and desktop/RDP regressions. Physical Intel display, USB and
performance require hardware tests.

See [the firmware validation record](firefox-validation.md) for results and artifacts.
