# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

PKG_NAME:=cockpit-runtime-deps
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/cockpit-runtime-deps
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Runtime dependencies for a source-installed native Cockpit
  DEPENDS:=@OPENWRT_SYSTEMD @USE_GLIBC +systemd +glib2 +json-glib \
	+libgnutls +krb5-libs +libpam +libcrypt-compat +python3 +ca-bundle
endef

define Package/cockpit-runtime-deps/description
  Keeps the system runtime libraries and Python dependencies of the local
  native Cockpit build installed through APK. Does not install Cockpit itself,
  adopt /usr/local files, configure PAM, or enable services.
endef

define Build/Compile
endef

define Package/cockpit-runtime-deps/install
	:
endef

$(eval $(call BuildPackage,cockpit-runtime-deps))
