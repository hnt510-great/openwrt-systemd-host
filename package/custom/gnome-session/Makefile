include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-session
PKG_VERSION:=51.0
PKG_RELEASE:=1
PKG_SOURCE:=gnome-session-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-session/51/
PKG_HASH:=5195c4f60542a953ab6ebd288f3785b8e7746292d8c167e0c99d353438a184d1
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME user session manager
GNOME_DEPENDS:=+glib2 +gnome-desktop +libsystemd
GNOME_MESON_ARGS:=-Ddocbook=false -Dman=false -Dsystemduserunitdir=/usr/lib/systemd/user

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
