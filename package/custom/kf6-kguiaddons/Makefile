include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kguiaddons
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kguiaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=ea1bf879d181e498d1786451234a0e58827f35cfb4c667661412cd551741e81a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Gui Addons
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +qt6quick-qml +qt6waylandclient +libwayland +libX11 +libxcb
PKG_BUILD_DEPENDS:=wayland wayland-protocols plasma-wayland-protocols
KF6_CMAKE_OPTIONS:=-DWITH_WAYLAND=ON -DWITH_X11=ON -DUSE_DBUS=ON -DBUILD_GEO_SCHEME_HANDLER=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
