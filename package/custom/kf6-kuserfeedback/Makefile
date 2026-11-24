include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kuserfeedback
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kuserfeedback-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=156cadff9de487538440a7f6cfce4a4f0240dc22ccbe4d48f37fb1bd84c75ee5
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KUserFeedback
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-network +qt6base-widgets +qt6svg +qt6quick-qml
KF6_CMAKE_OPTIONS:=-DENABLE_DOCS=OFF -DENABLE_PHP=OFF -DENABLE_PHP_UNIT=OFF -DENABLE_SURVEY_TARGET_EXPRESSIONS=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
