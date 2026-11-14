include $(TOPDIR)/rules.mk

PKG_NAME:=loupe
PKG_VERSION:=51.2
PKG_RELEASE:=1
PKG_SOURCE:=loupe-51.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/loupe/51/
PKG_HASH:=64ae1f9b381227eada39cb659edf29656ff7e42348823391678fcc01cdac01b8
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING.md
PKG_BUILD_DEPENDS:=rust/host
GNOME_TITLE:=GNOME Image Viewer
GNOME_DEPENDS:=+glib2 +gtk4 +libadwaita +libgweather +libseccomp +liblcms2 +glycin
GNOME_MESON_ARGS:=-Dprofile=release -Dx11=enabled

include $(INCLUDE_DIR)/gnome-package.mk
include $(INCLUDE_DIR)/gnome-rust.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
