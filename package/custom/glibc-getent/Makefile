include $(TOPDIR)/rules.mk

PKG_NAME:=glibc-getent
# Keep the integration revision independent of libc's runtime release and
# previously allocated ELF metadata rebuild identities.
GLIBC_GETENT_RELEASE:=3

ifeq ($(DUMP),1)
  GLIBC_VERSION:=<LIBC_VERSION>
  GLIBC_RUNTIME_VERSION:=<LIBC_VERSION>-r<LIBC_RELEASE>
  GLIBC_RUNTIME_RELEASE:=<LIBC_RELEASE>
else
  GLIBC_VERSION:=$(LIBC_VERSION)
  GLIBC_RUNTIME_VERSION:=$(strip $(shell cat $(STAGING_DIR)/libc.version 2>/dev/null))
  # Source-only goals (download, clean, ...) must work before libc is built.
  ifeq ($(GLIBC_RUNTIME_VERSION),)
    ifneq ($(filter download clean dirclean prereq check refresh,$(MAKECMDGOALS)),)
      GLIBC_RUNTIME_VERSION:=$(GLIBC_VERSION)-r0
    else
      $(error Missing $(STAGING_DIR)/libc.version; build the target libc package first)
    endif
  endif
  GLIBC_RUNTIME_RELEASE:=$(patsubst $(GLIBC_VERSION)-r%,%,$(GLIBC_RUNTIME_VERSION))
  ifeq ($(GLIBC_RUNTIME_RELEASE),$(GLIBC_RUNTIME_VERSION))
    $(error Unexpected target libc version: $(GLIBC_RUNTIME_VERSION))
  endif
endif

PKG_VERSION:=$(GLIBC_VERSION)_p$(GLIBC_GETENT_RELEASE)
PKG_RELEASE:=$(GLIBC_RUNTIME_RELEASE)
PKG_LICENSE:=LGPL-2.1-or-later

include $(INCLUDE_DIR)/package.mk

ifeq ($(DUMP),)
  GLIBC_GETENT_BUILD_ID:=$(shell $(MKHASH) md5 $(TOOLCHAIN_DIR)/bin/getent)
  STAMP_BUILT:=$(STAMP_BUILT)_$(GLIBC_GETENT_BUILD_ID)
endif

define Package/glibc-getent
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=glibc name service database query utility
  URL:=https://www.gnu.org/software/libc/
  DEPENDS:=@USE_GLIBC @!EXTERNAL_TOOLCHAIN +libc
  EXTRA_DEPENDS:=libc (=$(GLIBC_RUNTIME_VERSION))
endef

define Package/glibc-getent/description
  Installs the target glibc getent utility for NSS-aware account, group and
  other system database lookups, using the matching target libc runtime.
endef

define Build/Compile
endef

define Package/glibc-getent/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(TOOLCHAIN_DIR)/bin/getent $(1)/usr/bin/getent
endef

$(eval $(call BuildPackage,glibc-getent))
