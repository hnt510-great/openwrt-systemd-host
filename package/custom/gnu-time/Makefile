include $(TOPDIR)/rules.mk

PKG_NAME:=time
PKG_VERSION:=1.10
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=@GNU/time
PKG_HASH:=e8c29fb4ab599d8478e41e8618f50db8aede9c90af27d0d2ef28ae50d5de09c3
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/gnu-time
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=GNU program resource usage measurement
  URL:=https://www.gnu.org/software/time/
  ALTERNATIVES:=300:/usr/bin/time:/usr/libexec/time-gnu
endef

define Package/gnu-time/install
	$(INSTALL_DIR) $(1)/usr/libexec
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/time $(1)/usr/libexec/time-gnu
endef

$(eval $(call BuildPackage,gnu-time))
