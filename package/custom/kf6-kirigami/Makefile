include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kirigami
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kirigami-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=1cb13ef3ad1885726c383bcd1a35c494db3e9c2cf87b49398ea34d63129cf6d7
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.0-or-later LGPL-2.1-or-later (LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL)
PKG_LICENSE_FILES:=LICENSES/GPL-2.0-or-later.txt LICENSES/LGPL-2.0-or-later.txt \
	LICENSES/LGPL-2.1-or-later.txt LICENSES/LGPL-2.1-only.txt \
	LICENSES/LGPL-3.0-only.txt LICENSES/LicenseRef-KDE-Accepted-LGPL.txt

CMAKE_BINARY_SUBDIR:=build
PKG_BUILD_DEPENDS:=qt6shadertools
KF6_TITLE:=Kirigami
KF6_DEPENDS:=+qt6base-dbus +qt6base-concurrent +qt6svg \
	+qt6quick-qml-mod-qtquick-controls
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
