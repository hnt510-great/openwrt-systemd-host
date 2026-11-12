include $(TOPDIR)/rules.mk

PKG_NAME:=libtpms
PKG_VERSION:=0.10.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/stefanberger/libtpms/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=edac03680f8a4a1c5c1d609a10e3f41e1a129e38ff5158f0c8deaedc719fb127
PKG_LICENSE:=BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/libtpms
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=TPM 1.2 and TPM 2.0 emulation library
  URL:=https://github.com/stefanberger/libtpms
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libopenssl +@OPENSSL_WITH_CAMELLIA
endef

define Package/libtpms/description
  Library providing the TPM 1.2 and TPM 2.0 software emulation used by swtpm
  to give virtual machines a virtual TPM.
endef

# glibc's C23 const-preserving strstr trips upstream's -Werror.
TARGET_CFLAGS += -Wno-error=discarded-qualifiers

CONFIGURE_ARGS += \
	--disable-static \
	--with-openssl \
	--with-tpm2 \
	--disable-hardening

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/libtpms $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libtpms.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/libtpms.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libtpms/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libtpms.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libtpms))
