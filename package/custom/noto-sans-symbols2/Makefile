include $(TOPDIR)/rules.mk

PKG_NAME:=noto-sans-symbols2
PKG_VERSION:=2.008
PKG_RELEASE:=1
PKG_SOURCE:=NotoSansSymbols2-v$(PKG_VERSION).zip
PKG_SOURCE_URL:=https://github.com/notofonts/symbols/releases/download/NotoSansSymbols2-v$(PKG_VERSION)/
PKG_HASH:=346c930bbe8eb946701a05c54e9c11a2094dee1d93c387bf1771c0a3e335688f
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); unzip -q -o -j -d $(PKG_BUILD_DIR) $(DL_DIR)/$(PKG_SOURCE) NotoSansSymbols2/unhinted/otf/NotoSansSymbols2-Regular.otf OFL.txt
PKG_LICENSE:=OFL-1.1
PKG_LICENSE_FILES:=OFL.txt
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/noto-sans-symbols2
  SECTION:=fonts
  CATEGORY:=Fonts
  TITLE:=Noto Sans Symbols 2 regular font
  URL:=https://github.com/notofonts/symbols
  DEPENDS:=+fontconfig
endef

define Package/noto-sans-symbols2/description
 Symbol fallback font covering technical symbols, arrows, media control
 glyphs (for example U+23F5) and other pictographs missing from DejaVu.
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/noto-sans-symbols2/install
	$(INSTALL_DIR) $(1)/usr/share/fonts/noto-symbols2 $(1)/usr/share/licenses/noto-sans-symbols2
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/NotoSansSymbols2-Regular.otf $(1)/usr/share/fonts/noto-symbols2/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/OFL.txt $(1)/usr/share/licenses/noto-sans-symbols2/
endef

$(eval $(call BuildPackage,noto-sans-symbols2))
