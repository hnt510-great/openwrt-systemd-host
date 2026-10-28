include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-shell-extension-kimpanel
PKG_VERSION:=2026.10.27
PKG_RELEASE:=1
PKG_SOURCE:=gnome-shell-extension-kimpanel-3e818bb754f3.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/wengxt/gnome-shell-extension-kimpanel/tar.gz/3e818bb754f31586bef2a7908c6b5c9a2b099701?
PKG_HASH:=7a5259b8d41a930bde4310e37a45016097f365c625ffc5bb7a7348cf0a88abe4
PKG_BUILD_DIR:=$(BUILD_DIR)/gnome-shell-extension-kimpanel-3e818bb754f31586bef2a7908c6b5c9a2b099701
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=glib2/host extra-cmake-modules
PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/gnome-shell-extension-kimpanel
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=GNOME desktop
  TITLE:=Kimpanel candidate UI for GNOME Shell 51
  DEPENDS:=+gnome-shell +fcitx5
endef

CMAKE_OPTIONS += -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_INSTALL_LOCALEDIR=share/locale \
	-DECM_DIR=$(STAGING_DIR)/usr/share/ECM/cmake

define Build/Install
	$(call Build/Install/Default)
	$(STAGING_DIR_HOSTPKG)/bin/glib-compile-schemas $(PKG_INSTALL_DIR)/usr/share/gnome-shell/extensions/kimpanel@kde.org/schemas
endef

define Package/gnome-shell-extension-kimpanel/install
	$(INSTALL_DIR) $(1)/usr
	$(CP) $(PKG_INSTALL_DIR)/usr/share $(1)/usr/
endef

$(eval $(call BuildPackage,gnome-shell-extension-kimpanel))
