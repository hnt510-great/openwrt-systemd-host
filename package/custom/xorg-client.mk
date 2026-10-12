# Shared target-only staging and runtime installation for X.Org client libraries.
# Host generators and target headers are supplied by separate build dependencies.
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_FIXUP:=autoreconf
PKG_FILE_DEPENDS+=$(CURDIR)/../xorg-client.mk
PKG_BUILD_DEPENDS+=util-macros/host xorgproto
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk

define Package/$(PKG_NAME)
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=X.Org client libraries
  TITLE:=$(PKG_NAME) X.Org client library
  URL:=https://www.x.org/
  DEPENDS:=$(XORG_DEPENDS)
endef

CONFIGURE_ARGS += --disable-static --disable-specs --disable-docs --disable-devel-docs --without-xmlto --without-fop --without-xsltproc

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/$(PKG_NAME)/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
endef
