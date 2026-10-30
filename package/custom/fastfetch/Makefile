include $(TOPDIR)/rules.mk

PKG_NAME:=fastfetch
PKG_VERSION:=2.70.0
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/fastfetch-cli/fastfetch/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=$(PKG_VERSION)
PKG_HASH:=8aa01bd3faff2be1d94f231d76489ce6d9f781f51f6e93eafe82359d6d8669af

PKG_MAINTAINER:=Fastfetch-cli <https://github.com/fastfetch-cli/fastfetch>
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_FLAGS:=lto

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/fastfetch
  # Keep the old snapshot date as a fixed compatibility prefix so stable
  # releases upgrade dated packages. PKG_VERSION still tracks upstream tags.
  VERSION:=2026.06.28.$(PKG_VERSION)-r$(PKG_RELEASE)
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
# to minimize binary size, ensure deterministic builds, and avoid missing headers.
CMAKE_OPTIONS += \
	-DBUILD_TESTING=OFF \
	-DBUILD_TESTS=OFF \
	-DENABLE_VULKAN=OFF \
	-DENABLE_WAYLAND=OFF \
	-DENABLE_XCB_RANDR=OFF \
	-DENABLE_XRANDR=OFF \
	-DENABLE_DRM=OFF \
	-DENABLE_DRM_AMDGPU=OFF \
	-DENABLE_GIO=OFF \
	-DENABLE_DCONF=OFF \
	-DENABLE_DBUS=OFF \
	-DENABLE_SQLITE3=OFF \
	-DENABLE_RPM=OFF \
	-DENABLE_IMAGEMAGICK7=OFF \
	-DENABLE_IMAGEMAGICK6=OFF \
	-DENABLE_CHAFA=OFF \
	-DENABLE_EGL=OFF \
	-DENABLE_GLX=OFF \
	-DENABLE_OPENCL=OFF \
	-DENABLE_FREETYPE=OFF \
	-DENABLE_PULSE=OFF \
	-DENABLE_DDCUTIL=OFF \
	-DENABLE_ELF=OFF \
	-DENABLE_ZLIB=OFF \
	-DENABLE_LIBZFS=OFF

define Package/fastfetch/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/fastfetch $(1)/usr/bin/
	$(INSTALL_DIR) $(1)/usr/share/fastfetch/presets
	$(CP) $(PKG_INSTALL_DIR)/usr/share/fastfetch/presets/* $(1)/usr/share/fastfetch/presets/
endef

$(eval $(call BuildPackage,fastfetch))
