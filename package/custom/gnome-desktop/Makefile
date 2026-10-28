include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-desktop
PKG_VERSION:=51.0
PKG_RELEASE:=1
PKG_SOURCE:=gnome-desktop-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-desktop/51/
PKG_HASH:=9ebeb9f1769d3c310caeadd921ab34c8f264b92937740518b3bc859a579a6912
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME desktop platform libraries
GNOME_DEPENDS:=+glib2-gir +gtk4 +libgtk3 +libgdk-pixbuf +gsettings-desktop-schemas +libxkbcommon +libudev-systemd +libsystemd +iso-codes +fontconfig +libseccomp +libqrencode
GNOME_MESON_ARGS:=-Dintrospection=true -Dbuild_gtk4=true -Dlegacy_library=true -Dsystemd=enabled -Dudev=enabled -Ddesktop_docs=false -Dgtk_doc=false -Dinstalled_tests=false -Ddebug_tools=false -Dqr=enabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
