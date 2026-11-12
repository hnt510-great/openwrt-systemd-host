include $(TOPDIR)/rules.mk

PKG_NAME:=rtkit
PKG_VERSION:=0.14
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-v$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/pipewire/rtkit/-/archive/v$(PKG_VERSION)
PKG_HASH:=55dd379b11f52b81655e2dc676de9d602d050cb0beb18ef01f0f65569f0a5e59
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-v$(PKG_VERSION)

PKG_MAINTAINER:=OpenWrt Desktop Integration
PKG_LICENSE:=GPL-3.0-or-later BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE GPL
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/rtkit
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Realtime Policy and Watchdog Daemon
  URL:=https://gitlab.freedesktop.org/pipewire/rtkit
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +dbus +libdbus +libcap +libsystemd +polkit +librt +libpthread
  USERID:=rtkit=193:rtkit=193
endef

define Package/rtkit/description
  RealtimeKit is a D-Bus system service that changes the scheduling policy of
  user processes/threads to SCHED_RR (realtime scheduling mode) or high-priority
  nice levels on request, guarded by Polkit and a canary-based RT watchdog.
endef

MESON_ARGS += \
	--prefix=/usr \
	-Dinstalled_tests=false \
	-Dlibsystemd=enabled \
	-Dsystemd_systemunitdir=/usr/lib/systemd/system \
	-Ddbus_systemservicedir=/usr/share/dbus-1/system-services \
	-Ddbus_rulesdir=/usr/share/dbus-1/system.d \
	-Ddbus_interfacedir=/usr/share/dbus-1/interfaces \
	-Dpolkit_actiondir=/usr/share/polkit-1/actions

define Package/rtkit/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/libexec/rtkit-daemon $(1)/usr/libexec/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/sbin/rtkitctl $(1)/usr/sbin/

	$(INSTALL_DIR) $(1)/usr/share/dbus-1/system-services
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services/org.freedesktop.RealtimeKit1.service \
		$(1)/usr/share/dbus-1/system-services/

	$(INSTALL_DIR) $(1)/usr/share/dbus-1/system.d
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d/org.freedesktop.RealtimeKit1.conf \
		$(1)/usr/share/dbus-1/system.d/

	$(INSTALL_DIR) $(1)/usr/share/dbus-1/interfaces
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/interfaces/org.freedesktop.RealtimeKit1.xml \
		$(1)/usr/share/dbus-1/interfaces/

	$(INSTALL_DIR) $(1)/usr/share/polkit-1/actions $(1)/usr/share/polkit-1/rules.d
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/polkit-1/actions/org.freedesktop.RealtimeKit1.policy \
		$(1)/usr/share/polkit-1/actions/
	$(INSTALL_DATA) ./files/20-openwrt-rtkit.rules \
		$(1)/usr/share/polkit-1/rules.d/20-openwrt-rtkit.rules

	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/usr/lib/systemd/system/rtkit-daemon.service.d
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/rtkit-daemon.service \
		$(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/rtkit-service.conf \
		$(1)/usr/lib/systemd/system/rtkit-daemon.service.d/openwrt.conf
endef

$(eval $(call BuildPackage,rtkit))
