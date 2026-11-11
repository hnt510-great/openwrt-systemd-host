include $(TOPDIR)/rules.mk

PKG_NAME:=swtpm
PKG_VERSION:=0.10.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/stefanberger/swtpm/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=f61cf6f1e9bbcb4cefb30b70cafaf1c4df54c6961e65cfa63830e8ad0e220134
PKG_LICENSE:=BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/swtpm
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Virtualization
  TITLE:=Software TPM emulator for virtual machines
  URL:=https://github.com/stefanberger/swtpm
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libtpms +glib2 +json-glib +libopenssl +libgnutls +libtasn1 +libseccomp +certtool
  USERID:=swtpm=194:swtpm=194
endef

define Package/swtpm/description
  swtpm, swtpm_setup, swtpm_ioctl and the local CA used by libvirt's TPM
  emulator backend (<tpm><backend type='emulator'/></tpm>).
endef

define Package/swtpm/conffiles
/etc/swtpm_setup.conf
/etc/swtpm-localca.conf
/etc/swtpm-localca.options
endef

CONFIGURE_ARGS += \
	--disable-static \
	--with-openssl \
	--with-gnutls \
	--with-seccomp \
	--without-cuse \
	--without-selinux \
	--disable-tests \
	--disable-hardening \
	--with-tss-user=swtpm \
	--with-tss-group=swtpm

# Only the configure probe needs it; swtpm_localca finds certtool in PATH.
CONFIGURE_VARS += ac_cv_path_GNUTLS_CERTTOOL=/usr/bin/certtool

define Package/swtpm/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/swtpm $(1)/etc
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/swtpm $(PKG_INSTALL_DIR)/usr/bin/swtpm_setup \
		$(PKG_INSTALL_DIR)/usr/bin/swtpm_ioctl $(PKG_INSTALL_DIR)/usr/bin/swtpm_localca \
		$(PKG_INSTALL_DIR)/usr/bin/swtpm_cert $(PKG_INSTALL_DIR)/usr/bin/swtpm_bios $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/swtpm/*.so.* $(1)/usr/lib/swtpm/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/etc/swtpm_setup.conf $(PKG_INSTALL_DIR)/etc/swtpm-localca.options $(1)/etc/
	$(INSTALL_DATA) ./files/swtpm-localca.conf $(1)/etc/swtpm-localca.conf
endef

$(eval $(call BuildPackage,swtpm))
