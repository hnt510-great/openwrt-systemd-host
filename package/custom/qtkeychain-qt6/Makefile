include $(TOPDIR)/rules.mk

PKG_NAME:=qtkeychain-qt6
PKG_VERSION:=0.18.0
PKG_RELEASE:=1
PKG_SOURCE:=qtkeychain-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://github.com/frankosterfeld/qtkeychain/archive/refs/tags/$(PKG_VERSION)/
PKG_BUILD_DIR:=$(BUILD_DIR)/qtkeychain-$(PKG_VERSION)
PKG_HASH:=837af59f2b950760a73eff81ccae817f7d3051183b447438dc610bb984a41691
PKG_LICENSE:=BSD-3-Clause
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
CMAKE_INSTALL:=1
PKG_BUILD_DEPENDS:=qt6base/host qt6base qt6tools libsecret

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DBUILD_WITH_QT6=ON \
	-DLIBSECRET_SUPPORT=ON \
	-DBUILD_TRANSLATIONS=OFF \
	-DBUILD_TEST_APPLICATION=OFF \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)"

define Package/qtkeychain-qt6
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=KDE Frameworks 6
  TITLE:=Qt6 API for storing passwords securely (Secret Service)
  URL:=https://github.com/frankosterfeld/qtkeychain
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +qt6base-core +qt6base-dbus +libsecret +glib2 +libstdcpp
endef

define Package/qtkeychain-qt6/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libqt6keychain.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,qtkeychain-qt6))
