include $(TOPDIR)/rules.mk

PKG_NAME:=poppler
PKG_VERSION:=26.11.0
PKG_RELEASE:=1
PKG_SOURCE:=poppler-26.11.0.tar.xz
PKG_SOURCE_URL:=https://poppler.freedesktop.org/
PKG_HASH:=41c32680160addf5a8dd7a830e4869c01e9f6bee1abb91e44fabd1ba9d7828fb
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/poppler
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=GNOME desktop
  TITLE:=PDF rendering library and GLib wrapper
  URL:=https://poppler.freedesktop.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +libcairo +libfreetype +fontconfig +libjpeg +libpng +libtiff +liblcms2 +harfbuzz +zlib +libstdcpp
endef

CMAKE_OPTIONS += \
	-DBUILD_SHARED_LIBS=ON \
	-DBUILD_MANUAL_TESTS=OFF \
	-DBUILD_GTK_TESTS=OFF \
	-DBUILD_QT5_TESTS=OFF \
	-DBUILD_QT6_TESTS=OFF \
	-DBUILD_CPP_TESTS=OFF \
	-DENABLE_BOOST=OFF \
	-DENABLE_UTILS=ON \
	-DENABLE_CPP=OFF \
	-DENABLE_GLIB=ON \
	-DENABLE_GOBJECT_INTROSPECTION=OFF \
	-DENABLE_GTK_DOC=OFF \
	-DENABLE_QT5=OFF \
	-DENABLE_QT6=OFF \
	-DENABLE_BROTLI=OFF \
	-DENABLE_LIBOPENJPEG=OFF \
	-DENABLE_LIBJPEG=ON \
	-DENABLE_LCMS=ON \
	-DENABLE_LIBCURL=OFF \
	-DENABLE_LIBTIFF=ON \
	-DENABLE_NSS3=OFF \
	-DENABLE_GPGME=OFF \
	-DENABLE_HARFBUZZ=ON \
	-DRUN_GPERF_IF_PRESENT=OFF

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/libpoppler*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/poppler*.pc $(1)/usr/lib/pkgconfig/
	$(SED) 's,^libdir=/usr/lib,libdir=$$$${prefix}/lib,; s,^includedir=/usr/include,includedir=$$$${prefix}/include,' $(1)/usr/lib/pkgconfig/poppler*.pc
endef

define Package/poppler/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/bin/pdf* $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libpoppler*.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,poppler))
