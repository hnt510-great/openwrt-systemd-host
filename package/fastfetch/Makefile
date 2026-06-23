include $(TOPDIR)/rules.mk

PKG_NAME:=fastfetch
PKG_VERSION:=2.62.1
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/fastfetch-cli/fastfetch/tar.gz/$(PKG_VERSION)?
PKG_HASH:=8c4833e55b8b445a32c7cb7570007b5e10a9ee4cee74a494004ba61e88b12b26

PKG_MAINTAINER:=Fastfetch-cli <https://github.com/fastfetch-cli/fastfetch>
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_FLAGS:=lto

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/fastfetch
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=A maintained, feature-rich and performance oriented, neofetch like tool.
  URL:=https://github.com/fastfetch-cli/fastfetch
  DEPENDS:=+libpthread +librt
endef

define Package/fastfetch/description
  Fastfetch is a neofetch-like tool for fetching system information and
  displaying it in a pretty way. It is written mainly in C, with
  performance and customizability in mind.
endef

# Disable modules that are generally not useful or available on OpenWrt
# to minimize binary size and avoid missing headers.
CMAKE_OPTIONS += \
	-DBUILD_TESTING=OFF \
	-DENABLE_VULKAN=OFF \
	-DENABLE_WAYLAND=OFF \
	-DENABLE_X11=OFF \
	-DENABLE_DRM=OFF \
	-DENABLE_GIO=OFF \
	-DENABLE_PULSE=OFF \
	-DENABLE_OPENCL=OFF

define Package/fastfetch/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/fastfetch $(1)/usr/bin/
	$(INSTALL_DIR) $(1)/usr/share/fastfetch/presets
	$(CP) $(PKG_INSTALL_DIR)/usr/share/fastfetch/presets/* $(1)/usr/share/fastfetch/presets/
endef

$(eval $(call BuildPackage,fastfetch))
