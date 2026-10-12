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

The browser defaults to software WebRender and software video decoding.
H.264/AAC support uses the target FFmpeg libraries; WebM uses Firefox's
bundled decoders. Noto Sans CJK provides Simplified Chinese glyphs. X11 client
libraries and GTK's X11 backend satisfy the official binary's link requirements;
the browser uses Wayland and needs no Xorg or Xwayland server.

This integration covers browsing, downloads and basic video pictures.
Audio services/output, protected streaming, screen sharing and GPU acceleration
are outside its validated scope. Weston VNC mirrors the desktop and its input;
it does not transport browser audio.

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
