include $(TOPDIR)/rules.mk

PKG_NAME:=evince
PKG_VERSION:=48.4
PKG_RELEASE:=1
PKG_SOURCE:=evince-48.4.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/evince/48/
PKG_HASH:=f296c5c662886635d4cd597e8ac0afcde7982be4486533c2b7f095b268be8668
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME Document Viewer
GNOME_DEPENDS:=+glib2-gir +libgtk3 +libhandy +libsecret +gsettings-desktop-schemas +libarchive +libtiff +poppler +libxml2
GNOME_MESON_ARGS:=-Dplatform=gnome -Dviewer=true -Dpreviewer=true -Dthumbnailer=true -Dnautilus=false -Dcomics=enabled -Ddjvu=disabled -Ddvi=disabled -Dpdf=enabled -Dps=disabled -Dtiff=enabled -Dxps=disabled -Dgtk_doc=false -Duser_doc=false -Dintrospection=false -Ddbus=true -Dkeyring=enabled -Dgtk_unix_print=enabled -Dthumbnail_cache=disabled -Dmultimedia=disabled -Dgspell=disabled -Dsystemduserunitdir=/usr/lib/systemd/user

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
