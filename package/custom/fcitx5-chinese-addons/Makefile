include $(TOPDIR)/rules.mk

PKG_NAME:=fcitx5-chinese-addons
PKG_VERSION:=5.1.15
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)_dict.tar.zst
PKG_SOURCE_URL:=https://download.fcitx-im.org/fcitx5/fcitx5-chinese-addons/
PKG_HASH:=82f2fef12473ba4e1ffa51b522bf56bfe6a2132ee6d3b5467c653dc1b90cfd08
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules gettext-full/host
include $(INCLUDE_DIR)/package.mk

include $(INCLUDE_DIR)/cmake.mk

define Package/fcitx5-chinese-addons
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Fcitx5 Chinese Pinyin input method
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libime +fcitx5 +libstdcpp
endef
CMAKE_OPTIONS += -DCMAKE_INSTALL_LIBDIR=lib -DECM_DIR=$(STAGING_DIR)/usr/share/ECM/cmake \
	-DFCITX_INSTALL_CMAKECONFIG_DIR=$(STAGING_DIR)/usr/lib/cmake \
	-DENABLE_TEST=OFF -DENABLE_GUI=OFF -DENABLE_OPENCC=OFF -DENABLE_CLOUDPINYIN=OFF \
	-DENABLE_DATA=OFF -DENABLE_TOOLS=OFF

# Chaizi is mandatory for the Pinyin engine, even when optional data tools are off.
define Build/Compile
	$(call Build/Compile/Default)
	$(TOOLCHAIN_DIR)/lib/ld-linux-x86-64.so.2 --library-path $(STAGING_DIR)/usr/lib:$(TOOLCHAIN_DIR)/lib \
		$(STAGING_DIR)/usr/bin/libime_pinyindict $(PKG_BUILD_DIR)/im/pinyin/chaizi.txt $(PKG_BUILD_DIR)/im/pinyin/chaizi.dict
endef

define Package/fcitx5-chinese-addons/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/fcitx5 $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/fcitx5 $(1)/usr/share/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/im/pinyin/chaizi.dict $(1)/usr/share/fcitx5/pinyin/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/icons $(1)/usr/share/
endef
$(eval $(call BuildPackage,fcitx5-chinese-addons))
