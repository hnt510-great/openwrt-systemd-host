include $(TOPDIR)/rules.mk

PKG_NAME:=extra-cmake-modules
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=305f4e2b82eb073be6ac3e50ace85578b3c0c409be262ccc51d445449e3d9312
PKG_LICENSE:=BSD-3-Clause
PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/cmake.mk
CMAKE_OPTIONS += -DBUILD_TESTING=OFF -DBUILD_HTML_DOCS=OFF -DBUILD_MAN_DOCS=OFF -DBUILD_QTHELP_DOCS=OFF
CMAKE_HOST_OPTIONS += -DBUILD_TESTING=OFF -DBUILD_HTML_DOCS=OFF -DBUILD_MAN_DOCS=OFF -DBUILD_QTHELP_DOCS=OFF

define Package/extra-cmake-modules
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=KDE extra CMake modules (build files)
  BUILDONLY:=1
endef
CMAKE_INSTALL:=1
$(eval $(call BuildPackage,extra-cmake-modules))
$(eval $(call HostBuild))
