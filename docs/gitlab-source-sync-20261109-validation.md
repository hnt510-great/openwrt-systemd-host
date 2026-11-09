# GitLab source synchronization validation (2026-11-09)

Integrated GitLab main updates after `f9300b50750e82f0719df0d5297853e7fc3feca0`
through `b3731fd86a19df66b7c341c4cdc8eafa7f3e0b74` onto the public tree.
The 25 non-merge source commits have individual provenance records. Original
author names, email addresses, dates and co-author trailers were preserved and
checked against GitLab. Private GitLab history is not a merge parent.

Changes include Realtek DSA and L3 offload improvements, Ath79 driver/clock rework,
Airoha EN7581 thermal sensing, ccache 4.14.2, daed v2.1.1-r8 upstream core backports,
scheduled maintenance artifact preservation and publication retry support, the
staged router resource policy plan, Gemini architecture guidance refresh, ICU 79
rebuild allocations in the ELF ledger, automated rebuild release allocation
(`allocate-rebuild-releases.py`), and kernel generation isolation from host tool
upgrades. Previously removed repository agent instruction files remain untracked.

Personal home/evidence paths, private LAN addresses, user account references,
and internal storage directories use public/documentation examples
(`192.0.2.x`, `/srv/openwrt-validation`, `/srv/openwrt-automation`). Commit author
attribution and patch Signed-off-by / Co-Authored-By trailers are preserved.
No private keys, credentials, or host-specific overlays were added.

| Check | Result |
| --- | --- |
| Allocate rebuild releases | 9 tests passed |
| Build and publish suite | 68 tests passed, including host program upgrade generation isolation |
| Custom package registry | 47 tests passed |
| Scheduled maintenance suite | 24 tests passed; scheduler disabled in configuration |
| LuCI daed view | Node assertions passed |
| Author attribution | All 25 replayed commits match original author names, emails, dates and trailers |
| Personal marker scan | Added/modified lines across all 25 commits checked; zero private markers found |
| Whitespace | `git diff --check` passed |

Scope: local source integration and host checks only. No package or full firmware
build, VM run, physical-device validation, feed publication, deployment or
GitHub push was performed. Incoming build, VM, and router records describe
historical upstream work; those checks and actions were not repeated here.
