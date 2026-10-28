include $(TOPDIR)/rules.mk

PKG_NAME:=xdg-desktop-portal-gnome
PKG_VERSION:=51.0
PKG_RELEASE:=1
PKG_SOURCE:=xdg-desktop-portal-gnome-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/xdg-desktop-portal-gnome/51/
PKG_HASH:=ec228b305091b649c16c690e102aa1d66fc10e9834888d51e411913c82c1430d
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=blueprint-compiler/host
GNOME_TITLE:=GNOME screen capture and remote desktop portals
GNOME_DEPENDS:=+gtk4 +libadwaita +gnome-desktop +libgweather +geoclue +libportal +libpipewire +libsystemd +xdg-desktop-portal +gsettings-desktop-schemas
GNOME_MESON_ARGS:=-Dsystemd=enabled -Dsystemduserunitdir=/usr/lib/systemd/user

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
