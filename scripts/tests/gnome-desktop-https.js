// Run with target GJS. Fetch extension metadata and an archive without
// installing an extension or changing the user's Shell configuration.
imports.gi.versions.Soup = '3.0';
const {Gio, Soup} = imports.gi;
const backend = Gio.TlsBackend.get_default();
if (!backend.supports_tls())
    throw new Error('GIO has no TLS backend');

const session = new Soup.Session({timeout: 30});
const uuid = 'kimpanel@kde.org';
const params = Soup.form_encode_hash({uuid, shell_version: '51.1'});
const infoMessage = Soup.Message.new('GET',
    'https://extensions.gnome.org/extension-info/?' + params);
const infoBytes = session.send_and_read(infoMessage, null);
if (infoMessage.status_code !== 200 || infoMessage.tls_peer_certificate_errors !== 0)
    throw new Error('Extension metadata HTTPS request failed');
const info = JSON.parse(new TextDecoder().decode(infoBytes.get_data()));
if (info.uuid !== uuid)
    throw new Error('Unexpected extension metadata');

const zipMessage = Soup.Message.new('GET',
    'https://extensions.gnome.org/download-extension/' +
    encodeURIComponent(uuid) + '.shell-extension.zip?' +
    Soup.form_encode_hash({shell_version: '51.1'}));
const zip = session.send_and_read(zipMessage, null).get_data();
if (zipMessage.status_code !== 200 || zipMessage.tls_peer_certificate_errors !== 0 ||
    zip.length < 4 || zip[0] !== 0x50 || zip[1] !== 0x4b)
    throw new Error('Extension archive HTTPS request failed');
print(JSON.stringify({tls: backend.constructor.name, uuid: info.uuid,
    metadata_status: infoMessage.status_code, archive_status: zipMessage.status_code,
    archive_bytes: zip.length, certificate_errors: zipMessage.tls_peer_certificate_errors}));
