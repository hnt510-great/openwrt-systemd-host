#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <systemd/sd-journal.h>

struct fixture { const char *name; const char *value; size_t size; };
static struct fixture fields[16];
static int field_count;
static int time_error;
static char scratch[8192];

int sd_journal_get_data(sd_journal *j, const char *name, const void **data, size_t *size)
{
	for (int i = 0; i < field_count; i++) {
		if (strcmp(fields[i].name, name))
			continue;
		size_t prefix = strlen(name) + 1;
		snprintf(scratch, sizeof(scratch), "%s=", name);
		memcpy(scratch + prefix, fields[i].value, fields[i].size);
		*data = scratch;
		*size = prefix + fields[i].size;
		return 0;
	}
	return -2;
}
int sd_journal_get_realtime_usec(sd_journal *j, uint64_t *timestamp)
{
	*timestamp = 1234567890123ULL;
	return time_error;
}
#include "journal.c"

static void field(const char *name, const char *value)
{
	fields[field_count++] = (struct fixture){name, value, strlen(value)};
}
int main(void)
{
	struct journal_record r;
	assert(journal_record_read(&r) == 0);
	field("MESSAGE", "hello");
	assert(journal_record_read(&r) == 1);
	assert(r.priority == (LOG_DAEMON | LOG_INFO));
	assert(r.source == SOURCE_SYSLOG && !strcmp(r.msg, "journal: hello"));
	assert(r.ts.tv_sec == 1234567 && r.ts.tv_nsec == 890123000);
	field("SYSLOG_IDENTIFIER", "router");
	field("SYSLOG_PID", "4242");
	field("SYSLOG_FACILITY", "16");
	field("PRIORITY", "3");
	assert(journal_record_read(&r) == 1);
	assert(r.priority == 131 && !strcmp(r.msg, "router[4242]: hello"));
	fields[3].value = "99"; fields[3].size = 2;
	assert(journal_record_read(&r) == 1 && r.priority == (LOG_DAEMON | LOG_ERR));
	fields[4].value = "-1"; fields[4].size = 2;
	assert(journal_record_read(&r) == 1 && (r.priority & 7) == LOG_INFO);
	fields[2].value = "x]"; fields[2].size = 2;
	assert(journal_record_read(&r) == 1 && !strcmp(r.msg, "router: hello"));
	field("_TRANSPORT", "kernel");
	assert(journal_record_read(&r) == 1 && r.source == SOURCE_KLOG && !strcmp(r.msg, "hello"));
	char binary[] = "a\nb\0c\tend";
	fields[0].value = binary; fields[0].size = sizeof(binary) - 1;
	assert(journal_record_read(&r) == 1 && !strcmp(r.msg, "a b c end"));
	char large[4096]; memset(large, 'x', sizeof(large));
	fields[0].value = large; fields[0].size = sizeof(large);
	assert(journal_record_read(&r) == 1 && r.size == LOG_LINE_SIZE && strlen(r.msg) == LOG_LINE_SIZE - 1);
	time_error = -5;
	assert(journal_record_read(&r) == -5);
	char directory[] = "/tmp/logd-journal-path-XXXXXX";
	char previous[128], absent[128];
	assert(mkdtemp(directory));
	snprintf(previous, sizeof(previous), "%s-old", directory);
	snprintf(absent, sizeof(absent), "%s/absent", directory);
	journal_paths[0].name = directory;
	journal_paths[1].name = absent;
	assert(journal_paths_changed());
	assert(!journal_paths_changed());
	assert(rename(directory, previous) == 0);
	assert(mkdir(directory, 0700) == 0);
	assert(journal_paths_changed());
	assert(!journal_paths_changed());
	assert(rmdir(directory) == 0);
	assert(journal_paths_changed());
	assert(rename(previous, directory) == 0);
	assert(journal_paths_changed());
	assert(rmdir(directory) == 0);
	puts("record conversion passed");
}
