// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <linux/magic.h>
#include <linux/openat2.h>
#include <poll.h>
#include <pwd.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <sys/vfs.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <json-c/json.h>
#include <libubus.h>
#include <libubox/blobmsg_json.h>
#include <systemd/sd-login.h>

#define RUNTIME "/run/openwrt-needrestart"
#define MAX_BYTES (4 * 1024 * 1024)
/* Kernel inventories contain per-file hashes for retained generations. Keep
 * their input bound separate from proc/command/report output bounds.
 */
#define MAX_KERNEL_BYTES (16 * 1024 * 1024)
#define MAX_PROCESSES 32768
#define MAX_FINDINGS 4096
#define MAX_WARNINGS 128

static const char *test_root = "";
static json_object *report, *warnings, *subjects, *containers, *owners, *packages;
static json_object *applications, *flatpak_owners;
static void unit_name(pid_t pid, char **unit, bool *user);
static int atomic_json(const char *name, json_object *o);
static bool partial;
static int64_t deadline;
static unsigned int scanned, skipped, unreadable;
static size_t evidence_bytes;

/* Reuse comparisons only while both open objects retain their metadata.
 * Browser children commonly map the same large host libraries.
 */
static struct {
	struct stat old, current;
	int result;
} comparisons[512];
static size_t comparison_count;

static int64_t millis(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static json_object *get(json_object *o, const char *key)
{
	json_object *v = NULL;

	if (o && json_object_is_type(o, json_type_object))
		json_object_object_get_ex(o, key, &v);
	return v;
}

static size_t length(json_object *o)
{
	return o && json_object_is_type(o, json_type_array) ? json_object_array_length(o) : 0;
}

static const char *str(json_object *o, const char *key)
{
	json_object *v = get(o, key);

	return v && json_object_is_type(v, json_type_string) ? json_object_get_string(v) : "";
}

static void string(json_object *o, const char *key, const char *s)
{
	json_object_object_add(o, key, json_object_new_string(s ? s : ""));
}

static void number(json_object *o, const char *key, int64_t n)
{
	json_object_object_add(o, key, json_object_new_int64(n));
}

static const char *path(const char *name)
{
	static char buffers[8][PATH_MAX];
	static unsigned int n;
	char *p = buffers[n++ % 8];

	if (snprintf(p, PATH_MAX, "%s%s", test_root, name) >= PATH_MAX) {
		fprintf(stderr, "Path too long\n");
		exit(1);
	}
	return p;
}

static void warn(const char *reason)
{
	partial = true;
	for (size_t i = 0; i < length(warnings); i++)
		if (!strcmp(json_object_get_string(json_object_array_get_idx(warnings, i)), reason))
			return;
	if (length(warnings) < MAX_WARNINGS)
		json_object_array_add(warnings, json_object_new_string(reason));
}

static char *read_fd(int fd, size_t limit)
{
	char *data = malloc(limit + 1);
	size_t n = 0;
	ssize_t r;

	if (!data)
		return NULL;
	while (n < limit) {
		r = read(fd, data + n, limit - n);
		if (r < 0 && errno == EINTR)
			continue;
		if (r < 0) {
			free(data);
			return NULL;
		}
		if (!r) {
			data[n] = 0;
			return data;
		}
		n += r;
	}
	free(data);
	errno = EFBIG;
	return NULL;
}

static char *read_file(const char *p, size_t limit)
{
	int fd = open(p, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	char *s;

	if (fd < 0)
		return NULL;
	s = read_fd(fd, limit);
	close(fd);
	return s;
}

static json_object *read_json_limit(const char *p, size_t limit)
{
	char *s = read_file(p, limit);
	json_object *o = s ? json_tokener_parse(s) : NULL;

	free(s);
	return o;
}

static json_object *read_json(const char *p)
{
	return read_json_limit(p, MAX_BYTES);
}

static void save_error(const char *message)
{
	json_object *o = json_object_new_object();

	string(o, "error", message);
	number(o, "timestamp", time(NULL));
	atomic_json(RUNTIME "/error.json", o);
	json_object_put(o);
}

static bool valid_name(const char *s)
{
	if (!*s || strlen(s) > 200 || !isalnum((unsigned char)*s))
		return false;
	for (; *s; s++)
		if (!isalnum((unsigned char)*s) && !strchr("_.@:+-\\", *s))
			return false;
	return true;
}

/* No shell, inherited environment, container executables, or registry operations.
 * Rootless inspection drops all groups and both real/effective credentials.
 */
static char *command(uid_t uid, char *const argv[], int timeout)
{
	struct passwd *pw = getpwuid(uid);
	char home[PATH_MAX + 6], user[256], runtime[80];
	char *const env[] = {
	    "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL=C", home, user, runtime, NULL};
	int fds[2], status = 0;
	char *output;
	size_t n = 0;
	pid_t pid, done = 0;
	int64_t end = millis() + timeout;

	if (!pw || end > deadline)
		end = deadline;
	if (!pw || millis() >= end || pipe2(fds, O_CLOEXEC | O_NONBLOCK))
		return NULL;
	snprintf(home, sizeof(home), "HOME=%s", pw->pw_dir);
	snprintf(user, sizeof(user), "USER=%s", pw->pw_name);
	if (uid)
		snprintf(runtime, sizeof(runtime), "XDG_RUNTIME_DIR=/run/user/%u", uid);
	else
		snprintf(runtime, sizeof(runtime), "XDG_RUNTIME_DIR=/run");
	pid = fork();
	if (!pid) {
		int nullfd;

		setpgid(0, 0);
		fcntl(fds[1], F_SETFL, 0);
		dup2(fds[1], STDOUT_FILENO);
		nullfd = open("/dev/null", O_RDWR);
		if (nullfd < 0)
			_exit(126);
		dup2(nullfd, STDIN_FILENO);
		dup2(nullfd, STDERR_FILENO);
		close(nullfd);
		close(fds[0]);
		close(fds[1]);
		if (geteuid() == 0 &&
		    (setgroups(0, NULL) || setresgid(pw->pw_gid, pw->pw_gid, pw->pw_gid) ||
		     setresuid(uid, uid, uid)))
			_exit(126);
		execve(argv[0], argv, env);
		_exit(127);
	}
	close(fds[1]);
	if (pid < 0) {
		close(fds[0]);
		return NULL;
	}
	setpgid(pid, pid);
	output = malloc(MAX_BYTES + 1);
	while (output && millis() < end && n < MAX_BYTES) {
		ssize_t r = read(fds[0], output + n, MAX_BYTES - n);

		if (r > 0) {
			n += r;
			continue;
		}
		if (r == 0 && done)
			break;
		if (r < 0 && errno != EAGAIN && errno != EINTR)
			break;
		if (!done)
			done = waitpid(pid, &status, WNOHANG);
		struct pollfd p = {.fd = fds[0], .events = POLLIN};

		poll(&p, 1, 20);
	}
	close(fds[0]);
	if (!done)
		done = waitpid(pid, &status, WNOHANG);
	if (done <= 0 || n == MAX_BYTES || millis() >= end || !WIFEXITED(status) ||
	    WEXITSTATUS(status)) {
		kill(-pid, SIGKILL);
		if (done <= 0)
			waitpid(pid, &status, WNOHANG);
		free(output);
		return NULL;
	}
	if (output)
		output[n] = 0;
	return output;
}

static json_object *command_json(uid_t uid, char *const argv[])
{
	char *data = command(uid, argv, 4000);
	json_object *o = data ? json_tokener_parse(data) : NULL;

	free(data);
	return o;
}

static void ubus_reply(struct ubus_request *req, int type, struct blob_attr *msg)
{
	char *s;
	json_object **result = req->priv;
	(void)type;
	s = blobmsg_format_json(msg, true);
	if (s) {
		if (*result)
			json_object_put(*result);
		*result = json_tokener_parse(s);
		free(s);
	}
}

static json_object *procd_snapshot(void)
{
	struct ubus_context *ctx;
	struct blob_buf b = {};
	uint32_t id;
	json_object *o = NULL;
	int ret;
#ifdef NEEDRESTART_TEST
	if (*test_root)
		return read_json(path("/ubus.json"));
#endif
	ctx = ubus_connect(NULL);
	if (!ctx)
		return NULL;
	ret = ubus_lookup_id(ctx, "service", &id);
	if (!ret) {
		blob_buf_init(&b, 0);
		blobmsg_add_u8(&b, "verbose", true);
		ret = ubus_invoke(ctx, id, "list", b.head, ubus_reply, &o, 1500);
		blob_buf_free(&b);
	}
	ubus_free(ctx);
	if (ret && o) {
		json_object_put(o);
		o = NULL;
	}
	return o;
}

/* Parse installed file ownership without recursively invoking APK under its lock. */
static void package_index(void)
{
	FILE *f = fopen(path("/lib/apk/db/installed"), "r");
	char *line = NULL, name[256] = "", version[256] = "", dir[PATH_MAX] = "";
	size_t cap = 0;
	ssize_t n;

	packages = json_object_new_object();
	if (!f) {
		warn("Host APK file ownership unavailable");
		return;
	}
	while ((n = getline(&line, &cap, f)) > 0) {
		if (millis() > deadline || n > PATH_MAX) {
			warn("APK ownership parsing limit reached");
			break;
		}
		line[strcspn(line, "\r\n")] = 0;
		if (!*line) {
			name[0] = version[0] = dir[0] = 0;
			continue;
		}
		if (line[1] != ':')
			continue;
		switch (line[0]) {
		case 'P':
			snprintf(name, sizeof(name), "%s", line + 2);
			break;
		case 'V':
			snprintf(version, sizeof(version), "%s", line + 2);
			break;
		case 'F':
			snprintf(dir, sizeof(dir), "%s", line + 2);
			break;
		case 'R': {
			char file[PATH_MAX];
			json_object *owner;

			if (!*name || snprintf(file, sizeof(file), "/%s%s%s", dir, *dir ? "/" : "",
					       line + 2) >= (int)sizeof(file))
				break;
			owner = json_object_new_object();
			string(owner, "name", name);
			string(owner, "installed_version", version);
			json_object_object_add(packages, file, owner);
			break;
		}
		}
	}
	free(line);
	fclose(f);
}

static char *proc_read(pid_t pid, const char *file, size_t max)
{
	char p[128];

	snprintf(p, sizeof(p), "/proc/%d/%s", pid, file);
	return read_file(path(p), max);
}

static uint64_t start_time(pid_t pid)
{
	char *data = proc_read(pid, "stat", 8192), *p, *save, *word;
	uint64_t result = 0;
	int field = 3;

	if (!data)
		return 0;
	p = strrchr(data, ')');
	if (p)
		for (word = strtok_r(p + 1, " ", &save); word;
		     word = strtok_r(NULL, " ", &save), field++)
			if (field == 22) {
				result = strtoull(word, NULL, 10);
				break;
			}
	free(data);
	return result;
}

static char *group(pid_t pid)
{
	char *data = proc_read(pid, "cgroup", 65536), *p, *s = NULL;

	p = data ? strstr(data, "0::/") : NULL;
	if (p) {
		p += 3;
		p[strcspn(p, "\r\n")] = 0;
		s = strdup(p);
	}
	free(data);
	return s;
}

static void container_id(const char *cg, char id[65])
{
	const char *p = cg;

	id[0] = 0;
	while (p && (p = strstr(p, "/libpod-"))) {
		bool payload;

		p += 8;
		payload = !strncmp(p, "payload-", 8);
		if (payload)
			p += 8;
		if (strspn(p, "0123456789abcdef") != 64)
			continue;
		const char *end = p + 64;

		if (!payload && !strncmp(end, ".scope", 6))
			end += 6;
		else if (!payload)
			continue;
		if (*end && *end != '/' && *end != '\n')
			continue;
		memcpy(id, p, 64);
		id[64] = 0;
		return;
	}
}

static uid_t container_uid(const char *cg)
{
	const char *p = cg ? strstr(cg, "/user-") : NULL;
	char *end;
	unsigned long uid;

	if (!p)
		return 0;
	uid = strtoul(p + 6, &end, 10);
	return !strncmp(end, ".slice/", 7) && uid <= UINT_MAX ? (uid_t)uid : 0;
}

static json_object *container_find(const char *id, uid_t uid)
{
	for (size_t i = 0; i < length(containers); i++) {
		json_object *o = json_object_array_get_idx(containers, i);

		if (!strcmp(str(o, "id"), id) && json_object_get_int64(get(o, "uid")) == uid)
			return o;
	}
	return NULL;
}

static const char *image_id(json_object *o)
{
	const char *s = str(o, "Id");

	if (!*s)
		s = str(o, "ID");
	return !strncmp(s, "sha256:", 7) ? s + 7 : s;
}

static void add_store(uid_t uid, json_object *list, json_object *images)
{
	if (!list || !json_object_is_type(list, json_type_array) || !images ||
	    !json_object_is_type(images, json_type_array)) {
		warn("Podman inventory incomplete; container image freshness is unassessed");
		return;
	}
	for (size_t i = 0; i < length(list); i++) {
		json_object *c = json_object_array_get_idx(list, i), *state = get(c, "State");
		const char *id = str(c, "Id"), *ref = str(c, "ImageName"), *local = NULL;

		if (!json_object_get_boolean(get(state, "Running")))
			continue;
		if (strlen(id) != 64 || strspn(id, "0123456789abcdef") != 64)
			continue;
		if (length(containers) >= 512 || strlen(ref) > 1024 ||
		    strlen(str(c, "Name")) > 256) {
			warn("Container inventory size limit reached");
			continue;
		}
		json_object *o = json_object_new_object();

		string(o, "id", id);
		number(o, "uid", uid);
		struct passwd *pw = getpwuid(uid);

		string(o, "account", pw ? pw->pw_name : "unknown");
		string(o, "name", str(c, "Name"));
		string(o, "image_reference", ref);
		string(o, "running_image", str(c, "Image"));
		string(o, "image_status", "unknown");
		number(o, "init_pid", json_object_get_int64(get(state, "Pid")));
		pid_t conmon = json_object_get_int64(get(state, "ConmonPid"));
		char *comm = conmon > 0 ? proc_read(conmon, "comm", 128) : NULL;

		if (comm && !strncmp(comm, "conmon", 6)) {
			char *unit;
			bool user_unit;

			unit_name(conmon, &unit, &user_unit);
			if (unit && valid_name(unit) && strlen(unit) > 8 &&
			    !strcmp(unit + strlen(unit) - 8, ".service") &&
			    user_unit == (uid != 0)) {
				string(o, "controller", unit);
				json_object_object_add(o, "controller_is_user_unit",
						       json_object_new_boolean(user_unit));
			}
			free(unit);
		}
		free(comm);
		/* Match the exact stored reference only, never a registry search or date.
		 */
		for (size_t j = 0; j < length(images); j++) {
			json_object *img = json_object_array_get_idx(images, j),
				    *names = get(img, "Names");
			for (size_t k = 0; k < length(names); k++)
				if (*ref &&
				    json_object_is_type(json_object_array_get_idx(names, k),
							json_type_string) &&
				    !strcmp(
					json_object_get_string(json_object_array_get_idx(names, k)),
					ref))
					local = image_id(img);
		}
		if (json_object_get_boolean(get(c, "IsInfra")) && !*ref &&
		    !*str(c, "Image") && *str(c, "Rootfs")) {
			string(o, "image_status", "current");
		} else if (strchr(ref, '@')) {
			string(o, "image_status", "digest-pinned");
		} else if (local && *local) {
			const char *running = str(c, "Image");

			if (!strncmp(running, "sha256:", 7))
				running += 7;
			string(o, "local_image", local);
			string(o, "image_status", !strcmp(local, running) ? "current" : "changed");
		} else {
			warn("A container image reference is unavailable locally; image freshness is unassessed");
		}
		json_object_array_add(containers, o);
	}
}

static void podman_inventory(void)
{
	json_object *uids = json_object_new_object();
	DIR *d = opendir(path("/proc"));
	struct dirent *e;
#ifdef NEEDRESTART_TEST
	if (*test_root) {
		json_object *stores = read_json(path("/podman.json"));

		for (size_t i = 0; i < length(stores); i++) {
			json_object *s = json_object_array_get_idx(stores, i);

			add_store(json_object_get_int64(get(s, "uid")), get(s, "containers"),
				  get(s, "images"));
		}
		if (stores)
			json_object_put(stores);
		if (d)
			closedir(d);
		json_object_put(uids);
		return;
	}
#endif
	if (!d) {
		warn("Cannot enumerate host processes");
		json_object_put(uids);
		return;
	}
	/* Inspect only stores with live observed containers. Never initialize stores
	 * by probing every account or starting a Podman API socket.
	 */
	unsigned int count = 0;

	while ((e = readdir(d)) && count++ < MAX_PROCESSES && millis() < deadline) {
		char *cg, id[65], key[32];

		if (!isdigit((unsigned char)e->d_name[0]))
			continue;
		cg = group(atoi(e->d_name));
		container_id(cg, id);
		if (*id) {
			snprintf(key, sizeof(key), "%u", container_uid(cg));
			number(uids, key, container_uid(cg));
		}
		free(cg);
	}
	if (e)
		warn("Container process discovery limit reached");
	closedir(d);
	json_object_object_foreach(uids, key, value)
	{
		uid_t uid = json_object_get_int64(value);
		static char *const ps[] = {"/usr/bin/podman", "ps",   "--no-trunc",
					   "--format",	      "json", NULL};
		static char *const ls[] = {"/usr/bin/podman", "images", "--no-trunc",
					   "--format",	      "json",	NULL};
		json_object *pids = command_json(uid, ps), *images = command_json(uid, ls),
			    *list = NULL;
		(void)key;
		if (pids && json_object_is_type(pids, json_type_array) && length(pids) <= 512) {
			char *argv[517] = {"/usr/bin/podman", "container", "inspect"};
			size_t n = 3;

			for (size_t j = 0; j < length(pids); j++) {
				const char *id = image_id(json_object_array_get_idx(pids, j));

				if (strlen(id) == 64 && strspn(id, "0123456789abcdef") == 64)
					argv[n++] = (char *)id;
			}
			argv[n] = NULL;
			list = n > 3 ? command_json(uid, argv) : json_object_new_array();
		}
		add_store(uid, list, images);
		if (list)
			json_object_put(list);
		if (images)
			json_object_put(images);
		if (pids)
			json_object_put(pids);
	}
	json_object_put(uids);
}

static void unit_name(pid_t pid, char **unit, bool *user)
{
	*unit = NULL;
	*user = false;
#ifdef NEEDRESTART_TEST
	if (*test_root) {
		char key[32];

		snprintf(key, sizeof(key), "%d", pid);
		json_object *o = get(owners, key);
		*unit = strdup(str(o, "unit"));
		*user = json_object_get_boolean(get(o, "user"));
		return;
	}
#endif
	if (sd_pid_get_user_unit(pid, unit) >= 0) {
		*user = true;
		return;
	}
	sd_pid_get_unit(pid, unit);
}

static void unescape(char *s)
{
	char *out = s;

	for (char *p = s; *p; p++) {
		unsigned int v;

		if (p[0] == '\\' && p[1] == 'x' && isxdigit((unsigned char)p[2]) &&
		    isxdigit((unsigned char)p[3]) && sscanf(p + 2, "%2x", &v) == 1 && v &&
		    v < 128) {
			*out++ = v;
			p += 3;
		} else if (p[0] == '\\' && p[1] >= '0' && p[1] <= '7' && p[2] >= '0' &&
			   p[2] <= '7' && p[3] >= '0' && p[3] <= '7') {
			v = (p[1] - '0') * 64 + (p[2] - '0') * 8 + p[3] - '0';
			*out++ = v ? (char)v : '?';
			p += 3;
		} else {
			*out++ = *p;
		}
	}
	*out = 0;
}

static const char *procd_name(pid_t pid, const char *cg, json_object *snap, char name[256])
{
	/* The service slice also accounts for double forks and legacy scripts. */
	const char *p = cg ? strstr(cg, "/openwrt.slice/openwrt-") : NULL;

	if (p) {
		p += strlen("/openwrt.slice/openwrt-");
		const char *end = strstr(p, ".slice/");

		if (end && end - p < 256) {
			memcpy(name, p, end - p);
			name[end - p] = 0;
			unescape(name);
			if (valid_name(name))
				return name;
		}
	}
	if (snap) {
		json_object_object_foreach(snap, service, data)
		{
			json_object *instances = get(data, "instances");

			if (!instances || !valid_name(service))
				continue;
			json_object_object_foreach(instances, instance, detail)
			{
				(void)instance;
				if (json_object_get_int64(get(detail, "pid")) == pid &&
				    json_object_get_boolean(get(detail, "running")))
					return service;
			}
		}
	}
	return NULL;
}

static json_object *subject(pid_t pid, const char *cg, json_object *snap, bool host)
{
	char id[65], name[256], key[512], action[512] = "";
	const char *kind = "unmanaged", *display = NULL;
	char *unit = NULL;
	bool user = false, disruptive = false;
	uid_t uid = 0;
	struct stat st;
	char proc[64];

	snprintf(proc, sizeof(proc), "/proc/%d", pid);
	if (!stat(path(proc), &st))
		uid = st.st_uid;
	container_id(cg, id);
	char pidkey[32];

	snprintf(pidkey, sizeof(pidkey), "%d", pid);
	json_object *application = get(flatpak_owners, pidkey);
	const char *procd = procd_name(pid, cg, snap, name);

	if (*id) {
		kind = "container";
		display = id;
		uid = container_uid(cg);
		snprintf(action, sizeof(action),
			 "Restart affected code through the container's deployment controller (account UID %u)",
			 uid);
	} else if (application) {
		kind = "flatpak";
		display = str(application, "name");
		snprintf(action, sizeof(action),
			 "Close and relaunch Flatpak application '%s' as account UID %u", display, uid);
	} else if (procd) {
		display = procd;
		kind = "procd";
		snprintf(action, sizeof(action), "/etc/init.d/%s restart", display);
	} else if (!host) {
		kind = "isolated";
		snprintf(name, sizeof(name), "PID %d", pid);
		display = name;
		snprintf(action, sizeof(action),
			 "Identify the jail/container owner and restart through its deployment controller");
	} else {
		unit_name(pid, &unit, &user);
		if (unit && valid_name(unit) && strlen(unit) > 8 &&
		    !strcmp(unit + strlen(unit) - 8, ".service") && strncmp(unit, "user@", 5) &&
		    strcmp(unit, "openwrt-services.service")) {
			kind = user ? "user-service" : "systemd";
			display = unit;
			snprintf(action, sizeof(action),
				 user ? "As owning user: systemctl --user restart '%s'"
				      : "systemctl restart '%s'",
				 unit);
		} else if (cg && strstr(cg, "/user.slice/")) {
			kind = "session";
			display = unit && valid_name(unit) ? unit : "user-session";
			snprintf(action, sizeof(action),
				 "Restart the affected application or log out and log back in");
		}
	}
	if (!display) {
		snprintf(name, sizeof(name), "PID %d", pid);
		display = name;
		snprintf(action, sizeof(action),
			 "Identify the process owner and restart through its lifecycle controller");
	}
	if (pid == 1 || !strcmp(display, "openwrt-procd.service") || !strcmp(display, "procd") ||
	    !strcmp(display, "dbus.service") || !strcmp(display, "openwrt-ubusd.service")) {
		disruptive = true;
		snprintf(action, sizeof(action),
			 "Maintenance review required: service supervisor or system infrastructure; do not restart as an ordinary service");
	} else if (strstr(display, "network") || strstr(display, "firewall") ||
		   strstr(display, "dropbear") || strstr(display, "sshd") ||
		   strstr(display, "rpcd") || strstr(display, "dnsmasq")) {
		disruptive = true;
	}
	if (!strcmp(kind, "procd") || !strcmp(kind, "systemd"))
		uid = 0;
	snprintf(key, sizeof(key), "%s:%u:%s", kind, uid, display);
	json_object *o = get(subjects, key);

	if (!o) {
		o = json_object_new_object();
		string(o, "kind", kind);
		string(o, "name", display);
		number(o, "uid", uid);
		string(o, "recommended_action", action);
		json_object_object_add(o, "disruptive", json_object_new_boolean(disruptive));
		json_object_object_add(o, "processes", json_object_new_array());
		if (application)
			json_object_object_add(o, "application", json_object_get(application));
		if (*id) {
			json_object *c = container_find(id, uid);

			if (c)
				json_object_object_add(o, "container", json_object_get(c));
		}
		json_object_object_add(subjects, key, o);
	}
	free(unit);
	return o;
}

/* Absolute symlinks must resolve inside the inspected root. Never concatenate
 * /proc/PID/root with an attacker-controlled absolute symlink.
 */
static int rooted_open(int root, const char *p)
{
	struct open_how how = {.flags = O_RDONLY | O_CLOEXEC | O_NONBLOCK,
			       .resolve = RESOLVE_IN_ROOT | RESOLVE_NO_MAGICLINKS};
	return syscall(SYS_openat2, root, p, &how, sizeof(how));
}

static bool elf(int fd)
{
	unsigned char magic[4];

	return pread(fd, magic, sizeof(magic), 0) == sizeof(magic) && !memcmp(magic, "\177ELF", 4);
}

static bool same_object(const struct stat *a, const struct stat *b)
{
	return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_size == b->st_size &&
	       a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
	       a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}

/* 1: verified different bytes, 0: identical, -1: unable to establish. */
static int different(int old, int current)
{
	struct stat a, b, after_a, after_b;
	char x[65536], y[65536];
	int result = 0;

	if (fstat(old, &a) || fstat(current, &b) || !S_ISREG(a.st_mode) || !S_ISREG(b.st_mode) ||
	    !elf(old) || !elf(current))
		return -1;
	if (a.st_size != b.st_size)
		return 1;
	if (same_object(&a, &b))
		return 0;
	for (size_t i = 0; i < comparison_count; i++)
		if (same_object(&a, &comparisons[i].old) &&
		    same_object(&b, &comparisons[i].current))
			return comparisons[i].result;
	/* Large native executables are common. Stream with fixed buffers and
	 * the existing deadline rather than treating size alone as unverified.
	 */
	for (off_t n = 0; n < a.st_size;) {
		size_t size =
		    a.st_size - n < (off_t)sizeof(x) ? (size_t)(a.st_size - n) : sizeof(x);
		if (millis() > deadline || pread(old, x, size, n) != (ssize_t)size ||
		    pread(current, y, size, n) != (ssize_t)size)
			return -1;
		if (memcmp(x, y, size)) {
			result = 1;
			break;
		}
		n += size;
	}
	if (fstat(old, &after_a) || fstat(current, &after_b) ||
	    !same_object(&a, &after_a) || !same_object(&b, &after_b))
		return -1;
	if (comparison_count < 512) {
		comparisons[comparison_count].old = a;
		comparisons[comparison_count].current = b;
		comparisons[comparison_count++].result = result;
	}
	return result;
}

/* Firefox and Chrome children chroot into a vanished /proc/PID/fdinfo.
 * Host-path inspection requires the host mount namespace, a live same-user
 * parent chain rooted at the host filesystem, and the exact same executable
 * object. These checks also permit reporting an old, replaced browser
 * executable.
 */
static bool sandbox_host_browser(pid_t pid, const char *exe, int root)
{
	static const char *const binaries[] = {
	    "/usr/lib/firefox-esr/firefox-bin", "/opt/google/chrome/chrome", NULL};
	struct stat child, parent, host, parent_root, ns, host_ns, parent_ns, a, b;
	struct statfs fs;
	char proc[96], target[PATH_MAX], parent_target[PATH_MAX], *data, *end;
	pid_t current = pid, ppid, sandbox_pid;
	uint64_t parent_start;
	bool known = false;
	int n = 0;
	ssize_t len;

	for (size_t i = 0; binaries[i]; i++) {
		size_t m = strlen(binaries[i]);

		if (!strncmp(exe, binaries[i], m) &&
		    (!exe[m] || !strcmp(exe + m, " (deleted)")))
			known = true;
	}
	if (!known)
		return false;
	if (fstatfs(root, &fs))
		return false;
#ifdef NEEDRESTART_TEST
	if (!*test_root)
#endif
		if (fs.f_type != PROC_SUPER_MAGIC)
			return false;
	snprintf(proc, sizeof(proc), "/proc/%d/root", pid);
	len = readlink(path(proc), target, sizeof(target) - 1);
	if (len < 0)
		return false;
	target[len] = 0;
#ifdef NEEDRESTART_TEST
	if (*test_root && !strncmp(target, test_root, strlen(test_root)))
		memmove(target, target + strlen(test_root), strlen(target + strlen(test_root)) + 1);
#endif
	if (sscanf(target, "/proc/%d/fdinfo%n", &sandbox_pid, &n) != 1 ||
	    sandbox_pid <= 0 || !n || target[n])
		return false;
	snprintf(proc, sizeof(proc), "/proc/%d", pid);
	if (stat(path(proc), &child) || !child.st_uid)
		return false;
	if (stat(path("/"), &host) || stat(path("/proc/self/ns/mnt"), &host_ns))
		return false;
	snprintf(proc, sizeof(proc), "/proc/%d/ns/mnt", pid);
	if (stat(path(proc), &ns) || ns.st_dev != host_ns.st_dev ||
	    ns.st_ino != host_ns.st_ino)
		return false;
#ifdef NEEDRESTART_TEST
	const char *object = *test_root ? "test-exe" : "exe";
#else
	const char *object = "exe";
#endif
	snprintf(proc, sizeof(proc), "/proc/%d/%s", pid, object);
	if (stat(path(proc), &a) || !S_ISREG(a.st_mode))
		return false;
	for (unsigned int depth = 0; depth < 4; depth++, current = ppid) {
		uint64_t current_start = start_time(current);

		data = proc_read(current, "stat", 65536);
		end = data ? strrchr(data, ')') : NULL;
		bool parsed = end && sscanf(end + 1, " %*c %d", &ppid) == 1 && ppid > 1;

		free(data);
		if (!current_start || !parsed || current_start != start_time(current))
			return false;
		parent_start = start_time(ppid);
		if (!parent_start)
			return false;
		snprintf(proc, sizeof(proc), "/proc/%d", ppid);
		if (stat(path(proc), &parent) || child.st_uid != parent.st_uid)
			return false;
		snprintf(proc, sizeof(proc), "/proc/%d/ns/mnt", ppid);
		if (stat(path(proc), &parent_ns) || parent_ns.st_dev != host_ns.st_dev ||
		    parent_ns.st_ino != host_ns.st_ino)
			return false;
		snprintf(proc, sizeof(proc), "/proc/%d/%s", ppid, object);
		if (stat(path(proc), &b) || a.st_dev != b.st_dev || a.st_ino != b.st_ino)
			return false;
		snprintf(proc, sizeof(proc), "/proc/%d/root", ppid);
		if (!stat(path(proc), &parent_root) && host.st_dev == parent_root.st_dev &&
		    host.st_ino == parent_root.st_ino)
			return parent_start == start_time(ppid);
		len = readlink(path(proc), parent_target, sizeof(parent_target) - 1);
		if (len < 0)
			return false;
		parent_target[len] = 0;
#ifdef NEEDRESTART_TEST
		if (*test_root && !strncmp(parent_target, test_root, strlen(test_root)))
			memmove(parent_target, parent_target + strlen(test_root),
				strlen(parent_target + strlen(test_root)) + 1);
#endif
		if (strcmp(parent_target, target) || parent_start != start_time(ppid))
			return false;
	}
	return false;
}

/* Podman's bridge networks share one pasta process outside container units.
 * Correlate its owned PID record and user namespace with live inventoried
 * container processes; a scope name or executable name alone is insufficient.
 */
static bool shared_network_helper(pid_t pid, uid_t uid, const char *cg)
{
	char file[PATH_MAX], id[65], *data, *end;
	struct stat record, helper, ns, process;
	const char *scope = strrchr(cg, '/');
	bool matched = false;
	int fd;

	if (!scope || strncmp(scope, "/rootless-netns-", 16))
		return false;
	scope += 16;
	size_t n = strspn(scope, "0123456789abcdef");

	if (!n || n > 64 || strcmp(scope + n, ".scope"))
		return false;
	snprintf(file, sizeof(file),
		 "/run/user/%u/containers/networks/rootless-netns/rootless-netns-conn.pid", uid);
	fd = open(path(file), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
	if (fd < 0)
		return false;
	bool owned = !fstat(fd, &record) && S_ISREG(record.st_mode) &&
		     record.st_uid == uid && !(record.st_mode & 0022);
	char buffer[32];
	ssize_t len = owned ? read(fd, buffer, sizeof(buffer) - 1) : -1;

	close(fd);
	if (len <= 0)
		return false;
	buffer[len] = 0;
	long recorded = strtol(buffer, &end, 10);

	if (end == buffer || (*end && strcmp(end, "\n")) || recorded != pid)
		return false;
	snprintf(file, sizeof(file), "/proc/%d/ns/user", pid);
	if (stat(path(file), &helper))
		return false;
	for (size_t i = 0; i < length(containers); i++) {
		json_object *c = json_object_array_get_idx(containers, i);
		int64_t init = json_object_get_int64(get(c, "init_pid"));

		if (json_object_get_int64(get(c, "uid")) != uid || init <= 0 || init > INT_MAX)
			continue;
		uint64_t start = start_time(init);

		snprintf(file, sizeof(file), "/proc/%d", (int)init);
		if (!start || stat(path(file), &process) || process.st_uid != uid)
			continue;
		data = group(init);
		container_id(data, id);
		free(data);
		if (strcmp(id, str(c, "id")))
			continue;
		snprintf(file, sizeof(file), "/proc/%d/ns/user", (int)init);
		if (!stat(path(file), &ns) && helper.st_dev == ns.st_dev &&
		    helper.st_ino == ns.st_ino && start == start_time(init)) {
			matched = true;
			break;
		}
	}
	return matched;
}

/* Rootless network helpers pivot into an empty tmpfs after loading host code.
 * Treat it as a host helper only when its executable matches the installed
 * host binary and its user unit or shared network owns inventoried containers.
 * Other isolated roots retain the normal, conservative coverage warning.
 */
static bool sandbox_host_helper(pid_t pid, const char *cg, const char *exe, int root)
{
	uid_t uid = container_uid(cg);
	struct stat st;
	struct statfs fs;
	char proc[96], suffix[300];
	bool controller = false, identical;
	bool known = false;
	int old, current;
	static const char *const executables[] = {
	    "/usr/bin/slirp4netns", "/usr/bin/passt", "/usr/bin/passt.avx2",
	    "/usr/bin/pasta", "/usr/bin/pasta.avx2", NULL};

	for (size_t i = 0; executables[i]; i++)
		if (!strcmp(exe, executables[i]))
			known = true;
	if (!uid || !known)
		return false;
	snprintf(proc, sizeof(proc), "/proc/%d", pid);
	if (stat(path(proc), &st) || st.st_uid != uid)
		return false;
	if (fstatfs(root, &fs))
		return false;
#ifdef NEEDRESTART_TEST
	if (!*test_root)
#endif
		if (fs.f_type != TMPFS_MAGIC)
			return false;
	for (size_t i = 0; i < length(containers); i++) {
		json_object *c = json_object_array_get_idx(containers, i);
		const char *unit = str(c, "controller");

		if (json_object_get_int64(get(c, "uid")) != uid || !valid_name(unit) ||
		    !json_object_get_boolean(get(c, "controller_is_user_unit")))
			continue;
		for (unsigned int j = 0; j < 2; j++) {
			snprintf(suffix, sizeof(suffix), j ? "/%s" : "/%s/runtime", unit);
			size_t n = strlen(cg), m = strlen(suffix);

			if (n >= m && !strcmp(cg + n - m, suffix))
				controller = true;
		}
	}
	if (!controller && !shared_network_helper(pid, uid, cg))
		return false;
	snprintf(proc, sizeof(proc), "/proc/%d/exe", pid);
#ifdef NEEDRESTART_TEST
	if (*test_root)
		snprintf(proc, sizeof(proc), "/proc/%d/test-exe", pid);
#endif
	old = open(path(proc), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	current = open(path(exe), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	identical = old >= 0 && current >= 0 && different(old, current) == 0;
	if (old >= 0)
		close(old);
	if (current >= 0)
		close(current);
	return identical;
}

/* Native system services may chroot after loading their code; rtkit-daemon
 * enters /proc. Their mapped paths are relative to the root of the service's
 * mount namespace, which systemd sandboxing clones from the host. Resolve them
 * there only for a system .service unit that owns the process's cgroup, shares
 * the host user namespace, and whose namespace root is the host root object.
 * A short-lived child joins only that mount namespace to return an O_PATH
 * descriptor for "/"; it executes nothing and performs no other lookups.
 */
static int service_namespace_root(pid_t pid, const char *cg)
{
	char *unit = NULL, proc[96];
	bool user = false, owned = false;
	struct stat ns, host_ns, nsroot, hostroot;
	int result = -1;

	unit_name(pid, &unit, &user);
	if (unit && !user && valid_name(unit) && strlen(unit) > 8 &&
	    !strcmp(unit + strlen(unit) - 8, ".service") && strncmp(unit, "user@", 5) &&
	    strcmp(unit, "openwrt-services.service") && cg) {
		size_t n = strlen(unit);

		for (const char *p = cg; (p = strchr(p, '/')); p++)
			if (!strncmp(p + 1, unit, n) && (!p[n + 1] || p[n + 1] == '/'))
				owned = true;
	}
	free(unit);
	if (!owned)
		return -1;
	snprintf(proc, sizeof(proc), "/proc/%d/ns/user", pid);
	if (stat(path(proc), &ns) || stat(path("/proc/self/ns/user"), &host_ns) ||
	    ns.st_dev != host_ns.st_dev || ns.st_ino != host_ns.st_ino ||
	    stat(path("/"), &hostroot))
		return -1;
#ifdef NEEDRESTART_TEST
	if (*test_root) {
		snprintf(proc, sizeof(proc), "/proc/%d/test-ns-root", pid);
		result = open(path(proc), O_PATH | O_DIRECTORY | O_CLOEXEC);
		goto verify;
	}
#endif
	int fds[2], status;
	pid_t child;

	if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, fds))
		return -1;
	child = fork();
	if (!child) {
		int reply = fcntl(fds[1], F_DUPFD_CLOEXEC, 10), target, dir;
		char data = 0;
		union {
			char buffer[CMSG_SPACE(sizeof(int))];
			struct cmsghdr align;
		} control = {0};
		struct iovec iov = {.iov_base = &data, .iov_len = 1};
		struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
				     .msg_control = control.buffer,
				     .msg_controllen = sizeof(control.buffer)};
		struct cmsghdr *c = CMSG_FIRSTHDR(&msg);

		snprintf(proc, sizeof(proc), "/proc/%d/ns/mnt", pid);
		target = open(proc, O_RDONLY | O_CLOEXEC);
		if (reply < 0 || target < 0 || dup2(reply, 3) < 0 || dup2(target, 4) < 0 ||
		    syscall(SYS_close_range, 5, UINT_MAX, 0) || setns(4, CLONE_NEWNS))
			_exit(126);
		dir = open("/", O_PATH | O_DIRECTORY | O_CLOEXEC);
		if (dir < 0)
			_exit(126);
		c->cmsg_level = SOL_SOCKET;
		c->cmsg_type = SCM_RIGHTS;
		c->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(c), &dir, sizeof(int));
		_exit(sendmsg(3, &msg, MSG_NOSIGNAL) == 1 ? 0 : 126);
	}
	close(fds[1]);
	if (child > 0) {
		struct pollfd p = {.fd = fds[0], .events = POLLIN};
		int64_t end = millis() + 1000;

		if (end > deadline)
			end = deadline;
		while (millis() < end) {
			int remaining = end - millis(), ready;
			char data;
			union {
				char buffer[CMSG_SPACE(sizeof(int))];
				struct cmsghdr align;
			} control;
			struct iovec iov = {.iov_base = &data, .iov_len = 1};
			struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
					     .msg_control = control.buffer,
					     .msg_controllen = sizeof(control.buffer)};

			if (remaining <= 0)
				break;
			ready = poll(&p, 1, remaining);
			if (ready < 0 && errno == EINTR)
				continue;
			if (ready <= 0 || !(p.revents & POLLIN))
				break;

			ssize_t n = recvmsg(fds[0], &msg, MSG_CMSG_CLOEXEC);

			if (n < 0 && (errno == EINTR || errno == EAGAIN))
				continue;
			struct cmsghdr *c = n == 1 ? CMSG_FIRSTHDR(&msg) : NULL;

			if (c && c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS &&
			    c->cmsg_len == CMSG_LEN(sizeof(int)))
				memcpy(&result, CMSG_DATA(c), sizeof(int));
			break;
		}
		kill(child, SIGKILL);
		waitpid(child, &status, 0);
	}
	close(fds[0]);
#ifdef NEEDRESTART_TEST
verify:
#endif
	if (result >= 0 && (fstat(result, &nsroot) || nsroot.st_dev != hostroot.st_dev ||
			    nsroot.st_ino != hostroot.st_ino)) {
		close(result);
		result = -1;
	}
	return result;
}

struct file_probe {
	int error, comparison;
	bool regular, is_elf, old_is_elf, mismatch;
};

static struct file_probe probe_file(int root, const char *file, int oldfd, bool deleted,
				    bool executable, unsigned int maj, unsigned int min,
				    uint64_t ino)
{
	struct file_probe result = {.comparison = -1};
	struct stat current, old;
	int fd;

	result.old_is_elf = oldfd >= 0 && elf(oldfd);
	fd = rooted_open(root, file);

	if (fd < 0) {
		result.error = errno;
		return result;
	}
	if (fstat(fd, &current)) {
		result.error = errno;
		goto out;
	}
	result.regular = S_ISREG(current.st_mode);
	if (!result.regular)
		goto out;
	if (executable && oldfd >= 0 && !fstat(oldfd, &old))
		result.mismatch = old.st_dev != current.st_dev || old.st_ino != current.st_ino;
	else if (ino)
		result.mismatch = major(current.st_dev) != maj || minor(current.st_dev) != min ||
				  current.st_ino != ino;
	if (deleted || result.mismatch) {
		result.is_elf = elf(fd);
		if (oldfd >= 0)
			result.comparison = different(oldfd, fd);
	}
out:
	close(fd);
	return result;
}

/* FUSE rootless overlay mounts intentionally deny even host root. Inspect them
 * in a bounded, fully unprivileged child, never by changing FUSE permissions or
 * entering its mount/PID namespaces or executing its code. The child joins only
 * the target user namespace after dropping all host credentials. Only this
 * fixed-size result crosses back to root.
 */
static struct file_probe user_probe(uid_t uid, pid_t target, int root, const char *file,
				    const char *oldpath, int mapped, bool deleted, bool executable,
				    unsigned int maj, unsigned int min, uint64_t ino)
{
	struct file_probe result = {.error = EACCES, .comparison = -1};
	struct passwd *pw = getpwuid(uid);
	int fds[2], status;
	pid_t pid;
	char ns_path[96];
	int userns;

	snprintf(ns_path, sizeof(ns_path), "/proc/%d/ns/user", target);
	userns = open(path(ns_path), O_RDONLY | O_CLOEXEC);
#ifdef NEEDRESTART_TEST
	bool fixture = *test_root;
#else
	bool fixture = false;
#endif
	if (!pw || (userns < 0 && !fixture) ||
	    socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, fds)) {
		if (userns >= 0)
			close(userns);
		return result;
	}
	pid = fork();
	if (!pid) {
		int rootcopy = fcntl(root, F_DUPFD_CLOEXEC, 10);
		int replycopy = fcntl(fds[1], F_DUPFD_CLOEXEC, 10);
		int nscopy = userns >= 0 ? fcntl(userns, F_DUPFD_CLOEXEC, 10) : -1;
		int mapcopy = mapped >= 0 ? fcntl(mapped, F_DUPFD_CLOEXEC, 10) : -1;
		int nullfd = open("/dev/null", O_RDWR);
		int first = 5;

		close(fds[0]);
		if (rootcopy < 0 || replycopy < 0 || nullfd < 0 || chdir("/") ||
		    dup2(nullfd, 0) < 0 || dup2(nullfd, 1) < 0 || dup2(nullfd, 2) < 0 ||
		    dup2(rootcopy, 3) < 0 || dup2(replycopy, 4) < 0 ||
		    (userns >= 0 && (nscopy < 0 || dup2(nscopy, first++) < 0)) ||
		    (mapped >= 0 && (mapcopy < 0 || dup2(mapcopy, first++) < 0)) ||
		    syscall(SYS_close_range, first, UINT_MAX, 0))
			_exit(126);
		/* Discard host locks and all privileged descriptors before changing UID.
		 * A stuck FUSE request must never keep the parent's APK lock alive.
		 */
		if (geteuid() == 0 &&
		    (setgroups(0, NULL) || setresgid(pw->pw_gid, pw->pw_gid, pw->pw_gid) ||
		     setresuid(uid, uid, uid)))
			_exit(126);
		if (geteuid() != uid)
			_exit(126);
		if (userns >= 0 && setns(5, CLONE_NEWUSER))
			_exit(126);
		if (prctl(PR_SET_DUMPABLE, 0) || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0))
			_exit(126);
		/* map_files needs host CAP_CHECKPOINT_RESTORE; use the object
		 * the parent opened, if any, instead of reopening it here.
		 */
		int oldfd = mapped >= 0 ? first - 1 : open(oldpath, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
#ifdef NEEDRESTART_TEST
		/* Model the kernel's map_files restriction for unprivileged users. */
		char denied[128];

		snprintf(denied, sizeof(denied), "/proc/%d/test-map-files-denied", target);
		if (fixture && mapped < 0 && strstr(oldpath, "/map_files/") &&
		    !access(path(denied), F_OK) && oldfd >= 0) {
			close(oldfd);
			oldfd = -1;
		}
#endif

		result = probe_file(3, file, oldfd, deleted, executable, maj, min, ino);
		send(4, &result, sizeof(result), MSG_NOSIGNAL);
		_exit(0);
	}
	if (userns >= 0)
		close(userns);
	close(fds[1]);
	if (pid > 0) {
		struct pollfd p = {.fd = fds[0], .events = POLLIN};
		int64_t end = millis() + 1000;

		if (end > deadline)
			end = deadline;
		/* libubus installs a SIGCHLD handler. An earlier probe can exit
		 * while this one is running; retry interruptions within the same
		 * absolute deadline instead of killing a healthy probe.
		 */
		while (millis() < end) {
			struct file_probe reply;
			int remaining = end - millis();
			int ready;

			if (remaining <= 0)
				break;
			ready = poll(&p, 1, remaining);

			if (ready < 0 && errno == EINTR)
				continue;
			if (ready <= 0 || !(p.revents & POLLIN))
				break;

			ssize_t n = recv(fds[0], &reply, sizeof(reply), 0);

			if (n < 0 && (errno == EINTR || errno == EAGAIN))
				continue;
			if (n == sizeof(reply))
				result = reply;
			break;
		}
		kill(pid, SIGKILL);
		/* Never wait indefinitely for a user-controlled FUSE daemon. */
		waitpid(pid, &status, WNOHANG);
	}
	close(fds[0]);
	return result;
}

/* Rootless processes can map host files through bind mounts (for example a
 * shared home directory). Overlayfs reports its superblock device in maps but a
 * per-layer device from stat, so content comparison needs the old object, and
 * only host root may open /proc/PID/map_files. Root opens it only when every
 * mount of that device in the process's mount table is a non-FUSE filesystem,
 * so no request can reach a user-controlled FUSE daemon. Reading the table is
 * a plain procfs read.
 */
static bool host_openable_mapping(pid_t pid, unsigned int maj, unsigned int min)
{
	static pid_t cached_pid;
	static uint64_t cached_start;
	static char *table;
	uint64_t start = start_time(pid);
	bool matched = false, fuse = false;
	char *save, *line, *copy;

	if (!start)
		return false;
	if (cached_pid != pid || cached_start != start) {
		free(table);
		table = proc_read(pid, "mountinfo", MAX_BYTES);
		cached_pid = pid;
		cached_start = start;
	}
	copy = table ? strdup(table) : NULL;
	if (!copy)
		return false;
	for (line = strtok_r(copy, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
		unsigned int a, b;
		char *sep = strstr(line, " - ");

		if (sscanf(line, "%*u %*u %u:%u ", &a, &b) != 2 || a != maj || b != min)
			continue;
		matched = true;
		if (!sep || !strncmp(sep + 3, "fuse", 4) || !sep[3] || sep[3] == ' ')
			fuse = true;
	}
	free(copy);
	return matched && !fuse;
}

static void evidence(json_object *files, int root, pid_t pid, const char *mapped,
		     const char *object, bool executable, unsigned int maj, unsigned int min,
		     uint64_t ino, bool host, uid_t rootless_uid)
{
	char file[PATH_MAX], oldpath[160];
	bool deleted;
	int oldfd;
	const char *reason = NULL;

	if (*mapped != '/' || strlen(mapped) >= sizeof(file) || !strncmp(mapped, "/memfd:", 7) ||
	    !strncmp(mapped, "/dev/", 5))
		return;
	snprintf(file, sizeof(file), "%s", mapped);
	deleted = strlen(file) > 10 && !strcmp(file + strlen(file) - 10, " (deleted)");
	if (deleted)
		file[strlen(file) - 10] = 0;
	/* /proc/maps escapes newlines, not arbitrary backslash sequences.
	 */
	for (char *p = file; (p = strstr(p, "\\012"));) {
		*p = '\n';
		memmove(p + 1, p + 4, strlen(p + 4) + 1);
		p++;
	}
	for (size_t i = 0; i < length(files); i++)
		if (!strcmp(str(json_object_array_get_idx(files, i), "path"), file))
			return;
	snprintf(oldpath, sizeof(oldpath), "/proc/%d/%s", pid, object);
#ifdef NEEDRESTART_TEST
	if (*test_root && !strcmp(object, "exe")) {
		char retained[160];

		snprintf(retained, sizeof(retained), "/proc/%d/test-exe", pid);
		if (!access(path(retained), F_OK))
			snprintf(oldpath, sizeof(oldpath), "%s", retained);
	}
#endif
	oldfd = rootless_uid ? -1 : open(path(oldpath), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	struct file_probe probe;

	if (rootless_uid) {
		int object_fd = -1;

		if (!executable && host_openable_mapping(pid, maj, min))
			object_fd = open(path(oldpath), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
		probe = user_probe(rootless_uid, pid, root, file, path(oldpath), object_fd,
				   deleted, executable, maj, min, ino);
		if (object_fd >= 0)
			close(object_fd);
	} else
		probe = probe_file(root, file, oldfd, deleted, executable, maj, min, ino);
	if (probe.error) {
		if (probe.error == ENOENT && deleted && (executable || probe.old_is_elf))
			reason = "removed";
		else if (deleted || probe.error != ENOENT) {
			char detail[256];

			snprintf(detail, sizeof(detail),
				 "PID %d: mapped code unavailable in its filesystem root (%s)", pid,
				 strerror(probe.error));
			warn(detail);
		}
	} else if (!probe.regular) {
		if (deleted)
			warn("Replacement code is not a readable regular file");
	} else if (deleted) {
		if (probe.comparison > 0 || (probe.comparison < 0 && probe.is_elf))
			reason = "replaced";
	} else if (probe.mismatch) {
		if (probe.comparison > 0)
			reason = "replaced";
		else if (probe.comparison < 0)
			warn("Some differing mapped-file identities could not be verified (including possible overlayfs mappings)");
	}
	if (oldfd >= 0)
		close(oldfd);
	if (!reason)
		return;
	if (evidence_bytes + strlen(file) + 2048 > MAX_BYTES / 2) {
		warn("Executable detail output limit reached");
		return;
	}
	evidence_bytes += strlen(file) + 2048;
	json_object *o = json_object_new_object();

	string(o, "path", file);
	string(o, "reason", reason);
	string(o, "type", executable ? "executable" : "loaded-code");
	if (host && get(packages, file))
		json_object_object_add(o, "package", json_object_get(get(packages, file)));
	json_object_array_add(files, o);
}

/* Read only deployment identity from Flatpak's key file. Never retain its
 * environment or bus policies, and never execute anything inside the sandbox.
 */
static json_object *flatpak_info(int fd)
{
	char *data = read_fd(fd, 65536), section[32] = "", *save;
	json_object *o = json_object_new_object();
	static const char *const keys[] = {
	    "Application.name", "Application.runtime", "Instance.instance-id",
	    "Instance.app-path", "Instance.runtime-path", "Instance.app-commit",
	    "Instance.runtime-commit", "Instance.arch", "Instance.branch",
	    "Instance.app-extensions", "Instance.runtime-extensions", NULL};

	if (!data)
		goto bad;
	for (char *line = strtok_r(data, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
		line[strcspn(line, "\r")] = 0;
		if (*line == '[') {
			char *end = strchr(line, ']');

			section[0] = 0;
			if (end && !end[1] && end - line > 1 && (size_t)(end - line) < sizeof(section)) {
				memcpy(section, line + 1, end - line - 1);
				section[end - line - 1] = 0;
			}
			continue;
		}
		char *eq = strchr(line, '='), key[96];

		if (!eq || eq - line > 60)
			continue;
		*eq++ = 0;
		snprintf(key, sizeof(key), "%s.%s", section, line);
		for (size_t i = 0; keys[i]; i++) {
			if (strcmp(keys[i], key))
				continue;
			if (get(o, key) || strlen(eq) > 16384)
				goto bad;
			string(o, key, eq);
		}
	}
	free(data);
	return o;
bad:
	free(data);
	json_object_put(o);
	return NULL;
}

static bool commit_id(const char *s)
{
	return strlen(s) == 64 && strspn(s, "0123456789abcdef") == 64;
}

static bool deployment_name(const char *s, const char *commit)
{
	if (strncmp(s, commit, 64))
		return false;
	return !s[64] || (s[64] == '.' && s[65] && strspn(s + 65, "0123456789") == strlen(s + 65));
}

static bool flatpak_ref(const char *ref)
{
	char copy[512], *p, *part;
	unsigned int n = 0;

	if (strlen(ref) >= sizeof(copy))
		return false;
	snprintf(copy, sizeof(copy), "%s", ref);
	p = copy;
	while ((part = strsep(&p, "/"))) {
		if (!valid_name(part) || strchr(part, '\\') ||
		    (!n && strcmp(part, "app") && strcmp(part, "runtime")))
			return false;
		n++;
	}
	return n == 4;
}

static bool flatpak_active(const char *branch, char commit[65])
{
	char file[PATH_MAX], target[128];
	struct stat st;
	ssize_t n;

	if (snprintf(file, sizeof(file), "%s/active", branch) >= (int)sizeof(file))
		return false;
	n = readlink(path(file), target, sizeof(target) - 1);
	if (n < 64)
		return false;
	target[n] = 0;
	memcpy(commit, target, 64);
	commit[64] = 0;
	if (!commit_id(commit) || !deployment_name(target, commit))
		return false;
	if (snprintf(file, sizeof(file), "%s/active/files", branch) >= (int)sizeof(file))
		return false;
	return !stat(path(file), &st) && S_ISDIR(st.st_mode);
}

static void flatpak_store(uid_t uid, unsigned int index, char store[PATH_MAX])
{
	struct passwd *pw = getpwuid(uid);

	if (!index && pw)
		snprintf(store, PATH_MAX, "%s/.local/share/flatpak", pw->pw_dir);
	else
		snprintf(store, PATH_MAX, "/var/lib/flatpak");
}

/* 0 current, 1 changed, -1 unverified. Paths must belong to a known local
 * user/system store and the declared ref/commit, including deployment suffixes.
 */
static int flatpak_deployment(uid_t uid, const char *ref, const char *commit, const char *files)
{
	char store[PATH_MAX], branch[PATH_MAX], active[65], folder[128];

	if (!flatpak_ref(ref) || !commit_id(commit))
		return -1;
	for (unsigned int i = 0; i < 2; i++) {
		flatpak_store(uid, i, store);
		if (snprintf(branch, sizeof(branch), "%s/%s", store, ref) >= (int)sizeof(branch))
			continue;
		size_t n = strlen(branch), m = strlen(files);

		if (m <= n + 7 || strncmp(files, branch, n) || files[n] != '/' ||
		    strcmp(files + m - 6, "/files") || m - n - 7 >= sizeof(folder))
			continue;
		memcpy(folder, files + n + 1, m - n - 7);
		folder[m - n - 7] = 0;
		if (deployment_name(folder, commit) && flatpak_active(branch, active))
			return strcmp(active, commit) ? 1 : 0;
	}
	return -1;
}

static int flatpak_extension(uid_t uid, const char *id, const char *arch, const char *commit)
{
	char store[PATH_MAX], base[PATH_MAX], branch[PATH_MAX], file[PATH_MAX], active[65];
	bool retained = false;

	if (!valid_name(id) || strchr(id, '\\') || !valid_name(arch) || !commit_id(commit))
		return -1;
	for (unsigned int i = 0; i < 2; i++) {
		flatpak_store(uid, i, store);
		if (snprintf(base, sizeof(base), "%s/runtime/%s/%s", store, id, arch) >= (int)sizeof(base))
			continue;
		DIR *d = opendir(path(base));
		struct dirent *e;
		unsigned int branches = 0;

		while (d && (e = readdir(d))) {
			if (!valid_name(e->d_name))
				continue;
			if (++branches > 128 || millis() >= deadline) {
				closedir(d);
				return -1;
			}
			if (snprintf(branch, sizeof(branch), "%s/%s", base, e->d_name) >= (int)sizeof(branch) ||
			    !flatpak_active(branch, active))
				continue;
			if (!strcmp(active, commit)) {
				closedir(d);
				return 0;
			}
			DIR *versions = opendir(path(branch));
			struct dirent *v;
			unsigned int count = 0;
			struct stat st;

			while (versions && (v = readdir(versions))) {
				if (++count > 128 || millis() >= deadline)
					break;
				if (deployment_name(v->d_name, commit) &&
				    snprintf(file, sizeof(file), "%s/%s/files", branch, v->d_name) < (int)sizeof(file) &&
				    !stat(path(file), &st) && S_ISDIR(st.st_mode))
					retained = true;
			}
			if (versions)
				closedir(versions);
			if (count > 128 || millis() >= deadline) {
				closedir(d);
				return -1;
			}
		}
		if (d)
			closedir(d);
	}
	return retained ? 1 : -1;
}

static json_object *flatpak_application(pid_t pid, const char *cg, int root)
{
	int fd = rooted_open(root, "/.flatpak-info");
	json_object *info = NULL, *host = NULL, *wrap = NULL, *application = NULL;
	char proc[PATH_MAX], prefix[128], suffix[320], ref[512], key[32];
	struct stat st, ns, child_ns, child_root, process_root;
	uid_t uid = container_uid(cg);
	pid_t child;
	uint64_t child_start;

	if (fd < 0 || !uid)
		goto out;
	info = flatpak_info(fd);
	close(fd);
	fd = -1;
	const char *id = str(info, "Instance.instance-id"), *name = str(info, "Application.name");

	if (!*id || strlen(id) > 20 || strspn(id, "0123456789") != strlen(id) ||
	    !valid_name(name) || strchr(name, '\\'))
		goto out;
	snprintf(suffix, sizeof(suffix), "/app-flatpak-%s-%s.scope", name, id);
	const char *scope = strstr(cg, suffix);

	if (!scope || (scope[strlen(suffix)] && scope[strlen(suffix)] != '/'))
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d", pid);
	if (stat(path(proc), &st) || st.st_uid != uid)
		goto out;
	snprintf(prefix, sizeof(prefix), "/run/user/%u/.flatpak/%s", uid, id);
	snprintf(proc, sizeof(proc), "%s/info", prefix);
	fd = open(path(proc), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	if (fd < 0)
		goto out;
	host = flatpak_info(fd);
	close(fd);
	fd = -1;
	if (!info || !host)
		goto out;
	json_object_object_foreach(info, k, value)
	{
		(void)value;
		if (strcmp(str(info, k), str(host, k)))
			goto out;
	}
	snprintf(proc, sizeof(proc), "%s/bwrapinfo.json", prefix);
	wrap = read_json(path(proc));
	if (json_object_get_int64(get(wrap, "child-pid")) > INT_MAX)
		goto out;
	child = json_object_get_int64(get(wrap, "child-pid"));
	child_start = child > 1 ? start_time(child) : 0;
	if (!child_start)
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d", child);
	if (stat(path(proc), &st) || st.st_uid != uid)
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d/ns/mnt", pid);
	if (stat(path(proc), &ns) || ns.st_ino != json_object_get_uint64(get(wrap, "mnt-namespace")))
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d/ns/mnt", child);
	if (stat(path(proc), &child_ns) || child_ns.st_ino != ns.st_ino || child_ns.st_dev != ns.st_dev)
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d/root", child);
	if (stat(path(proc), &child_root) || fstat(root, &process_root) ||
	    child_root.st_dev != process_root.st_dev || child_root.st_ino != process_root.st_ino ||
	    child_start != start_time(child))
		goto out;
	for (size_t i = 0; i < length(applications); i++) {
		json_object *a = json_object_array_get_idx(applications, i);

		if (json_object_get_int64(get(a, "uid")) == uid && !strcmp(str(a, "instance"), id)) {
			application = a;
			goto identified;
		}
	}
	if (length(applications) >= 128)
		goto out;
	application = json_object_new_object();
	string(application, "kind", "flatpak");
	string(application, "name", name);
	string(application, "instance", id);
	number(application, "uid", uid);
	snprintf(ref, sizeof(ref), "app/%s/%s/%s", name, str(info, "Instance.arch"), str(info, "Instance.branch"));
	string(application, "reference", ref);
	string(application, "app_commit", str(info, "Instance.app-commit"));
	string(application, "runtime_commit", str(info, "Instance.runtime-commit"));
	int app = flatpak_deployment(uid, ref, str(info, "Instance.app-commit"), str(info, "Instance.app-path"));
	int runtime = flatpak_deployment(uid, str(info, "Application.runtime"),
					str(info, "Instance.runtime-commit"), str(info, "Instance.runtime-path"));
	int extensions = 0;
	bool extension_changed = false;
	const char *const extension_keys[] = {"Instance.app-extensions", "Instance.runtime-extensions", NULL};

	for (size_t i = 0; extension_keys[i]; i++) {
		char *list = strdup(str(info, extension_keys[i])), *save, *entry;
		unsigned int count = 0;

		if (!list)
			extensions = -1;
		for (entry = list ? strtok_r(list, ";", &save) : NULL; entry; entry = strtok_r(NULL, ";", &save)) {
			char *eq = strchr(entry, '=');
			int state = -1;

			if (eq && ++count <= 64) {
				*eq++ = 0;
				state = flatpak_extension(uid, entry, str(info, "Instance.arch"), eq);
			}
			if (state < 0)
				extensions = -1;
			else if (state > 0)
				extension_changed = true;
		}
		free(list);
	}
	string(application, "deployment_status", app > 0 || runtime > 0 || extension_changed ? "changed" :
	       app < 0 || runtime < 0 || extensions < 0 ? "unknown" : "current");
	string(application, "app_status", app < 0 ? "unknown" : app ? "changed" : "current");
	string(application, "runtime_status", runtime < 0 ? "unknown" : runtime ? "changed" : "current");
	string(application, "extensions_status", extension_changed ? "changed" : extensions < 0 ? "unknown" : "current");
	if (app < 0 || runtime < 0 || extensions < 0)
		warn("A Flatpak app, runtime, or extension deployment could not be verified locally");
	json_object_array_add(applications, application);
identified:
	snprintf(key, sizeof(key), "%d", pid);
	json_object_object_add(flatpak_owners, key, json_object_get(application));
out:
	if (fd >= 0)
		close(fd);
	if (info)
		json_object_put(info);
	if (host)
		json_object_put(host);
	if (wrap)
		json_object_put(wrap);
	return application;
}

/* Flatpak's D-Bus proxy has a separate empty sandbox. Verify its metadata
 * against the live application root rather than requiring identical mount
 * namespaces, which only the application's bwrap/payload processes share.
 */
static json_object *flatpak_proxy_application(pid_t pid, const char *cg, const char *exe, int root)
{
	json_object *info = NULL, *wrap = NULL, *child_info = NULL, *application = NULL;
	struct stat st;
	struct statfs fs;
	char file[PATH_MAX], key[32], *child_group = NULL;
	uid_t uid = container_uid(cg);
	int fd = -1, childroot = -1, old = -1, current = -1;

	if (!uid || strcmp(exe, "/usr/bin/xdg-dbus-proxy") || fstatfs(root, &fs))
		return NULL;
#ifdef NEEDRESTART_TEST
	if (!*test_root)
#endif
		if (fs.f_type != TMPFS_MAGIC)
			return NULL;
	snprintf(file, sizeof(file), "/proc/%d", pid);
	if (stat(path(file), &st) || st.st_uid != uid)
		return NULL;
	fd = rooted_open(root, "/.flatpak-info");
	if (fd < 0)
		goto out;
	info = flatpak_info(fd);
	close(fd);
	fd = -1;
	const char *id = str(info, "Instance.instance-id");

	if (!*id || strlen(id) > 20 || strspn(id, "0123456789") != strlen(id))
		goto out;
	snprintf(file, sizeof(file), "/run/user/%u/.flatpak/%s/bwrapinfo.json", uid, id);
	wrap = read_json(path(file));
	int64_t child = json_object_get_int64(get(wrap, "child-pid"));
	uint64_t start = child > 1 && child <= INT_MAX ? start_time(child) : 0;

	if (!start || child == pid)
		goto out;
	child_group = group(child);
	if (!child_group || !cg || strcmp(child_group, cg))
		goto out;
	snprintf(file, sizeof(file), "/proc/%d/root", (int)child);
	childroot = open(path(file), O_PATH | O_DIRECTORY | O_CLOEXEC);
	if (childroot < 0)
		goto out;
	fd = rooted_open(childroot, "/.flatpak-info");
	if (fd < 0)
		goto out;
	child_info = flatpak_info(fd);
	if (!info || !child_info)
		goto out;
	json_object_object_foreach(info, k, value)
	{
		(void)value;
		if (strcmp(str(info, k), str(child_info, k)))
			goto out;
	}
	snprintf(file, sizeof(file), "/proc/%d/exe", pid);
#ifdef NEEDRESTART_TEST
	if (*test_root)
		snprintf(file, sizeof(file), "/proc/%d/test-exe", pid);
#endif
	old = open(path(file), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	current = open(path(exe), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
	if (old < 0 || current < 0 || different(old, current) != 0 || start != start_time(child))
		goto out;
	application = flatpak_application(child, child_group, childroot);
	if (application) {
		snprintf(key, sizeof(key), "%d", pid);
		json_object_object_add(flatpak_owners, key, json_object_get(application));
	}
out:
	if (fd >= 0)
		close(fd);
	if (childroot >= 0)
		close(childroot);
	if (old >= 0)
		close(old);
	if (current >= 0)
		close(current);
	if (info)
		json_object_put(info);
	if (wrap)
		json_object_put(wrap);
	if (child_info)
		json_object_put(child_info);
	free(child_group);
	return application;
}

static void scan_process(pid_t pid, json_object *snap)
{
	char proc[128], exe[PATH_MAX], id[65];
	uint64_t start = start_time(pid);
	char *cg = group(pid), *maps = NULL;
	int root = -1;
	json_object *files = json_object_new_array();
	ssize_t len;

	if (!start || pid == getpid())
		goto out;
	snprintf(proc, sizeof(proc), "/proc/%d/root", pid);
	root = open(path(proc), O_PATH | O_DIRECTORY | O_CLOEXEC);
	if (root < 0) {
		if (errno != ENOENT && errno != ESRCH)
			unreadable++;
		goto out;
	}
	snprintf(proc, sizeof(proc), "/proc/%d/exe", pid);
	len = readlink(path(proc), exe, sizeof(exe) - 1);
	if (len < 0) {
		if (errno != ENOENT && errno != ESRCH)
			unreadable++;
		goto out;
	}
	exe[len] = 0;
	container_id(cg, id);
	struct stat rootstat, hoststat;
	bool host = !fstat(root, &rootstat) && !stat(path("/"), &hoststat) &&
		    rootstat.st_dev == hoststat.st_dev && rootstat.st_ino == hoststat.st_ino;
	json_object *application = !host && !*id ? flatpak_application(pid, cg, root) : NULL;
	bool flatpak_helper = false;

	if (!host && !*id && !application) {
		application = flatpak_proxy_application(pid, cg, exe, root);
		flatpak_helper = application != NULL;
	}

	if (application && !strcmp(exe, "/usr/bin/bwrap")) {
		int old, current;

		snprintf(proc, sizeof(proc), "/proc/%d/exe", pid);
		old = open(path(proc), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
		current = open(path(exe), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
		flatpak_helper = old >= 0 && current >= 0 && different(old, current) == 0;
		if (old >= 0)
			close(old);
		if (current >= 0)
			close(current);
	}

	if (!host && !*id && (flatpak_helper || sandbox_host_helper(pid, cg, exe, root) ||
			    sandbox_host_browser(pid, exe, root))) {
		int hostroot = open(path("/"), O_PATH | O_DIRECTORY | O_CLOEXEC);

		if (hostroot >= 0) {
			close(root);
			root = hostroot;
			host = true;
		}
	}
	if (!host && !*id && !application) {
		int nsroot = service_namespace_root(pid, cg);

		if (nsroot >= 0) {
			close(root);
			root = nsroot;
			host = true;
		}
	}
	uid_t rootless_uid = *id ? container_uid(cg) : 0;

	evidence(files, root, pid, exe, "exe", true, 0, 0, 0, host && !*id, rootless_uid);
	maps = proc_read(pid, "maps", MAX_BYTES);
	if (!maps) {
		if (start_time(pid) == start)
			unreadable++;
	} else {
		char *save, *line;

		for (line = strtok_r(maps, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
			unsigned long long lo, hi, off, ino;
			unsigned int maj, min;
			char perms[5], object[96];
			int n = 0;

			if (sscanf(line, "%llx-%llx %4s %llx %x:%x %llu %n", &lo, &hi, perms, &off,
				   &maj, &min, &ino, &n) != 7 ||
			    !strchr(perms, 'x') || !ino || !n)
				continue;
			if (millis() > deadline) {
				warn("Scan time limit reached");
				break;
			}
			snprintf(object, sizeof(object), "map_files/%llx-%llx", lo, hi);
			evidence(files, root, pid, line + n, object, false, maj, min, ino,
				 host && !*id, rootless_uid);
		}
	}
	if (application && !strcmp(str(application, "deployment_status"), "changed")) {
		json_object *change = json_object_new_object();

		string(change, "path", str(application, "reference"));
		string(change, "reason", "local-deployment-changed");
		string(change, "type", "flatpak-deployment");
		json_object_array_add(files, change);
	}
#ifdef NEEDRESTART_TEST
	if (*test_root) {
		snprintf(proc, sizeof(proc), "/proc/%d/test-pause", pid);
		if (!access(path(proc), F_OK)) {
			char ready[128];

			snprintf(ready, sizeof(ready), "/proc/%d/test-paused", pid);
			int fd = open(path(ready), O_WRONLY | O_CREAT | O_CLOEXEC, 0600);

			if (fd >= 0)
				close(fd);
			while (!access(path(proc), F_OK) && millis() < deadline)
				usleep(1000);
		}
	}
#endif
	if (start_time(pid) != start) {
		skipped++;
		goto out;
	}
	scanned++;
	if (length(files)) {
		json_object *s = subject(pid, cg, snap, host), *p = json_object_new_object();

		number(p, "pid", pid);
		number(p, "start_time", start);
		json_object_object_add(p, "files", json_object_get(files));
		json_object_array_add(get(s, "processes"), p);
	}
	if (*id && !container_find(id, container_uid(cg)))
		warn("An observed Podman container could not be inventoried");
	/* Other roots/namespaces are inspected for stale code, but never attributed
	 * to the host's supervisor as if it owned the contained service.
	 */
	if (!host && !*id && !application) {
		char service[256];

		if (!procd_name(pid, cg, snap, service)) {
			char message[768];

			snprintf(message, sizeof(message),
				 "Coverage incomplete for PID %d (%.*s), cgroup %.*s: isolated filesystem owner and deployment freshness unverified",
				 pid, 256, exe, 256, cg ? cg : "unknown");
			warn(message);
		}
	}
out:
	if (root >= 0)
		close(root);
	free(cg);
	free(maps);
	json_object_put(files);
}

static void kernel_status(void)
{
	json_object *o = json_object_new_object(),
		    *state = read_json_limit(path("/etc/openwrt-kernel/state.json"),
					   MAX_KERNEL_BYTES);
	struct utsname uts;
	const char *running;
	char *test = NULL;

	uname(&uts);
	running = uts.release;
#ifdef NEEDRESTART_TEST
	if (*test_root) {
		test = read_file(path("/release"), 512);
		if (test) {
			test[strcspn(test, "\n")] = 0;
			running = test;
		}
	}
#endif
	string(o, "running_release", running);
	string(o, "status", "unknown");
	json_object_object_add(report, "kernel", o);
	int schema = state ? json_object_get_int(get(state, "schema")) : 0;

	if (schema != 1 && schema != 2) {
		string(o, "detail", "Kernel manager metadata unavailable or unsupported");
		warn("Kernel activation status is unassessed");
		goto out;
	}
	if (*str(state, "phase") && strcmp(str(state, "phase"), "ready")) {
		string(o, "status", "activation-incomplete");
		warn("Kernel manager adoption is not complete; review kernelctl status/check");
		goto out;
	}
	if (schema == 2) {
		/* Kernel packages: like a distribution, a newer installed default
		 * kernel only needs a reboot; GRUB falls back after failed boots. */
		const char *def = str(state, "default"), *counting = str(state, "counting");
		json_object *kernels = get(state, "kernels"), *entry = NULL;

		if (kernels && json_object_is_type(kernels, json_type_object) && *def)
			entry = get(kernels, def);
		string(o, "default_release", def);
		if (!entry) {
			string(o, "status", "activation-incomplete");
			warn("Default kernel is not registered; review kernelctl list/check");
		} else if (strcmp(def, running) && strcmp(str(entry, "release"), running)) {
			string(o, "status", "reboot-pending");
			string(o, "pending_release", def);
			string(o, "recommended_action",
			       "A newer kernel is the boot default; reboot to run it (GRUB falls back after 3 failed boots)");
		} else if (*counting && !strcmp(counting, running)) {
			string(o, "status", "trial-running");
		} else {
			string(o, "status", "current");
		}
		goto out;
	}
	json_object *generations = get(state, "generations"), *current = NULL;

	if (generations && json_object_is_type(generations, json_type_object)) {
		json_object_object_foreach(generations, name, entry)
		{
			(void)name;
			if (!strcmp(str(entry, "release"), running))
				current = entry;
		}
	}
	if (!current || !*str(current, "abi")) {
		warn("Running kernel has no verified ABI metadata");
		goto out;
	}
	string(o, "running_abi", str(current, "abi"));
	const char *pending = str(state, "pending");

	if (!*pending) {
		json_object *selected = read_json(path("/usr/share/openwrt-kernel/selected.json"));

		if (selected && *str(selected, "generation") &&
		    strcmp(str(selected, "generation"), running)) {
			string(o, "status", "activation-incomplete");
			warn("Selected kernel is not running or armed; review kernelctl status/check before considering a reboot");
		} else {
			string(o, "status", "current");
		}
		if (selected)
			json_object_put(selected);
		goto out;
	}
	json_object *candidate = get(generations, pending);

	if (!candidate || !json_object_get_boolean(get(candidate, "ready")) ||
	    json_object_get_boolean(get(candidate, "failed")) || !*str(candidate, "abi")) {
		string(o, "status", "activation-incomplete");
		warn("Pending kernel metadata is incomplete or rejected; review kernelctl status/check");
		goto out;
	}
	string(o, "pending_release", str(candidate, "release"));
	string(o, "pending_abi", str(candidate, "abi"));
	if (!strcmp(str(candidate, "release"), running)) {
		string(o, "status", "trial-running");
		goto out;
	}
	static char *const argv[] = {"/usr/sbin/grub-editenv", "/boot/grub/grubenv", "list", NULL};
	char *env;
#ifdef NEEDRESTART_TEST
	if (*test_root)
		env = read_file(path("/grubenv"), 65536);
	else
#endif
		env = command(0, argv, 1500);
	char expected[512];

	snprintf(expected, sizeof(expected), "next_entry=owrt-%s", pending);
	bool armed = false;

	if (env) {
		char *save;

		for (char *p = strtok_r(env, "\n", &save); p; p = strtok_r(NULL, "\n", &save))
			if (!strcmp(p, expected))
				armed = true;
	}
	free(env);
	if (!armed) {
		string(o, "status", "activation-incomplete");
		warn("Pending kernel is not verified as the GRUB trial selection");
	} else if (!strcmp(str(current, "abi"), str(candidate, "abi"))) {
		string(o, "status", "optional-same-abi-trial");
		string(o, "recommended_action",
		       "Same exact ABI: no required kernel reboot; an explicitly staged trial is optional");
	} else {
		string(o, "status", "reboot-pending");
		string(o, "recommended_action",
		       "A verified different-ABI kernel trial is ready; reboot deliberately during maintenance");
	}
out:
	free(test);
	if (state)
		json_object_put(state);
}

static bool same_file(const struct stat *a, const struct stat *b)
{
	return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_size == b->st_size &&
	       a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec;
}

static json_object *scan(void)
{
	DIR *d;
	struct dirent *e;
	json_object *snap;
	struct stat before[5] = {}, after;
	static const char *const inputs[] = {
	    "/lib/apk/db/installed", "/etc/openwrt-kernel/state.json", RUNTIME "/pending",
	    "/usr/share/openwrt-kernel/selected.json", "/boot/grub/grubenv"};
	bool exists[5];
	char *boot;

	partial = false;
	scanned = skipped = unreadable = 0;
	evidence_bytes = 0;
	comparison_count = 0;
	deadline = millis() + 20000;
	report = json_object_new_object();
	warnings = json_object_new_array();
	subjects = json_object_new_object();
	containers = json_object_new_array();
	applications = json_object_new_array();
	flatpak_owners = json_object_new_object();
	json_object_object_add(report, "warnings", warnings);
	json_object_object_add(report, "containers", containers);
	json_object_object_add(report, "applications", applications);
	json_object_object_add(report, "services", json_object_new_array());
	number(report, "schema_version", 1);
	number(report, "timestamp", time(NULL));
	boot = read_file(path("/proc/sys/kernel/random/boot_id"), 128);
	if (boot)
		boot[strcspn(boot, "\n")] = 0;
	string(report, "boot_id", boot ? boot : "");
	if (!boot)
		warn("Boot identity unavailable");
	free(boot);
	for (size_t i = 0; i < 5; i++)
		exists[i] = !stat(path(inputs[i]), &before[i]);
	package_index();
	snap = procd_snapshot();
	if (snap && !json_object_is_type(snap, json_type_object)) {
		json_object_put(snap);
		snap = NULL;
	}
	if (!snap)
		warn("Procd service ownership unavailable; degraded placement may leave processes unassigned");
#ifdef NEEDRESTART_TEST
	owners = *test_root ? read_json(path("/ownership.json")) : NULL;
#endif
	podman_inventory();
	d = opendir(path("/proc"));
	if (!d)
		warn("Cannot enumerate host processes");
	unsigned int count = 0;

	while (d && (e = readdir(d))) {
		if (!isdigit((unsigned char)e->d_name[0]) ||
		    strspn(e->d_name, "0123456789") != strlen(e->d_name))
			continue;
		if (++count > MAX_PROCESSES || millis() > deadline ||
		    json_object_object_length(subjects) >= MAX_FINDINGS) {
			warn("Process inspection limit reached");
			break;
		}
		scan_process(atoi(e->d_name), snap);
	}
	if (d)
		closedir(d);
	if (unreadable)
		warn("Some live processes or executable mappings were inaccessible");
	kernel_status();
	json_object_object_foreach(subjects, key, value)
	{
		(void)key;
		json_object_array_add(get(report, "services"), json_object_get(value));
	}
	for (size_t i = 0; i < 5; i++) {
		bool now = !stat(path(inputs[i]), &after);

		if (now != exists[i] || (now && !same_file(&before[i], &after))) {
			warn("Package, kernel, or request state changed during inspection; "
			     "rescan required");
			json_object_object_add(report, "changed_during_scan",
					       json_object_new_boolean(true));
		}
	}
	number(report, "processes_scanned", scanned);
	number(report, "processes_exited", skipped);
	number(report, "processes_unreadable", unreadable);
	string(report, "scan_status", partial ? "partial" : "complete");
	json_object_object_add(report, "complete", json_object_new_boolean(!partial));
	json_object_put(subjects);
	json_object_put(packages);
	json_object_put(flatpak_owners);
	if (snap)
		json_object_put(snap);
	if (owners) {
		json_object_put(owners);
		owners = NULL;
	}
	return report;
}

static int ensure_runtime(void)
{
	struct stat st;

	if (mkdir(path(RUNTIME), 0700) && errno != EEXIST)
		return -1;
	if (lstat(path(RUNTIME), &st) || !S_ISDIR(st.st_mode) || (st.st_mode & 0077) ||
	    st.st_uid != geteuid()) {
		errno = EPERM;
		return -1;
	}
	return 0;
}

static int atomic_json(const char *name, json_object *o)
{
	char tmp[PATH_MAX];
	const char *data = json_object_to_json_string_ext(o, JSON_C_TO_STRING_PLAIN);

	snprintf(tmp, sizeof(tmp), "%s/.report.XXXXXX", path(RUNTIME));
	int fd = mkostemp(tmp, O_CLOEXEC);

	if (fd < 0)
		return -1;
	size_t total = strlen(data), n = 0;
	int ret = -1;

	while (n < total) {
		ssize_t r = write(fd, data + n, total - n);

		if (r < 0 && errno == EINTR)
			continue;
		if (r <= 0)
			goto out;
		n += r;
	}
	if (!fsync(fd) && !rename(tmp, path(name)))
		ret = 0;
out:
	close(fd);
	unlink(tmp);
	return ret;
}

static int lock_file(const char *p, int op, int seconds, bool create)
{
	int fd =
	    open(path(p), O_CLOEXEC | O_NOFOLLOW | (create ? O_RDWR | O_CREAT : O_RDONLY), 0600);
	int64_t end = millis() + seconds * 1000;

	if (fd < 0)
		return -1;
	while (flock(fd, op | LOCK_NB)) {
		if ((errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) ||
		    millis() >= end) {
			close(fd);
			return -1;
		}
		usleep(50000);
	}
	return fd;
}

static void print_text(json_object *r)
{
	printf("Restart advice: %s (scanned %lld processes)\n", str(r, "scan_status"),
	       (long long)json_object_get_int64(get(r, "processes_scanned")));
	json_object *list = get(r, "services");

	if (!length(list))
		puts("No affected host services or processes detected within assessed coverage.");
	for (size_t i = 0; i < length(list); i++) {
		json_object *s = json_object_array_get_idx(list, i),
			    *processes = get(s, "processes");
		printf("\n%s %s%s\n  %s\n", str(s, "kind"), str(s, "name"),
		       json_object_get_boolean(get(s, "disruptive")) ? " [disruptive/maintenance]"
								     : "",
		       str(s, "recommended_action"));
		for (size_t j = 0; j < length(processes); j++) {
			json_object *p = json_object_array_get_idx(processes, j),
				    *files = get(p, "files");
			for (size_t k = 0; k < length(files); k++) {
				json_object *f = json_object_array_get_idx(files, k);

				printf("  PID %lld: %s %s\n",
				       (long long)json_object_get_int64(get(p, "pid")),
				       str(f, "reason"),
				       json_object_to_json_string(get(f, "path")));
			}
		}
	}
	json_object *kernel = get(r, "kernel");

	printf("\nKernel: %s\n", str(kernel, "status"));
	if (*str(kernel, "recommended_action"))
		printf("  %s\n", str(kernel, "recommended_action"));
	list = get(r, "containers");
	for (size_t i = 0; i < length(list); i++) {
		json_object *c = json_object_array_get_idx(list, i);

		printf("Container %.12s (UID %lld): %s\n", str(c, "id"),
		       (long long)json_object_get_int64(get(c, "uid")), str(c, "image_status"));
		if (!strcmp(str(c, "image_status"), "changed"))
			puts("  Local image changed — recreation through its deployment controller is needed to use it.");
	}
	list = get(r, "applications");
	for (size_t i = 0; i < length(list); i++) {
		json_object *a = json_object_array_get_idx(list, i);

		printf("Flatpak %s (UID %lld): %s\n", str(a, "name"),
		       (long long)json_object_get_int64(get(a, "uid")), str(a, "deployment_status"));
	}
	list = get(r, "warnings");
	for (size_t i = 0; i < length(list); i++)
		printf("Warning: %s\n", json_object_get_string(json_object_array_get_idx(list, i)));
}

int main(int argc, char **argv)
{
	bool cached = false, json = false, worker = false, queue = false;

	for (int i = 1; i < argc; i++) {
#ifdef NEEDRESTART_TEST
		if (!strcmp(argv[i], "--test-root") && i + 1 < argc) {
			test_root = argv[++i];
			continue;
		}
#endif
		if (!strcmp(argv[i], "--cached"))
			cached = true;
		else if (!strcmp(argv[i], "--json"))
			json = true;
		else if (!strcmp(argv[i], "--worker"))
			worker = true;
		else if (!strcmp(argv[i], "--queue"))
			queue = true;
		else {
			fprintf(stderr, "Usage: needrestart [--json] [--cached]\n");
			return 1;
		}
	}
	if (geteuid() != 0 && !*test_root) {
		fprintf(stderr, "Run needrestart as root\n");
		return 1;
	}
	if (!*test_root && access("/run/systemd/system", F_OK)) {
		fprintf(stderr, "needrestart requires a native-systemd boot\n");
		return 1;
	}
	if (ensure_runtime()) {
		perror("needrestart runtime");
		return 1;
	}
	if (queue) {
		int request_lock = lock_file(RUNTIME "/request.lock", LOCK_EX, 2, true);

		if (request_lock < 0)
			return 1;
		json_object *o = json_object_new_object();

		number(o, "requested", time(NULL));
		int result = atomic_json(RUNTIME "/pending", o);

		json_object_put(o);
		close(request_lock);
		if (result)
			return 1;
		deadline = millis() + 3000;
		static char *const args[] = {"/usr/bin/systemctl", "--no-block", "start",
					     "openwrt-needrestart.path", NULL};
		char *data = command(0, args, 2000);

		if (!data) {
			save_error("Unable to activate the restart report worker; inspect openwrt-needrestart.path");
			return 1;
		}
		free(data);
		return 0;
	}
	json_object *r = NULL;

	if (cached) {
		r = read_json(path(RUNTIME "/report.json"));
		if (!r || json_object_get_int(get(r, "schema_version")) != 1) {
			fprintf(stderr,
				"No report available; run needrestart or queue a scan in LuCI\n");
			if (r)
				json_object_put(r);
			return 1;
		}
		char *boot = read_file(path("/proc/sys/kernel/random/boot_id"), 128);

		if (boot)
			boot[strcspn(boot, "\n")] = 0;
		if (!boot || strcmp(boot, str(r, "boot_id"))) {
			json_object_object_add(r, "complete", json_object_new_boolean(false));
			string(r, "scan_status", "stale");
		}
		free(boot);
	} else {
		int lock = lock_file(RUNTIME "/scan.lock", LOCK_EX, worker ? 30 : 2, true);

		if (lock < 0) {
			fprintf(stderr, "Another restart scan is active\n");
			return 1;
		}
		struct stat request = {}, now;
		bool requested = !stat(path(RUNTIME "/pending"), &request);
		/* Kernel APK policy finishes after ordinary commit hooks. Holding a
		 * shared APK lock keeps the entire bounded scan transaction-consistent.
		 */
		int apk = lock_file("/lib/apk/db/lock", LOCK_SH, worker ? 60 : 2, true);

		if (apk < 0) {
			fprintf(
			    stderr,
			    "APK transaction is busy or its lock is unavailable; scan deferred\n");
			save_error(
			    "APK transaction is busy or its lock is unavailable; scan deferred");
			close(lock);
			return 1;
		}
		json_object *active = json_object_new_object();

		number(active, "started", time(NULL));
		number(active, "pid", getpid());
		number(active, "start_time", start_time(getpid()));
		atomic_json(RUNTIME "/running", active);
		json_object_put(active);
		r = scan();
		if (atomic_json(RUNTIME "/report.json", r)) {
			perror("Saving restart report");
			save_error("Unable to save restart report");
			close(apk);
			close(lock);
			unlink(path(RUNTIME "/running"));
			json_object_put(r);
			return 1;
		}
		/* Queue replacement is serialized by the hook's rename. Retain a new
		 * request for PathExists to rerun after this oneshot exits.
		 */
		int request_lock = lock_file(RUNTIME "/request.lock", LOCK_EX, 2, true);

		if (request_lock >= 0) {
			if (requested && !stat(path(RUNTIME "/pending"), &now) &&
			    same_file(&request, &now) &&
			    !json_object_get_boolean(get(r, "changed_during_scan")))
				unlink(path(RUNTIME "/pending"));
			close(request_lock);
		}
		unlink(path(RUNTIME "/running"));
		unlink(path(RUNTIME "/error.json"));
		close(apk);
		close(lock);
	}
	if (json)
		puts(json_object_to_json_string_ext(r, JSON_C_TO_STRING_PLAIN));
	else
		print_text(r);
	int result = json_object_get_boolean(get(r, "complete")) ? 0 : 2;

	json_object_put(r);
	/* A valid partial report is a successful reporting job, not a reason for
	 * systemd's path activation to retry continuously.
	 */
	return worker ? 0 : result;
}
