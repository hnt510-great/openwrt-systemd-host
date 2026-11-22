include $(TOPDIR)/rules.mk

PKG_NAME:=qt6multimedia
PKG_VERSION:=6.9.3
PKG_RELEASE:=2
PKG_SOURCE:=qtmultimedia-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.9/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtmultimedia-everywhere-src-$(PKG_VERSION)
PKG_HASH:=a275bee7ea60c91851236acdf99d76b891da90f428b68f51fe332354f19b86f5
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_LICENSE_FILES:= \
	LICENSES/LicenseRef-Qt-Commercial.txt \
	LICENSES/LGPL-3.0-only.txt \
	LICENSES/GPL-2.0-only.txt \
	LICENSES/GPL-3.0-only.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base qt6shadertools ffmpeg pulseaudio

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DCMAKE_MODULE_PATH="$(CURDIR)/cmake" \
	-DFEATURE_ffmpeg=ON \
	-DFEATURE_gstreamer=OFF \
	-DFEATURE_alsa=OFF \
	-DFEATURE_pulseaudio=ON \
	-DFEATURE_pipewire=OFF \
	-DFEATURE_linux_v4l=OFF \
	-DFEATURE_linux_dmabuf=OFF \
	-DFEATURE_vaapi=OFF \
	-DFEATURE_spatialaudio=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Qml=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick3D=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Svg=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

define Package/qt6multimedia/Default
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6Multimedia
  URL:=https://www.qt.io
endef

define Package/qt6multimedia
  $(call Package/qt6multimedia/Default)
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-gui +qt6base-network \
	+BUILD_qt6base-gui_OPENGL_OPENGLES2:qt6base-opengl \
	+libffmpeg +libpulse +libstdcpp
endef

define Package/qt6multimedia-widgets
  $(call Package/qt6multimedia/Default)
  TITLE+=widgets
  DEPENDS:=+qt6multimedia +qt6base-widgets
endef

define Package/qt6multimedia-dev
  $(call Package/qt6multimedia/Default)
  TITLE+=development files
  DEPENDS:=+qt6base-dev +qt6multimedia +qt6multimedia-widgets
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6multimedia/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6/plugins/multimedia
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Multimedia.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/metatypes/qt6multimedia_metatypes.json $(1)/usr/lib/qt6/metatypes/ 2>/dev/null || true
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/multimedia/*.so $(1)/usr/lib/qt6/plugins/multimedia/
endef

define Package/qt6multimedia-widgets/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6MultimediaWidgets.so.* $(1)/usr/lib/
endef

define Package/qt6multimedia-dev/install
	$(INSTALL_DIR) $(1)/usr/include/qt6 $(1)/usr/lib/cmake \
		$(1)/usr/lib/pkgconfig $(1)/usr/lib/qt6/metatypes
	$(CP) $(PKG_INSTALL_DIR)/usr/include/qt6/. $(1)/usr/include/qt6/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6Multimedia* $(1)/usr/lib/cmake/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6FFmpegMediaPluginImplPrivate \
		$(1)/usr/lib/cmake/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/Qt6Multimedia*.pc \
		$(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/metatypes/. \
		$(1)/usr/lib/qt6/metatypes/
endef

$(eval $(call BuildPackage,qt6multimedia))
$(eval $(call BuildPackage,qt6multimedia-widgets))
$(eval $(call BuildPackage,qt6multimedia-dev))
