include $(TOPDIR)/rules.mk

PKG_NAME:=glibc-gconv
# Keep the integration revision independent of libc's runtime release and
# previously allocated ELF metadata rebuild identities.
GLIBC_GCONV_RELEASE:=1

ifeq ($(DUMP),1)
  GLIBC_VERSION:=<LIBC_VERSION>
  GLIBC_RUNTIME_VERSION:=<LIBC_VERSION>-r<LIBC_RELEASE>
  GLIBC_RUNTIME_RELEASE:=<LIBC_RELEASE>
else
  GLIBC_VERSION:=$(LIBC_VERSION)
  GLIBC_RUNTIME_VERSION:=$(strip $(shell cat $(STAGING_DIR)/libc.version 2>/dev/null))
  ifeq ($(GLIBC_RUNTIME_VERSION),)
    $(error Missing $(STAGING_DIR)/libc.version; build the target libc package first)
  endif
  GLIBC_RUNTIME_RELEASE:=$(patsubst $(GLIBC_VERSION)-r%,%,$(GLIBC_RUNTIME_VERSION))
  ifeq ($(GLIBC_RUNTIME_RELEASE),$(GLIBC_RUNTIME_VERSION))
    $(error Unexpected target libc version: $(GLIBC_RUNTIME_VERSION))
  endif
endif

PKG_VERSION:=$(GLIBC_VERSION)_p$(GLIBC_GCONV_RELEASE)
PKG_RELEASE:=$(GLIBC_RUNTIME_RELEASE)
PKG_LICENSE:=LGPL-2.1-or-later

include $(INCLUDE_DIR)/package.mk

ifeq ($(DUMP),)
  GLIBC_GCONV_BUILD_ID:=$(shell cat $(TOOLCHAIN_DIR)/lib/gconv/gconv-modules $(TOOLCHAIN_DIR)/lib/gconv/gconv-modules.d/*.conf $(TOOLCHAIN_DIR)/lib/gconv/*.so | $(MKHASH) md5)
  STAMP_BUILT:=$(STAMP_BUILT)_$(GLIBC_GCONV_BUILD_ID)
endif

define Package/glibc-gconv
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=glibc character conversion modules
  URL:=https://www.gnu.org/software/libc/
  DEPENDS:=@USE_GLIBC @!EXTERNAL_TOOLCHAIN +libc
  EXTRA_DEPENDS:=libc (=$(GLIBC_RUNTIME_VERSION))
endef

define Package/glibc-gconv/description
  Loadable character converters and their registry from the exact target libc
  build. Required for legacy Chinese and other non-UTF character encodings.
endef

define Build/Compile
endef

define Package/glibc-gconv/install
	$(INSTALL_DIR) $(1)/lib/gconv
	$(CP) $(TOOLCHAIN_DIR)/lib/gconv/. $(1)/lib/gconv/
endef

$(eval $(call BuildPackage,glibc-gconv))
