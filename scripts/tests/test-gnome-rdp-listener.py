#!/usr/bin/env python3
"""Exercise the patched GRD listener against real loopback TCP sockets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RdpListenerTest(unittest.TestCase):
    def test_listener_rejects_wildcards_and_never_negotiates_another_port(self):
        archive = ROOT / 'dl/gnome-remote-desktop-51.0.tar.xz'
        if not archive.exists():
            self.skipTest('run make download for gnome-remote-desktop first')
        with tempfile.TemporaryDirectory(prefix='gnome-rdp-listener-') as directory:
            work = Path(directory)
            subprocess.run(['tar', '-xf', str(archive), '-C', str(work)], check=True)
            source = work / 'gnome-remote-desktop-51.0'
            patch = ROOT / 'package/custom/gnome-remote-desktop/patches/001-bind-only-configured-lan.patch'
            subprocess.run(['patch', '-p1', '--fuzz=0', '-i', str(patch)],
                           cwd=source, check=True, capture_output=True)
            text = (source / 'src/grd-utils.c').read_text()
            begin = text.index('gboolean\ngrd_bind_socket (')
            end = text.index('\n}\n', begin) + 3
            program = '#include <gio/gio.h>\n#include <stdint.h>\n' + text[begin:end]
            program += r'''
static void must_fail(const char *address, uint16_t port) {
  g_autoptr(GSocketListener) listener = g_socket_listener_new();
  g_autoptr(GError) error = NULL;
  uint16_t selected = 42;
  if (address) g_setenv("OPENWRT_RDP_ADDRESS", address, TRUE);
  else g_unsetenv("OPENWRT_RDP_ADDRESS");
  g_assert_false(grd_bind_socket(listener, port, &selected, TRUE, &error));
  g_assert_nonnull(error);
  g_assert_cmpuint(selected, ==, 42);
}
int main(void) {
  must_fail(NULL, 3389);
  must_fail("", 3389);
  must_fail("0.0.0.0", 3389);
  must_fail("::1", 3389);
  must_fail("224.0.0.1", 3389);
  must_fail("127.0.0.2", 0);
  g_autoptr(GSocketListener) listener = g_socket_listener_new();
  g_autoptr(GError) error = NULL;
  g_autoptr(GSocket) probe = g_socket_new(G_SOCKET_FAMILY_IPV4,
      G_SOCKET_TYPE_STREAM, G_SOCKET_PROTOCOL_TCP, &error);
  g_assert_no_error(error);
  g_autoptr(GInetAddress) ip = g_inet_address_new_from_string("127.0.0.2");
  g_autoptr(GSocketAddress) ephemeral = g_inet_socket_address_new(ip, 0);
  g_assert_true(g_socket_bind(probe, ephemeral, FALSE, &error));
  g_assert_no_error(error);
  g_autoptr(GSocketAddress) actual = g_socket_get_local_address(probe, &error);
  uint16_t port = g_inet_socket_address_get_port(G_INET_SOCKET_ADDRESS(actual));
  g_socket_close(probe, NULL);
  uint16_t selected = 0;
  g_setenv("OPENWRT_RDP_ADDRESS", "127.0.0.2", TRUE);
  g_assert_true(grd_bind_socket(listener, port, &selected, FALSE, &error));
  g_assert_no_error(error);
  g_assert_cmpuint(selected, ==, port);
  must_fail("127.0.0.2", port);
  g_autoptr(GSocketClient) client = g_socket_client_new();
  g_socket_client_set_timeout(client, 2);
  g_autoptr(GSocketConnection) accepted = g_socket_client_connect_to_host(
      client, "127.0.0.2", port, NULL, &error);
  g_assert_no_error(error);
  g_assert_nonnull(accepted);
  g_autoptr(GSocketConnection) denied = g_socket_client_connect_to_host(
      client, "127.0.0.1", port, NULL, &error);
  g_assert_null(denied);
  g_assert_nonnull(error);
  g_socket_listener_close(listener);
  return 0;
}
'''
            (work / 'listener.c').write_text(program)
            env = dict(os.environ)
            for name in ['PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR', 'PKG_CONFIG_SYSROOT_DIR']:
                env.pop(name, None)
            pkgconfig = ['pkg-config', '--cflags', '--libs', 'gio-2.0']
            if subprocess.run(['pkg-config', '--exists', 'gio-2.0'], env=env).returncode:
                env['PKG_CONFIG_PATH'] = str(ROOT / 'staging_dir/hostpkg/lib/pkgconfig')
                pkgconfig.insert(1, '--static')
            flags = subprocess.check_output(pkgconfig, env=env, text=True).split()
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(work / 'listener.c'),
                            '-o', str(work / 'listener'), *flags], check=True)
            subprocess.run([str(work / 'listener')], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
