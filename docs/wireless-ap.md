# Wireless access point

The x86_64 router (Beelink EQ, Raptor Lake-P) has an onboard Intel Wi-Fi 6
AX101 CNVi module (`8086:51f1`, subsystem `8086:0244`, RF `HR1 B3`). The
fragment `configs/wireless-ap.config` selects what it needs to run as an
access point bridged into `lan`, plus management tools:

| Package | Purpose |
| --- | --- |
| `iwlwifi-firmware-ax101` | `iwlwifi-so-a0-hr-b0-89.ucode`; without it iwlwifi binds but creates no `phy` |
| `wpad-mbedtls` | hostapd and wpa_supplicant (WPA2/WPA3/SAE), matching the tree's mbedtls ustream |
| `iwinfo` | `iwinfo` CLI: status, association list, scan |
| `hostapd-utils` | `hostapd_cli` |
| `luci-app-wifischedule` | LuCI *Services → Wifi Schedule* (pulls `wifischedule` and its zh-cn translation) |

`kmod-iwlwifi`, `wifi-scripts`, `hostapd-common` and `rpcd-mod-iwinfo` were
already selected. Validation: [wireless-ap-validation.md](wireless-ap-validation.md).

## Build and publish

Merge the fragment into the working configuration:

```sh
./scripts/kconfig.pl + .config configs/wireless-ap.config > .config.new && mv .config.new .config && make defconfig
make package/firmware/linux-firmware/compile package/network/services/hostapd/compile \
	package/network/utils/iwinfo/compile package/feeds/packages/wifischedule/compile \
	package/feeds/luci/luci-app-wifischedule/compile V=s
./scripts/publish-changed-feeds.sh --dry-run
./scripts/publish-changed-feeds.sh
```

None of these packages changes the kernel ABI.

## Router setup

```sh
apk add iwlwifi-firmware-ax101 wpad-mbedtls iwinfo hostapd-utils luci-app-wifischedule
modprobe -r iwlmld iwlmvm iwldvm iwlwifi && modprobe iwlwifi   # or reboot
/etc/init.d/wpad enable && /etc/init.d/wpad start
```

Installing `wpad-mbedtls` does not start it. Until the `wpad` rc script runs,
`ubus call network.wireless status` shows `radio0` as `pending` and no
`hostapd.*` ubus object exists. Under native systemd it runs as
`openwrt-wpad@hostapd.service` and `openwrt-wpad@supplicant.service`.

Once the phy exists, `wifi-scripts` writes a disabled, open `radio0`
(`band 5g`, `channel 36`, `HE80`) into `/etc/config/wireless`. The working
configuration is:

```sh
uci-history --json begin --timeout 300 --note 'enable wireless AP'
uci set wireless.radio0.band=2g
uci set wireless.radio0.channel=6
uci set wireless.radio0.htmode=HE20
uci set wireless.radio0.country=SG
uci set wireless.default_radio0.ssid=...
uci set wireless.default_radio0.encryption=sae-mixed
uci set wireless.default_radio0.key=...
uci set wireless.default_radio0.ieee80211w=1
uci delete wireless.default_radio0.disabled
uci commit wireless && wifi reload
uci-history --json confirm
```

LuCI shows the radio under *Network → Wireless*. That menu entry depends on a
`wifi-device` section existing, and LuCI caches its menu, so delete
`/tmp/luci-indexcache.*` if it does not appear after setup. The AP is not a
separate entry on *Network → Interfaces*: `phy0-ap0` is a port of `br-lan`
and appears in the `lan` device and on the *Devices* tab.

## 5 GHz is not available for AP mode

The AX101 is a self-managed regulatory device (Intel LAR). `iw reg get`
shows `phy#0 (self-managed) country 00` regardless of `radio0.country`, and
every 5 GHz rule carries `PASSIVE-SCAN`; hostapd reports
`Frequency 5180 (primary) not allowed for AP mode, flags: ... NO-IR` and the
AP stays `DISABLED`. The `IR-CONCURRENT` rules only relax `NO-IR` for P2P-GO
and station/TDLS interfaces (`cfg80211_ir_permissive_chan`), not for AP mode.

`-89` is both `IWL_AX210_UCODE_API_MAX` in the 7.3 driver and the newest
`so-a0-hr-b0` image in linux-firmware, so no firmware upgrade changes this.
Patching iwlwifi to strip `NO_IR` is not supported here: the firmware enforces
the same policy. 5 GHz AP mode needs another radio, for example an M.2 MT7922
(`kmod-mt7921e`, `kmod-mt7922-firmware`; the E-key slot must carry PCIe), a USB
MT7921AU (`kmod-mt7921u`) or a USB MT7612U (`kmod-mt76x2u`).

The radio supports one AP (`#{ AP, P2P-client, P2P-GO } <= 1`) alongside at
most one managed interface on the same channel.

## Operation

```sh
wifi down | wifi up | wifi reload
iwinfo phy0-ap0 info
iwinfo phy0-ap0 assoclist
hostapd_cli -i phy0-ap0 status
hostapd_cli -i phy0-ap0 all_sta
ubus call network.wireless status
```

With no associated stations, the AP reports no signal quality and *Status →
Overview* shows the grey `signal-000-000.svg` badge; that is expected.
The overview used to rebuild every section on each poll (default 5 s), which
made that badge blink. `feeds/luci` commit `7aa3995f1e` (mirrored as
`patches/feeds/0034-luci-status-redraw.patch`, baseline
`configs/luci-status-redraw-feeds.json`) replaces only the top-level nodes
whose markup changed, so the radio box stays in place while the station list
is rebuilt. Test: `node scripts/tests/test-luci-status-redraw.js`.

Wifi Schedule is installed disabled (`wifi_schedule.@global[0].enabled='0'`).
Keep its "unload modules" option off on this card: unloading iwlwifi forces a
firmware reload on every resume.

## Recovery

`uci-history` reverts an unconfirmed wireless change automatically after the
timeout. To turn the AP off, set `wireless.default_radio0.disabled=1` and run
`wifi reload`, or run `wifi down`. Removing `wpad-mbedtls` stops all AP and
supplicant operation; the firmware package can stay installed.
