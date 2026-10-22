include $(TOPDIR)/rules.mk

PKG_NAME:=passt
PKG_VERSION:=2026.10.02
PKG_RELEASE:=1
PKG_SOURCE_VERSION:=2026_10_02.cba3570

PKG_SOURCE:=$(PKG_NAME)-$(PKG_SOURCE_VERSION).tar.xz
PKG_SOURCE_URL:=https://passt.top/passt/snapshot/
PKG_HASH:=aa75616cc43925f0bd6c05bcfbbaecd77397c03d7bd23591b34ef535be5dfcdc
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_SOURCE_VERSION)
PKG_LICENSE:=GPL-2.0-or-later BSD-3-Clause
PKG_LICENSE_FILES:=LICENSES/GPL-2.0-or-later.txt LICENSES/BSD-3-Clause.txt
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/passt
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Unprivileged socket networking for containers and VMs
  DEPENDS:=@x86_64
  URL:=https://passt.top/
endef

# The x86_64 target uses 4 KiB pages; do not query a host getconf while
# cross-compiling. OpenWrt supplies its own fortification flags.
MAKE_FLAGS += VERSION=$(PKG_SOURCE_VERSION) PAGE_SIZE=4096 FORTIFY_FLAG=

define Build/Compile
	$(call Build/Compile/Default,passt $(if $(CONFIG_x86_64),passt.avx2))
endef

define Package/passt/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/passt $(1)/usr/bin/
	$(LN) passt $(1)/usr/bin/pasta
ifeq ($(CONFIG_x86_64),y)
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/passt.avx2 $(1)/usr/bin/
	$(LN) passt.avx2 $(1)/usr/bin/pasta.avx2
endif
endef

$(eval $(call BuildPackage,passt))
