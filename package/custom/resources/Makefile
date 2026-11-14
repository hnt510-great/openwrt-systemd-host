include $(TOPDIR)/rules.mk

PKG_NAME:=resources
PKG_VERSION:=1.10.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/nokyan/resources/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=v$(PKG_VERSION)
PKG_HASH:=120aa520cf6b9cf957958c12a84b562db742114d41aeea59ad6b6caa63f34654
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=rust/host
GNOME_TITLE:=GTK4 and libadwaita system resources and process monitor
GNOME_DEPENDS:=+glib2 +gtk4 +libadwaita +polkit +pciutils +kmod
GNOME_MESON_ARGS:=-Dprofile=default

include $(INCLUDE_DIR)/gnome-package.mk
include $(INCLUDE_DIR)/gnome-rust.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
