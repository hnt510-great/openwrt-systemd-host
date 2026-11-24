include $(TOPDIR)/rules.mk

PKG_NAME:=qcoro6
PKG_VERSION:=0.13.0
PKG_RELEASE:=1
PKG_SOURCE:=qcoro-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://github.com/qcoro/qcoro/archive/refs/tags/v$(PKG_VERSION)/
PKG_BUILD_DIR:=$(BUILD_DIR)/qcoro-$(PKG_VERSION)
PKG_HASH:=4bff7513c5c8e301b66308df05795043b1792ed16381a484e5c990171b8ff19e
PKG_LICENSE:=MIT
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
CMAKE_INSTALL:=1
PKG_BUILD_DEPENDS:=qt6base/host qt6base qt6quick

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DUSE_QT_VERSION=6 \
	-DBUILD_SHARED_LIBS=ON \
	-DQCORO_BUILD_EXAMPLES=OFF \
	-DBUILD_TESTING=OFF \
	-DQCORO_WITH_QTWEBSOCKETS=OFF \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)"

define Package/qcoro6
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=KDE Frameworks 6
  TITLE:=C++20 coroutines for Qt6
  URL:=https://qcoro.dvratil.cz/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6base-dbus +qt6base-network +qt6quick +libstdcpp
endef

define Package/qcoro6/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQCoro6*.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,qcoro6))
