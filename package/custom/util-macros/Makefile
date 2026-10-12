include $(TOPDIR)/rules.mk

PKG_NAME:=util-macros
PKG_VERSION:=1.20.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/util/
PKG_HASH:=9ac269eba24f672d7d7b3574e4be5f333d13f04a7712303b1821b2a51ac82e8e

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_HOST_ONLY:=1
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk

define Package/util-macros
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=X.Org autoconf macros
  BUILDONLY:=1
endef

define Host/Compile
endef

define Host/Install
	$(MAKE) -C $(HOST_BUILD_DIR) install
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,util-macros))
