include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kidletime
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kidletime-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=a7b53ff5a5f80bf8b8869b377de11594c9e5bccf84064c96efd6bab16974c1be
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KIdleTime
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +qt6waylandclient +libwayland +libX11 +libxcb
PKG_BUILD_DEPENDS:=wayland wayland-protocols plasma-wayland-protocols
KF6_CMAKE_OPTIONS:=-DWITH_WAYLAND=ON -DWITH_X11=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
