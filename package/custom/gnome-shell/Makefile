include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-shell
PKG_VERSION:=51.1
PKG_RELEASE:=2
PKG_SOURCE:=gnome-shell-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-shell/51/
PKG_HASH:=c1eb08d9651a567ed5d9b2791371f1898e657cf45e75e1d88adefbab807977d6
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=blueprint-compiler/host
GNOME_TITLE:=GNOME Shell
GNOME_DEPENDS:=+gnome-autoar +libsoup3 +libgio-gnutls +ca-bundle +gjs +mutter +gcr4 +gtk4 +libadwaita +libxml2 +polkit +gsettings-desktop-schemas +gnome-desktop +json-glib +librsvg +glycin +evolution-data-server +libgdm +libibus +accountsservice +upower +libgweather +libpulse +libsecret +gnome-settings-daemon +adwaita-icons
GNOME_MESON_ARGS:=-Dnetworkmanager=false -Dportal_helper=false -Dsystemd=true -Dcamera_monitor=true -Dtests=false -Dman=false -Dgtk_doc=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
