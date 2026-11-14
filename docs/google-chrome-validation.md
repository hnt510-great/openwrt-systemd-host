# Google Chrome package validation

Built and published on 2026-11-13 (Asia/Singapore). The image was not booted
in a VM and no physical router was flashed. The publication preflight
simulated the router's upgrade, which this release only changes for
`base-files`. After publication, Chrome was installed on the router from the
LAN feed with APK (see the router section).

## Delivered artifacts

- Upstream archive: `google-chrome-stable_157.0.8103.78-1_amd64.deb`, SHA256
  `4d740636b5c96f687798602c5aad6a5a270f44dd02e48db0638ae77aa4867b1b`, which
  matches Google's apt `Packages` index.
- APK: `bin/systemd/packages/x86_64/base/google-chrome-bin-157.0.8103.78-r1.apk`
  (207,533,726 bytes). Its SHA256 in the published snapshot is
  `3bf01e6fa651f662da49ad1701e8ba1f56fa5454206886bb79d178651c10b2d9`.
- Firmware: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  (938,563,377 bytes), SHA256
  `9def261690b60f8401b00ab00bf39ae40d4ff1f991011cfc46eb8f342741e59a`.
- Userspace snapshot: `/srv/openwrt-feeds/public/snapshots/20261113T023446.369526Z`.
  The kernel generation was reused unchanged (`linux-image-7.3.4-62-openwrt`).

## Results

| Check | Result |
| --- | --- |
| `update-custom-packages.py --check --package google-chrome-bin` against the live index | `current`, digest matches |
| `scripts/tests/test-custom-package-updates.py` (49 tests, including two new Chrome provider tests) | Passed |
| `scripts/tests/test-firefox-updater.py` | Passed |
| `make package/custom/google-chrome-bin/{clean,compile}` | Passed |
| `elf-abi.py` dependency resolution | 32 `so:` dependencies, all resolved; no loader-path policy needed |
| `/opt/google/chrome/chrome` compared with the upstream archive | Byte-identical (not stripped) |
| `chrome --version` run through the target `ld-linux` and target libraries | `Google Chrome 157.0.8103.78`; one benign warning: target `libasound.so.2` has no symbol versions |
| Full `build-and-publish.sh -j16` firmware build | Passed |
| Publication ELF transition scan | 1,369 packages and 2,405 ELF files accepted |
| Router upgrade preflight and publication | Passed; status `published` |
| `git diff --check` | Passed |

## Router installation

On 2026-11-13, after the publication above, Chrome was installed on the router
(`router-admin@192.0.2.1`), which has 48 GiB free on its overlay.

| Check | Result |
| --- | --- |
| `apk add --simulate google-chrome-bin` | Installs only `google-chrome-bin`; no other packages change |
| `apk add google-chrome-bin` | Passed; post-commit uci-history and needrestart hooks ran |
| `/opt/google/chrome/chrome --version` | `Google Chrome 157.0.8103.78` |
| `user.max_user_namespaces` | 63026 (namespace sandbox available) |
| `google-chrome --headless=new --dump-dom https://example.com/` as the ordinary user, sandbox enabled | Page loaded over HTTPS; `<title>Example Domain</title>` returned |
| stderr | Only the benign `libasound.so.2: no version information available` warning |

## Not covered

Not checked: an interactive Wayland window in the GNOME session, GPU/EGL
selection, audio, video decoding and remote-desktop interaction.

## Evidence

Build and publication log: `tmp/chrome-build-and-publish.log` (git-ignored).
Upgrade receipt: `/srv/openwrt-feeds/upgrade-receipts/1794537305071379264.json`.
