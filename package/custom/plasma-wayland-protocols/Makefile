include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-wayland-protocols
PKG_VERSION:=1.23.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma-wayland-protocols/
PKG_HASH:=16c5ad917bde2ed795942dacba76654819ddc6a1566842325ef34e0b553ef138
PKG_LICENSE:=BSD-3-Clause
PKG_INSTALL:=1
CMAKE_INSTALL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DECM_DIR="$(STAGING_DIR)/usr/share/ECM/cmake" \
	-DKDE_INSTALL_USE_QT_SYS_PATHS=OFF \
	-DKDE_INSTALL_LIBDIR=lib \
	-DBUILD_TESTING=OFF

define Package/plasma-wayland-protocols
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Plasma Wayland protocol XML files
  URL:=https://invent.kde.org/libraries/plasma-wayland-protocols
  BUILDONLY:=1
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
