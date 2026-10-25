include $(TOPDIR)/rules.mk

PKG_NAME:=cups-runtime
PKG_VERSION:=2.4.20
PKG_RELEASE:=3
PKG_SOURCE:=cups-$(PKG_VERSION)-source.tar.gz
PKG_SOURCE_URL:=https://github.com/OpenPrinting/cups/releases/download/v$(PKG_VERSION)/
PKG_HASH:=ab4d9cd7f3e58060091d2b24972223d6401675f11c49b65abf4f6ef31dea22ff
PKG_BUILD_DIR:=$(BUILD_DIR)/cups-$(PKG_VERSION)
PKG_BUILD_PARALLEL:=1
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE

include $(INCLUDE_DIR)/package.mk

define Package/libcups-runtime
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=Printing
  TITLE:=CUPS client library for desktop applications
  URL:=https://openprinting.github.io/cups/
  DEPENDS:=+zlib +libpthread +libopenssl +libcrypt-compat
endef

define Package/libcups-runtime/description
  The libcups.so.2 client library required by Electron applications.
  No printing daemon, filters, discovery service or command-line tools
  are installed. The existing feed's build-only libcups is independent.
endef

CONFIGURE_ARGS += \
	--with-components=core --with-tls=openssl \
	--disable-acl --disable-dbus --with-dnssd=no --disable-gssapi \
	--disable-libusb --disable-pam --disable-slp \
	--without-perl --without-python --without-php

define Build/Compile
	+$(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR)/cups \
		$(TARGET_CONFIGURE_OPTS) libcups.so.2
endef

define Package/libcups-runtime/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_BUILD_DIR)/cups/libcups.so.2 $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libcups-runtime))
