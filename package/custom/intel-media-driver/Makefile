include $(TOPDIR)/rules.mk

PKG_NAME:=intel-media-driver
PKG_VERSION:=26.3.5
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/intel/media-driver/tar.gz/intel-media-$(PKG_VERSION)?
PKG_HASH:=76f41c06cefc91d57e0b7d366b7a91b8420ec77939326491795f9fb26afca7e7
PKG_BUILD_DIR:=$(BUILD_DIR)/media-driver-intel-media-$(PKG_VERSION)
PKG_LICENSE:=MIT BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE.md
CMAKE_BINARY_SUBDIR:=openwrt-build

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/intel-media-driver
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=Video
  TITLE:=Intel iHD VA-API media driver
  URL:=https://github.com/intel/media-driver
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libva +libigdgmm +libstdcpp
endef

define Package/intel-media-driver/description
  Intel's VA-API driver for Broadwell and newer GPUs, including Jasper Lake.
  Uses the upstream full-feature build with prebuilt media shaders. The
  existing Intel DRM kernel driver and render-node access are required.
endef

CMAKE_OPTIONS += \
	-DCMAKE_INSTALL_LIBDIR=lib \
	-DBUILD_TYPE=release \
	-DBUILD_CMRTLIB=OFF \
	-DENABLE_KERNELS=ON \
	-DENABLE_NONFREE_KERNELS=ON \
	-DBUILD_KERNELS=OFF \
	-DMEDIA_RUN_TEST_SUITE=OFF \
	-DLIBVA_DRIVERS_PATH=/usr/lib/dri

define Package/intel-media-driver/install
	$(INSTALL_DIR) $(1)/usr/lib/dri $(1)/usr/share/licenses/intel-media-driver
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/dri/iHD_drv_video.so $(1)/usr/lib/dri/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/LICENSE.md $(PKG_BUILD_DIR)/third-party-programs.txt \
		$(1)/usr/share/licenses/intel-media-driver/
endef

$(eval $(call BuildPackage,intel-media-driver))
