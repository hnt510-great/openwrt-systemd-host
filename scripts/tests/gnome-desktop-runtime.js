// Load the real GNOME libraries and their complete runtime typelib chains.
// This checks library loading, not desktop rendering or remote interaction.
// In the guest, set GI_TYPELIB_PATH and LD_LIBRARY_PATH to
// /usr/lib/gnome-shell:/usr/lib/mutter-51 before running gjs FILE.
const probes = [
    ['GLib', '2.0', 'MainLoop'],
    ['Gtk', '4.0', 'Widget'],
    ['Adw', '1', 'Application'],
    ['ECal', '2.0', 'Client'],
    ['GnomeDesktop', '4.0', 'DesktopThumbnailFactory'],
    ['GWeather', '4.0', 'Info'],
    ['Geoclue', '2.0', 'Simple'],
    ['IBus', '1.0', 'Bus'],
    ['AccountsService', '1.0', 'UserManager'],
    ['UPowerGlib', '1.0', 'Client'],
    ['Gdm', '1.0', 'Client'],
    ['Gcr', '4', 'SystemPrompt'],
    ['Atspi', '2.0', 'Accessible'],
    ['Meta', '51', 'Context'],
    ['Gvc', '1.0', 'MixerControl'],
    ['St', '51', 'Widget'],
    ['Shell', '51', 'Global'],
];

for (const [name, version, symbol] of probes) {
    imports.gi.versions[name] = version;
    const value = imports.gi[name][symbol];
    if (value === undefined)
        throw new Error(name + '.' + symbol + ' is missing');
    print(name + ' ' + version + ': ' + typeof value);
}

const Gio = imports.gi.Gio;
const schemas = Gio.SettingsSchemaSource.get_default();
for (const name of ['org.gnome.login-screen', 'org.gnome.shell',
    'org.gnome.desktop.interface', 'org.gnome.desktop.remote-desktop.rdp']) {
    if (!schemas.lookup(name, true))
        throw new Error('Missing runtime settings schema: ' + name);
    print(name + ': settings schema');
}
