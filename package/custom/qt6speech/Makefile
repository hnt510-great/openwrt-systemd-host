include $(TOPDIR)/rules.mk

PKG_NAME:=qt6speech
PKG_VERSION:=6.9.3
PKG_RELEASE:=1
PKG_SOURCE:=qtspeech-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.9/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtspeech-everywhere-src-$(PKG_VERSION)
PKG_HASH:=f86f5a4c742fb86ccc6e90ee72a9213150986575c3d238829a4b48a28bc9ab3e
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_LICENSE_FILES:= \
	LICENSES/LicenseRef-Qt-Commercial.txt \
	LICENSES/LGPL-3.0-only.txt \
	LICENSES/GPL-2.0-only.txt \
	LICENSES/GPL-3.0-only.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base qt6multimedia flite

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

# The flite plugin renders audio through Qt Multimedia, so the two modules
# must be built together. speech-dispatcher is not packaged.
CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DFEATURE_flite=ON \
	-DFEATURE_speechd=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_SpeechDispatcher=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

define Package/qt6speech
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 TextToSpeech
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6multimedia +libflite +libstdcpp
endef

define Package/qt6speech-dev
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 TextToSpeech development files
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-dev +qt6multimedia-dev +qt6speech
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6speech/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6/plugins/texttospeech
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6TextToSpeech.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/texttospeech/*.so $(1)/usr/lib/qt6/plugins/texttospeech/
endef

define Package/qt6speech-dev/install
	$(INSTALL_DIR) $(1)/usr/include/qt6 $(1)/usr/lib/cmake \
		$(1)/usr/lib/pkgconfig $(1)/usr/lib/qt6/metatypes
	$(CP) $(PKG_INSTALL_DIR)/usr/include/qt6/. $(1)/usr/include/qt6/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6TextToSpeech* $(1)/usr/lib/cmake/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/Qt6TextToSpeech*.pc \
		$(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/metatypes/. \
		$(1)/usr/lib/qt6/metatypes/
endef

$(eval $(call BuildPackage,qt6speech))
$(eval $(call BuildPackage,qt6speech-dev))
