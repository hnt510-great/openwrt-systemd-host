include $(TOPDIR)/rules.mk

PKG_NAME:=cpio
PKG_VERSION:=2.15
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.bz2
PKG_SOURCE_URL:=@GNU/cpio
PKG_HASH:=937610b97c329a1ec9268553fb780037bcfff0dcffe9725ebc4fd9c1aa9075db
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_CPE_ID:=cpe:/a:gnu:cpio
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/cpio
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=GNU cpio archiver
  URL:=https://www.gnu.org/software/cpio/
endef

define Package/cpio/description
  GNU cpio copies files into or out of cpio and tar archives, and
  copies directory trees in pass-through mode (cpio -p).
endef

CONFIGURE_ARGS += \
	--disable-nls \
	--disable-rpath \
	--disable-mt \
	--with-rmt=/usr/libexec/rmt

define Package/cpio/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/cpio $(1)/usr/bin/
endef

$(eval $(call BuildPackage,cpio))
