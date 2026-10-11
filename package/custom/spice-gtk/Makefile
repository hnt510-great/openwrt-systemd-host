include $(TOPDIR)/rules.mk

PKG_NAME:=spice-gtk
PKG_VERSION:=0.41
PKG_RELEASE:=2
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://www.spice-space.org/download/gtk
PKG_HASH:=d8f8b5cbea9184702eeb8cc276a67d72acdb6e36e7c73349fb8445e5bca0969f
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python3/host glib2/host spice-protocol wayland/host

PYTHON3_PKG_BUILD:=0
HOST_PYTHON3_PACKAGE_BUILD_DEPENDS:=./host-pip-requirements.txt
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

MESON_VARS += PYTHONPATH="$(HOST_PYTHON3PATH)"
MESON_ARGS += \
	-Dauto_features=disabled -Dgtk=enabled -Dwayland-protocols=enabled \
	-Dintrospection=enabled -Dvapi=disabled -Dgtk_doc=disabled \
	-Dwebdav=disabled -Dusbredir=disabled -Dlibcap-ng=disabled \
	-Dpolkit=disabled -Dsmartcard=disabled -Dsasl=disabled \
	-Dopus=disabled -Dlz4=disabled -Dcoroutine=ucontext \
	-Dspice-common:generate-code=client -Dspice-common:python-checks=true \
	-Dspice-common:smartcard=disabled -Dspice-common:opus=disabled \
	-Dspice-common:manual=false -Dspice-common:tests=false

define Package/spice-gtk
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=SPICE GTK3 Wayland console with OpenGL and Python metadata
  URL:=https://www.spice-space.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libgtk3 +libepoxy +libwayland +wayland-protocols +pixman +libopenssl +libjpeg +zlib +json-glib +libgst1app +libgst1audio +libgst1video +libgstreamer1
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	$(call Py3Build/InstallBuildDepends)
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libspice-client*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/SpiceClient*.gir $(1)/usr/share/gir-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/SpiceClient*.typelib $(1)/usr/lib/girepository-1.0/
endef

define Package/spice-gtk/install
	$(INSTALL_DIR) $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libspice-client*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/SpiceClient*.typelib $(1)/usr/lib/girepository-1.0/
endef

$(eval $(call BuildPackage,spice-gtk))
