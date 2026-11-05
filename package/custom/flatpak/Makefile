include $(TOPDIR)/rules.mk

PKG_NAME:=flatpak
PKG_VERSION:=1.18.4
PKG_RELEASE:=4
PKG_SOURCE:=flatpak-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://github.com/flatpak/flatpak/releases/download/$(PKG_VERSION)
PKG_HASH:=b899a7a00c48d2c626cb8ec33fe556720b376c25805d7222430c0fdca4c6ac8d
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host wayland/host wayland-protocols python-pyparsing/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/flatpak
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=flatpak for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +libcap +libarchive +libcurl +libxml2 +libzstd +dconf +libsystemd +libfuse3 +fuse3-utils +@FUSE3_UTILS_SETUID +libostree +json-glib +appstream +libgdk-pixbuf +libseccomp +libgpgme +gnupg2 +gnupg2-utils +bubblewrap +xdg-dbus-proxy +dbus +coreutils-stat +libwayland +libXau
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dsystem_helper=disabled -Dseccomp=enabled \
	-Dsystemd=enabled -Ddconf=enabled -Dgir=disabled -Dgtkdoc=disabled -Dman=disabled \
	-Ddocbook_docs=disabled -Dtests=false -Dinstalled_tests=false -Dmalcontent=disabled \
	-Dselinux_module=disabled -Dxauth=enabled -Dsystem_bubblewrap=/usr/bin/bwrap \
	-Dsystem_dbus_proxy=/usr/bin/xdg-dbus-proxy -Dsystem_fusermount=/usr/bin/fusermount3 \
	-Dsystem_install_dir=/srv/flatpak/system -Dsystemduserunitdir=/usr/lib/systemd/user \
	-Dsystemduserenvgendir=/usr/lib/systemd/user-environment-generators \
	-Dsystemdsystemenvgendir=/usr/lib/systemd/system-environment-generators

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/dbus-1/interfaces
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1/interfaces/. $(1)/usr/share/dbus-1/interfaces/
endef
define Package/flatpak/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib $(1)/usr/libexec $(1)/usr/share $(1)/etc/profile.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/flatpak $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/libexec/. $(1)/usr/libexec/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1 $(PKG_INSTALL_DIR)/usr/share/flatpak $(1)/usr/share/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/etc/profile.d/flatpak.sh $(1)/etc/profile.d/
endef

$(eval $(call BuildPackage,flatpak))
