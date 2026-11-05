include $(TOPDIR)/rules.mk
PKG_NAME:=libvirt-python
PKG_VERSION:=12.9.0
PKG_RELEASE:=1
PKG_SOURCE:=libvirt-python-12.9.0.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/libvirt/libvirt-python/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=v$(PKG_VERSION)
PKG_HASH:=50942a810c376e88733db3d91e05db4b73fd252c38446c6479f98aca0e53710c
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=python-setuptools/host
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-libvirt
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=Libvirt Python bindings
  DEPENDS:=+python3 +libvirt
endef
$(eval $(call Py3Package,python3-libvirt))
$(eval $(call BuildPackage,python3-libvirt))
