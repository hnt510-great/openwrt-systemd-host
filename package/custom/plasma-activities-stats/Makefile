include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-activities-stats
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=88681ff26460d3498b966aa3d16f4b9ba60e5571408af6341b46f6da35ec141f
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Activities Stats
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +qt6base-sql +kf6-kconfig +kf6-kcoreaddons +plasma-activities
PKG_BUILD_DEPENDS:=boost

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
