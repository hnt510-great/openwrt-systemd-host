# Firefox ESR on the Weston desktop

The x86_64/glibc image includes Mozilla's official Simplified Chinese Firefox
ESR build as `firefox-esr-bin`. It runs directly on Wayland as an ordinary user.
After creating a user, setting a password and running `desktop-setup USER`,
click the Firefox icon in Weston's top panel. The browser does not start
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
video decoding is validated separately from audio and remote-display transport. Weston VNC mirrors the desktop and its input;
it does not transport browser audio.

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

On the build host:

```sh
package/custom/scripts/update-firefox-esr.sh --check
package/custom/scripts/update-firefox-esr.sh --update
make defconfig
make package/custom/firefox-esr-bin/compile V=s
make -j2 V=s
```

The check is the default action; exit status 1 means an update is available.
The update action verifies the official archive's SHA256, atomically changes
version/hash metadata and resets the package release. It stays on the packaged
ESR major branch. When that branch is no longer advertised, review a supported
major version manually. Repeat ELF dependency and fresh-image VM validation
before distributing updated packages.

Close Firefox before backing up its profile. As the desktop user:

```sh
tar -czf "$HOME/firefox-profile-backup.tar.gz" -C "$HOME" .config/mozilla/firefox
```

For a legacy or custom profile, substitute the root directory shown by
`about:profiles`. Store a copy outside the router. The existing upgrade rules preserve
`/home/` when configuration is retained, including profiles and downloads;
check the resulting backup size before upgrading. An upgrade without retained
configuration removes this state. Keep a matching profile backup if rolling
back to an older Firefox version; profiles updated by newer versions are not
guaranteed to work after a downgrade.

This image's sysupgrade backup also records the ownership and permissions of
selected files' parent directories under `/home/`, using GNU tar without
recursive expansion of the file selection. When upgrading from an older image,
apply the updated sysupgrade script on the running system before creating the
backup/starting the upgrade, or separately preserve and restore directory
metadata. Installing a new image cannot retroactively add directory metadata
to an archive created by the older upgrader.

## Build and runtime checks

`configs/firefox-esr-feeds.json` records the video feed base and local commit.
The incremental patch is `patches/feeds/0003-video-firefox-esr.patch`. Apply it
only to a clean video feed at the recorded base that does not already contain
this change. Keep the earlier feed integrations described in
[local build instructions](local-build.md). The current checkout already
contains the Firefox feed commit; do not apply it again.

On the matching feed base, from the OpenWrt root directory:

```sh
git -C feeds/video am "$PWD/patches/feeds/0003-video-firefox-esr.patch"
./scripts/feeds install -a
```

VA-API also requires the packages-feed patch and base recorded in
`configs/firefox-vaapi-feeds.json`. Apply that patch with `git apply` only to
the matching clean base; do not reapply it to this checkout. New driver recipes
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
APK reinstall, retained-configuration recovery upgrades and desktop/VNC
regressions. Physical Intel display, USB and performance require hardware tests.

See [the firmware validation record](firefox-validation.md) for results and artifacts.
