include $(TOPDIR)/rules.mk

PKG_NAME:=libstartup-notification
PKG_VERSION:=0.12
PKG_RELEASE:=1
PKG_SOURCE:=startup-notification-0.12.tar.gz
PKG_SOURCE_URL:=https://www.freedesktop.org/software/startup-notification/releases/
PKG_HASH:=3c391f7e930c583095045cd2d10eb73a64f085c7fde9d260f2652c7cb3cfbe4a
PKG_BUILD_DIR:=$(BUILD_DIR)/startup-notification-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/libstartup-notification
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libstartup-notification GNOME platform dependency
  DEPENDS:=+libX11 +libxcb +libxcb-util +libXext
endef

CONFIGURE_VARS += lf_cv_sane_realloc=yes

CONFIGURE_ARGS += --disable-static

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libstartup-notification/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/startup-notification-$(PKG_VERSION) ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/startup-notification-$(PKG_VERSION) $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libstartup-notification))
