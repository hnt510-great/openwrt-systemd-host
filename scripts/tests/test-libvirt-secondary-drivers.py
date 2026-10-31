#!/usr/bin/env python3
"""Read-only target checks for OpenWrt's disabled libvirt secondary drivers.

Run on the native-systemd router with python3-libvirt and access to
qemu:///system. Disabled APIs must report NO_SUPPORT, allowing clients such
as virt-manager to distinguish absent capabilities from broken services.
"""
import unittest

import libvirt


class SecondaryDrivers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        libvirt.registerErrorHandler(lambda context, error: None, None)
        cls.conn = libvirt.open('qemu:///system')

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_disabled_drivers_report_no_support(self):
        for api, args in (('listAllNetworks', (0,)),
                          ('listAllDevices', (0,)),
                          ('listAllInterfaces', (0,)),
                          ('listAllNWFilters', (0,)),
                          ('listNetworks', ()),
                          ('listDevices', (None, 0))):
            with self.subTest(api=api):
                with self.assertRaises(libvirt.libvirtError) as caught:
                    getattr(self.conn, api)(*args)
                self.assertEqual(caught.exception.get_error_code(),
                                 libvirt.VIR_ERR_NO_SUPPORT)

    def test_enabled_drivers_remain_available(self):
        self.assertIsInstance(self.conn.listAllDomains(0), list)
        self.assertIsInstance(self.conn.listAllStoragePools(0), list)
        self.assertIsInstance(self.conn.listAllSecrets(0), list)


if __name__ == '__main__':
    unittest.main()
