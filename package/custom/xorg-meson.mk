# Target-only staging and installation for X.Org libraries built with Meson.
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_FILE_DEPENDS+=$(CURDIR)/../xorg-meson.mk
PKG_BUILD_DEPENDS+=xorgproto
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/$(PKG_NAME)
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=X.Org client libraries
  TITLE:=$(PKG_NAME) X.Org library
  URL:=https://www.x.org/
  DEPENDS:=$(XORG_DEPENDS)
endef

MESON_ARGS += --wrap-mode=nofallback

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/$(PKG_NAME)/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
endef
