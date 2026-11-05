# Desktop setup wizard validation

## Skip setup update — 2026-11-05

The pre-apply exit is explicitly labeled **Skip setup**, with English and
Simplified Chinese guidance that setup is optional and can be reopened from
the System menu. It uses the existing persistent deferral RPC.

- Frontend Node assertions pass for skipping each pre-apply page with empty
  fields, invoking only `defer`, returning to the overview, keeping the page
  open on save failure, and disabling skip for read-only users.
- All 19 backend/helper tests pass, including suppression of automatic entry,
  reading deferral from a fresh backend instance, and no setup helper calls.
- All 47 custom package registry tests, `msgfmt --check` and `git diff --check`
  pass. The app release is bumped to 2.
- `make -j1 package/custom/luci-app-desktop-setup/compile V=s` exited 0,
  rebuilding the app and Chinese translation. Build log:
  `/tmp/desktop-setup-skip-build.log` (temporary, not committed).
- No guest or physical-device validation was performed for this update.

## Original enrollment validation

Date: 2026-11-04. Scope: host-side source/behavior tests, cross-built APKs,
strict Kconfig checks and a browser preview with mocked RPC. No complete
firmware image was built, no guest was provisioned, and no physical device
was accessed, flashed or rebooted. No APK feed publication was performed. Source commits and GitHub pushes are
separate from these build and validation checks.

| Check | Result |
| --- | --- |
| Backend and helper tests | 19 passed. Isolated account/shadow fixtures, strict input validation, password stdin transport, lock exclusion, real forked worker, partial failure/recovery, completion/poll race, group refresh reporting and public certificate fingerprint filtering. The shell test exercises the actual desktop-setup script with stubbed system operations. |
| Frontend flow | Node assertions passed: account/feature navigation, validation and password confirmation, explicit restart confirmation, read-only behavior, progress polling, secret clearing, existing keyring inputs and first-visit redirect authorization. |
| RDP regression | 4 tests passed. |
| Real keyring bootstrap regression | 1 test passed using the built target daemon on an isolated host bus and temporary home; this is not a VM enrollment test. |
| Sunshine/GNOME regression | 2 tests passed. |
| Custom package registry/updater | 47 tests passed; the new local recipe is registered. |
| Gettext and syntax | Chinese catalog passes msgfmt --check; shell/JavaScript syntax and git diff --check pass. |
| Strict configuration | Current configuration and the saved full desktop snapshot pass conf --fatalrecursive. Capability gates are selected directly to avoid a transitive audio-support selection cycle. |
| Active configuration preservation | Every original configuration value retained. Exactly luci-app-desktop-setup=y and luci-i18n-desktop-setup-zh-cn=y added through the feature fragment. |
| Package build | Final serial make -j1 package/custom/luci-app-desktop-setup/compile V=s exited 0. App, Chinese translation and openwrt-desktop release 26 APKs produced. |
| Payload | Packaged executable backend matches final source byte-for-byte. Host Python test bytecode is excluded from source, package payload and generated root staging. APK metadata enforces openwrt-desktop>=26. |
| Browser preview | Chinese account, feature and review screens rendered in Chrome and visually inspected. Preview uses the real view code with mock RPC and a minimal stylesheet, not a running LuCI/router session. |
| Existing workloads | Source/tests confirm no user-manager termination, container deletion, account deletion or network/firewall changes. User-manager group lag is reported for explicit maintenance. |

## Local build artifacts

These signed local artifacts are not published. Paths are relative to the main
tree, under bin/systemd/packages/x86_64/base:

| APK | SHA256 |
| --- | --- |
| `luci-app-desktop-setup-1.0.0-r1.apk` | `3a3e52ae39bed9d778b0a46b53cfa4136d8992468d84a24b6fe0db8adf118e8c` |
| `luci-i18n-desktop-setup-zh-cn-0.apk` | `47723d949e858f5605bb5c004dbee2f930dbbe26a159748897b67d782f4bb63a` |
| `openwrt-desktop-26.apk` | `cfeece8f12f703e908a0c5a881595360548daf48f27be6226f65570aac248b6b` |

Evidence is in `/tmp/desktop-setup-build-o9f4jl2w/`, including
`package-build-verified.log`, `kconfig-strict.log`, `snapshot-strict.log`,
`artifacts.json` and `account.png`, `features.png`, `review.png`. Temporary
build/preview evidence is not committed and may not persist.

## Guest acceptance still required

1. Boot a fresh native-systemd image with these packages and an isolated LAN.
   Log into LuCI as an administrator; verify automatic entry from overview.
2. Create an ordinary account and select all features. Check the Unix password,
   GNOME identity, separate RDP credentials/certificate, local and remote input,
   audio, Sunshine Web enrollment and actual Moonlight pairing.
3. Verify subordinate IDs, user linger, LuCI Podman allowlisting and a real
   rootless container; install/run a user Flatpak; verify the authorized GUI and
   virsh connection to qemu:///system and create a controlled guest.
4. Reopen the wizard, preserve the existing Unix/RDP credentials, add selected
   roles, and verify group-cache reporting without stopping existing containers.
5. Exercise a helper failure, re-entry, interrupted worker and locked-account
   recovery. Reboot and check unattended desktop/remote startup and that the
   completed wizard no longer redirects. Test Skip setup separately, including
   rebooting after skipping and reopening it from the permanent System menu.
6. Repeat appropriate GPU/display/input and actual client checks on separately
   authorized physical hardware. VM or browser results do not establish them.

See [design and operation](desktop-setup.md) for permissions, persistence and
failure behavior. The existing date-specific GNOME validation is background
evidence and does not certify this new wizard's complete runtime workflow.
