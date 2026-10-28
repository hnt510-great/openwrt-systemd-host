include $(TOPDIR)/rules.mk

PKG_NAME:=libportal
PKG_VERSION:=0.9.1
PKG_RELEASE:=1
PKG_SOURCE:=libportal-0.9.1.tar.xz
PKG_SOURCE_URL:=https://github.com/flatpak/libportal/releases/download/0.9.1/
PKG_HASH:=de801ee349ed3c255a9af3c01b1a401fab5b3fc1c35eb2fd7dfb35d4b8194d7f
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=libportal
GNOME_DEPENDS:=+glib2-gir +gtk4 +libgtk3
GNOME_MESON_ARGS:=-Dbackend-gtk3=enabled -Dbackend-gtk4=enabled -Dbackend-qt5=disabled -Dbackend-qt6=disabled -Dintrospection=true -Dvapi=false -Ddocs=false -Dtests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
