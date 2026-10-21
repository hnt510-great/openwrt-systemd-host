include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

LUCI_TITLE:=LuCI restart advice
LUCI_DEPENDS:=@OPENWRT_SYSTEMD +luci-mod-status +openwrt-needrestart +rpcd-mod-ucode +ucode-mod-fs +coreutils-timeout
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
