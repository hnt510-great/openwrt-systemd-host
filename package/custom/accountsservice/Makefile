include $(TOPDIR)/rules.mk

PKG_NAME:=accountsservice
PKG_VERSION:=26.27.3
PKG_RELEASE:=1
PKG_SOURCE:=accountsservice-26.27.3.tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/accountsservice/accountsservice/-/archive/26.27.3/
PKG_HASH:=11de07bcd499c2277f78a6fc830d1437654f3397cc7bbed19c28b3818435ba38
PKG_LICENSE:=GPL-3.0-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=D-Bus account information service
GNOME_DEPENDS:=+glib2-gir +polkit +libjson-c +dbus +libsystemd +libpam
GNOME_MESON_ARGS:=-Dsystemdsystemunitdir=/usr/lib/systemd/system -Dintrospection=true -Dvapi=false -Ddocbook=false -Dgtk_doc=false -Dtests=false -Dlibxcrypt=false -Dadmin_group=wheel

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
