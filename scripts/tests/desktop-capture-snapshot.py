#!/usr/bin/env python3
"""Print CPU counters for the current user's desktop and isolated test server."""
import json
import os
from pathlib import Path
import subprocess
import time

probe = int(subprocess.check_output(['systemctl', '--user', 'show',
                                   'desktop-capture-probe.service', '-p', 'MainPID', '--value'], text=True))
processes = {}
for directory in Path('/proc').glob('[0-9]*'):
    try:
        if directory.stat().st_uid != os.getuid():
            continue
        name = (directory / 'comm').read_text().strip()
        role = 'sunshine' if int(directory.name) == probe else name
        if role not in ['weston', 'weston-desktop-', 'pipewire', 'sunshine']:
            continue
        if role == 'sunshine' and int(directory.name) != probe:
            continue
        fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
        processes[role] = {'pid': int(directory.name), 'ticks': int(fields[11]) + int(fields[12])}
    except (OSError, ValueError, IndexError):
        continue
print(json.dumps({'time': time.monotonic(), 'hz': os.sysconf('SC_CLK_TCK'), 'processes': processes}))
