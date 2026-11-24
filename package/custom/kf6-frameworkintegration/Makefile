include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-frameworkintegration
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=frameworkintegration-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=874e13434e808cb0b2081af0f993e09236d0c3e44a6ae37d4fe724ee7547a912
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Framework Integration
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +kf6-kcolorscheme +kf6-kconfig +kf6-kconfigwidgets +kf6-ki18n +kf6-kiconthemes +kf6-knewstuff +kf6-knotifications +kf6-kpackage +kf6-kwidgetsaddons
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_AppStreamQt=ON -DCMAKE_DISABLE_FIND_PACKAGE_packagekitqt6=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
