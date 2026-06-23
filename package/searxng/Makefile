include $(TOPDIR)/rules.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-version.mk

PKG_NAME:=searxng
PKG_VERSION:=2024.01.01
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/searxng/searxng.git
PKG_SOURCE_VERSION:=HEAD
PKG_MIRROR_HASH:=skip

include $(INCLUDE_DIR)/package.mk

define Package/searxng
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=SearXNG, a privacy-respecting, hackable metasearch engine
  URL:=https://searxng.org/
  DEPENDS:=+python3 +python3-yaml +python3-msgspec +python3-typing-extensions \
           +uwsgi +uwsgi-python3-plugin +nginx \
           +python3-babel +python3-dateutil +python3-jinja2 \
           +python3-urllib3 +python3-lxml
endef

define Package/searxng/description
  SearXNG is a free internet metasearch engine which aggregates results from various search services and databases. Users are neither tracked nor profiled.
endef

define Build/Compile
	# SearXNG is primarily Python scripts and resources, no C-extension compilation needed.
endef

define Package/searxng/install
	$(INSTALL_DIR) $(1)/usr/lib/python$(PYTHON3_VERSION)/site-packages/searx
	$(CP) $(PKG_BUILD_DIR)/searx/* $(1)/usr/lib/python$(PYTHON3_VERSION)/site-packages/searx/
	
	$(INSTALL_DIR) $(1)/etc/searxng
	$(CP) $(PKG_BUILD_DIR)/utils/templates/etc/searxng/settings.yml $(1)/etc/searxng/ 2>/dev/null || \
	$(CP) $(PKG_BUILD_DIR)/searx/settings.yml $(1)/etc/searxng/ 2>/dev/null || true
	
	sed -e 's|@PYTHON3_VERSION@|$(PYTHON3_VERSION)|g' ./files/searxng.uwsgi.ini > $(1)/etc/searxng/uwsgi.ini
	
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/searxng.init $(1)/etc/init.d/searxng
endef

$(eval $(call BuildPackage,searxng))
