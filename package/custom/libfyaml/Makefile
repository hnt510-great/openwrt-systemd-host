include $(TOPDIR)/rules.mk

PKG_NAME:=libfyaml
PKG_VERSION:=0.9.6
PKG_RELEASE:=1
PKG_SOURCE:=libfyaml-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://github.com/pantoniou/libfyaml/releases/download/v$(PKG_VERSION)
PKG_HASH:=a59cc3331e2eb903ec36933ad52a45888041cac31e44f553a00511131242c483
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
PKG_FIXUP:=autoreconf

include $(INCLUDE_DIR)/package.mk

define Package/libfyaml
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libfyaml for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +libgcc
endef

CONFIGURE_ARGS += --disable-network --without-libclang --disable-shave


define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libfyaml/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libfyaml))
