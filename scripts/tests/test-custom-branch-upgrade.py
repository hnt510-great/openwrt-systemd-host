#!/usr/bin/env python3
"""Smoke the built branch upgrades with target libraries, without installation."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / 'staging_dir/target-x86_64_glibc'
TARGET = STAGING / 'root-x86-systemd'
RUNNER = ROOT / 'scripts/gi-target-runner'


class BranchUpgradeTests(unittest.TestCase):
    def target(self, program, *args, env=None):
        return subprocess.check_output([str(RUNNER), str(program), *args],
                                       cwd=ROOT, text=True, env=env)

    def test_node_and_npm_with_target_libraries(self):
        node = TARGET / 'usr/bin/node'
        result = json.loads(self.target(node, '-p',
            'JSON.stringify({version:process.version,lts:process.release.lts,modules:process.versions.modules})'))
        self.assertEqual(result['lts'], 'Lithium')
        self.assertEqual(result['modules'], '147')
        self.assertTrue(result['version'].startswith('v26.'))
        npm = TARGET / 'usr/lib/node_modules/npm/bin/npm-cli.js'
        self.assertTrue(self.target(node, str(npm), '--version').strip())
        for name in ('npm', 'npx', 'corepack'):
            path = TARGET / 'usr/bin' / name
            self.assertFalse(path.is_symlink() and not path.exists(), name)

    def test_target_typelibs_and_weather_database(self):
        database = TARGET / 'usr/lib/gweather-locations/Locations.bin'
        self.assertGreater(database.stat().st_size, 100000)
        env = dict(os.environ,
                   GI_TYPELIB_PATH=os.pathsep.join(str(STAGING / p) for p in
                       ('usr/lib/girepository-1.0', 'usr/lib/gjs/girepository-1.0')),
                   LIBGWEATHER_LOCATIONS_PATH=str(database))
        script = '''
imports.gi.versions.Atspi = '2.0';
imports.gi.versions.Xdp = '1.0';
imports.gi.versions.GWeather = '4.0';
imports.gi.versions.EDataServer = '1.2';
imports.gi.versions.ECal = '2.0';
imports.gi.versions.SpiceClientGLib = '2.0';
imports.gi.versions.SpiceClientGtk = '3.0';
const {Atspi, Xdp, GWeather, EDataServer, ECal, SpiceClientGLib, SpiceClientGtk, GLib} = imports.gi;
if (!Atspi.Accessible || !Xdp.Portal || !EDataServer.Source || !ECal.Client ||
    !SpiceClientGLib.Session || !SpiceClientGtk.Display)
    throw new Error('Missing GI API');
const [ok, maps] = GLib.file_get_contents('/proc/self/maps');
if (!ok || !imports.byteArray.toString(maps).includes('libedataserver-1.2.so.28'))
    throw new Error('EDataServer typelib did not load SONAME 28');
const world = GWeather.Location.get_world();
if (!world) throw new Error('Cannot read location database');
const airport = world.find_by_station_code('WSSS');
if (!airport) throw new Error('Missing WSSS station in location database');
print(JSON.stringify({station: airport.get_code(), name: airport.get_name()}));
'''
        result = json.loads(self.target(TARGET / 'usr/bin/gjs', '-c', script, env=env))
        self.assertEqual(result['station'], 'WSSS')
        self.assertTrue(result['name'])

    def test_calendar_server_uses_new_eds_soname(self):
        program = TARGET / 'usr/libexec/gnome-shell-calendar-server'
        result = subprocess.check_output(['readelf', '-d', str(program)], text=True)
        self.assertIn('libedataserver-1.2.so.28', result)
        self.assertNotIn('libedataserver-1.2.so.27', result)
        subprocess.run([str(RUNNER), '--list', str(program)], cwd=ROOT,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_weather_default_path_has_no_build_host_prefix(self):
        library = TARGET / 'usr/lib/libgweather-4.so.0'
        strings = subprocess.check_output(['strings', str(library)], text=True)
        self.assertTrue('/usr/lib/gweather-locations/Locations.bin' in strings.splitlines(),
                        'The active libgweather must use the target database path')
        self.assertFalse(str(ROOT) + '/' in strings, 'Build host prefix leaked into libgweather')


if __name__ == '__main__':
    unittest.main()
