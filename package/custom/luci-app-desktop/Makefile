include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=3
PKG_LICENSE:=GPL-2.0-only

LUCI_TITLE:=LuCI control for the OpenWrt desktop session
LUCI_DEPENDS:=@OPENWRT_SYSTEMD +openwrt-desktop-base +luci-base +rpcd-mod-ucode +ucode-mod-fs +coreutils-timeout
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
