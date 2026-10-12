/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <linux/capability.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	struct __user_cap_header_struct header = {
		.version = _LINUX_CAPABILITY_VERSION_3,
		.pid = 0,
	};
	struct __user_cap_data_struct caps[2] = { { 0 } };

	if (argc < 2 || getuid() < 1000 || getuid() != geteuid() || getegid() == 0) {
		fprintf(stderr, "desktop-no-caps: requires an ordinary user and a command\n");
		return 1;
	}
	/* pam_systemd can grant CAP_WAKE_ALARM to local-seat sessions. Bubblewrap
	 * requires a non-setuid ordinary user to enter with no capabilities.
	 * Keep the bounding set and normal exec semantics for FUSE helpers.
	 */
	if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) < 0 ||
	    syscall(SYS_capset, &header, caps) < 0) {
		perror("desktop-no-caps: clear capabilities");
		return 1;
	}
	execvp(argv[1], argv + 1);
	perror("desktop-no-caps: exec");
	return 1;
}
