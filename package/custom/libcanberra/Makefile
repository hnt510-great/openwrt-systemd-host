include $(TOPDIR)/rules.mk

PKG_NAME:=libcanberra
PKG_VERSION:=0.30
PKG_RELEASE:=1
PKG_SOURCE:=libcanberra-0.30.tar.xz
PKG_SOURCE_URL:=https://0pointer.de/lennart/projects/libcanberra/
PKG_HASH:=c2b671e67e0c288a69fc33dc1b6f1b534d07882c2aceed37004bf48c601afa72
PKG_BUILD_DIR:=$(BUILD_DIR)/libcanberra-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/libcanberra
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libcanberra GNOME platform dependency
  DEPENDS:=+glib2 +libvorbis +libltdl +libpulse
endef

CONFIGURE_ARGS += --disable-gtk --disable-gtk3 --disable-gstreamer --disable-alsa --disable-oss --enable-pulse --disable-udev --disable-gtk-doc --disable-lynx --with-builtin=dso

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libcanberra/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/libcanberra-$(PKG_VERSION) ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/libcanberra-$(PKG_VERSION) $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libcanberra))
