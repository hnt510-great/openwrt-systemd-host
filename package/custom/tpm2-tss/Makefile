include $(TOPDIR)/rules.mk

PKG_NAME:=tpm2-tss
PKG_VERSION:=4.2.1
PKG_RELEASE:=1
PKG_SOURCE:=tpm2-tss-4.2.1.tar.gz
PKG_SOURCE_URL:=https://github.com/tpm2-software/tpm2-tss/releases/download/4.2.1/
PKG_HASH:=d4aadbc1610876385a370494bbfd7d994356f446dff60cd09eea5933befb1471
PKG_BUILD_DIR:=$(BUILD_DIR)/tpm2-tss-$(PKG_VERSION)
PKG_LICENSE:=BSD-2-Clause
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/tpm2-tss
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=tpm2-tss GNOME platform dependency
  DEPENDS:=+libopenssl +libjson-c +libuuid +libusb-1.0
endef

CONFIGURE_ARGS += --disable-doxygen-doc --disable-static --disable-fapi --disable-policy --disable-tcti-spi-helper --disable-tcti-i2c-helper --disable-tcti-pcap --with-udevrulesdir=/usr/lib/udev/rules.d --with-sysusersdir=/usr/lib/sysusers.d --with-tmpfilesdir=/usr/lib/tmpfiles.d

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/tpm2-tss/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/tpm2-tss-$(PKG_VERSION) ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/tpm2-tss-$(PKG_VERSION) $(1)/usr/lib/
endef

$(eval $(call BuildPackage,tpm2-tss))
