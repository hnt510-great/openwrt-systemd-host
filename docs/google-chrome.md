# Google Chrome on the GNOME desktop

The x86_64/glibc desktop profile can include Google's official Chrome stable
build as `google-chrome-bin`. The recipe repackages Google's signed Debian
archive (`google-chrome-stable_VERSION-1_amd64.deb`) without rebuilding or
stripping it. Chrome's private runtime (SwiftShader, its bundled Vulkan loader,
Widevine CDM) stays under `/opt/google/chrome/`.

## Installing and starting

The package is selected by the fragment `configs/google-chrome.config`:

```sh
./scripts/kconfig.pl + .config configs/google-chrome.config > .config.new
mv .config.new .config
make defconfig
make package/custom/google-chrome-bin/compile V=s
```

On a running router that already uses the LAN feed:

```sh
sudo apk add google-chrome-bin
```

After `desktop-setup USER`, start Google Chrome from the GNOME application grid,
or from a terminal as the desktop user:

```sh
google-chrome
google-chrome https://example.com/
```

`google-chrome-stable` is the same launcher, and root launches are rejected.
Each user has a private profile under `~/.config/google-chrome/`. The package
does not create users or change the default browser. GNOME Settings lists
Chrome as a candidate default browser through the upstream
`default-apps/google-chrome.xml` entry.

## What differs from Google's Debian package

| Upstream item | In this package |
| --- | --- |
| `/opt/google/chrome/*` | Installed byte-for-byte |
| `chrome-sandbox` (setuid helper) | Omitted: Chrome uses its user-namespace sandbox, which this kernel provides (the same feature rootless Podman uses) |
| `libqt5_shim.so`, `libqt6_shim.so` | Omitted: the image selects no Qt packages; Chrome uses its GTK UI |
| `/etc/cron.daily/google-chrome`, `opt/google/chrome/cron` | Omitted: it would add Google's apt repository, which this system does not use |
| `apparmor.d` | Omitted: no AppArmor |
| Desktop entries, AppStream data, GNOME default-app entry, icons | Installed (`/usr/share/metainfo/` instead of `appdata/`) |
| `/usr/bin/google-chrome-stable` | A shell launcher that rejects root, then runs Google's wrapper |

Debian's `Depends:` list is translated into OpenWrt packages. `scripts/elf-abi.py`
derives the exact `so:` dependencies from the binaries; the extra `DEPENDS`
cover libraries Chrome loads with `dlopen` (GTK3, Mesa EGL/GBM, PulseAudio,
libva and the Intel iHD driver) and the fonts.

If user namespaces are disabled, Chrome refuses to start with "No usable
sandbox". Re-enable them instead of passing `--no-sandbox`.

## Display, GPU and video

Chrome selects Wayland automatically in the GNOME session (`chrome://gpu` shows
`Ozone platform: wayland`). Rendering uses Mesa's EGL through `libmesa`;
SwiftShader is Chrome's software fallback. VA-API video decoding is not on by
default in Chrome for Linux; the libraries are present for users who opt in
from `chrome://flags`. Firefox ESR remains the validated browser for
hardware video decoding (see [Firefox](firefox.md)).

## Updates

Chrome for Linux does not update itself. Upstream versions are tracked by the
custom package updater with the `chrome` provider, which reads Google's apt
index (`dl.google.com/linux/chrome/deb/dists/stable/main/binary-amd64/Packages`)
and takes the SHA-256 recorded there for the `google-chrome-stable` entry.
The registry entry uses policy `stable`, so it follows every new stable major:

```sh
python3 scripts/update-custom-packages.py --check --package google-chrome-bin
python3 scripts/update-custom-packages.py --update --package google-chrome-bin
make package/custom/google-chrome-bin/compile V=s
```

`./scripts/feeds update -a` runs the same update for every registered recipe.
The update downloads the archive, verifies the `!<arch>` signature and the
index SHA-256, sets the new version and hash, and resets `PKG_RELEASE` to 1.
A Debian revision other than `-1`, or a pool path that does not match the
version, stops the update for manual review. Google removes superseded
archives from its pool soon after a release. Build a version while its archive
is still listed, or keep the cached copy in `dl/`.

Publish through the normal gated path (`scripts/build-and-publish.sh` or
`scripts/publish-changed-feeds.sh`); the router then receives the new
version with `apk upgrade`.

## Licensing

Google Chrome is proprietary software under the Google Chrome Terms of
Service; third-party notices are at `chrome://credits`. This package is meant
for the private LAN feed and images of this fork; do not mirror it to a public
repository.

See the [validation record](google-chrome-validation.md).
