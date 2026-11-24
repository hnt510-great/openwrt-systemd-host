include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kimageformats
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kimageformats-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=298069eab84d34b909fc271d818b0762c6c63cc8490f2d8b0fe48dc0d8804b5c
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KImageFormats
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +qt6base-printsupport +kf6-karchive
KF6_CMAKE_OPTIONS:=-DKIMAGEFORMATS_HEIF=OFF -DKIMAGEFORMATS_JXL=OFF -DKIMAGEFORMATS_RAW=OFF -DCMAKE_DISABLE_FIND_PACKAGE_OpenEXR=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
