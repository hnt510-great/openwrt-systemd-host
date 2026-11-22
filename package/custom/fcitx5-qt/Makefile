include $(TOPDIR)/rules.mk

PKG_NAME:=fcitx5-qt
PKG_VERSION:=5.1.16
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.zst
PKG_SOURCE_URL:=https://download.fcitx-im.org/fcitx5/fcitx5-qt/
PKG_HASH:=2d49cb4dfade430e822377beabae5f23da5caf2b2ff49e1eb54213b64dd0840e
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules fcitx5 qt6base qt6wayland \
	wayland wayland-protocols gettext-full/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk
include $(INCLUDE_DIR)/nls.mk

CMAKE_OPTIONS += \
	-DENABLE_QT4=OFF -DENABLE_QT5=OFF -DENABLE_QT6=ON \
	-DENABLE_X11=ON -DENABLE_QT6_WAYLAND_WORKAROUND=ON \
	-DBUILD_ONLY_PLUGIN=OFF -DBUILD_STATIC_PLUGIN=OFF \
	-DCMAKE_INSTALL_LIBDIR=lib \
	-DCMAKE_INSTALL_QT6PLUGINDIR=/usr/lib/qt6/plugins \
	-DECM_DIR="$(STAGING_DIR)/usr/share/ECM/cmake"

define Package/fcitx5-qt
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Fcitx5 Qt6 input method module
  URL:=https://github.com/fcitx/fcitx5-qt
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +fcitx5 +qt6base-core +qt6base-gui \
	+qt6base-widgets +qt6base-dbus +qt6waylandclient +libxkbcommon \
	+libX11 +libxcb +libstdcpp
endef

define Package/fcitx5-qt/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/qt6/plugins $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libFcitx5Qt6*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/qt6/plugins/. $(1)/usr/lib/qt6/plugins/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/fcitx5 ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/share/fcitx5 $(1)/usr/share/
endef

$(eval $(call BuildPackage,fcitx5-qt))
