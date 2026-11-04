# Public source cleanup validation

Audit date: 2026-11-04. Scope: current working tree, including ignored local
feeds and the initialized theme submodule. Git history and author metadata
were excluded from cleanup at the user's request. No firmware build, VM run,
physical device access, feed publication or Git push was performed.

| Check | Result |
| --- | --- |
| Personal account provisioning | Personal provisioning script is absent; generic tracked account helpers have no preset personal user/password. Removed the personal account document and its links. |
| Personal identity | Final main-tree sweep covered 11,760 source files. Also removed one personal author header in a local video feed patch; feed history and commits are unchanged. Removed the personal username/email from current tracked contents, patch author headers and file names; replaced personal home/evidence paths with examples. |
| Private infrastructure | Replaced personal domains, LAN addresses, MAC, observed public/proxy IPs and device/boot UUIDs. Replaced private GitLab submodule URL with a relative sibling URL. |
| Publication defaults | Example domain/address only; router SSH target is empty. Dedicated service user replaces personal user. Client package release incremented to 7. |
| Root overlay | Exactly 11 tracked generic integration files; no additional personal overlay files present in this checkout. |
| Credential filenames and content | Inspected key/certificate, account database, hash, token, password, URL-authentication and backup patterns. No personal signing keys or credential files found in the current checkout. |
| Secret scanner | Gitleaks v8.30.1, downloaded outside the repository and checked against its published SHA-256 checksums; directory scan included local feeds and submodule. 41 findings reviewed, no identified personal credentials. |
| Ignore protections | Added local environment/SSH/key, agent state, Python cache, backup and archive exclusions. Already tracked generic source remains tracked. |
| Feed client | 9 tests passed. |
| Scheduled maintenance | 17 tests passed; no schedule installed or enabled. |
| LuCI daed | Node assertions passed. |
| LAN publisher | 6 tests passed; integration class skipped because built APK tools/kernel package are absent. |
| Build and publish | All 63 tests skipped because built APK host tool is absent. |
| nginx | 1 test skipped because nginx is absent. |
| Whitespace | `git diff --check` passed. |
| Public recursive clone | Not verified; customized theme repository must be published with the recorded commit. |

## Scanner triage

Nine private-key matches are non-personal source fixtures: seven explicitly
identified public development keys in
`package/boot/arm-trusted-firmware-microchipsw/src/keys/` and two old/new TLS test
keys in the local feed's nginx Lua test patch. These were preserved because
removing them would alter unrelated upstream development/test support. Never
use these development keys as private production signing identities.

The other 32 matches are package version mappings, empty service/key settings,
key-related source identifiers, upstream SRP protocol examples, hostapd test
vectors, shell expressions and bundled JavaScript. Reviewed findings contain
no identified personal access token, private signing identity or account hash.
The upstream EAD password/hash fixture is also non-personal example material.

The scanner and its redacted report were kept in a private temporary directory
outside the repository. No broad scanner allowlist was added. Automated scans
and manual inspection reduce exposure risk but cannot prove the absence of all
possible secrets, especially in history, which was outside this audit's scope.
