include $(TOPDIR)/rules.mk

PKG_NAME:=libksysguard
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=a44aa32511a1ce842e8c6adac972f268d662d736650cff6c86360112c4dd2681
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=libksysguard
KF6_DEPENDS:=+qt6base-dbus +qt6base-network +qt6base-widgets +qt6quick +kf6-kcoreaddons +kf6-kconfig +kf6-ki18n +kf6-kauth +kf6-kservice +kf6-kpackage +kf6-knewstuff +kf6-solid +zlib +libnl +libpcap +libcap +libsensors +libdrm +libudev
PKG_BUILD_DEPENDS:=kf6-kconfig/host libcap lm-sensors libdrm
KF6_CMAKE_OPTIONS:=-DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake" \
	-DNL_INCLUDE_DIR="$(STAGING_DIR)/usr/include/libnl3" \
	-DNL_LIBRARY="$(STAGING_DIR)/usr/lib/libnl-3.so" \
	-DNLROUTE_LIBRARY="$(STAGING_DIR)/usr/lib/libnl-route-3.so" \
	-DNL_INCLUDE_DIRS="$(STAGING_DIR)/usr/include/libnl3" \
	-DNL_LIBRARIES="$(STAGING_DIR)/usr/lib/libnl-3.so;$(STAGING_DIR)/usr/lib/libnl-route-3.so"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
