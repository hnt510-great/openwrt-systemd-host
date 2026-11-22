include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kio
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kio-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=7e67d471fc10b7df3d76e6ce859480be5d6e675d316592e7a8419b97f01bd649
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KIO
KF6_DEPENDS:=+qt6base-widgets +qt6base-network +qt6base-concurrent +qt6base-xml \
	+qt6base-dbus +libacl +libmount +libX11 +kf6-karchive \
	+kf6-kbookmarks +kf6-kcolorscheme +kf6-kcompletion +kf6-kconfig \
	+kf6-kcoreaddons +kf6-kcrash +kf6-kdbusaddons +kf6-kguiaddons +kf6-ki18n \
	+kf6-kiconthemes +kf6-kitemviews +kf6-kjobwidgets +kf6-kservice +kf6-solid \
	+kf6-kwidgetsaddons +kf6-kwindowsystem
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON -DKIOCORE_ONLY=OFF -DKIOGUI_ONLY=OFF \
	-DBUILD_DESIGNERPLUGIN=OFF -DWITH_X11=ON -DWITH_WAYLAND=OFF
# Qt Test is required by KIO's configure step but not linked by the shipped
# libraries, so it stays a build-only dependency.
PKG_BUILD_DEPENDS:=qt6base

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
