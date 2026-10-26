include $(TOPDIR)/rules.mk

PKG_NAME:=fcitx5-gtk
PKG_VERSION:=5.1.7
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.zst
PKG_SOURCE_URL:=https://download.fcitx-im.org/fcitx5/fcitx5-gtk/
PKG_HASH:=bda5aae72886d0f046e896c48461ffa257ecaa6045e17827ffe27f1530172c42
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules
include $(INCLUDE_DIR)/package.mk

include $(INCLUDE_DIR)/cmake.mk

define Package/fcitx5-gtk
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Fcitx5 GTK3 input module for Firefox and GTK applications
  DEPENDS:=+fcitx5 +libgtk3 +libxkbcommon +libX11
endef
CMAKE_OPTIONS += -DCMAKE_INSTALL_LIBDIR=lib -DECM_DIR=$(STAGING_DIR)/usr/share/ECM/cmake \
	-DENABLE_GTK2_IM_MODULE=OFF -DENABLE_GTK3_IM_MODULE=ON \
	-DENABLE_GTK4_IM_MODULE=OFF -DENABLE_GIR=OFF -DBUILD_ONLY_PLUGIN=ON

define Package/fcitx5-gtk/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/gtk-3.0 $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/share/fcitx5-gtk
	$(INSTALL_DATA) ./files/immodules.cache $(1)/usr/share/fcitx5-gtk/
endef

$(eval $(call BuildPackage,fcitx5-gtk))
