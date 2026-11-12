# Wireless access point validation

Build, publication and router install: 2026-11-12, in this checkout. Evidence
is under `/srv/openwrt-validation/wireless-ap-validation-20261112/` (build and
publication logs, upgrade receipts, APK hashes, and `router-state.txt`, the
router's wireless state with the key masked). No image was built and no
device was flashed. The packages were published to the LAN feed and installed
on the physical router at the user's request. Guide: [wireless-ap.md](wireless-ap.md).

## Detection

| Check | Result |
| --- | --- |
| `lspci -nnk` | `00:14.3 Network controller [0280]: Intel Raptor Lake PCH CNVi WiFi [8086:51f1]`, subsystem `8086:0244` |
| Boot log before change | `Detected Intel(R) Wi-Fi 6 AX101`; `iwlwifi-so-a0-hr-b0-89 is required`; no `/sys/class/ieee80211` entry |
| Installed before change | `kmod-iwlwifi`, `hostapd-common`, `rpcd-mod-iwinfo`, other iwlwifi firmware; no AX101 firmware, no hostapd/wpad |

## Build and publication

| Check | Result |
| --- | --- |
| `make defconfig` after fragment merge | Pass; working config differs only by the five selections, `wifischedule`, the zh-cn translation and unselected `hostapd-utils`/`wpa-cli` symbols |
| Firmware and wpad build, first attempt | Failed: `elf-abi.py` read a partially written staging JSON (`Expecting value: line 1 column 1`) during parallel packaging of `terminfo`; transient |
| Firmware and wpad build, retry | Pass |
| Tool build (`iwinfo`, `hostapd`, `wifischedule`, `luci-app-wifischedule`) | Pass |
| Publication dry runs | Pass; `changed_packages` were exactly the new packages, `same_version_rebuilds` empty, kernel `unchanged` (generation 61) |
| Publications | Pass; snapshots `20261112T075616.795821Z` and `20261112T080527.647775Z`, receipts `1794470199557770824.json` and `1794470748086887893.json` (`passed`) |

| APK | SHA-256 |
| --- | --- |
| `iwlwifi-firmware-ax101-20261019-r1.apk` | `6d1d9c5bb304638c354cd3a74178f71ab488fc931b1ee1f8805c9736d9a5cfd6` |
| `wpad-mbedtls-2026.08.07~831364bf-r6.apk` | `3837c8b10c76b7ba26ecb369eb8e5596efbd15be386f23a9bbbc5bed7b036f88` |
| `hostapd-utils-2026.08.07~831364bf-r6.apk` | `a0b9eff420788124456664e5086e72b58e88cfd051e6693df0bc3d42613dfdb5` |
| `iwinfo-2026.05.26~66bdd1a0-r1.apk` | `68e0fbba6846456550fd8d33a9d5c27397611577303ecd34e1ec0a4faaf0e4e2` |
| `wifischedule-1.1.0-r0.apk` | `b33a3385f33bf3ef899f4c0189b43dfa94152b0a0cfead6b543d1aacb8feb981` |
| `luci-app-wifischedule-26.220.05359~b702d11.apk` | `d1a098e5abce1e3a416ff71bec9a7a9c268d8c9bee1ebe63c61cac5a4743da0a` |
| `luci-i18n-wifischedule-zh-cn-26.310.60063~9a62efc.apk` | `1a34c8fb5f3fa96b8239a3e6c8b0eb73ea67f6d22ab1177697b43995ec7bf474` |

## Physical router

Running kernel `7.3.4-60-openwrt`.

| Check | Result |
| --- | --- |
| `apk add iwlwifi-firmware-ax101 wpad-mbedtls` | Pass |
| iwlwifi reload | `loaded firmware version 89.b20dcd1f.0 so-a0-hr-b0-89.ucode op_mode iwlmvm`; `phy0` created |
| `iw list` | AP and AP/VLAN supported; one AP per radio |
| Generated config | `radio0` 5g/36/HE80, open, disabled |
| AP on 5 GHz channel 36 | Fails: `Frequency 5180 (primary) not allowed for AP mode, flags: 0x70853 NO-IR`; `iw reg get` shows `phy#0 (self-managed) country 00` with `PASSIVE-SCAN` on all 5 GHz rules |
| `radio0` before `wpad` started | `pending`; no hostapd process or ubus object |
| `/etc/init.d/wpad enable && start` | `openwrt-wpad@hostapd.service` and `openwrt-wpad@supplicant.service` active; `S19wpad` enabled |
| AP on 2.4 GHz channel 6 HE20, `sae-mixed`, `ieee80211w=1` | `AP-ENABLED`; `hostapd_cli status` `state=ENABLED`; `iwinfo` Master, channel 6, 22 dBm, `SAE / WPA-PSK / WPA-PSK-SHA256 (CCMP)` |
| Bridge | `br-lan` ports `eth0 phy0-ap0 vnet0` |
| WAN after change | `ping 1.1.1.1` succeeds |
| `uci-history` transaction | Confirmed within the 300 s window |
| LuCI backend | `luci-rpc getWirelessDevices` and `iwinfo devices` report `radio0`/`phy0-ap0` |
| `apk add iwinfo hostapd-utils luci-app-wifischedule` | Pass; `iwinfo`, `hostapd_cli` work; `wifi_schedule` installed disabled |

## Status overview redraw

| Check | Result |
| --- | --- |
| Router data behind the Wireless box | 12 samples of `luci-rpc getWirelessDevices` one second apart were identical (Master, same BSSID, `quality_max 70`, no `quality`); hostapd logged no restarts |
| `node scripts/tests/test-luci-status-redraw.js` | Pass: unchanged nodes kept across polls; radio icon kept while a station list with fresh `data-idref` widgets is rebuilt; registry entries of replaced and discarded nodes released; changed attributes, text, child count and strings replaced; user-mutated output re-rendered; hidden and failed includes untouched |
| Same test against the unpatched view | Fails at "unchanged icon element is kept across polls" |
| Same test against the minified file in the built package | Pass |
| `make package/feeds/luci/luci-mod-status/compile V=s` | Pass, `luci-mod-status-26.316.29868~7aa3995-r2` |
| Publication dry run and publication | Pass; only `luci-mod-status` changed; snapshot `20261112T081905.065019Z`, receipt `1794471562950873046.json`; APK SHA-256 `fcda9537f57bd36c2bd4a54d8b1218f50f6336cd43903c0e2ba36b00167dba6c` |
| Router upgrade | `apk add -u luci-mod-status`: `26.298.44302~5d5a1d9-r2 -> 26.316.29868~7aa3995-r2` |

The test uses a minimal DOM shim, not a browser; the absence of flicker was
not observed in a real browser.

## Scope

Not checked: a wireless client association or throughput test, LuCI pages in
a real browser, Wifi Schedule timing, behavior across a router reboot, and an
image build containing the fragment. The 5 GHz finding applies to this AX101
module and firmware `-89`; no replacement radio was tested.
