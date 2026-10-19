// SPDX-License-Identifier: LGPL-2.1-only
/* Exercise failure completion and the pipe lifecycle without a live daemon. */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>

#define main logread_program_main
#include "logread.c"
#undef main

bool uloop_cancelled;
static int freed_streams;

int uloop_timeout_cancel(struct uloop_timeout *timeout)
{
	timeout->pending = false;
	return 0;
}

void ustream_free(struct ustream *stream)
{
	assert(stream == &log_stream.stream);
	assert(fcntl(log_stream.fd.fd, F_GETFD) >= 0);
	freed_streams++;
}

int main(void)
{
	int fds[2];

	log_follow = 1;
	read_timeout.pending = true;
	logread_request_done(NULL, UBUS_STATUS_NOT_FOUND);
	assert(!read_timeout.pending && uloop_cancelled);
	assert(read_status == UBUS_STATUS_NOT_FOUND);
	assert(logd_conn_tries == LOGD_CONNECT_RETRY);

	uloop_cancelled = false;
	log_stream_open = true;
	logread_request_done(NULL, 0);
	assert(!uloop_cancelled && read_status == 0);

	log_stream_open = false;
	logread_request_done(NULL, 0);
	assert(uloop_cancelled && read_status == UBUS_STATUS_UNKNOWN_ERROR);

	uloop_cancelled = false;
	logd_conn_tries = 0;
	logread_request_timeout(NULL);
	assert(uloop_cancelled && read_status == UBUS_STATUS_TIMEOUT);
	assert(logd_conn_tries == LOGD_CONNECT_RETRY);

	assert(pipe(fds) == 0);
	log_stream.fd.fd = fds[0];
	log_stream_open = true;
	logread_stream_close();
	assert(!log_stream_open && freed_streams == 1);
	assert(fcntl(fds[0], F_GETFD) < 0 && errno == EBADF);
	logread_stream_close();
	assert(freed_streams == 1);
	close(fds[1]);
	puts("forwarder request failure, timeout and reconnect cleanup passed");
}
