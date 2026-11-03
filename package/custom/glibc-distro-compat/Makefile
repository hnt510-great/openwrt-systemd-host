include $(TOPDIR)/rules.mk

PKG_NAME:=glibc-distro-compat
# Keep the package revision independent of libc's runtime release. The p1/r6
# identity was already allocated by the ELF metadata migration.
GLIBC_COMPAT_RELEASE:=3

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

PKG_VERSION:=$(GLIBC_VERSION)_p$(GLIBC_COMPAT_RELEASE)
PKG_RELEASE:=$(GLIBC_RUNTIME_RELEASE)

PKG_LICENSE:=LGPL-2.1-or-later

include $(INCLUDE_DIR)/package.mk

GLIBC_EXTRA_RUNTIME_LIBS:= \
	libBrokenLocale.so.1 \
	libc_malloc_debug.so.0 \
	libmemusage.so \
	libmvec.so.1 \
	libnss_compat.so.2 \
	libnss_db.so.2 \
	libnss_hesiod.so.2 \
	libpcprofile.so

GLIBC_COMPAT_SOURCE_FILES:= \
	$(addprefix $(TOOLCHAIN_DIR)/lib/,$(GLIBC_EXTRA_RUNTIME_LIBS)) \
	$(TOOLCHAIN_DIR)/lib/libc_nonshared.a \
	$(TOOLCHAIN_DIR)/lib/libc.so \
	$(TOOLCHAIN_DIR)/lib/libm.so

ifeq ($(DUMP),)
  GLIBC_COMPAT_BUILD_ID:=$(shell cat $(GLIBC_COMPAT_SOURCE_FILES) 2>/dev/null | $(MKHASH) md5)
  STAMP_BUILT:=$(STAMP_BUILT)_$(GLIBC_COMPAT_BUILD_ID)
endif

define Package/glibc-distro-compat
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Common x86_64 glibc libraries and path compatibility
  EXTRA_DEPENDS:=libc (=$(GLIBC_RUNTIME_VERSION))
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @!EXTERNAL_TOOLCHAIN \
	+libc +libgcc +libatomic +libstdcpp +libpthread +librt \
	+libthread-db +libcrypt-compat
  PKGARCH:=x86_64
endef

define Package/glibc-distro-compat/description
  Installs additional glibc runtime modules, development linker names, and
  Debian-style multiarch library paths commonly expected by generic x86_64
  Linux binaries and native build systems.
endef

define Build/Compile
endef

define Package/glibc-distro-compat/install
	$(INSTALL_DIR) $(1)/lib $(1)/usr/lib
	for library in $(GLIBC_EXTRA_RUNTIME_LIBS); do \
		$(CP) $(TOOLCHAIN_DIR)/lib/$$$$library $(1)/lib/; \
	done

	# glibc linker scripts need the non-shared support archive at this path.
	$(INSTALL_DATA) $(TOOLCHAIN_DIR)/lib/libc_nonshared.a $(1)/lib/
	$(INSTALL_DATA) $(TOOLCHAIN_DIR)/lib/libc.so $(1)/usr/lib/
	$(INSTALL_DATA) $(TOOLCHAIN_DIR)/lib/libm.so $(1)/usr/lib/

	# Debian/Ubuntu multiarch paths; /lib64 and /usr/lib64 come from base-files.
	$(LN) . $(1)/lib/x86_64-linux-gnu
	$(LN) . $(1)/usr/lib/x86_64-linux-gnu

	# Unversioned linker and dlopen names normally supplied by distro -dev packages.
	$(LN) ../../lib/libBrokenLocale.so.1 $(1)/usr/lib/libBrokenLocale.so
	$(LN) ../../lib/libanl.so.1 $(1)/usr/lib/libanl.so
	$(LN) ../../lib/libatomic.so.1 $(1)/usr/lib/libatomic.so
	$(LN) libcrypt.so.1 $(1)/usr/lib/libcrypt.so
	$(LN) ../../lib/libdl.so.2 $(1)/usr/lib/libdl.so
	$(LN) ../../lib/libgcc_s.so.1 $(1)/usr/lib/libgcc_s.so
	$(LN) ../../lib/libc_malloc_debug.so.0 $(1)/usr/lib/libc_malloc_debug.so
	$(LN) ../../lib/libmvec.so.1 $(1)/usr/lib/libmvec.so
	$(LN) ../../lib/libnsl.so.1 $(1)/usr/lib/libnsl.so
	$(LN) ../../lib/libnss_compat.so.2 $(1)/usr/lib/libnss_compat.so
	$(LN) ../../lib/libnss_db.so.2 $(1)/usr/lib/libnss_db.so
	$(LN) ../../lib/libnss_hesiod.so.2 $(1)/usr/lib/libnss_hesiod.so
	$(LN) ../../lib/libpthread.so.0 $(1)/usr/lib/libpthread.so
	$(LN) ../../lib/libresolv.so.2 $(1)/usr/lib/libresolv.so
	$(LN) ../../lib/librt.so.1 $(1)/usr/lib/librt.so
	$(LN) libstdc++.so.6 $(1)/usr/lib/libstdc++.so
	$(LN) ../../lib/libthread_db.so.1 $(1)/usr/lib/libthread_db.so
	$(LN) ../../lib/libutil.so.1 $(1)/usr/lib/libutil.so
endef

$(eval $(call BuildPackage,glibc-distro-compat))
