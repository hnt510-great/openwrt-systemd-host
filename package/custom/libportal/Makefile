include $(TOPDIR)/rules.mk

PKG_NAME:=libportal
PKG_VERSION:=0.11.0
PKG_RELEASE:=1
PKG_SOURCE:=libportal-0.11.0.tar.xz
PKG_SOURCE_URL:=https://github.com/flatpak/libportal/releases/download/0.11.0/
PKG_HASH:=abb9e452a1c372133bd3eb8f0bb30d07b2d0a8fb02001c4155cf287555db4040
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=libportal
GNOME_DEPENDS:=+glib2-gir +gtk4 +libgtk3
GNOME_MESON_ARGS:=-Dbackend-gtk3=enabled -Dbackend-gtk4=enabled -Dbackend-qt5=disabled -Dbackend-qt6=disabled -Dintrospection=true -Dvapi=false -Ddocs=false -Dtests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
