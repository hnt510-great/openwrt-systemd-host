include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-tweaks
PKG_VERSION:=49.0
PKG_RELEASE:=1
PKG_SOURCE:=gnome-tweaks-49.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-tweaks/49/
PKG_HASH:=b3909bdcb4905b68427d6ab581e01f436dff8e5c0a389b1e0b14500f18806ebb
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=LICENSES/GPL-3.0
PKG_BUILD_DEPENDS:=python3/host
GNOME_TITLE:=GNOME Tweaks
GNOME_DEPENDS:=+python3-gobject +python3-light +python3-xml +python3-logging +gtk4 +libadwaita +libgudev +libnotify +gnome-desktop +gsettings-desktop-schemas +gnome-shell

include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk
GNOME_MESON_ARGS:=-Dpython.purelibdir=$(PYTHON3_PKG_DIR) -Dpython.platlibdir=$(PYTHON3_PKG_DIR)

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
