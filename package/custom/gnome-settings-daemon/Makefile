include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-settings-daemon
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=gnome-settings-daemon-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-settings-daemon/51/
PKG_HASH:=e7de8d30ae2d63c7a9a21f8f0247219275cbc1d7f5ed09205e4a47642666f6ae
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.0-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME settings services
GNOME_DEPENDS:=+glib2 +gnome-desktop +gsettings-desktop-schemas +libgweather +geocode-glib +geoclue +libcanberra +libnotify +libpulse-mainloop-glib +polkit +upower +libsystemd +libgudev +colord +libX11 +libXfixes +alsa-lib +gcr4
GNOME_MESON_ARGS:=-Dsystemd=true -Dsystemd-units=true -Dnetwork_manager=false -Dwwan=false -Dsmartcard=false -Dusb-protection=false -Dcups=false -Dcolord=true -Dxwayland=true

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
