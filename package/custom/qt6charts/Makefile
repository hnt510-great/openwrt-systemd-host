include $(TOPDIR)/rules.mk

PKG_NAME:=qt6charts
PKG_VERSION:=6.11.3
PKG_RELEASE:=1
PKG_SOURCE:=qtcharts-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.11/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtcharts-everywhere-src-$(PKG_VERSION)
PKG_HASH:=1d51d18e6f36e8b0dbbcd1a59f3ce9452ca5bf9b2d2fc8465be18cd0d06d6700
PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:= \
	LICENSES/LicenseRef-Qt-Commercial.txt \
	LICENSES/GPL-3.0-only.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base qt6quick

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

ifneq ($(CONFIG_USE_SSTRIP),)
  STRIP:=$(TARGET_CROSS)strip $(call qstrip,$(CONFIG_STRIP_ARGS))
  RSTRIP:= \
    export CROSS="$(TARGET_CROSS)" \
		$(if $(CONFIG_KERNEL_KALLSYMS),NO_RENAME=1) \
		$(if $(CONFIG_KERNEL_PROFILING),KEEP_SYMBOLS=1); \
    NM="$(TARGET_CROSS)nm" \
    STRIP="$(STRIP)" \
    STRIP_KMOD="$(SCRIPT_DIR)/strip-kmod.sh" \
    $(SCRIPT_DIR)/rstrip.sh
endif

define Package/qt6charts/Default
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Charts
  URL:=https://www.qt.io
endef

define Package/qt6charts
  $(call Package/qt6charts/Default)
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6base-gui +qt6base-network +qt6base-widgets \
	+BUILD_qt6base-gui_OPENGL_OPENGLES2:qt6base-opengl \
	+BUILD_qt6base-gui_OPENGL_OPENGLES2:qt6base-openglwidgets \
	+qt6quick +qt6quick-qml +libstdcpp
endef

define Package/qt6charts-dev
  $(call Package/qt6charts/Default)
  TITLE+=development files
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-dev +qt6quick-dev +qt6charts
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6charts/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Charts*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/qml ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/qml $(1)/usr/lib/qt6/
endef

define Package/qt6charts-dev/install
	$(INSTALL_DIR) $(1)/usr/include/qt6 $(1)/usr/lib/cmake \
		$(1)/usr/lib/pkgconfig $(1)/usr/lib/qt6/metatypes
	$(CP) $(PKG_INSTALL_DIR)/usr/include/qt6/. $(1)/usr/include/qt6/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Charts*.so $(1)/usr/lib/
	[ ! -e $(PKG_INSTALL_DIR)/usr/lib/libQt6Charts.prl ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Charts*.prl $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6Charts* $(1)/usr/lib/cmake/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/Qt6Charts*.pc \
		$(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/metatypes/. \
		$(1)/usr/lib/qt6/metatypes/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/mkspecs ] || { \
		$(INSTALL_DIR) $(1)/usr/lib/qt6/mkspecs; \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/mkspecs/. $(1)/usr/lib/qt6/mkspecs/; \
	}
endef

$(eval $(call BuildPackage,qt6charts))
$(eval $(call BuildPackage,qt6charts-dev))
