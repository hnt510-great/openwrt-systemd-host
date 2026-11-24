include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-krunner
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=krunner-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=5f9729b5f160fdf17c676b8dd1c5edad861576d4793c1a20cd0cb23ff9d2052b
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KRunner
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n +kf6-kitemmodels +kf6-kwindowsystem

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
