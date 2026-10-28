include $(TOPDIR)/rules.mk

PKG_NAME:=tecla
PKG_VERSION:=49.0
PKG_RELEASE:=1
PKG_SOURCE:=tecla-49.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/tecla/49/
PKG_HASH:=2ca424e402baf60cd6b13777703b701ebb1faf8f3d0f2f971144d823f651249f
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=wayland/host wayland-protocols
GNOME_TITLE:=GNOME keyboard layout preview
GNOME_DEPENDS:=+gtk4 +libadwaita +libxkbcommon +libwayland
GNOME_MESON_ARGS:=

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
