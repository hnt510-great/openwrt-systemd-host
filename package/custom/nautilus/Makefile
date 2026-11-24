include $(TOPDIR)/rules.mk

PKG_NAME:=nautilus
PKG_VERSION:=51.2
PKG_RELEASE:=1
PKG_SOURCE:=nautilus-51.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/nautilus/51/
PKG_HASH:=11e3784441cd59a4696b47ed458dddaacf5b1b616f71686d6738fdbaa4809db1
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=blueprint-compiler/host
GNOME_TITLE:=GNOME Files
GNOME_DEPENDS:=+glib2 +gvfs +gtk4 +libadwaita +glycin +gnome-autoar +gnome-desktop +libportal +tinysparql +icu
GNOME_MESON_ARGS:=-Dselinux=false -Dcloudproviders=false -Dextensions=false -Dtests=none -Ddocs=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
