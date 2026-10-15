include $(TOPDIR)/rules.mk

PKG_NAME:=traceroute
PKG_VERSION:=2.1.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://downloads.sourceforge.net/project/traceroute/traceroute/traceroute-$(PKG_VERSION)
PKG_HASH:=9ccef9cdb9d7a98ff7fbf93f79ebd0e48881664b525c4b232a0fcec7dcb9db5e
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/traceroute
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Full IPv4 and IPv6 traceroute for Linux
  URL:=https://traceroute.sourceforge.net/
  ALTERNATIVES:=300:/usr/bin/traceroute:/usr/libexec/traceroute \
    300:/usr/bin/traceroute6:/usr/libexec/traceroute
endef

define Build/Configure
endef

MAKE_FLAGS += env=yes

define Package/traceroute/install
	$(INSTALL_DIR) $(1)/usr/libexec
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/traceroute/traceroute $(1)/usr/libexec/traceroute
endef

$(eval $(call BuildPackage,traceroute))
