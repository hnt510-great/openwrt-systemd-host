include $(TOPDIR)/rules.mk

PKG_NAME:=wireplumber
PKG_VERSION:=0.5.18
PKG_RELEASE:=4
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/PipeWire/wireplumber/tar.gz/refs/tags/$(PKG_VERSION)?
PKG_HASH:=8c8a326a5b2a570681c1503c83f1fce0cc54ba862019815604b2bc92a7d483a1
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/wireplumber
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=PipeWire session and audio policy manager
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +pipewire +glib2 +glib2-gio +liblua5.4 +libsystemd
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --wrap-mode=nodownload \
	-Ddefault_library=shared -Dintrospection=disabled -Ddoc=disabled \
	-Dtests=false -Ddbus-tests=false -Dsystem-lua=true -Dsystem-lua-version=5.4 \
	-Dsystemd=enabled -Dsystemd-system-service=false -Dsystemd-user-service=true \
	-Dsystemd-user-unit-dir=/usr/lib/systemd/user

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/wireplumber-0.5 $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libwireplumber-0.5.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/wireplumber/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib $(1)/usr/share $(1)/usr/lib/systemd/user
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/wireplumber $(PKG_INSTALL_DIR)/usr/bin/wpctl $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libwireplumber-0.5.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/wireplumber-0.5 $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/wireplumber $(1)/usr/share/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/user/wireplumber.service $(1)/usr/lib/systemd/user/
endef

$(eval $(call BuildPackage,wireplumber))
