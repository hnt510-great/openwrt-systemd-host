include $(TOPDIR)/rules.mk

PKG_NAME:=nautilus
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=nautilus-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/nautilus/51/
PKG_HASH:=a703bc152d18d161d9dab957e2390a36e6246bb5c24de7b15c9624fcfa2f2816
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=blueprint-compiler/host
GNOME_TITLE:=GNOME Files
GNOME_DEPENDS:=+glib2 +gtk4 +libadwaita +glycin +gnome-autoar +gnome-desktop +libportal +tinysparql +icu
GNOME_MESON_ARGS:=-Dselinux=false -Dcloudproviders=false -Dextensions=false -Dtests=none -Ddocs=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
