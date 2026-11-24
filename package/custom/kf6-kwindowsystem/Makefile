include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kwindowsystem
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kwindowsystem-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=43a32eb940c740f5acc917ce24c4939ba08b9e08c26091dbb5577ad0ef74f3a0
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Window System
KF6_DEPENDS:=+qt6base-gui +qt6quick-qml +libX11 +libXfixes +libxcb +libxcb-keysyms \
	+libxcb-render-util +libxcb-wm +qt6waylandclient
# Both backends are built: native Wayland for desktop sessions and X11 for
# applications started through XWayland.
KF6_CMAKE_OPTIONS:=-DKWINDOWSYSTEM_QML=ON -DKWINDOWSYSTEM_WAYLAND=ON \
	-DKWINDOWSYSTEM_X11=ON
PKG_BUILD_DEPENDS:=qt6base wayland wayland-protocols \
	plasma-wayland-protocols

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
