# SPDX-License-Identifier: GPL-2.0-only
# Deliberately empty logical packages still need an ABI-pinned generation payload.
# Keep the conditional default symbolic: metadata scanning does not load .config.
define KernelCompatibility
  ifdef KernelPackage/$(1)
    $$(error Compatibility package kmod-$(1) already has an upstream recipe)
  endif
  ifeq ($$(CONFIG_OPENWRT_KERNEL_UPGRADE),y)
    # Existing .config files may not have been normalized since the rule was
    # added. Build the channel APK without changing their image selections.
    CONFIG_PACKAGE_kmod-$(1) ?= m
  endif
  define KernelPackage/$(1)
    SUBMENU:=Kernel compatibility
    TITLE:=Kernel compatibility for kmod-$(1)
    HIDDEN:=1
    DEFAULT:=y if OPENWRT_KERNEL_UPGRADE
    DEPENDS:=$(addprefix +,$(2))
  endef

  define KernelPackage/$(1)/description
 Compatibility package for kmod-$(1); functionality is supplied by $(2).
  endef

  $$(eval $$(call KernelPackage,$(1)))
endef

kernel_compat_recipes := $(shell python3 $(SCRIPT_DIR)/apk-migrations.py --make $(TOPDIR)/configs/apk-migrations.json)
ifneq ($(.SHELLSTATUS),0)
  $(error Invalid APK migration rules)
endif
$(eval $(kernel_compat_recipes))
