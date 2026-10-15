include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-full-utils
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-full-utils
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Prefer standalone utilities with BusyBox recovery fallbacks
  DEPENDS:=+logger +taskset +hexdump +setsid +hwclock +procps-ng-pidof \
    +bind-nslookup +ncat +gnu-time +traceroute +ncurses-utils +kbd-chvt \
    +vim-runtime +net-tools-netstat +net-tools-ifconfig +iputils-ping
  # Selecting a virtual Vim provider creates a Kconfig provider/conflict cycle.
  # The desktop profile selects vim-full; retain the dependency in the APK too.
  EXTRA_DEPENDS:=vim-full (>=0)
  ALTERNATIVES:=300:/usr/bin/vi:/usr/bin/vim \
    300:/usr/bin/nc:/usr/bin/ncat \
    300:/usr/bin/netstat:/usr/libexec/net-tools-netstat \
    300:/usr/bin/ping6:/usr/bin/ping
endef

define Package/openwrt-full-utils/description
 Prefer packaged standalone tools while retaining BusyBox ash/sh, login,
 cron, DHCP, NTP, boot/recovery helpers and OpenWrt-specific applets.
 Existing router init scripts and their BusyBox-specific options are retained.
endef

define Build/Compile
endef

define Package/openwrt-full-utils/install
	$(INSTALL_DIR) $(1)/usr/share/doc/openwrt-full-utils
	$(INSTALL_DATA) ./files/README $(1)/usr/share/doc/openwrt-full-utils/README
endef

$(eval $(call BuildPackage,openwrt-full-utils))
