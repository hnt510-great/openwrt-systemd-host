include $(TOPDIR)/rules.mk

PKG_NAME:=gcr4
PKG_VERSION:=4.4.1
PKG_RELEASE:=1
PKG_SOURCE:=gcr-4.4.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gcr/4.4/
PKG_HASH:=c4442c15d4330f17a1f5194df08c576877af68412ab2521446a93bd5e24c931b
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DIR:=$(BUILD_DIR)/gcr-$(PKG_VERSION)
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME certificate and authentication library
GNOME_DEPENDS:=+glib2-gir +libgcrypt +p11-kit +gtk4 +libsecret +libsystemd
GNOME_MESON_ARGS:=-Dintrospection=true -Dvapi=false -Dgtk_doc=false -Dgtk4=true -Dgpg_path=/usr/bin/gpg -Dssh_agent=false -Dsystemd=enabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
