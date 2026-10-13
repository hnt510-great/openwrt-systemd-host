include $(TOPDIR)/rules.mk

PKG_NAME:=xkbcomp
PKG_VERSION:=1.5.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/app/
PKG_HASH:=2ac31f26600776db6d9cd79b3fcd272263faebac7eb85fb2f33c7141b8486060
PKG_BUILD_DEPENDS:=xorgproto
PKG_BUILD_PARALLEL:=1
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/xkbcomp
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=X.Org keyboard map compiler
  URL:=https://www.x.org/
  DEPENDS:=+libX11 +libxkbfile +xkeyboard-config
endef

MESON_ARGS += --wrap-mode=nofallback -Dxkb-config-root=/usr/share/X11/xkb

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib/pkgconfig
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/xkbcomp.pc $(1)/usr/lib/pkgconfig/
endef

define Package/xkbcomp/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/xkbcomp $(1)/usr/bin/
endef

$(eval $(call BuildPackage,xkbcomp))
