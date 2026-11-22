include $(TOPDIR)/rules.mk

PKG_NAME:=libutempter
PKG_VERSION:=1.2.3
PKG_RELEASE:=2
PKG_SOURCE:=libutempter-717116b.tar.gz
PKG_SOURCE_URL:=https://github.com/altlinux/libutempter/archive/717116b93d496a19f7f8abf8702517de0053f66e.tar.gz
PKG_HASH:=e6214ba8ed567d6124030d81e50e652c16ecada51af7ff3672481bf36287d1f5
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_DIR:=$(BUILD_DIR)/libutempter-717116b93d496a19f7f8abf8702517de0053f66e

include $(INCLUDE_DIR)/package.mk

# The tarball keeps the library sources in a subdirectory and has no
# top-level configure script; drive that Makefile directly.
define Build/Compile
	$(MAKE) -C $(PKG_BUILD_DIR)/libutempter \
		CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS) $(TARGET_CPPFLAGS)" \
		LDFLAGS="$(TARGET_LDFLAGS)"
endef

define Build/Install
	$(MAKE) -C $(PKG_BUILD_DIR)/libutempter \
		DESTDIR="$(PKG_INSTALL_DIR)" install
endef

define Package/libutempter
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=utmp/wtmp record helper library
  URL:=https://github.com/altlinux/libutempter
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD
endef

define Package/libutempter/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/lib/utempter
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libutempter.so.* $(1)/usr/lib/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/utempter/utempter $(1)/usr/lib/utempter/utempter
	chmod 0711 $(1)/usr/lib/utempter/utempter
	$(INSTALL_DIR) $(1)/usr/lib/tmpfiles.d
	$(INSTALL_DATA) ./files/libutempter.conf $(1)/usr/lib/tmpfiles.d/
endef

# Image builds run the tmpfiles rule at first boot, after sysusers has
# created the utmp group. Apply it immediately for live APK installs.
define Package/libutempter/postinst
#!/bin/sh
[ -z "$${IPKG_INSTROOT}" ] || exit 0
group_add_next utmp >/dev/null || exit 1
/usr/bin/systemd-tmpfiles --create /usr/lib/tmpfiles.d/libutempter.conf
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/include/utempter.h $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libutempter.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libutempter))
