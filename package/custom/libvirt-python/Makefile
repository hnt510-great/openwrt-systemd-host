include $(TOPDIR)/rules.mk
PKG_NAME:=libvirt-python
PKG_VERSION:=12.8.0
PKG_RELEASE:=1
PKG_SOURCE:=libvirt-python-12.8.0.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/libvirt/libvirt-python/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=v$(PKG_VERSION)
PKG_HASH:=0c10c9916af33dbefd958613a9eef2e9b5b8d5fd5540c1ccb8fb8e79c49593c1
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
