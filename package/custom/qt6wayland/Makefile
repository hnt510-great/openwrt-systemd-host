include $(TOPDIR)/rules.mk

PKG_NAME:=qt6wayland
PKG_VERSION:=6.11.3
PKG_RELEASE:=1
PKG_SOURCE:=qtwayland-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.11/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtwayland-everywhere-src-$(PKG_VERSION)
PKG_HASH:=7f6185eb6e7d75202c42dfaf18dc54ae96f2d9a7a265358d061a6f85366f6c97
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_LICENSE_FILES:= \
	LICENSES/LicenseRef-Qt-Commercial.txt \
	LICENSES/LGPL-3.0-only.txt \
	LICENSES/GPL-2.0-only.txt \
	LICENSES/GPL-3.0-only.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
# Starting in Qt 6.11, qtbase builds libQt6WaylandClient, qtwaylandscanner
# and the core Wayland client QPA plugins (owned by qt6waylandclient /
# qt6waylandclient-dev in feeds/video/frameworks/qt6/qt6base). This recipe
# only packages optional extra client plugins from the qtwayland submodule.
PKG_BUILD_DEPENDS:=qt6base wayland wayland-protocols wayland/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DFEATURE_wayland_client=ON \
	-DFEATURE_wayland_server=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick3D=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

define Package/qt6wayland-extras
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Wayland extra client plugins (Adwaita/IVI/Qt-shell)
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6waylandclient +libstdcpp
endef

define Package/qt6wayland-extras/install
	$(INSTALL_DIR) $(1)/usr/lib/qt6/plugins
	for d in wayland-decoration-client wayland-shell-integration; do \
		[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/$$$$d ] || \
			$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/$$$$d $(1)/usr/lib/qt6/plugins/; \
	done
endef

$(eval $(call BuildPackage,qt6wayland-extras))
