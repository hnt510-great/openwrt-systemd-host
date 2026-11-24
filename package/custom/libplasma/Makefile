include $(TOPDIR)/rules.mk

PKG_NAME:=libplasma
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=76f081f2d96c7dccf1f29fa0a301572d0115b0c5bec1b32ede0fea4a45c254c4
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=libplasma
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +qt6svg +qt6quick +qt6quick-controls2 +qt6waylandclient +libwayland +kf6-kconfig +kf6-kcoreaddons +kf6-kglobalaccel +kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kio +kf6-kwindowsystem +kf6-knotifications +kf6-kpackage +kf6-kirigami +kf6-ksvg +kf6-kcolorscheme +kf6-kdbusaddons +plasma-activities
PKG_BUILD_DEPENDS:=wayland wayland-protocols plasma-wayland-protocols qt6shadertools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
