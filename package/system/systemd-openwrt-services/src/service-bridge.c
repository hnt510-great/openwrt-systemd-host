// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <json-c/json.h>
#include <libubus.h>
#include <libubox/blobmsg_json.h>
#include <libubox/uloop.h>
#include <systemd/sd-daemon.h>
#include <systemd/sd-bus.h>

#define SELF "/usr/libexec/openwrt-service-bridge"
#define RUNTIME "/run/openwrt-service-bridge"
#define SOCKET RUNTIME "/control"
#define MAX_PACKET 8192
#define MAX_WORKERS 32
#define ACTION_TIMEOUT 900

static const char *test_root = "";
static struct uloop_timeout receipt_timer;
static struct uloop_fd server;
static unsigned int workers;
static unsigned int connections;
static int daemon_lock = -1;

static bool privileged(uid_t uid)
{
#ifdef BRIDGE_TEST
	if (*test_root && uid == geteuid())
		return true;
#endif
	return uid == 0;
}

/* Path overrides exist only in the separately compiled test executable. */
static const char *path(const char *suffix)
{
	static char paths[16][PATH_MAX];
	static unsigned int slot;
	char *p = paths[slot++ % 16];

	if (snprintf(p, PATH_MAX, "%s%s", test_root, suffix) >= PATH_MAX)
		abort();
	return p;
}

static json_object *field(json_object *o, const char *key)
{
	json_object *v = NULL;

	if (o)
		json_object_object_get_ex(o, key, &v);
	return v;
}

static const char *string(json_object *o, const char *key)
{
	json_object *v = field(o, key);

	return v && json_object_is_type(v, json_type_string) ?
		json_object_get_string(v) : "";
}

static void add_string(json_object *o, const char *key, const char *value)
{
	json_object_object_add(o, key, json_object_new_string(value));
}

static void add_int(json_object *o, const char *key, int value)
{
	json_object_object_add(o, key, json_object_new_int(value));
}

static bool valid_name(const char *s)
{
	const unsigned char *p = (const unsigned char *)s;

	if (!*p || strlen(s) > 127 || !isalnum(*p))
		return false;
	for (; *p; p++)
		if (!isalnum(*p) && !strchr("_.-", *p))
			return false;
	return true;
}

static bool excluded(const char *name)
{
	return !strcmp(name, "dbus") || !strcmp(name, "sshd") ||
		!strcmp(name, "umount");
}

static bool installed(const char *name)
{
	char p[256];
	struct stat st;

	if (!valid_name(name) || excluded(name))
		return false;
	snprintf(p, sizeof(p), "/etc/init.d/%s", name);
	return !stat(path(p), &st) && S_ISREG(st.st_mode) &&
		!access(path(p), X_OK);
}

static json_object *read_json(const char *p)
{
	return json_object_from_file(p);
}

static void write_json(const char *p, json_object *o)
{
	char tmp[PATH_MAX];
	int fd;
	const char *data = json_object_to_json_string_ext(o, JSON_C_TO_STRING_PLAIN);
	size_t len = strlen(data);

	if (snprintf(tmp, sizeof(tmp), "%s.%ld", p, (long)getpid()) >= (int)sizeof(tmp))
		return;
	fd = open(tmp, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
	if (fd < 0)
		return;
	if (write(fd, data, len) == (ssize_t)len && !close(fd)) {
		if (rename(tmp, p))
			unlink(tmp);
	} else {
		close(fd);
		unlink(tmp);
	}
}

/* Execute argv directly; script names, unit names and actions are never shell code. */
static int run(char *const argv[], int timeout)
{
	pid_t pid = fork();
	int status;
	time_t until = time(NULL) + timeout;

	if (pid < 0)
		return 1;
	if (!pid) {
		int fd = open("/dev/null", O_RDWR);

		setsid();
		if (fd >= 0) {
			dup2(fd, STDIN_FILENO);
			/* Script output belongs in the bridge journal, not the RPC reply. */
			if (!strcmp(argv[0], path("/usr/bin/systemctl")) ||
			    !strcmp(argv[0], path("/usr/sbin/nft"))) {
				dup2(fd, STDOUT_FILENO);
				dup2(fd, STDERR_FILENO);
			}
			if (fd > STDERR_FILENO)
				close(fd);
		}
		unsetenv("NOTIFY_SOCKET");
		execv(argv[0], argv);
		_exit(127);
	}
	for (;;) {
		pid_t done = waitpid(pid, &status, WNOHANG);

		if (done == pid)
			return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
		if (done < 0 && errno != EINTR)
			return 1;
		if (time(NULL) >= until) {
			kill(-pid, SIGTERM);
			usleep(200000);
			kill(-pid, SIGKILL);
			while (waitpid(pid, &status, 0) < 0 && errno == EINTR)
				;
			return 124;
		}
		usleep(20000);
	}
}

static int script_action(const char *name, const char *action)
{
	char p[256], executable[PATH_MAX];
	char *argv[6] = { executable, (char *)action, NULL };

	snprintf(p, sizeof(p), "/etc/init.d/%s", name);
	snprintf(executable, sizeof(executable), "%s", path(p));
	if (!*test_root) {
		char line[256];
		FILE *f = fopen(executable, "r");
		bool common = f && fgets(line, sizeof(line), f) && strstr(line, "/etc/rc.common");

		if (f)
			fclose(f);
		if (!common) {
			argv[0] = "/usr/libexec/openwrt-cgroup";
			argv[1] = "exec";
			argv[2] = (char *)name;
			argv[3] = executable;
			argv[4] = (char *)action;
			argv[5] = NULL;
		}
	}
	return run(argv, ACTION_TIMEOUT);
}

static void receipt(const char *name, const char *action, int code)
{
	char p[256];
	json_object *o;

	/* enable/disable and queries must not overwrite runtime action state. */
	if (!strcmp(action, "enable") || !strcmp(action, "disable") ||
	    !strcmp(action, "enabled") || !strcmp(action, "running"))
		return;
	if (strcmp(action, "boot") && strcmp(action, "shutdown") &&
	    strcmp(action, "start") && strcmp(action, "stop") &&
	    strcmp(action, "restart") && strcmp(action, "reload"))
		return;
	o = json_object_new_object();
	add_string(o, "action", action);
	add_int(o, "code", code);
	json_object_object_add(o, "completed", json_object_new_int64(time(NULL)));
	snprintf(p, sizeof(p), RUNTIME "/receipts/%s", name);
	write_json(path(p), o);
	json_object_put(o);
}

static json_object *get_receipt(const char *name)
{
	char p[256];

	snprintf(p, sizeof(p), RUNTIME "/receipts/%s", name);
	return read_json(path(p));
}

static bool stopped_receipt(json_object *r)
{
	return r && !json_object_get_int(field(r, "code")) &&
		(!strcmp(string(r, "action"), "stop") ||
		 !strcmp(string(r, "action"), "shutdown"));
}

static void metadata(const char *name, char *start, char *stop, bool *procd)
{
	char p[256], line[1024];
	FILE *f;

	*start = *stop = '\0';
	*procd = false;
	snprintf(p, sizeof(p), "/etc/init.d/%s", name);
	f = fopen(path(p), "r");
	if (!f)
		return;
	while (fgets(line, sizeof(line), f)) {
		char *s = line + strspn(line, " \t");
		char *value, *target = NULL;
		size_t n;

		if (!strncmp(s, "USE_PROCD=", 10))
			*procd = true;
		if (!strncmp(s, "START=", 6))
			target = start;
		else if (!strncmp(s, "STOP=", 5))
			target = stop;
		if (!target)
			continue;
		value = strchr(s, '=') + 1;
		if (*value == '"' || *value == '\'')
			value++;
		n = strspn(value, "0123456789");
		if (n && n <= 3) {
			memcpy(target, value, n);
			target[n] = '\0';
		}
	}
	fclose(f);
}

static bool enabled(const char *name)
{
	char start[4], stop[4], p[256];
	bool procd;
	struct stat st;

	metadata(name, start, stop, &procd);
	if (*start) {
		snprintf(p, sizeof(p), "/etc/rc.d/S%s%s", start, name);
		if (lstat(path(p), &st) || !S_ISLNK(st.st_mode))
			return false;
	}
	if (*stop) {
		snprintf(p, sizeof(p), "/etc/rc.d/K%s%s", stop, name);
		if (lstat(path(p), &st) || !S_ISLNK(st.st_mode))
			return false;
	}
	return true;
}

static const char *kind(const char *name)
{
	static char result[64];
	char key[128], value[64], line[256];
	FILE *f = fopen(path("/usr/share/openwrt-service-bridge/service-kinds"), "r");

	*result = '\0';
	if (!f)
		return result;
	while (fgets(line, sizeof(line), f))
		if (sscanf(line, "%127s %63s", key, value) == 2 && !strcmp(key, name)) {
			snprintf(result, sizeof(result), "%s", value);
			break;
		}
	fclose(f);
	return result;
}

static void ubus_data(struct ubus_request *req, int type, struct blob_attr *msg)
{
	json_object **result = req->priv;
	char *s;

	(void)type;
	if (!msg)
		return;
	s = blobmsg_format_json(msg, true);
	if (s) {
		if (*result)
			json_object_put(*result);
		*result = json_tokener_parse(s);
		free(s);
	}
}

static json_object *snapshot(const char *name)
{
	struct ubus_context *ctx;
	struct blob_buf b = {};
	json_object *o = NULL;
	uint32_t id;
	int ret;

#ifdef BRIDGE_TEST
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
		if (name)
			blobmsg_add_string(&b, "name", name);
		ret = ubus_invoke(ctx, id, "list", b.head, ubus_data, &o, 1500);
		blob_buf_free(&b);
	}
	ubus_free(ctx);
	if (ret && o) {
		json_object_put(o);
		o = NULL;
	}
	return o;
}

static int passwall_processes(const char *name)
{
	DIR *d = opendir(path("/proc"));
	struct dirent *e;
	char prefix[128], p[PATH_MAX], cmd[16384];
	int count = 0;

	if (!d)
		return -1;
	snprintf(prefix, sizeof(prefix), "/tmp/etc/%s/", name);
	while ((e = readdir(d))) {
		FILE *f;
		size_t n, i;

		if (strspn(e->d_name, "0123456789") != strlen(e->d_name))
			continue;
		snprintf(p, sizeof(p), "/proc/%s/cmdline", e->d_name);
		f = fopen(path(p), "r");
		if (!f)
			continue;
		n = fread(cmd, 1, sizeof(cmd) - 1, f);
		fclose(f);
		for (i = 0; i < n; i++)
			if (!cmd[i])
				cmd[i] = ' ';
		cmd[n] = '\0';
		if (strstr(cmd, prefix))
			count++;
	}
	closedir(d);
	return count;
}

/* A failed nft inspection is unknown, not proof that the table is absent. */
static int firewall_active(void)
{
	int descriptors[2], status = 0, result = -1;
	pid_t pid;
	char data[65536], executable[PATH_MAX];
	size_t used = 0;
	bool complete = false;
	time_t deadline = time(NULL) + 3;
	json_object *o, *tables;
	unsigned int i;

	snprintf(executable, sizeof(executable), "%s", path("/usr/sbin/nft"));
	if (pipe2(descriptors, O_CLOEXEC | O_NONBLOCK))
		return -1;
	pid = fork();
	if (!pid) {
		int null = open("/dev/null", O_RDWR);

		fcntl(descriptors[1], F_SETFL, 0);
		dup2(descriptors[1], STDOUT_FILENO);
		if (null >= 0) {
			dup2(null, STDIN_FILENO);
			dup2(null, STDERR_FILENO);
		}
		execl(executable, executable, "-j", "list", "tables", NULL);
		_exit(127);
	}
	close(descriptors[1]);
	if (pid < 0) {
		close(descriptors[0]);
		return -1;
	}
	while (time(NULL) < deadline && used < sizeof(data) - 1) {
		struct pollfd fd = { .fd = descriptors[0], .events = POLLIN };
		ssize_t n;

		poll(&fd, 1, 100);
		n = read(descriptors[0], data + used, sizeof(data) - 1 - used);
		if (!n) {
			complete = true;
			break;
		}
		if (n > 0)
			used += n;
		else if (errno != EAGAIN && errno != EINTR)
			break;
	}
	close(descriptors[0]);
	if (!complete)
		kill(pid, SIGKILL);
	while (waitpid(pid, &status, 0) < 0 && errno == EINTR)
		;
	if (!complete || !WIFEXITED(status) || WEXITSTATUS(status))
		return -1;
	data[used] = '\0';
	o = json_tokener_parse(data);
	tables = field(o, "nftables");
	if (tables && json_object_is_type(tables, json_type_array)) {
		result = 0;
		for (i = 0; i < json_object_array_length(tables); i++) {
			json_object *table = field(json_object_array_get_idx(tables, i), "table");

			if (!strcmp(string(table, "family"), "inet") &&
			    !strcmp(string(table, "name"), "fw4"))
				result = 1;
		}
	}
	if (o)
		json_object_put(o);
	return result;
}

/* Native placement is an observation, never a lifecycle or health decision. */
static void placement(const char *name, json_object *o)
{
	sd_bus *bus = NULL;
	sd_bus_message *reply = NULL;
	char slice[256] = "openwrt-";
	const char *group, *comm;
	uint32_t pid;
	size_t n = strlen(slice);
	int count = 0, ret;

	for (const char *p = name; *p; p++) {
		if (n + (*p == '-' ? 4 : 1) + sizeof(".slice") > sizeof(slice))
			return;
		if (*p == '-') {
			memcpy(slice + n, "\\x2d", 4);
			n += 4;
		} else {
			slice[n++] = *p;
		}
	}
	strcpy(slice + n, ".slice");
	add_string(o, "systemd_slice", slice);
	if (*test_root)
		return;
	ret = sd_bus_open_system(&bus);
	if (ret >= 0)
		ret = sd_bus_set_method_call_timeout(bus, 1500000);
	if (ret >= 0)
		ret = sd_bus_call_method(bus, "org.freedesktop.systemd1",
					 "/org/freedesktop/systemd1",
					 "org.freedesktop.systemd1.Manager",
					 "GetUnitProcesses", NULL, &reply, "s", slice);
	if (ret >= 0)
		ret = sd_bus_message_enter_container(reply, 'a', "(sus)");
	while (ret > 0) {
		ret = sd_bus_message_read(reply, "(sus)", &group, &pid, &comm);
		if (ret > 0)
			count++;
	}
	add_string(o, "systemd_placement", ret >= 0 && count ? "managed" : "unknown");
	if (ret >= 0)
		add_int(o, "scope_processes", count);
	sd_bus_message_unref(reply);
	sd_bus_flush_close_unref(bus);
}

static json_object *health(const char *name, json_object *snap)
{
	json_object *o = json_object_new_object(), *r = get_receipt(name);
	json_object *service = field(snap, name), *instances = field(service, "instances");
	const char *adapter = kind(name), *state = "unknown", *detail = "no health adapter";
	char message[256], start[4], stop[4];
	bool procd, respawning = false;
	int running = 0, total = 0, failed = 0, unknown = 0;

	metadata(name, start, stop, &procd);
	if (!strcmp(adapter, "task")) {
		if (!r)
			detail = "no completion observed in this boot";
		else if (stopped_receipt(r)) {
			state = "inactive";
			detail = "setup task stopped";
		} else if (json_object_get_int(field(r, "code"))) {
			state = "failed";
			detail = "setup action failed";
		} else {
			state = "active";
			detail = "setup action completed; no daemon expected";
		}
	} else if (!strcmp(adapter, "firewall")) {
		int present = firewall_active();

		state = present == 1 ? "active" : present == 0 ? "inactive" : "unknown";
		detail = present == 1 ? "inet fw4 table present" :
			present == 0 ? "inet fw4 table absent" : "nft inspection unavailable";
	} else if (!strcmp(adapter, "passwall") || !strcmp(adapter, "passwall_server")) {
		running = total = passwall_processes(name);
		state = running > 0 ? "active" : running == 0 ? "inactive" : "unknown";
		detail = running > 0 ? "live processes reference service runtime directory" :
			running == 0 ? "no service runtime processes" : "process inspection unavailable";
	} else if (!strcmp(adapter, "zram")) {
		char line[1024];
		FILE *f = fopen(path("/proc/swaps"), "r");

		if (f) {
			state = "inactive";
			detail = "no active zram swap";
			while (fgets(line, sizeof(line), f))
				if (!strncmp(line, "/dev/zram", 9)) {
					state = "active";
					detail = "zram swap active";
				}
			fclose(f);
		} else {
			detail = "swap inspection unavailable";
		}
	} else if (service || procd) {
		if (!snap) {
			detail = "ubus/procd status unavailable";
		} else if (!service) {
			state = "inactive";
			detail = "not registered with procd";
		} else if (!instances || !json_object_object_length(instances)) {
			state = "active";
			detail = "configured with no instances";
		} else {
			json_object_object_foreach(instances, key, in) {
				(void)key;
				total++;
				if (json_object_get_boolean(field(in, "running")))
					running++;
				else if (field(in, "respawn"))
					respawning = true;
				else if (!field(in, "exit_code"))
					unknown++;
				else if (json_object_get_int(field(in, "exit_code")))
					failed++;
			}
			state = running ? "active" : respawning ? "activating" :
				failed ? "failed" : unknown ? "unknown" :
				!strcmp(adapter, "procd-task") ? "active" : "inactive";
			snprintf(message, sizeof(message), "%d/%d instances running%s",
				 running, total, respawning ? "; procd respawn pending" :
				 failed ? "; instance failure" :
				 unknown ? "; exit status unavailable" :
				 !running && !strcmp(adapter, "procd-task") ?
				 "; setup completed successfully; no daemon expected" :
				 running < total ? "; instances exited successfully" : "");
			detail = message;
		}
	}
	if (!strcmp(state, "inactive") && r &&
	    json_object_get_int(field(r, "code"))) {
		state = "failed";
		detail = "last action failed and service is not running";
	}
	if (instances) {
		json_object *placement = json_object_new_object();

		json_object_object_foreach(instances, key, in) {
			json_object *entry = json_object_new_object();

			add_string(entry, "scope", string(in, "systemd_scope"));
			add_string(entry, "placement", string(in, "systemd_placement"));
			json_object_object_add(placement, key, entry);
		}
		json_object_object_add(o, "cgroups", placement);
	}
	placement(name, o);
	add_string(o, "name", name);
	add_string(o, "state", state);
	add_string(o, "detail", detail);
	add_int(o, "running", running);
	add_int(o, "total", total);
	add_int(o, "enabled", enabled(name));
	if (r)
		json_object_object_add(o, "last_action", r);
	return o;
}

static int rpc(json_object *request, json_object **reply, bool no_reply)
{
	struct sockaddr_un address = { .sun_family = AF_UNIX };
	struct timeval timeout = { .tv_sec = ACTION_TIMEOUT + 30 };
	char packet[MAX_PACKET];
	const char *data = json_object_to_json_string_ext(request, JSON_C_TO_STRING_PLAIN);
	int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0), ret = -1;
	ssize_t n;

	if (fd < 0)
		return -1;
	snprintf(address.sun_path, sizeof(address.sun_path), "%s", path(SOCKET));
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
	if (no_reply) {
		timeout.tv_sec = 0;
		timeout.tv_usec = 100000;
		setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
	}
	if (connect(fd, (struct sockaddr *)&address, sizeof(address)) ||
	    send(fd, data, strlen(data), MSG_NOSIGNAL) < 0)
		goto out;
	if (no_reply) {
		ret = 0;
		goto out;
	}
	n = recv(fd, packet, sizeof(packet) - 1, 0);
	if (n <= 0 || n >= (ssize_t)sizeof(packet) - 1)
		goto out;
	packet[n] = '\0';
	*reply = json_tokener_parse(packet);
	if (*reply)
		ret = 0;
out:
	close(fd);
	return ret;
}

static json_object *request(const char *action, const char *name)
{
	json_object *o = json_object_new_object();

	add_string(o, "action", action);
	add_string(o, "name", name ?: "");
	return o;
}

static bool mutation(const char *action)
{
	return !strcmp(action, "start") || !strcmp(action, "stop") ||
		!strcmp(action, "restart") || !strcmp(action, "reload") ||
		!strcmp(action, "enable") || !strcmp(action, "disable");
}

static json_object *handle(json_object *q, uid_t uid)
{
	const char *action = string(q, "action"), *name = string(q, "name");
	json_object *o, *snap;
	char p[256];
	int rc = 0, lock = -1;

	o = json_object_new_object();
	if (!installed(name)) {
		add_string(o, "error", excluded(name) ?
			   "use native dbus.service or sshd.service; umount is recovery-only" :
			   "unknown OpenWrt service");
		rc = 4;
	} else if (!mutation(action) && strcmp(action, "status") &&
		   strcmp(action, "is-active") && strcmp(action, "is-enabled")) {
		add_string(o, "error", "unsupported bridge action");
		rc = 2;
	} else if (mutation(action) && !privileged(uid)) {
		add_string(o, "error", "bridge changes require root/sudo");
		rc = 1;
	} else if (mutation(action)) {
		snprintf(p, sizeof(p), RUNTIME "/locks/%s", name);
		lock = open(path(p), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
		if (lock < 0 || flock(lock, LOCK_EX)) {
			add_string(o, "error", "cannot lock service action");
			rc = 1;
		} else {
			rc = script_action(name, action);
			receipt(name, action, rc);
			if (!rc && json_object_get_boolean(field(q, "now")) &&
			    (!strcmp(action, "enable") || !strcmp(action, "disable"))) {
				const char *next = !strcmp(action, "enable") ? "start" : "stop";

				rc = script_action(name, next);
				receipt(name, next, rc);
			}
		}
		if (lock >= 0)
			close(lock);
		if (rc && !field(o, "error")) {
			char detail[256];

			snprintf(detail, sizeof(detail),
				 "%s exited %d; see journalctl -u openwrt-service-bridge",
				 action, rc);
			add_string(o, "error", detail);
		}
	} else if (!strcmp(action, "is-enabled")) {
		add_string(o, "state", enabled(name) ? "enabled" : "disabled");
		rc = enabled(name) ? 0 : 1;
	} else {
		json_object_put(o);
		snap = snapshot(name);
		o = health(name, snap);
		if (snap)
			json_object_put(snap);
		rc = !strcmp(string(o, "state"), "active") ? 0 :
			!strcmp(string(o, "state"), "unknown") ? 4 : 3;
	}
	add_int(o, "code", rc);
	return o;
}

struct connection {
	struct uloop_fd fd;
	struct uloop_timeout timeout;
};

struct worker {
	struct uloop_process process;
};

/* Receipts have no authority over processes or systemd units. */
static void prune_receipts(struct uloop_timeout *t)
{
	DIR *d = opendir(path(RUNTIME "/receipts"));
	struct dirent *entry;

	if (d) {
		while ((entry = readdir(d))) {
			char p[512];

			if (!valid_name(entry->d_name) || installed(entry->d_name))
				continue;
			snprintf(p, sizeof(p), RUNTIME "/receipts/%s", entry->d_name);
			unlink(path(p));
		}
		closedir(d);
	}
	uloop_timeout_set(t, 30000);
}

static void schedule(void)
{
	uloop_timeout_set(&receipt_timer, 100);
}

static void worker_done(struct uloop_process *p, int status)
{
	(void)status;
	workers--;
	free(container_of(p, struct worker, process));
	schedule();
}

static void close_connection(struct connection *c)
{
	uloop_timeout_cancel(&c->timeout);
	uloop_fd_delete(&c->fd);
	close(c->fd.fd);
	connections--;
	free(c);
}

static void connection_timeout(struct uloop_timeout *t)
{
	close_connection(container_of(t, struct connection, timeout));
}

static void receive_request(struct uloop_fd *fd, unsigned int events)
{
	struct connection *c = container_of(fd, struct connection, fd);
	struct ucred credential;
	socklen_t length = sizeof(credential);
	char packet[MAX_PACKET];
	json_object *q;
	struct worker *w;
	ssize_t n;

	(void)events;
	n = recv(fd->fd, packet, sizeof(packet) - 1, MSG_DONTWAIT | MSG_TRUNC);
	if (n <= 0 || n >= (ssize_t)sizeof(packet) - 1 ||
	    getsockopt(fd->fd, SOL_SOCKET, SO_PEERCRED, &credential, &length))
		goto done;
	packet[n] = '\0';
	q = json_tokener_parse(packet);
	if (!q)
		goto done;
	if (!strcmp(string(q, "action"), "notify")) {
		if (privileged(credential.uid) && installed(string(q, "name"))) {
			receipt(string(q, "name"), string(q, "operation"),
				json_object_get_int(field(q, "code")));
			schedule();
		}
	} else if (!strcmp(string(q, "action"), "refresh")) {
		if (privileged(credential.uid))
			schedule();
	} else if (workers < MAX_WORKERS) {
		w = calloc(1, sizeof(*w));
		if (w) {
			w->process.pid = fork();
			if (!w->process.pid) {
				json_object *o;
				const char *data;

				close(server.fd);
				/* Do not inherit the parent's event-loop signal machinery. */
				uloop_done();
				signal(SIGCHLD, SIG_DFL);
				if (fd->fd > 3)
					close_range(3, fd->fd - 1, 0);
				close_range(fd->fd + 1, ~0U, 0);
				o = handle(q, credential.uid);
				data = json_object_to_json_string_ext(o, JSON_C_TO_STRING_PLAIN);
				send(fd->fd, data, strlen(data), MSG_NOSIGNAL);
				json_object_put(o);
				_exit(0);
			}
			if (w->process.pid > 0) {
				workers++;
				w->process.cb = worker_done;
				uloop_process_add(&w->process);
			} else {
				free(w);
			}
		}
	}
	json_object_put(q);
done:
	close_connection(c);
}

static void accept_request(struct uloop_fd *fd, unsigned int events)
{
	int client;
	struct connection *c;

	(void)events;
	client = accept4(fd->fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
	if (client < 0)
		return;
	if (connections >= 128) {
		close(client);
		return;
	}
	c = calloc(1, sizeof(*c));
	if (!c) {
		close(client);
		return;
	}
	c->fd.fd = client;
	connections++;
	c->fd.cb = receive_request;
	c->timeout.cb = connection_timeout;
	uloop_fd_add(&c->fd, ULOOP_READ);
	uloop_timeout_set(&c->timeout, 2000);
}

static int daemon_main(void)
{
	struct sockaddr_un address = { .sun_family = AF_UNIX };
	static const char * const directories[] = {
		RUNTIME, RUNTIME "/receipts", RUNTIME "/locks"
	};
	unsigned int i;
	FILE *comm;
	char init[32];

	if (!*test_root) {
		comm = fopen("/proc/1/comm", "r");
		if (!comm)
			return 1;
		*init = '\0';
		if (!fgets(init, sizeof(init), comm))
			*init = '\0';
		fclose(comm);
		if (geteuid() || strcmp(init, "systemd\n") ||
		    access("/etc/openwrt-systemd", F_OK))
			return 1;
	}

	for (i = 0; i < sizeof(directories) / sizeof(*directories); i++)
		if (mkdir(path(directories[i]), i == 2 ? 0700 : 0755) && errno != EEXIST)
			return 1;
	daemon_lock = open(path(RUNTIME "/daemon.lock"), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
	if (daemon_lock < 0 || flock(daemon_lock, LOCK_EX | LOCK_NB))
		return 1;
	server.fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (server.fd < 0)
		return 1;
	snprintf(address.sun_path, sizeof(address.sun_path), "%s", path(SOCKET));
	unlink(address.sun_path);
	if (bind(server.fd, (struct sockaddr *)&address, sizeof(address)) ||
	    chmod(address.sun_path, 0666) || listen(server.fd, 32))
		return 1;
	uloop_init();
	server.cb = accept_request;
	uloop_fd_add(&server, ULOOP_READ);
	receipt_timer.cb = prune_receipts;
	uloop_timeout_set(&receipt_timer, 100);
	sd_notify(0, "READY=1");
	uloop_run();
	unlink(address.sun_path);
	uloop_done();
	return 0;
}

static bool decode_unit(const char *unit, char name[128])
{
	const char *end;
	size_t n;

	if (strncmp(unit, "openwrt@", 8))
		return false;
	end = unit + strlen(unit);
	if (end - unit >= 8 && !strcmp(end - 8, ".service"))
		end -= 8;
	n = end - (unit + 8);
	if (n >= 128)
		return false;
	memcpy(name, unit + 8, n);
	name[n] = '\0';
	return valid_name(name);
}

static int client(int argc, char **argv)
{
	const char *action;
	bool now = false, quiet = false, any = false;
	int i, result = 0;

	if (argc < 2)
		return 2;
	action = argv[1];
	/* Validate the entire request before the first action has side effects. */
	for (i = 2; i < argc; i++) {
		char name[128];

		if (!strcmp(argv[i], "--now")) {
			now = true;
			continue;
		}
		if (!strcmp(argv[i], "--quiet")) {
			quiet = true;
			continue;
		}
		if (!decode_unit(argv[i], name)) {
			fprintf(stderr, "Invalid OpenWrt unit name; use separate commands for native units.\n");
			return 2;
		}
		if (!installed(name)) {
			fprintf(stderr, "%s: %s\n", argv[i], excluded(name) ?
				"use native dbus.service or sshd.service; umount is recovery-only" :
				"unknown OpenWrt service");
			return 4;
		}
	}
	for (i = 2; i < argc; i++) {
		char name[128];
		const char *unit = argv[i];
		json_object *q, *reply = NULL;
		int rc;

		if (!strcmp(unit, "--now"))
			continue;
		if (!strcmp(unit, "--quiet"))
			continue;
		if (!decode_unit(unit, name))
			return 2;
		q = request(action, name);
		add_int(q, "now", now);
		rc = rpc(q, &reply, false);
		json_object_put(q);
		if (rc) {
			fprintf(stderr, "OpenWrt service bridge unavailable; no fallback action performed.\n");
			return 4;
		}
		rc = json_object_get_int(field(reply, "code"));
		if (*string(reply, "error"))
			fprintf(stderr, "%s: %s\n", unit, string(reply, "error"));
		else if (!quiet && (!strcmp(action, "status"))) {
			json_object *last = field(reply, "last_action");

			printf("%s\n  Boot: %s\n  State: %s (%s)\n", unit,
			       json_object_get_int(field(reply, "enabled")) ? "enabled" : "disabled",
			       string(reply, "state"), string(reply, "detail"));
			printf("  Placement: %s (%s)\n", string(reply, "systemd_placement"),
			       string(reply, "systemd_slice"));
			json_object *groups = field(reply, "cgroups");

			if (groups) {
				json_object_object_foreach(groups, key, entry) {
					if (*string(entry, "placement"))
						printf("  Cgroup %s: %s %s\n", key,
						       string(entry, "placement"), string(entry, "scope"));
				}
			}
			if (last)
				printf("  Last action: %s (exit %d)\n", string(last, "action"),
				       json_object_get_int(field(last, "code")));
		} else if (!quiet && (!strcmp(action, "is-active") || !strcmp(action, "is-enabled"))) {
			puts(string(reply, "state"));
		}
		/* systemctl queries succeed if at least one requested unit matches. */
		any |= rc == 0;
		if (rc && !result)
			result = rc;
		json_object_put(reply);
	}
	if (!strcmp(action, "is-active") || !strcmp(action, "is-enabled"))
		return any ? 0 : result;
	return result;
}

int main(int argc, char **argv)
{
	const char *command;

#ifdef BRIDGE_TEST
	if (argc >= 3 && !strcmp(argv[1], "--test-root")) {
		test_root = argv[2];
		argc -= 2;
		argv += 2;
	}
#endif
	if (argc < 2)
		return 2;
	command = argv[1];
	if (!strcmp(command, "daemon"))
		return daemon_main();
	if (!strcmp(command, "systemctl"))
		return client(argc - 1, argv + 1);
	if (!strcmp(command, "notify") || !strcmp(command, "refresh")) {
		json_object *q;
		int ret;

		if (!strcmp(command, "notify") && (argc != 5 || !valid_name(argv[2])))
			return 2;
		q = request(command, argc > 2 ? argv[2] : "");
		if (!strcmp(command, "notify")) {
			add_string(q, "operation", argv[3]);
			add_int(q, "code", atoi(argv[4]));
		}
		ret = rpc(q, NULL, true);
		json_object_put(q);
		return ret ? 1 : 0;
	}
	return 2;
}
