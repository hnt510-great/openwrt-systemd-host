include $(TOPDIR)/rules.mk

PKG_NAME:=qt6wayland
PKG_VERSION:=6.9.3
PKG_RELEASE:=1
PKG_SOURCE:=qtwayland-everywhere-src-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.qt.io/archive/qt/6.9/$(PKG_VERSION)/submodules/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtwayland-everywhere-src-$(PKG_VERSION)
PKG_HASH:=e413d4bc9263e80a465761debf8cb8317aa6b01e814b20046a05258e6573dadd
PKG_LICENSE:=LGPL-3.0-only GPL-2.0-only GPL-3.0-only
PKG_LICENSE_FILES:= \
	LICENSES/LicenseRef-Qt-Commercial.txt \
	LICENSES/LGPL-3.0-only.txt \
	LICENSES/GPL-2.0-only.txt \
	LICENSES/GPL-3.0-only.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=qt6base wayland wayland-protocols wayland/host qt6wayland/host
HOST_BUILD_DEPENDS:=qt6base/host wayland/host
HOST_BUILD_DIR:=$(BUILD_DIR_HOST)/qtwayland-everywhere-src-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/cmake.mk

# Only the client side is needed: applications run under the GNOME/Mutter
# compositor. Qt compositors and their Quick dependencies are not built.
CMAKE_OPTIONS += \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DQT_QMAKE_TARGET_MKSPEC="linux-openwrt-g++" \
	-DQT_FORCE_BUILD_TOOLS=ON \
	-DFEATURE_wayland_client=ON \
	-DFEATURE_wayland_server=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick3D=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

# The host build only provides qtwaylandscanner for the cross build. Wayland
# libraries are not used by that tool, so they may be absent on the host.
CMAKE_HOST_OPTIONS += \
	-DFEATURE_wayland_client=OFF \
	-DFEATURE_wayland_server=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_Wayland=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Test=ON

define Package/qt6waylandclient
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Wayland client platform plugins
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-gui +qt6svg +libwayland \
	+BUILD_qt6base-gui_OPENGL_OPENGLES2:qt6base-opengl \
	+libxkbcommon +libstdcpp
endef

define Package/qt6waylandclient-dev
  SECTION:=video-frameworks
  CATEGORY:=Video
  SUBMENU:=Frameworks and Toolkits
  TITLE:=Qt6 Wayland client development files
  URL:=https://www.qt.io
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-dev +qt6svg-dev +qt6waylandclient \
	+wayland-scanner +wayland-protocols
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
endef

define Package/qt6waylandclient/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6/plugins
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Wayland*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libQt6Wl*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/platforms $(1)/usr/lib/qt6/plugins/
	for d in wayland-decoration-client wayland-graphics-integration-client \
		wayland-shell-integration; do \
		[ ! -d $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/$$$$d ] || \
			$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/$$$$d $(1)/usr/lib/qt6/plugins/; \
	done
endef

define Package/qt6waylandclient-dev/install
	$(INSTALL_DIR) $(1)/usr/include/qt6 $(1)/usr/lib/cmake \
		$(1)/usr/lib/pkgconfig $(1)/usr/lib/qt6/libexec \
		$(1)/usr/lib/qt6/metatypes
	$(CP) $(PKG_INSTALL_DIR)/usr/include/qt6/. $(1)/usr/include/qt6/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6Wayland* \
		$(PKG_INSTALL_DIR)/usr/lib/cmake/Qt6WlShellIntegrationPrivate \
		$(1)/usr/lib/cmake/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/Qt6Wayland*.pc \
		$(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/metatypes/. \
		$(1)/usr/lib/qt6/metatypes/
	[ ! -x $(PKG_INSTALL_DIR)/usr/lib/qt6/libexec/qtwaylandscanner ] || \
		$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/qt6/libexec/qtwaylandscanner \
			$(1)/usr/lib/qt6/libexec/
endef

$(eval $(call BuildPackage,qt6waylandclient))
$(eval $(call BuildPackage,qt6waylandclient-dev))
$(eval $(call HostBuild))
