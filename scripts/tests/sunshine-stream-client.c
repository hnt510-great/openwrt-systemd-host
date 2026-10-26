/* SPDX-License-Identifier: GPL-3.0-only
 * Headless Moonlight receiver: save H.264 frames and timing, decode Opus.
 * Link against the pinned moonlight-common-c used by Sunshine, libdl and libm.
 */
#include <Limelight.h>
#include <arpa/inet.h>
#include <dlfcn.h>
#include <math.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static FILE *video, *timing;
static atomic_int terminated;
static unsigned frames, packets;
static unsigned long long samples;
static double square_sum;
static int peak, channels;
static void *opus, *decoder;
static void *(*decoder_create)(int, int, int, int, const unsigned char *, int *);
static int (*decode)(void *, const unsigned char *, int, short *, int, int);
static void (*decoder_destroy)(void *);

static double now(void)
{
	struct timespec value;
	clock_gettime(CLOCK_MONOTONIC, &value);
	return value.tv_sec + value.tv_nsec / 1e9;
}

static int setup(int format, int width, int height, int rate, void *context, int flags)
{
	(void)context;
	(void)flags;
	fprintf(timing, "setup,%d,%d,%d,%d\n", format, width, height, rate);
	return format == VIDEO_FORMAT_H264 ? 0 : -1;
}

static int frame(PDECODE_UNIT unit)
{
	fprintf(timing, "frame,%u,%d,%.9f,%llu,%u\n", frames++, unit->frameNumber,
		now(), (unsigned long long)unit->presentationTimeUs, unit->frameHostProcessingLatency);
	for (PLENTRY entry = unit->bufferList; entry; entry = entry->next)
		if (fwrite(entry->data, 1, entry->length, video) != (size_t)entry->length)
			return DR_NEED_IDR;
	return DR_OK;
}

static int audio_init(int configuration, const POPUS_MULTISTREAM_CONFIGURATION config, void *context, int flags)
{
	(void)configuration;
	(void)context;
	(void)flags;
	int error;
	channels = config->channelCount;
	opus = dlopen("libopus.so.0", RTLD_NOW);
	if (!opus)
		return -1;
	*(void **)(&decoder_create) = dlsym(opus, "opus_multistream_decoder_create");
	*(void **)(&decode) = dlsym(opus, "opus_multistream_decode");
	*(void **)(&decoder_destroy) = dlsym(opus, "opus_multistream_decoder_destroy");
	if (!decoder_create || !decode || !decoder_destroy)
		return -1;
	decoder = decoder_create(config->sampleRate, channels, config->streams, config->coupledStreams, config->mapping, &error);
	return error || !decoder ? -1 : 0;
}

static void audio_sample(char *data, int length)
{
	short pcm[5760 * AUDIO_CONFIGURATION_MAX_CHANNEL_COUNT];
	int count = decode(decoder, (unsigned char *)data, length, pcm, 5760, 0);
	packets++;
	for (int i = 0; i < count * channels; i++) {
		int value = abs(pcm[i]);
		if (value > peak)
			peak = value;
		square_sum += (double)value * value;
		samples++;
	}
}

static void audio_cleanup(void)
{
	if (decoder)
		decoder_destroy(decoder);
	if (opus)
		dlclose(opus);
}

static void connection_terminated(int error)
{
	fprintf(stderr, "Connection terminated: %d\n", error);
	terminated = 1;
}

static void stage_failed(int stage, int error)
{
	fprintf(stderr, "Stage %d failed: %d\n", stage, error);
}

static void log_message(const char *format, ...)
{
	va_list args;
	va_start(args, format);
	vfprintf(stderr, format, args);
	va_end(args);
}

int main(int argc, char **argv)
{
	if (argc != 12) {
		fprintf(stderr, "Usage: %s HOST APP_VERSION GFE_VERSION RTSP_URL AES_HEX KEY_ID SECONDS PREFIX WIDTH HEIGHT FPS\n", argv[0]);
		return 2;
	}
	char path[4096];
	snprintf(path, sizeof(path), "%s.h264", argv[8]);
	video = fopen(path, "wb");
	snprintf(path, sizeof(path), "%s.csv", argv[8]);
	timing = fopen(path, "w");
	if (!video || !timing)
		return 2;
	setvbuf(timing, NULL, _IOLBF, 0);
	SERVER_INFORMATION server;
	STREAM_CONFIGURATION config;
	DECODER_RENDERER_CALLBACKS dr;
	AUDIO_RENDERER_CALLBACKS ar;
	CONNECTION_LISTENER_CALLBACKS callbacks;
	LiInitializeServerInformation(&server);
	LiInitializeStreamConfiguration(&config);
	LiInitializeVideoCallbacks(&dr);
	LiInitializeAudioCallbacks(&ar);
	LiInitializeConnectionCallbacks(&callbacks);
	server.address = argv[1];
	server.serverInfoAppVersion = argv[2];
	server.serverInfoGfeVersion = argv[3];
	server.rtspSessionUrl = argv[4];
	server.serverCodecModeSupport = 1; /* This probe requests H.264 only. */
	config.width = atoi(argv[9]);
	config.height = atoi(argv[10]);
	config.fps = atoi(argv[11]);
	config.bitrate = 12000;
	config.packetSize = 1024;
	config.streamingRemotely = STREAM_CFG_LOCAL;
	config.audioConfiguration = AUDIO_CONFIGURATION_STEREO;
	config.supportedVideoFormats = VIDEO_FORMAT_H264;
	config.clientRefreshRateX100 = config.fps * 100;
	if (strlen(argv[5]) != 32)
		return 2;
	for (int i = 0; i < 16; i++) {
		unsigned value;
		if (sscanf(argv[5] + i * 2, "%2x", &value) != 1)
			return 2;
		config.remoteInputAesKey[i] = value;
	}
	uint32_t key_id = htonl(strtoul(argv[6], NULL, 10));
	memcpy(config.remoteInputAesIv, &key_id, sizeof(key_id));
	dr.setup = setup;
	dr.submitDecodeUnit = frame;
	dr.capabilities = CAPABILITY_DIRECT_SUBMIT;
	ar.init = audio_init;
	ar.decodeAndPlaySample = audio_sample;
	ar.cleanup = audio_cleanup;
	ar.capabilities = CAPABILITY_DIRECT_SUBMIT | CAPABILITY_SUPPORTS_ARBITRARY_AUDIO_DURATION;
	callbacks.connectionTerminated = connection_terminated;
	callbacks.stageFailed = stage_failed;
	callbacks.logMessage = log_message;
	int result = LiStartConnection(&server, &config, &callbacks, &dr, &ar, NULL, 0, NULL, 0);
	if (result) {
		fprintf(stderr, "Connection failed: %d\n", result);
		return 1;
	}
	double start = now(), next_key = start + 5, deadline = start + atoi(argv[7]);
	while (!terminated && now() < deadline) {
		if (now() >= next_key) {
			fprintf(timing, "input,%.9f\n", now());
			LiSendKeyboardEvent(0x77, KEY_ACTION_DOWN, 0);
			LiSendKeyboardEvent(0x77, KEY_ACTION_UP, 0);
			next_key += 1;
		}
		usleep(10000);
	}
	LiStopConnection();
	fprintf(timing, "summary,%u,%u,%llu,%d,%.3f,%.3f\n", frames, packets, samples, peak,
		samples ? sqrt(square_sum / samples) : 0, now() - start);
	fclose(video);
	fclose(timing);
	return terminated || !frames ? 1 : 0;
}
