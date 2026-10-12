include $(TOPDIR)/rules.mk

PKG_NAME:=noto-sans-cjk-sc
PKG_VERSION:=2.004
PKG_RELEASE:=1
PKG_SOURCE:=NotoSansCJKsc-Regular-$(PKG_VERSION).otf
PKG_SOURCE_URL:=https://raw.githubusercontent.com/notofonts/noto-cjk/Sans$(PKG_VERSION)/Sans/OTF/SimplifiedChinese/
PKG_SOURCE_URL_FILE:=NotoSansCJKsc-Regular.otf
PKG_HASH:=2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); $(CP) $(DL_DIR)/$(PKG_SOURCE) $(PKG_BUILD_DIR)/font.otf; $(CP) ./files/LICENSE $(PKG_BUILD_DIR)/LICENSE
PKG_LICENSE:=OFL-1.1
PKG_LICENSE_FILES:=LICENSE
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/noto-sans-cjk-sc
  SECTION:=fonts
  CATEGORY:=Fonts
  TITLE:=Noto Sans CJK Simplified Chinese regular font
  URL:=https://github.com/notofonts/noto-cjk
  DEPENDS:=+fontconfig
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/noto-sans-cjk-sc/install
	$(INSTALL_DIR) $(1)/usr/share/fonts/noto-cjk $(1)/usr/share/licenses/noto-sans-cjk-sc
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/font.otf $(1)/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/LICENSE $(1)/usr/share/licenses/noto-sans-cjk-sc/
endef

$(eval $(call BuildPackage,noto-sans-cjk-sc))
