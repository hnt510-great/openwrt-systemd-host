include $(TOPDIR)/rules.mk

PKG_NAME:=appstream
PKG_VERSION:=1.2.1
PKG_RELEASE:=1
PKG_SOURCE:=appstream-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/ximion/appstream/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=2bc53d1d63ae28e7409a15747d4ae23a557409249461aab87a7947640402d1bd
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/appstream
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=appstream for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +libcurl +libxml2 +libfyaml +libxmlb +libzstd +libsystemd
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dstemming=false -Dgir=false -Dqt=false \
	-Dcompose=false -Dtools=false -Ddocs=false -Dapidocs=false -Dman=false -Dinstall-docs=false \
	-Dbash-completion=false -Ddisplay-detection=none -Dblake3-support=false


define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/appstream/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/share/appstream
	$(CP) $(PKG_INSTALL_DIR)/usr/share/appstream/. $(1)/usr/share/appstream/
endef

$(eval $(call BuildPackage,appstream))
