include $(TOPDIR)/rules.mk

PKG_NAME:=polkit-kde-agent-1
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=59abbe4c339966f5961daf0f7151b29b67d749c4f7e78e821af287ea96cab4b3
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Polkit KDE Agent
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +qt6base-widgets +qt6quick +kf6-ki18n +kf6-kwindowsystem +kf6-knotifications +kf6-kdbusaddons +kf6-kcoreaddons +kf6-kcrash +kf6-kirigami +polkit-qt6

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
