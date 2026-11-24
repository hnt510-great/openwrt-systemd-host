include $(TOPDIR)/rules.mk

PKG_NAME:=kirigami-addons
PKG_VERSION:=1.16.1
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/kirigami-addons/
PKG_HASH:=124b01267acf603c3afd9fb9599a33fee7a28d65756890163e9593a3932084dd
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Kirigami Addons
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +qt6quick +qt6quick-controls2 +qt6svg \
	+kf6-kconfig +kf6-kcoreaddons +kf6-kcrash +kf6-kglobalaccel +kf6-kguiaddons +kf6-ki18n \
	+kf6-kiconthemes +kf6-kirigami
PKG_BUILD_DEPENDS:=qt6shadertools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
