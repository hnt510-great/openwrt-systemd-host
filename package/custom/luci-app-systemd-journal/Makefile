include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=2
PKG_LICENSE:=Apache-2.0

LUCI_TITLE:=LuCI systemd journal viewer
LUCI_DEPENDS:=@OPENWRT_SYSTEMD +luci-mod-status +rpcd-mod-ucode +ucode-mod-fs +systemd +coreutils-timeout
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
