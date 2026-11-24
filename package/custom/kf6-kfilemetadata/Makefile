include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kfilemetadata
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kfilemetadata-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=f74fcb857e52613095d9b264ac6e8ddf0eca326c884e8c83fd536e70b111241a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_SUBMENU:=KDE Frameworks 6
KF6_PACKAGE_TITLE:=KF6 FileMetaData
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-xml +kf6-karchive +kf6-kcodecs +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n +libattr
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_Poppler=ON -DCMAKE_DISABLE_FIND_PACKAGE_Taglib=ON -DCMAKE_DISABLE_FIND_PACKAGE_LibExiv2=ON -DCMAKE_DISABLE_FIND_PACKAGE_FFmpeg=ON -DCMAKE_DISABLE_FIND_PACKAGE_EPub=ON -DCMAKE_DISABLE_FIND_PACKAGE_QMobipocket6=ON -DCMAKE_DISABLE_FIND_PACKAGE_libappimage=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
