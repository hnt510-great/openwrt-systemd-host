include $(TOPDIR)/rules.mk

include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=kernel-dev-headers
PKG_VERSION:=$(LINUX_VERSION)
PKG_RELEASE:=$(LINUX_RELEASE)

PKG_LICENSE:=GPL-2.0-only
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk

ifeq ($(DUMP),)
  KERNEL_DEV_BUILD_ID:=$(shell cat $(LINUX_DIR)/.vermagic \
	$(LINUX_DIR)/Module.symvers 2>/dev/null | $(MKHASH) md5)
  STAMP_BUILT:=$(STAMP_BUILT)_$(KERNEL_DEV_BUILD_ID)
endif

# Keep this aligned with the prepared kernel tree exported by target/sdk.
KERNEL_DEV_ARCH_FILES:= \
	Makefile* \
	module.lds \
	Kbuild.platforms \
	*/Platform \
	include \
	*/include \
	scripts \
	kernel/asm-offsets.s \
	kernel/module.lds

KERNEL_DEV_BASE_FILES:= \
	.config \
	Makefile \
	scripts \
	tools/objtool \
	include \
	Module.symvers \
	modules.builtin \
	$(addprefix arch/$(LINUX_KARCH)/,$(KERNEL_DEV_ARCH_FILES))

KERNEL_DEV_FILES:=$(patsubst $(LINUX_DIR)/%,%,$(wildcard $(addprefix $(LINUX_DIR)/,$(KERNEL_DEV_BASE_FILES))))
KERNEL_HEADERS_DIR:=linux-headers-$(LINUX_UNAME_VERSION)
KERNEL_DEV_VERSION:=$(subst -rc,_rc,$(LINUX_VERSION))~$(LINUX_VERMAGIC)-r$(LINUX_RELEASE)

define Package/kernel-dev-headers
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Prepared Linux kernel headers for native module builds
  VERSION:=$(if $(CONFIG_OPENWRT_KERNEL_UPGRADE),1000.$(CONFIG_OPENWRT_KERNEL_SEQUENCE).)$(KERNEL_DEV_VERSION)
  EXTRA_DEPENDS:=kernel (=$(KERNEL_DEV_VERSION))
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @!EXTERNAL_TOOLCHAIN \
	+gcc +make +binutils
  PKGARCH:=x86_64
endef

define Package/kernel-dev-headers/description
  Installs the configured kernel headers, generated headers, Kbuild scripts,
  Module.symvers, and native helper programs required to build external kernel
  modules on this x86_64 target. It also provides conventional Linux header
  paths used by distro-oriented build systems.
endef

define Build/Compile
endef

define Package/kernel-dev-headers/install
	$(INSTALL_DIR) $(1)/usr/src/$(KERNEL_HEADERS_DIR)
	$(TAR) -cf - -C $(LINUX_DIR) $(KERNEL_DEV_FILES) | \
		$(TAR) -xf - -C $(1)/usr/src/$(KERNEL_HEADERS_DIR)
	# The SDK file set intentionally omits foreign architecture DTS trees.
	find $(1)/usr/src/$(KERNEL_HEADERS_DIR)/scripts/dtc/include-prefixes \
		-type l -delete

	$(INSTALL_DIR) $(1)/lib/modules/$(LINUX_UNAME_VERSION)
	$(LN) $(KERNEL_HEADERS_DIR) $(1)/usr/src/linux
	$(LN) ../../../usr/src/$(KERNEL_HEADERS_DIR) \
		$(1)/lib/modules/$(LINUX_UNAME_VERSION)/build
	$(LN) ../../../usr/src/$(KERNEL_HEADERS_DIR) \
		$(1)/lib/modules/$(LINUX_UNAME_VERSION)/source

	# Debian-style multiarch header locations without duplicating the headers.
	$(INSTALL_DIR) \
		$(1)/usr/include/x86_64-linux-gnu \
		$(1)/usr/include/x86_64-openwrt-linux-gnu
	for header in a.out.h asm bits fpu_control.h gnu ieee754.h sys; do \
		$(LN) ../$$$$header $(1)/usr/include/x86_64-linux-gnu/$$$$header; \
		$(LN) ../$$$$header $(1)/usr/include/x86_64-openwrt-linux-gnu/$$$$header; \
	done
endef

$(eval $(call BuildPackage,kernel-dev-headers))
