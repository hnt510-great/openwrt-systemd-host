include $(TOPDIR)/rules.mk

PKG_NAME:=upower
PKG_VERSION:=1.91.5
PKG_RELEASE:=2
PKG_SOURCE:=upower-v1.91.5.tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/upower/upower/-/archive/v1.91.5/
PKG_HASH:=d900f175e39fbc0dfd8632f7c70606e10f79903ee4171d199aa777dfa3a396e2
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DIR:=$(BUILD_DIR)/upower-v1.91.5
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=Power device D-Bus service
GNOME_DEPENDS:=+glib2-gir +libgudev +libudev-systemd +polkit +libsystemd
GNOME_MESON_ARGS:=-Dsystemdsystemunitdir=/usr/lib/systemd/system -Dintrospection=enabled -Dman=false -Dgtk-doc=false -Didevice=disabled -Dpolkit=enabled -Dinstalled_tests=false -Dzshcompletiondir=no -Dos_backend=linux

include $(INCLUDE_DIR)/gnome-package.mk

define Build/Install
	$(call Build/Install/Meson)
	$(INSTALL_DIR) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/upower.service.d
	$(INSTALL_DATA) ./files/openwrt.conf $(PKG_INSTALL_DIR)/usr/lib/systemd/system/upower.service.d/
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
