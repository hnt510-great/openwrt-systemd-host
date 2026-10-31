include $(TOPDIR)/rules.mk

PKG_NAME:=gvfs
PKG_VERSION:=1.62.0
PKG_RELEASE:=1
PKG_SOURCE:=gvfs-1.62.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gvfs/1.62/
PKG_HASH:=dd8e6c255fd3bed5eeb190b59027c88b38e63c1be0932ddce9cfeb48f3c43d0f
PKG_LICENSE:=LGPL-2.0-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME virtual file system (Trash, Recent, Network, FTP, SFTP)
GNOME_DEPENDS:=+glib2 +dbus +gsettings-desktop-schemas
GNOME_MESON_ARGS:=-Dsystemduserunitdir=/usr/lib/systemd/user -Dtmpfilesdir=/usr/lib/tmpfiles.d \
	-Dadmin=false -Dafc=false -Dafp=false -Darchive=false -Dcdda=false -Ddnssd=false \
	-Dgoa=false -Dgoogle=false -Dgphoto2=false -Dhttp=false -Dmtp=false -Dnfs=false \
	-Donedrive=false -Dsftp=true -Dsmb=false -Dudisks2=false -Dwsdd=false -Dbluray=false \
	-Dfuse=false -Dgcr=false -Dgcrypt=false -Dgudev=false -Dkeyring=false -Dlogind=false \
	-Dlibusb=false -Dman=false -Dunit_tests=false -Dinstalled_tests=false -Ddevel_utils=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
