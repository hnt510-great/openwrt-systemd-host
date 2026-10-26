include $(TOPDIR)/rules.mk

PKG_NAME:=antigravity-cli
PKG_VERSION:=1.4.7
PKG_RELEASE:=1

PKG_SOURCE:=agy_cli_linux_x64-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL_FILE:=agy_cli_linux_x64.tar.gz
PKG_SOURCE_URL:=https://github.com/google-antigravity/antigravity-cli/releases/download/$(PKG_VERSION)/
PKG_HASH:=8ee3ca32574c431285efbf4d4732f7f8d53e959370bc4a61646e4fa496f7f2b6

PKG_MAINTAINER:=Google Antigravity <https://github.com/google-antigravity>
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE

include $(INCLUDE_DIR)/package.mk

define Package/antigravity-cli
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Antigravity CLI - AI coding assistant for your terminal
  URL:=https://github.com/google-antigravity/antigravity-cli
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libpthread +librt
  PKGARCH:=x86_64
endef

define Package/antigravity-cli/description
  Antigravity CLI brings the reasoning, execution, and orchestration
  capabilities of the Antigravity agent harness directly into your terminal.
  It is optimized for keyboard-driven workflows and remote SSH sessions
  with minimal resource overhead. Features multi-step reasoning,
  multi-file editing, tool calling, and persistent history.
endef

# The tarball extracts to a directory; skip the default unpack and handle
# the prebuilt binary directly.
define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(TAR) -xzf $(DL_DIR)/$(PKG_SOURCE) -C $(PKG_BUILD_DIR) --strip-components=0
endef

define Build/Compile
endef

define Package/antigravity-cli/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/antigravity $(1)/usr/bin/antigravity
	$(LN) antigravity $(1)/usr/bin/agy
endef

$(eval $(call BuildPackage,antigravity-cli))
