include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kguiaddons
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kguiaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=33caf5ae46f1a6214f56596180e0c6ccb4af2cce0dcae060ae4fb7078260a476
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Gui Addons
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +libX11 +libxcb
KF6_CMAKE_OPTIONS:=-DWITH_WAYLAND=OFF -DWITH_X11=ON -DUSE_DBUS=ON -DBUILD_GEO_SCHEME_HANDLER=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
