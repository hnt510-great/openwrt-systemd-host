include $(TOPDIR)/rules.mk
PKG_NAME:=python3-libxml2
PKG_VERSION:=2.15.4
PKG_RELEASE:=1
PKG_SOURCE:=libxml2-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=@GNOME/libxml2/2.15
PKG_HASH:=98087fd181d9070724f3fbc65c7377db03038eb92bd882374daff44940138821
PKG_BUILD_DIR:=$(BUILD_DIR)/python-libxml2-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); xzcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) --strip-components=1 -C $(PKG_BUILD_DIR) -xf -
PKG_LICENSE:=MIT
PKG_BUILD_DEPENDS:=python3/host
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk
define Package/python3-libxml2
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=libxml2 legacy Python bindings
  DEPENDS:=+python3-light +libxml2
endef

define Build/Configure
endef

define Build/Compile
	$(CP) $(PKG_BUILD_DIR)/dist-doc/xml $(PKG_BUILD_DIR)/doc/
	cd $(PKG_BUILD_DIR)/python && $(HOST_PYTHON3_BIN) $(PKG_BUILD_DIR)/python/generator.py
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) $(FPIC) -shared \
		-I$(PYTHON3_INC_DIR) -I$(STAGING_DIR)/usr/include/libxml2 -I$(PKG_BUILD_DIR)/python \
		$(PKG_BUILD_DIR)/python/libxml2-py.c $(PKG_BUILD_DIR)/python/libxml.c $(PKG_BUILD_DIR)/python/types.c \
		-o $(PKG_BUILD_DIR)/libxml2mod.so $(TARGET_LDFLAGS) -lxml2 -lpython$(PYTHON3_VERSION)
endef

define Build/Install
endef

define Package/python3-libxml2/install
	$(INSTALL_DIR) $(1)/$(PYTHON3_PKG_DIR)
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/libxml2mod.so $(1)/$(PYTHON3_PKG_DIR)/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/python/libxml2.py $(PKG_BUILD_DIR)/python/drv_libxml2.py $(1)/$(PYTHON3_PKG_DIR)/
endef
$(eval $(call BuildPackage,python3-libxml2))
