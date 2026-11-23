include $(TOPDIR)/rules.mk

PKG_NAME:=distrobox
PKG_VERSION:=1.8.2.6
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/89luca89/distrobox/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=$(PKG_VERSION)
PKG_HASH:=693c85f44720f9c2be8691141eaa1dc2773ee37e63ae02fff8b838dcf54c413e

PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=COPYING.md

include $(INCLUDE_DIR)/package.mk

define Package/distrobox
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Integrated Linux distribution containers
  URL:=https://distrobox.it/
  PKGARCH:=all
  DEPENDS:=@USE_GLIBC +glibc-getent +openwrt-podman-rootless \
	+coreutils-id +coreutils-realpath +coreutils-readlink +coreutils-sort \
	+findutils-find +findutils-xargs +mount-utils +rev
endef

define Package/distrobox/description
  Run Linux distribution userlands using rootless Podman, sharing files,
  terminal commands and graphical applications with the OpenWrt host.
endef

define Build/Compile
endef

define Package/distrobox/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/share/man/man1
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/distrobox* $(1)/usr/bin/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/man/man1/* $(1)/usr/share/man/man1/
	$(INSTALL_DIR) $(1)/usr/share/bash-completion/completions
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/completions/bash/* $(1)/usr/share/bash-completion/completions/
	$(INSTALL_DIR) $(1)/usr/share/zsh/site-functions
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/completions/zsh/* $(1)/usr/share/zsh/site-functions/
	$(INSTALL_DIR) $(1)/usr/share/icons/hicolor/scalable/apps
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/icons/terminal-distrobox-icon.svg $(1)/usr/share/icons/hicolor/scalable/apps/
	$(CP) $(PKG_BUILD_DIR)/icons/hicolor/* $(1)/usr/share/icons/hicolor/
endef

$(eval $(call BuildPackage,distrobox))
