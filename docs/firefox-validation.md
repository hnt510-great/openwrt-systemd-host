# Firefox ESR firmware validation

Validated on 2026-10-12 (Asia/Singapore) with an isolated 4 GiB QEMU/KVM VM.
No physical router was flashed.

## Delivered artifacts

- Firmware: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
- SHA256: `40e7b5d928944f7c4b7f1493511465362380abb1aaa094e3a7dfaa521d314f60`
- Compressed size: 492,869,716 bytes (470.0 MiB), an increase of 120.5 MiB
  over the initial image. The root partition remains 8 GiB.
- Browser APK: `bin/systemd/packages/x86_64/base/firefox-esr-bin-153.4.0-r1.apk`.
  Its upstream archive is Mozilla's official `153.4.0esr`, x86_64, zh-CN build.

APK signatures were verified with the public key embedded in the firmware.
The image checksum list and extracted final rootfs audit passed. Thirty
upstream browser ELF files remained byte-for-byte unchanged; the audit checked
87 ELF files including dependencies, finding no missing libraries or symbols.
Bundled NSS/NSPR remain in the browser's private application directory.
The existing enabled configuration and unrelated tracked changes were retained.

## Runtime results

| Check | Result |
| --- | --- |
| Narrow X.Org, Cairo, libepoxy, GTK3 and Firefox package builds | Passed |
| Complete native-systemd firmware build | Passed |
| Update-script default check and seven offline failure/upgrade cases | Passed |
| Ordinary-user panel launch and command-line launch | Passed; root launcher rejected |
| Native display protocol | Wayland |
| Rendering | WebRender (Software); hardware video decoding disabled |
| Content sandbox | Effective level 6; seccomp and user namespaces available |
| Content, socket and media process seccomp filters | Enabled |
| Browser application-update policy | DisableAppUpdate active |
| HTTPS without certificate override and local LuCI page | Passed |
| Chinese browser UI, web text and Noto CJK glyphs | Passed |
| Browser's complete upstream license document | Available through about:license |
| Native GTK file chooser, upload selection and download contents | Passed |
| 720p H.264, H.264 with AAC track, VP9 WebM | Video frames advanced for all three |
| Video pause, seek and native-input fullscreen | Passed |
| Terminal and virt-manager on the updated GTK3 stack | Passed; qemu:///system connected |
| Desktop restart and native reboot autostart | Passed |
| Profile settings and bookmark after native reboot | Retained |
| Signed APK release upgrade in the VM | Passed; settings/profile retained |
| Actual GRUB procd-recovery boot and Firefox panel launch | Passed |
| Actual retained-configuration firmware flash from procd | Returned to systemd |
| Home/profile directory owners and permissions | Preserved by the updated sysupgrade backup |
| Final image launcher and introspection metadata | 32-pixel icon and xlib-2.0 typelib present |
| Browser autostart | Disabled; browser opens only when requested |

The APK upgrade used a test-only signed `153.4.0-r2` metadata revision with
the same upstream executable payload, then the actual firmware upgrade
returned to the delivered `r1` package. This checks the APK release-upgrade
and data-preservation path; future upstream versions still require their own
dependency and runtime validation.

## Integration findings and limits

Enabling GTK3's X11 backend also required Cairo Xlib support, libepoxy GLX
interfaces and the `xlib-2.0` introspection metadata used by Python GTK clients.
The latter was added to the base gobject-introspection package after a
virt-manager regression exposed it.

A retained upgrade exposed the old file-only backup behavior: Firefox's files
survived, but its directories were recreated as root-owned and the ordinary user
could not write the bookmark database. Sysupgrade now includes parent directory
metadata for selected home files when GNU tar supports `--no-recursion`; the
desktop explicitly depends on GNU tar. Host tests ensure that unselected files
are not included. The repaired path was validated with an actual upgrade after
applying the updated upgrader to the running VM, including UID/GID and 0700/0710
directory mode checks. See the older-image migration note in [usage](firefox.md).

The packaged ESR uses `~/.config/mozilla/firefox/` for fresh Linux profiles.
Legacy/custom locations remain under Firefox's control. The existing `/home/`
upgrade retention preserves both locations; see [profile backups](firefox.md).

Audio services/output, protected streaming, screen sharing, GPU acceleration
and physical Intel display/USB/performance were outside this validation.
Video samples were muted. Temporary accounts, credentials and automation
flags existed only in the disposable VM, never in the delivered firmware.

Evidence and reproducible VM scripts are under
`/srv/openwrt-validation/firefox-validation-20261012/`, including
`final-image.json`, `final-rootfs-audit.json`, `browser-tests.json`,
`browser-support.json`, `desktop-regression.json`,
`apk-upgrade-result.json` and `retained-upgrade-persistence.json`.

[Usage and updates](firefox.md).


## VA-API addition, 2026-10-23

Implemented for the physical Intel Celeron N5105 / Jasper Lake host at
`192.0.2.1`, retaining its existing i915 driver and ordinary-user render-node
permissions. Firefox remains Mozilla's official `153.5.1esr` zh-CN payload;
all 30 upstream ELF files are unchanged.

### Source and build

Delivered packages are `firefox-esr-bin-153.5.1-r2`, `libffmpeg-9.0.1-r3`,
`ffmpeg-9.0.1-r3`, `libva-2.24.1-r1`, `libigdgmm-22.10.2-r1`,
`intel-media-driver-26.3.5-r1` and `libva-utils-2.24.0-r1`.
GmmLib uses a separate CMake build directory and a patch making pkg-config
include/library paths relative to its prefix, so media-driver uses target
staging headers. The iHD driver uses the upstream full-feature build; shader
and third-party license notices are packaged alongside it. Unit tests and CMRT
are disabled in that target package.

FFmpeg's restored `FFMPEG_VAAPI` option selects libva and DRM support; the mini
variant stays without VA-API. Firefox selects that option and the iHD runtime.
The packaged defaults enable hardware video decoding and allow upstream
WebRender/EGL detection. No blacklist bypass, forced hardware decoder,
Vulkan decoder, disabled RDD sandbox, or global driver-name environment override
was added. ESR 153 has no `media.ffmpeg.vaapi.enabled` preference.

| Source/build check | Result |
| --- | --- |
| Custom updater, package-metadata Kconfig and Firefox updater suites | 39 + 4 + 7 tests passed |
| Complete generated Kconfig with `conf --fatalrecursive` | Passed |
| FFmpeg recipe option matrix | Five combinations passed, including mini and manual selection |
| Actual target configure matrix | VA-API enabled/disabled and manual selection without patented H.264 passed |
| Original `.config` selections | All existing `y`/`m` selections retained; five feature selections added |
| Custom recipe registry / generated feed links | All 92 recipes registered; zero broken links |
| Signed APK verification | All seven accepted packages passed locally, in the VM and on hardware |
| Target rootfs ELF audit | 30 browser ELFs / 100 total dependency ELFs; no missing libraries or symbols |
| Full `make -j3 V=s` firmware build and target checksum list | Passed |

The existing independent system NSS/NSPR packages coexist with Firefox's
private copies. The audit now covers dynamically loaded FFmpeg/libva/iHD and
allows independently packaged system NSS/NSPR while rejecting escaped copies
of the browser's private libraries.

Firmware: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256: `a4244a901acb50f5d669f5e42e341bf8f7f7442cb11a5f49400a47613bb347ed`; compressed size: 621,365,529 bytes.
The full build retained the exact SHA256 of all seven APKs accepted for
installation. Packages-feed provenance and its reproducible patch are in
`configs/firefox-vaapi-feeds.json`. LAN publication is recorded below; no Git
commit was made.

### Isolated VM results

An isolated 3 GiB KVM VM first installed the seven signed APKs on the existing
image after exact offline simulation. A second VM booted the freshly built
firmware without an APK overlay. Both used an ordinary desktop user, Wayland
and VirtIO/VirGL rendering, without a hardware VA-API decoder.

Both passed H.264 720p30, VP9 720p30 and AV1 360p24 software playback, advancing
video frames, pause, seek, resume and H.264 fullscreen. Captured video screenshots
were inspected. The codec table remained software-only, proving graceful
fallback rather than hardware decoding in these guests. Content sandbox level
remained 6; RDD and content process snapshots showed seccomp mode 2,
`NoNewPrivs=1` and zero effective capabilities. Both disposable VMs were powered
off and their PIDs verified absent.

### Physical N5105 results

The initial baseline used software decoding for all three samples. The exact
offline transaction added four packages and upgraded Firefox, libffmpeg and the
FFmpeg CLI. No packages were removed. The original three upgraded APKs were
signature-verified and retained under `/root/firefox-vaapi-20261023/rollback/`.
No firmware was flashed and no system or desktop restart was performed.

| Hardware check | Result |
| --- | --- |
| Ordinary-user DRM access and `vainfo` | iHD loaded, VA-API 1.24; H.264 and VP9 VLD profiles present |
| Firefox compositor / protocol | WebRender / Wayland |
| H.264 playback | OS FFmpeg: VA-API initialization succeeded, `IsHardwareAccelerated=true`, VAAPI pixel format |
| VP9 playback | Bundled FFVPX: VA-API initialization succeeded, `IsHardwareAccelerated=true`, VAAPI pixel format |
| AV1 playback | Software decoding; N5105 exposes no AV1 hardware decode profile |
| Pause, seek, resume / H.264 fullscreen | Passed; screenshots visually inspected |
| GPU activity during playback | Video engine peak 21.48%; Firefox RDD PID 8631 Video peak 18.95% |
| Sandbox | Content level 6; RDD seccomp 2, `NoNewPrivs=1`, zero effective capabilities |
| Protected runtime state | Boot ID, running kernel, network/container-helper PIDs, config/key hashes unchanged |
| Normal Firefox data | 462 files unchanged, including settings, history and bookmarks |
| Failed system units / temporary browser and monitoring processes | None at final inspection |

The first temporary-profile probes updated Firefox's shared
`Crash Reports/crash_helper_server.log`; no normal profile data or settings
changed. The guest test now also isolates XDG config/cache/data/state directories.
A final physical rerun with that isolation again passed actual H.264/VP9 VA-API
and software AV1, with no further changes to the ordinary user's Firefox tree.
Temporary browser profiles and the router's test directory were removed;
rollback packages remain available.

These are short functional checks, not a throughput/CPU benchmark. HEVC profile
availability in `vainfo` is not HEVC playback validation. Protected streaming,
audio, and end-to-end remote-client playback were not tested here.

Evidence: `/srv/openwrt-validation/firefox-vaapi-20261023-9ovdzlqx/`, including
`package-sha256.json`, `image.json`, `final-rootfs-audit.json`, `vm-result/`,
`final-vm-result/`, `physical-verified/`, `physical-isolated/`, `gpu-summary.json`,
`physical-preservation.json`, `preservation.json`, build logs and VM commands.
`physical-verified/` includes the matching decoder log, browser RDD PID and GPU
client samples. GPU JSON contains concatenated objects from intel_gpu_top;
`gpu-summary.json` records their parsed counts and peaks. Its 35-second monitor
was ended with SIGINT by timeout (expected exit 124).

The reproducible browser probe is `scripts/tests/firefox-vaapi-guest.py`:

```sh
# Run as the desktop user with that session's XDG_RUNTIME_DIR and WAYLAND_DISPLAY.
# SAMPLES must contain h264.mp4, vp9.webm and av1.webm; OUTPUT must not exist.
python3 firefox-vaapi-guest.py SAMPLES OUTPUT
```

It enables Marionette and privileged diagnostics only in a disposable profile,
records frame/control checks, screenshots, about:support and process sandbox
state, then closes its own browser process group. The caller must inspect the
FFmpegVideo logs and GPU client activity to establish hardware decoding.


### LAN publication and custom feed, 2026-10-23

Published only the seven accepted APKs using an isolated source projection,
after the incremental publisher dry-run passed. Snapshot:
`20261022T180426.332161Z` for kernel ABI
`6.18.55~628a4581533e057afecd1eb41702012b-r1`.

`base` and the projected `custom` feed both contain
`firefox-esr-bin-153.5.1-r2`, `intel-media-driver-26.3.5-r1`,
`libigdgmm-22.10.2-r1` and `libva-utils-2.24.0-r1`. The `packages` feed contains
`libffmpeg-9.0.1-r3` and `ffmpeg-9.0.1-r3`; `video` contains
`libva-2.24.1-r1`. These custom recipes are already registered in the custom
source updater and its generated index.

The four changed signed indexes and all eleven APK URLs (including custom
projections) passed HTTP SHA256 checks. All pre-existing published APK hashes
were retained, with no same-version replacements. Kernel-channel files and
ABI kernel-package records remained unchanged.

The physical router ran `apk update` successfully. A custom-only repository
query and download selected the exact four new custom APKs; their signatures
and hashes matched the accepted artifacts. Installed package inventory,
`/etc/apk/world` and boot ID stayed unchanged during publication verification.
The temporary download directory was removed. Publication evidence is under
`publication/` in the validation artifact directory, including `dry-run.json`,
`result.json`, before/after manifests, `http-verification.json`,
`router-update.log` and `router-custom-fetch.log`.
