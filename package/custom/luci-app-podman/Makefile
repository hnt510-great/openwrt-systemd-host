include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=4
PKG_LICENSE:=Apache-2.0

LUCI_TITLE:=LuCI rootless Podman management
LUCI_DEPENDS:=+luci-base +rpcd-mod-ucode +ucode-mod-fs +ucode-mod-uci +openwrt-podman-rootless +coreutils-timeout

define Package/luci-app-podman/conffiles
/etc/config/luci_podman
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
