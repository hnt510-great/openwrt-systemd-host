include $(TOPDIR)/rules.mk

PKG_NAME:=gcr3
PKG_VERSION:=3.41.2
PKG_RELEASE:=1
PKG_SOURCE:=gcr-3.41.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gcr/3.41/
PKG_HASH:=bad10f3c553a0e1854649ab59c5b2434da22ca1a54ae6138f1f53961567e1ab7
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DIR:=$(BUILD_DIR)/gcr-$(PKG_VERSION)-gnome
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); xzcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) --strip-components=1 -C $(PKG_BUILD_DIR) -xf -
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME keyring certificate support
GNOME_DEPENDS:=+glib2-gir +libgcrypt +p11-kit
GNOME_MESON_ARGS:=-Dintrospection=false -Dgtk_doc=false -Dgtk=false -Dgpg_path=/usr/bin/gpg -Dssh_agent=false -Dsystemd=enabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
