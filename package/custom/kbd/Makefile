include $(TOPDIR)/rules.mk

PKG_NAME:=kbd
PKG_VERSION:=2.10.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=@KERNEL/linux/utils/kbd
PKG_HASH:=6e5ca4f8d76ee9e3a8db700b667f13e12aac9933828a64e1aaad93d26be9b479
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/kbd-chvt
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Virtual console switching tools from kbd
  URL:=https://kbd-project.org/
  ALTERNATIVES:=300:/usr/bin/chvt:/usr/libexec/chvt-kbd
endef

CONFIGURE_ARGS += --disable-nls --disable-vlock --disable-tests --disable-libkeymap --disable-libkfont

define Build/Compile
	$(MAKE_VARS) $(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR)/src/libcommon
	$(MAKE_VARS) $(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR)/src chvt fgconsole
endef

define Package/kbd-chvt/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/libexec
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/src/chvt $(1)/usr/libexec/chvt-kbd
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/src/fgconsole $(1)/usr/bin/fgconsole
endef

$(eval $(call BuildPackage,kbd-chvt))
