include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ktexteditor
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=ktexteditor-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=13d906ecac31158eb68a6d6315a64948a3e79282d6c9316e82fc38c86640d084
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KTextEditor
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-printsupport +qt6base-xml +qt6quick-qml +kf6-karchive +kf6-kauth +kf6-kcodecs +kf6-kcolorscheme +kf6-kcompletion +kf6-kconfig +kf6-kconfigwidgets +kf6-kcoreaddons +kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kio +kf6-kparts +kf6-ktextwidgets +kf6-kwidgetsaddons +kf6-kxmlgui +kf6-sonnet +kf6-syntax-highlighting
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_EditorConfig=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
