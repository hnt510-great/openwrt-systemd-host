include $(TOPDIR)/rules.mk

PKG_NAME:=systemsettings
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=0b4f536509aa030bac53230a625320ec56ea7bb418c27e4a093399cfbf8ce9e6
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KDE System Settings
KF6_DEPENDS:=+qt6base-widgets +qt6quick +qt6quick-widgets +kf6-kauth +kf6-kcrash +kf6-kitemviews +kf6-kitemmodels +kf6-kcmutils +kf6-ki18n +kf6-kio +kf6-kservice +kf6-kiconthemes +kf6-kwidgetsaddons +kf6-kwindowsystem +kf6-kxmlgui +kf6-kdbusaddons +kf6-kconfig +kf6-kguiaddons +kf6-kirigami +kf6-kjobwidgets +kf6-krunner +kf6-kcolorscheme +plasma-activities
PKG_BUILD_DEPENDS:=kf6-kconfig/host
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
