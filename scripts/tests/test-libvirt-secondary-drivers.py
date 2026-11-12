#!/usr/bin/env python3
"""Read-only target checks for OpenWrt's libvirt secondary drivers.

Run on the native-systemd router with python3-libvirt and access to
qemu:///system. The excluded network and interface drivers must report
NO_SUPPORT, allowing clients such as virt-manager to distinguish absent
capabilities from broken services. Node devices, network filters and the
UEFI/vTPM domain capabilities must be available.
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
                          ('listAllInterfaces', (0,)),
                          ('listNetworks', ())):
            with self.subTest(api=api):
                with self.assertRaises(libvirt.libvirtError) as caught:
                    getattr(self.conn, api)(*args)
                self.assertEqual(caught.exception.get_error_code(),
                                 libvirt.VIR_ERR_NO_SUPPORT)

    def test_enabled_drivers_remain_available(self):
        self.assertIsInstance(self.conn.listAllDomains(0), list)
        self.assertIsInstance(self.conn.listAllStoragePools(0), list)
        self.assertIsInstance(self.conn.listAllSecrets(0), list)

    def test_node_devices_are_listed(self):
        names = [dev.name() for dev in self.conn.listAllDevices(0)]
        self.assertIn('computer', names)
        pci = self.conn.listAllDevices(libvirt.VIR_CONNECT_LIST_NODE_DEVICES_CAP_PCI_DEV)
        self.assertTrue(pci, 'no PCI devices reported by virtnodedevd')

    def test_default_network_filters_are_defined(self):
        names = {flt.name() for flt in self.conn.listAllNWFilters(0)}
        for name in ('clean-traffic', 'no-ip-spoofing', 'no-mac-spoofing'):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_uefi_and_tpm_capabilities(self):
        caps = self.conn.getDomainCapabilities(None, 'x86_64', 'q35', 'kvm', 0)
        self.assertIn("<value>efi</value>", caps)
        self.assertIn("<enum name='secureBoot'>", caps)
        self.assertIn("<enum name='enrolledKeys'>", caps)
        self.assertIn('/usr/share/OVMF/OVMF_CODE_4M', caps)
        self.assertIn("<tpm supported='yes'>", caps)
        self.assertIn('<value>emulator</value>', caps)


if __name__ == '__main__':
    unittest.main()
