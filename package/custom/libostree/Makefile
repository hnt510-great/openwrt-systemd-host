include $(TOPDIR)/rules.mk

PKG_NAME:=libostree
PKG_VERSION:=2026.7
PKG_RELEASE:=1
PKG_SOURCE:=libostree-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://github.com/ostreedev/ostree/releases/download/v$(PKG_VERSION)
PKG_HASH:=43e0295e869927edfd41e7cb9cdf5ca8f8515a6f1460af4b381f1f701168494c
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
PKG_FIXUP:=autoreconf

include $(INCLUDE_DIR)/package.mk

define Package/libostree
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libostree for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +liblzma +zlib +libe2p +libcurl +libgpgme +libarchive +libmount +libsystemd +libgcc
endef

CONFIGURE_ARGS += --with-curl --without-soup --without-soup3 --with-gpgme --without-selinux --without-avahi --without-composefs --disable-rofiles-fuse --disable-man --disable-gtk-doc --disable-introspection --disable-installed-tests --without-dracut --without-mkinitcpio


define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libostree/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libostree))
