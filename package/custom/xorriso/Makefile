include $(TOPDIR)/rules.mk
PKG_NAME:=xorriso
PKG_VERSION:=1.5.8_p2
PKG_RELEASE:=1
PKG_SOURCE:=xorriso-1.5.8.pl02.tar.gz
PKG_SOURCE_URL:=https://www.gnu.org/software/xorriso/
PKG_HASH:=b1455ecafbf0692ddafe1d71002a96f2ce2d77f4deae602678261ce033f97bc8
PKG_BUILD_DIR:=$(BUILD_DIR)/xorriso-1.5.8
PKG_LICENSE:=GPL-2.0-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
include $(INCLUDE_DIR)/package.mk
define Package/xorriso
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=ISO 9660 image manipulation
  DEPENDS:=+zlib +libbz2
endef
CONFIGURE_ARGS += --disable-shared --enable-static --disable-libacl --disable-xattr --disable-libreadline --disable-libedit --disable-libjte

define Package/xorriso/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/xorriso $(1)/usr/bin/
endef
$(eval $(call BuildPackage,xorriso))
