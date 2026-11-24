include $(TOPDIR)/rules.mk

PKG_NAME:=plasma5support
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=e97329a0b0d200df15ec30cbf14c8572c72869eef65629a96e8cb3706361d105
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma5Support
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6quick +qt6base-sql +qt6base-widgets +kf6-kconfig +kf6-kcoreaddons +kf6-kguiaddons +kf6-ki18n +kf6-knotifications +kf6-solid +kf6-kservice +kf6-kidletime +kf6-kio +kf6-kunitconversion +kf6-kholidays +libksysguard +plasma-activities

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
