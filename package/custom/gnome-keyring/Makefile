include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-keyring
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=gnome-keyring-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-keyring/51/
PKG_HASH:=dfe7adc5876ef0670e7eba2907799bdbb8875ce58bb4208e1a52169bd16a47ca
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.0-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME Secret Service daemon
GNOME_DEPENDS:=+glib2 +gcr3 +libgcrypt +p11-kit +libsystemd +libpam
GNOME_MESON_ARGS:=-Dssh-agent=false -Dsystemd=enabled -Dpam=true -Dselinux=disabled -Dlibcap-ng=disabled -Dmanpage=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
