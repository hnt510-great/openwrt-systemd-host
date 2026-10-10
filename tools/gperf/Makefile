include $(TOPDIR)/rules.mk

PKG_NAME:=gperf
PKG_VERSION:=3.1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=@GNU/gperf
PKG_HASH:=588546b945bba4b70b6a3a616e80b4ab466e3f33024a352fc2198112cdbb3ae2
PKG_LICENSE:=GPL-3.0-or-later
HOST_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/host-build.mk

$(eval $(call HostBuild))
