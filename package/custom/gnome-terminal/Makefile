include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-terminal
PKG_VERSION:=3.60.0
PKG_RELEASE:=1
PKG_SOURCE:=gnome-terminal-3.60.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-terminal/3.60/
PKG_HASH:=b8daf3f08545172c4d2885733f720361ab0349ea669b99245eed4ad16ed3de28
PKG_LICENSE:=GPL-3.0-or-later
PKG_BUILD_DEPENDS:=libxslt/host
GNOME_TITLE:=GNOME terminal emulator
GNOME_DEPENDS:=+libgtk3 +libvte3 +libhandy +gsettings-desktop-schemas +libuuid +libpcre2
GNOME_MESON_ARGS:=-Dappstream=false -Ddocs=false -Dnautilus_extension=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
