// audout:u: the game's FMOD output. (LAS Recomp's audren:u mixer is not here: this game never opens it.)
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>

#include <SDL3/SDL.h>

#include "../hle.h"
#include "../settings.h"
#include "../ipc.h"
#include "../platform.h"

// ------------------------------------------------------------------ audout (buffers released in real time)
typedef struct AudioOut {
    uint32_t rate, channels, state;
    uint64_t tags[64], sizes[64], datas[64];
    SDL_AudioStream *stream;
    FILE *wav;
    uint32_t wav_bytes;
    int queued, released_n;
    uint64_t released[64];
    uint32_t ev_r, ev_w;
    KEvent *event;
    uint64_t played;
    pthread_mutex_t lock;
    pthread_t thread;
    volatile bool quit;  // (audout_free)
    // (diagnostics, logged every HM_AUDIO_STATS seconds: docs/audio.md)
    int id;
    uint64_t st_t0, st_frames, st_appends, st_underruns, st_wait_ns;
    int st_max_queued, st_min_sdl, st_max_sdl;
} AudioOut;

// Output gain: menu volume times HM_AUDIO_GAIN (applied live).
static void apply_gain(SDL_AudioStream *st) {
    static double env = -1;
    if (env < 0) env = getenv("HM_AUDIO_GAIN") ? atof(getenv("HM_AUDIO_GAIN")) : 1.0;
    float g = (float)(env * g_settings.volume);
    if (st && SDL_GetAudioStreamGain(st) != g) SDL_SetAudioStreamGain(st, g);
}

// Every open audio out (closed once: audout_close).
static AudioOut *g_outs[8];
static pthread_mutex_t g_track_lock = PTHREAD_MUTEX_INITIALIZER;
static void audio_track(AudioOut *a) {
    pthread_mutex_lock(&g_track_lock);
    for (int i = 0; i < 8; i++)
        if (a && !g_outs[i]) { g_outs[i] = a; a = NULL; }
    pthread_mutex_unlock(&g_track_lock);
}

static void audout_free(AudioOut *a) {
    a->quit = true;
    pthread_join(a->thread, NULL);
    if (a->stream) SDL_DestroyAudioStream(a->stream);
    if (a->wav) fclose(a->wav);
    free(a);
}

// The game closes its IAudioOut after every movie (the title's attract loop opens one per showing): stop the
// thread and the output stream then, or each showing leaves both running and fills g_outs.
static void audout_close(Service *s) {
    AudioOut *a = s->state;
    bool mine = false;
    pthread_mutex_lock(&g_track_lock);
    for (int i = 0; i < 8; i++) if (g_outs[i] == a) { g_outs[i] = NULL; mine = true; }
    pthread_mutex_unlock(&g_track_lock);
    if (!mine) return;  // (a reboot already closed it)
    s->state = NULL;
    audout_free(a);
    LOG("[audout] closed\n");
}

// Buffers are copied into an SDL stream and released once the stream has drained below its target, so the
// stream plays the role of the hardware queue. Without a device, buffers are released in real time.
static void *audout_thread(void *arg) {
    AudioOut *a = arg;
    uint32_t ch = a->channels ? a->channels : 2;
    int target = 0;
    if (a->stream) {
        SDL_AudioSpec dev;
        int dev_frames = 0;
        if (!SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(a->stream), &dev, &dev_frames) || dev_frames <= 0)
            dev_frames = 1024;
        // Release the next game buffer once the stream holds less than this: one device period by default
        // (audio_queue_ms; LAS Recomp held two, 43 ms at its 1024-frame period). The game keeps two or three
        // buffers queued behind it, so a late wake-up here doesn't starve the device.
        double qms = getenv("HM_AUDIO_QUEUE_MS") ? atof(getenv("HM_AUDIO_QUEUE_MS")) : g_settings.audio_queue_ms;
        target = qms > 0 ? (int)(qms * (a->rate ? a->rate : 48000) / 1000.0) * 2 * (int)ch : dev_frames * 2 * (int)ch;
        LOG("[audio] out %d: device %s, %d Hz, %d ch, %d frames per period; release below %.1f ms queued\n", a->id,
            SDL_GetAudioDeviceName(SDL_GetAudioStreamDevice(a->stream)), dev.freq, dev.channels, dev_frames,
            target / (2.0 * ch) * 1000.0 / (a->rate ? a->rate : 48000));
    }
    while (!a->quit) {
        pthread_mutex_lock(&a->lock);
        uint64_t size = 0, tag = 0, data = 0;
        if (a->state == 0 && a->queued) { size = a->sizes[0]; tag = a->tags[0]; data = a->datas[0]; }
        pthread_mutex_unlock(&a->lock);
        if (!size) { struct timespec ts = {0, 1000000}; nanosleep(&ts, NULL); continue; }
        uint64_t frames = size / (2 * ch);
        if (a->stream) {
            apply_gain(a->stream);
            int before = SDL_GetAudioStreamQueued(a->stream);
            if (before == 0 && a->st_frames) a->st_underruns++;  // (the device had nothing of ours left: a gap)
            if (data) SDL_PutAudioStreamData(a->stream, (const void *)(uintptr_t)data, (int)size);
            int q = SDL_GetAudioStreamQueued(a->stream);
            if (!a->st_appends || q < a->st_min_sdl) a->st_min_sdl = q;
            if (q > a->st_max_sdl) a->st_max_sdl = q;
            uint64_t w0 = plat_now_ns();
            while (SDL_GetAudioStreamQueued(a->stream) > target && !a->quit) { struct timespec ts = {0, 1000000}; nanosleep(&ts, NULL); }
            a->st_wait_ns += plat_now_ns() - w0;
        } else {
            uint64_t ns = frames * 1000000000ull / (a->rate ? a->rate : 48000);
            struct timespec ts = {(time_t)(ns / 1000000000ull), (long)(ns % 1000000000ull)};
            nanosleep(&ts, NULL);
        }
        if (a->wav && data) {
            fwrite((const void *)(uintptr_t)data, 1, size, a->wav);
            fflush(a->wav);
            a->wav_bytes += (uint32_t)size;
        }
        pthread_mutex_lock(&a->lock);
        if (a->queued && a->tags[0] == tag) {
            if (a->released_n < 64) a->released[a->released_n++] = a->tags[0];
            memmove(a->tags, a->tags + 1, (a->queued - 1) * 8);
            memmove(a->sizes, a->sizes + 1, (a->queued - 1) * 8);
            memmove(a->datas, a->datas + 1, (a->queued - 1) * 8);
            a->queued--;
            a->played += frames;
        }
        int inflight = a->queued;
        pthread_mutex_unlock(&a->lock);
        {   // stats: frames released per second against the wall clock, the game's queue, SDL's queue
            uint64_t now = plat_now_ns();
            if (!a->st_t0) a->st_t0 = now;
            a->st_frames += frames;
            a->st_appends++;
            if (inflight > a->st_max_queued) a->st_max_queued = inflight;
            static double every = -1;
            if (every < 0) every = getenv("HM_AUDIO_STATS") ? atof(getenv("HM_AUDIO_STATS")) : 0;
            double el = (now - a->st_t0) / 1e9;
            if (every > 0 && el >= every) {
                double bpf = 2.0 * ch;
                LOG("[audio] out %d: %.1f frames/s over %.1f s (%llu buffers of ~%llu frames), game queue up to %d, "
                    "SDL queue %.1f-%.1f ms, %llu gaps, waiting %.0f%%\n", a->id, a->st_frames / el, el,
                    (unsigned long long)a->st_appends, (unsigned long long)(a->st_frames / (a->st_appends ? a->st_appends : 1)),
                    a->st_max_queued, a->st_min_sdl / bpf * 1000.0 / a->rate, a->st_max_sdl / bpf * 1000.0 / a->rate,
                    (unsigned long long)a->st_underruns, 100.0 * a->st_wait_ns / 1e9 / el);
                a->st_t0 = now, a->st_frames = a->st_appends = a->st_underruns = a->st_wait_ns = 0;
                a->st_max_queued = a->st_max_sdl = 0;
            }
        }
        pthread_mutex_lock(&g_klock);
        kernel_signal(a->event);
        pthread_mutex_unlock(&g_klock);
    }
    return NULL;
}

static void audio_out(Service *s, IpcReq *req, IpcResp *resp) {
    AudioOut *a = s->state;
    if (getenv("HM_AUDIO_LOG") && req->cmd != 3 && req->cmd != 7) {
        IpcBuf *ob = out_buf(req, 0);
        LOG("[audout] cmd %u out %llx/%llx\n", req->cmd, ob ? (unsigned long long)ob->addr : 0ull,
            ob ? (unsigned long long)ob->size : 0ull);
    }
    switch (req->cmd) {
    case 0: OUT(uint32_t, 0) = a->state; resp_size(resp, 4); break;   // GetAudioOutState
    case 1: a->state = 0; break;                                      // Start
    case 2: a->state = 1; break;                                      // Stop
    case 3: case 7: {  // AppendAudioOutBuffer(tag) <- AudioOutBuffer {next, samples, capacity, size, offset}
        IpcBuf *b = in_buf(req, 0);
        uint64_t tag = IN(uint64_t, 0);
        uint64_t size = b && b->size >= 0x28 ? ((uint64_t *)(uintptr_t)b->addr)[3] : 0;
        if (getenv("HM_AUDIO_LOG") && b)
            LOG("[audout] append tag %llx buf %llx size %llx: %llx %llx %llx %llx %llx\n", (unsigned long long)tag,
                (unsigned long long)b->addr, (unsigned long long)b->size, ((unsigned long long *)(uintptr_t)b->addr)[0],
                ((unsigned long long *)(uintptr_t)b->addr)[1], ((unsigned long long *)(uintptr_t)b->addr)[2],
                ((unsigned long long *)(uintptr_t)b->addr)[3], ((unsigned long long *)(uintptr_t)b->addr)[4]);
        pthread_mutex_lock(&a->lock);
        // AudioOutBuffer {next, samples, capacity, size, offset}
        uint64_t data = b && b->size >= 0x28 ? ((uint64_t *)(uintptr_t)b->addr)[1] + ((uint64_t *)(uintptr_t)b->addr)[4] : 0;
        if (a->queued < 64) {
            a->tags[a->queued] = tag;
            a->sizes[a->queued] = size ? size : 4096;
            a->datas[a->queued] = size ? data : 0;
            a->queued++;
        }
        pthread_mutex_unlock(&a->lock);
        break;
    }
    case 4: resp->copy_handles[resp->ncopy++] = a->ev_r; break;  // RegisterBufferEvent
    case 5: case 8: {  // GetReleasedAudioOutBuffers -> tags
        IpcBuf *b = out_buf(req, 0);
        pthread_mutex_lock(&a->lock);
        int n = a->released_n;
        int max = b ? (int)(b->size / 8) : 0;
        if (n > max) n = max;
        if (b && b->size) memset((void *)(uintptr_t)b->addr, 0, b->size);  // SDK reads entry 0 even when n == 0
        for (int i = 0; i < n; i++) ((uint64_t *)(uintptr_t)b->addr)[i] = a->released[i];
        if (getenv("HM_AUDIO_LOG") && n) LOG("[audout] released %d (first %llx)\n", n, (unsigned long long)a->released[0]);
        memmove(a->released, a->released + n, (a->released_n - n) * 8);
        a->released_n -= n;
        pthread_mutex_unlock(&a->lock);
        OUT(uint32_t, 0) = (uint32_t)n;
        resp_size(resp, 4);
        break;
    }
    case 6: OUT(uint8_t, 0) = 0; resp_size(resp, 1); break;
    case 9: OUT(uint32_t, 0) = (uint32_t)a->queued; resp_size(resp, 4); break;
    case 10: OUT(uint64_t, 0) = a->played; resp_size(resp, 8); break;
    case 11: OUT(uint8_t, 0) = 1; resp_size(resp, 1); break;
    case 12: break;
    case 13: OUT(float, 0) = 1.0f; resp_size(resp, 4); break;
    default: LOG("[audout] IAudioOut cmd %u (ok)\n", req->cmd);
    }
}

SERVICE("audout:u", audout_u) {
    (void)s;
    switch (req->cmd) {
    case 0: case 2: {  // ListAudioOuts
        IpcBuf *b = out_buf(req, 0);
        if (b && b->size >= 0x100) strcpy((char *)(uintptr_t)b->addr, "DeviceOut");
        OUT(uint32_t, 0) = 1;
        resp_size(resp, 4);
        break;
    }
    case 1: case 3: {  // OpenAudioOut(rate, channels, aruid, name) -> rate, channels, format, state + IAudioOut
        AudioOut *a = calloc(1, sizeof *a);
        a->rate = IN(uint32_t, 0) ? IN(uint32_t, 0) : 48000;
        a->channels = IN(uint16_t, 4) ? IN(uint16_t, 4) : 2;
        if (a->channels != 1 && a->channels != 2 && a->channels != 6) a->channels = 2;
        a->state = 1;
        pthread_mutex_init(&a->lock, NULL);
        a->event = kernel_create_event_pair(&a->ev_w, &a->ev_r);
        static int g_audout_ids;
        a->id = ++g_audout_ids;
        if (getenv("HM_AUDOUT_WAV")) {  // raw s16le PCM, one file per output: <prefix>-<n>.raw
            char path[512];
            snprintf(path, sizeof path, "%s-%d.raw", getenv("HM_AUDOUT_WAV"), a->id);
            a->wav = fopen(path, "wb");
        }
        uint64_t open_t0 = plat_now_ns();
        {   // the device period asked of the audio server (PipeWire / Pulse): small, as the console's (docs/audio.md)
            static bool hinted;
            if (!hinted) {
                hinted = true;
                char frames[16];
                int p = getenv("HM_AUDIO_PERIOD") ? atoi(getenv("HM_AUDIO_PERIOD")) : g_settings.audio_period;
                if (p > 0) {
                    snprintf(frames, sizeof frames, "%d", p);
                    SDL_SetHint(SDL_HINT_AUDIO_DEVICE_SAMPLE_FRAMES, frames);
                }
            }
        }
        if (!(getenv("HM_NO_AUDIO") && strcmp(getenv("HM_NO_AUDIO"), "0")) && SDL_InitSubSystem(SDL_INIT_AUDIO)) {
            SDL_AudioSpec spec = {SDL_AUDIO_S16, (int)a->channels, (int)a->rate};
            a->stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, NULL, NULL);
            if (a->stream) {
                if (getenv("HM_AUDIO_GAIN")) SDL_SetAudioStreamGain(a->stream, (float)atof(getenv("HM_AUDIO_GAIN")));
                SDL_ResumeAudioStreamDevice(a->stream);
            }
        }
        pthread_create(&a->thread, NULL, audout_thread, a);
        audio_track(a);
        IpcBuf *b = out_buf(req, 0);
        if (b && b->size) strncpy((char *)(uintptr_t)b->addr, "DeviceOut", b->size);
        OUT(uint32_t, 0) = a->rate;
        OUT(uint32_t, 4) = a->channels;
        OUT(uint32_t, 8) = 2;  // PCM16
        OUT(uint32_t, 12) = 1; // stopped
        resp_size(resp, 16);
        Service *svc = service_new("IAudioOut", audio_out, a);
        svc->on_close = audout_close;
        ipc_return_object(resp, svc);
        LOG("[audout] opened %u Hz, %u ch (%.1f ms)\n", a->rate, a->channels, (plat_now_ns() - open_t0) / 1e6);
        break;
    }
    default: LOG("[audout] cmd %u (ok)\n", req->cmd);
    }
}
