#!/usr/bin/env python3
"""Regress stale prompts and repeated askfirst activation after a guest reboot."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('test-uci-history-vm.py')
SPEC = importlib.util.spec_from_file_location('history_vm', SOURCE)
VM = importlib.util.module_from_spec(SPEC)
with patch.object(sys, 'dont_write_bytecode', True):
    SPEC.loader.exec_module(VM)


class Socket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.reads = 0

    def recv(self, size):
        self.reads += 1
        return self.chunks.pop(0)

    def sendall(self, data):
        self.sent.append(data)


class Guest:
    def __init__(self, chunks):
        self.socket = Socket(chunks)

    def alive(self):
        pass


class ConsoleTest(unittest.TestCase):
    def test_old_prompt_cannot_complete_reboot(self):
        guest = Guest([b'root@old:~# ', b'boot log', b'Please press Enter',
                       b'initializing', b'root@new:~# '])
        VM.wait_reboot_console(guest)
        self.assertEqual(guest.socket.reads, 5)
        self.assertEqual(guest.socket.sent, [b'\n'])

    def test_only_one_activation_enter(self):
        guest = Guest([b'Please press Enter', b'Please press Enter',
                       b'systemd startup', b'root@new:~# '])
        VM.wait_reboot_console(guest)
        self.assertEqual(guest.socket.reads, 4)
        self.assertEqual(guest.socket.sent, [b'\n'])


if __name__ == '__main__':
    unittest.main()
