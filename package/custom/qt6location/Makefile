include $(TOPDIR)/rules.mk

PKG_NAME:=qt6location
PKG_VERSION:=6.11.3
PKG_RELEASE:=1
PKG_SOURCE:=qtlocation-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.11/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtlocation-everywhere-src-$(PKG_VERSION)
PKG_HASH:=5413fa6bb540d4042080ec468a723f01e3d21b312935c604127a2af1b375520e
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base qt6quick qt6positioning qt6shadertools

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++"

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

define Package/qt6location
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Location
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6base-gui +qt6base-network +qt6quick +qt6quick-shapes +qt6positioning +libstdcpp
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6location/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Location*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins $(1)/usr/lib/qt6/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/qml ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/qml $(1)/usr/lib/qt6/
endef

$(eval $(call BuildPackage,qt6location))
