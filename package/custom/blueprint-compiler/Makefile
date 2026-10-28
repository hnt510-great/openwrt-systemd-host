include $(TOPDIR)/rules.mk

PKG_NAME:=blueprint-compiler
PKG_VERSION:=0.20.4
PKG_RELEASE:=1
PKG_SOURCE:=blueprint-compiler-0.20.4.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/blueprint-compiler/0.20/
PKG_HASH:=1f1ecc84bcd698902d422f7de83d39229a209dd3016f6d2c3b0ed0ab123f6891
PKG_LICENSE:=LGPL-3.0-or-later
HOST_BUILD_DEPENDS:=python3/host pygobject/host
HOST_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-host.mk

MESON_USE_STAGING_PYTHON:=1
PYTHON_BIN:=$(STAGING_DIR_HOSTPKG)/bin/python3
MESON_HOST_ARGS += -Ddocs=false

define Package/blueprint-compiler
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Blueprint UI compiler host build
  BUILDONLY:=1
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,blueprint-compiler))
