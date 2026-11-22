include $(TOPDIR)/rules.mk

PKG_NAME:=hunspell-en
PKG_VERSION:=4.0.0
PKG_RELEASE:=1
PKG_SOURCE:=dictionaries-8cfea406.tar.gz
PKG_SOURCE_URL:=https://github.com/wooorm/dictionaries/archive/8cfea406b505e4d7df52d5a19bce525df98c54ab.tar.gz
PKG_HASH:=1ce550ad1d03e03a11b16c81ee5edc31cf5792578dbe5926a403bf0ffba0a443
PKG_LICENSE:=MIT
PKG_BUILD_DIR:=$(BUILD_DIR)/dictionaries-8cfea406b505e4d7df52d5a19bce525df98c54ab

include $(INCLUDE_DIR)/package.mk

define Package/hunspell-en
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=English (US) Hunspell dictionary
  URL:=https://github.com/wooorm/dictionaries
  DEPENDS:=+hunspell
endef

define Build/Compile
endef

define Package/hunspell-en/install
	$(INSTALL_DIR) $(1)/usr/share/hunspell
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/dictionaries/en/index.aff $(1)/usr/share/hunspell/en_US.aff
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/dictionaries/en/index.dic $(1)/usr/share/hunspell/en_US.dic
endef

$(eval $(call BuildPackage,hunspell-en))
