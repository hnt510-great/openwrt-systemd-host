# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

PKG_NAME:=dwarves
PKG_VERSION:=1.31
PKG_RELEASE:=2

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://fedorapeople.org/~acme/dwarves/
PKG_HASH:=0a7f255ccacf8cc7f8cd119099eb327179b4b3c67cb015af646af6d0cb03054d

PKG_LICENSE:=GPL-2.0-only
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_PARALLEL:=1
PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/pahole
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=DWARF type inspection and BTF generation
  URL:=https://github.com/acmel/dwarves
  DEPENDS:=@USE_GLIBC +libdw +libelf +libbpf +zlib +binutils
endef

define Package/pahole/description
  Inspect structure layouts in DWARF debug information and encode BTF for
  kernel and eBPF builds. Uses the target libbpf and elfutils libraries.
endef

# Keep private dwarves libraries in the executable; runtime dependencies remain
# shared and owned by their existing packages. Never use host libraries.
CMAKE_OPTIONS += \
	-DBUILD_SHARED_LIBS=OFF \
	-DLIBBPF_EMBEDDED=OFF \
	-D__LIB=lib

define Package/pahole/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/pahole $(1)/usr/bin/
endef

$(eval $(call BuildPackage,pahole))
