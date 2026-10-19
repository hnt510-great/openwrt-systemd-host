#!/bin/sh
# Run on a matching target after installing native-build-deps.
set -eu

work_dir=$(mktemp -d /tmp/native-app-deps.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
cd "$work_dir"

modules='gio-unix-2.0 json-glib-1.0 gnutls nettle hogweed krb5 krb5-gssapi
pam libcrypt libcap libattr libacl dbus-1 libuv yaml-0.1 libxslt libexslt
libusb-1.0 libarchive'
pkg-config --exists $modules
pkg-config --modversion $modules
test "$(pkg-config --variable=gdbus_codegen gio-2.0)" = /usr/bin/gdbus-codegen
test "$(pkg-config --variable=glib_mkenums glib-2.0)" = /usr/bin/glib-mkenums

cat > probe.c <<'EOF'
#include <assert.h>
#include <gio/gunixinputstream.h>
#include <json-glib/json-glib.h>
#include <gnutls/gnutls.h>
#include <nettle/sha2.h>
#include <krb5.h>
#include <gssapi/gssapi.h>
#include <security/pam_appl.h>
#include <crypt.h>
#include <sys/capability.h>
#include <attr/libattr.h>
#include <sys/acl.h>
#include <dbus/dbus.h>
#include <uv.h>
#include <yaml.h>
#include <libxslt/xslt.h>
#include <libexslt/exslt.h>
#include <libusb.h>
#include <archive.h>

int main(void)
{
    struct sha256_ctx sha;
    krb5_context krb;
    OM_uint32 minor;
    gss_buffer_desc buffer = GSS_C_EMPTY_BUFFER;
    yaml_parser_t yaml;
    uv_loop_t loop;
    GInputStream *stream = g_unix_input_stream_new(0, FALSE);
    JsonNode *node = json_node_new(JSON_NODE_OBJECT);
    cap_t cap = cap_init();
    acl_t acl = acl_init(0);
    DBusMessage *message = dbus_message_new_signal("/probe", "org.example.Probe", "Ready");
    struct archive *archive = archive_write_new();
    assert(stream && node && cap && acl && message && archive);
    assert(gnutls_check_version(NULL));
    sha256_init(&sha);
    assert(krb5_init_context(&krb) == 0);
    krb5_free_context(krb);
    assert(gss_release_buffer(&minor, &buffer) == GSS_S_COMPLETE);
    assert(pam_strerror(NULL, PAM_SUCCESS));
    assert(crypt("native", "$6$native$"));
    (void)attr_copy_action("user.native", NULL);
    assert(uv_loop_init(&loop) == 0);
    assert(uv_loop_close(&loop) == 0);
    assert(yaml_parser_initialize(&yaml));
    yaml_parser_delete(&yaml);
    xsltInit();
    exsltRegisterAll();
    assert(libusb_get_version());
    assert(archive_write_free(archive) == ARCHIVE_OK);
    dbus_message_unref(message);
    cap_free(cap);
    acl_free(acl);
    json_node_free(node);
    g_object_unref(stream);
    xsltCleanupGlobals();
    return 0;
}
EOF
gcc -Wall -Wextra -Werror probe.c -o probe $(pkg-config --cflags --libs $modules)
./probe

cat > probe.xml <<'EOF'
<node><interface name="org.example.Probe"><method name="Ping"/></interface></node>
EOF
gdbus-codegen --generate-c-code generated probe.xml
gcc -Wall -Wextra -Werror -c generated.c $(pkg-config --cflags gio-2.0)
printf '%s\n' 'VOID:STRING' > marshal.list
glib-genmarshal --header marshal.list > marshal.h
glib-mkenums --version
printf '%s\n' '<gresources><gresource prefix="/probe"><file>probe.xml</file></gresource></gresources>' > resources.xml
glib-compile-resources --generate-source resources.xml
gcc -Wall -Wextra -Werror -c resources.c $(pkg-config --cflags gio-2.0)

# Exercise translation output and the installed gettext ITS data.
printf '%s\n' 'msgid "Native probe"' 'msgstr "Translated probe"' > probe.po
msgfmt -o probe.mo probe.po
printf '%s\n' 'fr' > LINGUAS
mkdir po
cp probe.po po/fr.po
cp LINGUAS po/LINGUAS
printf '%s\n' '<component type="generic"><id>org.example.Probe</id><name>Native probe</name></component>' > probe.metainfo.xml
msgfmt --xml --template=probe.metainfo.xml -d po -o translated.xml
grep -q 'Translated probe' translated.xml
echo 'Native application dependencies: PASS'
