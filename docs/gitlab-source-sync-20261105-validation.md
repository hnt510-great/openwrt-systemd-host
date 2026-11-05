# GitLab source synchronization validation (2026-11-05)

Reconciled GitLab `main` snapshot `672b596a340edc36c87abb9bd3a0c092275fff6d`
with the public source tree. The previous GitLab baseline was `6c6e073b25`,
corresponding to public source commit `bddb9be2ae`. Histories differ because of
public-source anonymization; the incoming delta was applied to that public
baseline before merging. Raw private GitLab history is not a merge parent.

The four incoming commits add default-enabled systemd service-bridge controls
and procd instance-job guards, APK same-version rebuild diagnostics, daed
release 5, and supervision documentation. Existing GitHub feed URLs, relative
submodule URL, public example defaults and desktop enrollment changes remain.
Personal evidence paths in incoming documentation use `/srv/openwrt-validation`.

| Check | Result |
| --- | --- |
| APK rebuild diagnostics | 14 tests passed, including real APK fixtures |
| procd units packaging | 9 tests passed |
| Service bridge | 25 tests run, 24 passed and 1 skipped |
| LAN publisher | 6 host tests passed; package integration class skipped because no built native-systemd kernel APK is available |
| Custom package registry | 47 tests passed |
| systemd 262 patch application | Patches 001 and 002 apply to the original source archive with zero fuzz and zero offsets |
| Guest shell script syntax | Passed for procd units and native systemd smoke scripts |
| APK source-version policy | Two existing errors reproduced before and after the merge: reserved future releases nginx-ssl-util 1.7-r8 and native-libs-dev 1-r7 |
| Personal identifier scan | Scanned 11,921 tracked paths; no personal username/domain/LAN matches or token-prefix findings. Home-path matches are unchanged upstream diagnostics, generic examples or test fixtures. Incoming documents retain only the existing example MAC 02:00:00:00:00:01. |
| Gitleaks 8.30.1 | 27 findings, all in unchanged files; none in incoming files. Existing public development keys, protocol/test fixtures, empty settings and source/version identifiers are retained. |
| Public settings | Example domain and documentation addresses retained; router SSH target remains empty |
| Theme submodule | Existing public gitlink retained. GitLab still references unavailable commit f05f1462df; this synchronization does not change it. |
| Whitespace | `git diff --check` passed |

Scope: local source integration and host checks. The checked-in profile enables
the service bridge as requested upstream; the working `.config`, feed repositories
and local overlays are preserved. No full package/firmware build, new VM run,
physical-device validation, package publication or GitHub push was performed.
Incoming upstream VM/build records are historical evidence and were not rerun by
this synchronization. Existing Git author attribution and preexisting history
were not rewritten.

CLI credentials are stored outside the repository in the operating system
keyring. Private scan reports and patch logs are retained outside the checkout.
