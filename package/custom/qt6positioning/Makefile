include $(TOPDIR)/rules.mk

PKG_NAME:=qt6positioning
PKG_VERSION:=6.11.3
PKG_RELEASE:=1
PKG_SOURCE:=qtpositioning-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.11/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtpositioning-everywhere-src-$(PKG_VERSION)
PKG_HASH:=a38695bc412b7261476e8e96178460ec9319e61c34ecc6a14eb2e76e5c73eca1
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base qt6quick

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6SerialPort=ON \
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

define Package/qt6positioning
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Positioning
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6base-dbus +qt6quick +libstdcpp
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6positioning/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Positioning*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins $(1)/usr/lib/qt6/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/qml ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/qml $(1)/usr/lib/qt6/
endef

$(eval $(call BuildPackage,qt6positioning))
