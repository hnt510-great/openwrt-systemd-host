# GitLab source synchronization validation (2026-11-07)

Integrated GitLab main updates after `b7cb955d13446ec68d30d789066140b1500e1239`
through `f9300b50750e82f0719df0d5297853e7fc3feca0` onto the public tree.
The 66 non-merge source commits have individual provenance records. Original
author names, email addresses, dates and co-author trailers were preserved and
checked against GitLab. Private GitLab history is not a merge parent.

Changes include the hybrid USB/optical installer, router connection auditing,
Linux 7.3.3, DMA-BUF/video integration, fastfetch 2.71.0, platform fixes and
upstream validation records. BusyBox r12 and procd r7 retain GitLab's merge
resolutions. Public desktop enrollment, feed URLs and the SQLite URI fix remain.
The theme update has a provenance-only commit: GitLab's referenced submodule
object is unavailable, so the existing public theme gitlink is preserved.
Previously removed repository agent instruction files are not restored.

Personal home/evidence paths, account references, SSH key filenames, LAN
addresses and host-specific ACL identifiers use public examples. Matching
synthetic connection fixtures use documentation addresses. Attribution in
commits and patch headers remains intact. No collected audit databases, private
overlays, credentials, keys, build outputs or scanner reports were added.

Host Python 3.15 removed `SourceFileLoader.load_module()`. The installer bootstrap
builder and optical host test now use `spec_from_loader()` and `exec_module()`;
this fixes the observed import failure without changing target package code.

| Check | Result |
| --- | --- |
| Installer planning/serialization | 9 tests: 7 passed, 2 skipped (host GPT/terminal prerequisites) |
| Optical media source safety | 2 tests: 1 passed, frozen target-tool execution skipped (prepared target root required) |
| Router connection collector | 8 passed |
| Router audit regression suite | 29 passed; expected timeout fixture BrokenPipe diagnostic |
| Desktop GPU coldplug | 4 passed |
| Custom package registry | 47 passed |
| procd units packaging | 9 passed |
| Kernel APK integration | All 25 skipped: isolated patched APK not provided; no integration validation claimed |
| Net source delta | Matches sanitized upstream delta with public differences retained; only additional code changes are the Python import fix |
| Author attribution | All 66 source records match original names, emails, dates and co-author trailers |
| Personal marker scan | Every incoming commit's added lines checked; identified private paths, account/key identifiers and LAN subnet absent |
| Gitleaks 8.30.1 | Download checksum verified; incoming commit range scanned, zero findings |
| Whitespace | `git diff --check` passed |

The isolated worktree reused the existing host staging tools and a reference to
the existing theme recipe for registry tests. The working `.config`, README
edit, independent feeds, theme checkout and local overlays were preserved.

Scope: local source integration and host tests only. No package/full firmware
build, VM run, physical-device validation, feed publication, deployment or GitHub
push was performed. Incoming build, VM, router and publication records describe
historical upstream work; those checks and actions were not repeated here.
