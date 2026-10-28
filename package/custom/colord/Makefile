include $(TOPDIR)/rules.mk

PKG_NAME:=colord
PKG_VERSION:=1.4.8
PKG_RELEASE:=3
PKG_SOURCE:=colord-1.4.8.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/hughsie/colord/tar.gz/refs/tags/1.4.8?
PKG_HASH:=4f707604f1d8c3e9d9191bc4499605ebcf03b2e4f45a246a78cbd381333879b7
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=colord
GNOME_DEPENDS:=+glib2-gir +libgusb +libgudev +libudev-systemd +liblcms2 +libsqlite3 +polkit +libsystemd
GNOME_MESON_ARGS:=-Dintrospection=true -Dvapi=false -Ddaemon=true -Ddaemon_user=colord -Dargyllcms_sensor=false -Dtests=false -Dinstalled_tests=false -Ddocs=false -Dman=false -Dbash_completion=false -Dsystemd=true -Dudev_rules=true

include $(INCLUDE_DIR)/gnome-package.mk

Package/colord/Default:=$(Package/colord)
define Package/colord
  $(Package/colord/Default)
  USERID:=colord:colord
endef

define Build/Install
	$(call Build/Install/Meson)
	$(INSTALL_DIR) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/colord.service.d
	$(INSTALL_DATA) ./files/openwrt.conf $(PKG_INSTALL_DIR)/usr/lib/systemd/system/colord.service.d/
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
