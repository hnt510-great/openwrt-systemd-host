include $(TOPDIR)/rules.mk
PKG_NAME:=libosinfo
PKG_VERSION:=1.12.0
PKG_RELEASE:=1
PKG_SOURCE:=libosinfo-1.12.0.tar.xz
PKG_SOURCE_URL:=https://gitlab.com/libosinfo/libosinfo/-/releases/v1.12.0/downloads/
PKG_HASH:=ad8557ece26793da43d26de565e3d68ce2ee6bfb8d0113b7cc7dfe07f6bfc6b6
PKG_BUILD_DIR:=$(BUILD_DIR)/libosinfo-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/libosinfo
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libosinfo
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2-gir +libxml2 +libxslt +libsoup3
endef
MESON_ARGS += -Denable-introspection=enabled -Denable-vala=disabled -Denable-tests=false -Denable-gtk-doc=false -Dlibsoup-abi=3.0

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/libosinfo/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/share/libosinfo $(1)/usr/share/
endef

$(eval $(call BuildPackage,libosinfo))
