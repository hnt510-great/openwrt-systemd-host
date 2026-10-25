// SPDX-License-Identifier: Apache-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void fail(const char *message)
{
	fprintf(stderr, "%s\n", message);
	exit(125);
}

static int runtime_available(const char *path, uid_t uid)
{
	struct stat st;

	/* A traversal-only ACL (e.g. libvirt PipeWire access) sets the group
	 * execute bit through the ACL mask. It grants no directory listing or
	 * modification. Keep rejecting group read/write and all other access. */
	return !lstat(path, &st) && S_ISDIR(st.st_mode) && st.st_uid == uid &&
	       !(st.st_mode & 0067);
}

/* Not setuid. Only rpcd/root may use this helper. Podman and all of its
 * children run with the selected account's real and effective IDs. */
int main(int argc, char **argv)
{
	struct passwd *pw;
	char runtime[64], bus[128];
	char **args;
	int i;

	if (getuid() != 0 || geteuid() != 0 || argc < 3)
		fail("Usage (root only): podman-luci-exec USER PODMAN_ARGUMENTS...");
	pw = getpwnam(argv[1]);
	if (!pw || pw->pw_uid < 1000 || pw->pw_gid == 0 || pw->pw_dir[0] != '/')
		fail("An existing ordinary account with an absolute home is required.");
	snprintf(runtime, sizeof(runtime), "/run/user/%lu", (unsigned long)pw->pw_uid);
	if (!runtime_available(runtime, pw->pw_uid))
		fail("User runtime directory unavailable. Log in through SSH/PAM first; on systemd, enable linger for persistent access.");
	snprintf(bus, sizeof(bus), "unix:path=%s/bus", runtime);
	if (initgroups(pw->pw_name, pw->pw_gid) || setgid(pw->pw_gid) || setuid(pw->pw_uid))
		fail("Unable to switch to the rootless account.");
	if (getuid() == 0 || geteuid() == 0 || getgid() == 0 || getegid() == 0)
		fail("Refusing to run Podman as root.");
	/* Ignore rpcd's HOME and remote/storage overrides. Keep the user's own
 * containers.conf and storage.conf by setting its actual home. */
	if (clearenv() || setenv("HOME", pw->pw_dir, 1) ||
	    setenv("USER", pw->pw_name, 1) || setenv("LOGNAME", pw->pw_name, 1) ||
	    setenv("PATH", "/usr/sbin:/usr/bin:/sbin:/bin", 1) ||
	    setenv("LC_ALL", "C", 1) || setenv("XDG_RUNTIME_DIR", runtime, 1) ||
	    setenv("DBUS_SESSION_BUS_ADDRESS", bus, 1) || chdir(pw->pw_dir))
		fail("Unable to initialize the rootless environment.");
	args = calloc(argc + 1, sizeof(*args));
	if (!args)
		fail("Out of memory.");
	args[0] = "/usr/bin/podman";
	args[1] = "--remote=false";
	for (i = 2; i < argc; i++)
		args[i] = argv[i];
	execv(args[0], args);
	fprintf(stderr, "Unable to execute Podman: %s\n", strerror(errno));
	return 125;
}
