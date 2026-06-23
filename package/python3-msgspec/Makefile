include $(TOPDIR)/rules.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-version.mk

PKG_NAME:=python3-msgspec
PKG_VERSION:=0.20.0
PKG_RELEASE:=1

PKG_SOURCE:=msgspec-$(PKG_VERSION)-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
PKG_SOURCE_URL:=https://files.pythonhosted.org/packages/b8/8e/6b17e43f6eb9369d9858ee32c97959fcd515628a1df376af96c11606cf70/
PKG_HASH:=27d35044dd8818ac1bd0fedb2feb4fbdff4e3508dd7c5d14316a12a2d96a0de0

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk

define Package/python3-msgspec
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=Fast JSON/MessagePack library
  URL:=https://jcristharif.com/msgspec/
  DEPENDS:=+python3-light
endef

define Package/python3-msgspec/description
  msgspec is a fast serialization and validation library, with built-in support for JSON, MessagePack, YAML, and TOML.
  This package installs pre-compiled x86_64 binary wheels.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	unzip -q $(DL_DIR)/$(PKG_SOURCE) -d $(PKG_BUILD_DIR)
endef

define Build/Compile
	# Nothing to compile, it is a prebuilt wheel
endef

define Package/python3-msgspec/install
	$(INSTALL_DIR) $(1)/usr/lib/python$(PYTHON3_VERSION)/site-packages
	$(CP) $(PKG_BUILD_DIR)/msgspec $(1)/usr/lib/python$(PYTHON3_VERSION)/site-packages/
	$(CP) $(PKG_BUILD_DIR)/msgspec-$(PKG_VERSION).dist-info $(1)/usr/lib/python$(PYTHON3_VERSION)/site-packages/
endef

$(eval $(call BuildPackage,python3-msgspec))
