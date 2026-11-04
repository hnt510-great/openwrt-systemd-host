include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=Apache-2.0

LUCI_TITLE:=LuCI first-run desktop setup wizard
# Select capability gates directly: transitive multimedia constraints otherwise
# make this selector depend on a capability that its selected packages enable.
LUCI_DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +audio-support +input-support +video-support +accel-support \
	+luci-mod-status +python3 +shadow-chpasswd +openwrt-desktop +sunshine \
	+openwrt-podman-rootless +openwrt-flatpak +virt-manager +luci-app-podman +luci-app-qemu
LUCI_PKGARCH:=all
LUCI_EXTRA_DEPENDS:=openwrt-desktop (>=26)

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
