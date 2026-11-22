include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kwindowsystem
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kwindowsystem-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=836be005df3c8cfc81d9ca199f19e36ba0df515d69e7d8b06343465412f6f477
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Window System
KF6_DEPENDS:=+qt6base-gui +libX11 +libXfixes +libxcb +libxcb-keysyms \
	+libxcb-render-util +libxcb-wm +qt6waylandclient
# Both backends are built: native Wayland for the GNOME session and X11 for
# applications started through XWayland.
KF6_CMAKE_OPTIONS:=-DKWINDOWSYSTEM_QML=OFF -DKWINDOWSYSTEM_WAYLAND=ON \
	-DKWINDOWSYSTEM_X11=ON
PKG_BUILD_DEPENDS:=qt6wayland wayland wayland-protocols \
	plasma-wayland-protocols

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
