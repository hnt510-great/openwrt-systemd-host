include $(TOPDIR)/rules.mk

PKG_NAME:=node-bin
# Updated by package/custom/scripts/update-prebuilt-packages.sh.
PKG_VERSION:=24.20.0
PKG_RELEASE:=1

PKG_SOURCE:=node-v$(PKG_VERSION)-linux-x64.tar.xz
PKG_SOURCE_URL:=https://nodejs.org/dist/v$(PKG_VERSION)/
PKG_HASH:=2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2

PKG_BUILD_DIR:=$(BUILD_DIR)/node-v$(PKG_VERSION)-linux-x64

include $(INCLUDE_DIR)/package.mk

define Package/node-bin
  SECTION:=lang
  CATEGORY:=Languages
  TITLE:=Node.js pre-compiled binary (glibc x64)
  URL:=https://nodejs.org/
  DEPENDS:=@x86_64 +libstdcpp +libpthread
endef

define Package/node-bin/description
  Official pre-compiled Node.js binaries downloaded directly from nodejs.org.
  Requires an x86_64 target utilizing glibc.
endef

define Build/Compile
	# Skip compilation, using pre-built binaries
endef

define Package/node-bin/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_DIR) $(1)/usr/lib

	# 1. Install the core Node binary with correct executable permissions
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/bin/node $(1)/usr/bin/

	# 2. Copy the entire node_modules directory
	$(CP) $(PKG_BUILD_DIR)/lib/node_modules $(1)/usr/lib/

	# 3. Safely recreate the relative symlinks for NPM and NPX
	ln -sf ../lib/node_modules/npm/bin/npm-cli.js $(1)/usr/bin/npm
	ln -sf ../lib/node_modules/npm/bin/npx-cli.js $(1)/usr/bin/npx
	ln -sf ../lib/node_modules/corepack/dist/corepack.js $(1)/usr/bin/corepack
endef

$(eval $(call BuildPackage,node-bin))
