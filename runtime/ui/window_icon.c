// The window's icon: the same picture as the menu entry's (owner). That is the 256 px PNG the package installs into
// the icon theme (installer/pack.py make_icon: made from the game's own icon in the player's dump), so it is read
// from there at run time: inside the AppImage when running from one, the player's own icon folder, the system's;
// else icon.jpg in the game folder (a development install). Decoded with FFmpeg, which the movies already need (SDL
// itself reads only BMP). Wayland compositors mostly show the menu entry's icon through the app id anyway; this one
// is for X11 / XWayland and compositors that take a window's own icon.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <SDL3/SDL.h>
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>

#include "../rt.h"

#define ICON_REL "icons/hicolor/256x256/apps/hylian-melodies.png"

static bool find_icon(char *out, size_t cap) {
    const char *gd = getenv("HM_GAME_DIR");  // (an AppImage: <image>/opt/hylian-melodies; its icons beside)
    const char *m = gd ? strstr(gd, "/opt/hylian-melodies") : NULL;
    if (m) {
        snprintf(out, cap, "%.*s/usr/share/" ICON_REL, (int)(m - gd), gd);
        if (access(out, R_OK) == 0) return true;
    }
    const char *xd = getenv("XDG_DATA_HOME"), *home = getenv("HOME");
    if (xd && *xd == '/') snprintf(out, cap, "%s/" ICON_REL, xd);
    else if (home) snprintf(out, cap, "%s/.local/share/" ICON_REL, home);
    if ((xd || home) && access(out, R_OK) == 0) return true;
    const char *dirs = getenv("XDG_DATA_DIRS");
    if (!dirs || !*dirs) dirs = "/usr/local/share:/usr/share";
    for (const char *p = dirs; *p;) {
        const char *e = strchr(p, ':');
        int n = e ? (int)(e - p) : (int)strlen(p);
        snprintf(out, cap, "%.*s/" ICON_REL, n, p);
        if (n && access(out, R_OK) == 0) return true;
        p += n + (e != NULL);
    }
    snprintf(out, cap, "icon.jpg");  // (the game folder: the working directory)
    return access(out, R_OK) == 0;
}

// -> an RGBA surface of the picture (at most 256 px a side), or NULL
static SDL_Surface *decode(const char *path) {
    AVFormatContext *fmt = NULL;
    AVCodecContext *dec = NULL;
    AVPacket *pkt = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    SDL_Surface *s = NULL;
    if (!pkt || !frame || avformat_open_input(&fmt, path, NULL, NULL) < 0) goto done;
    if (avformat_find_stream_info(fmt, NULL) < 0) goto done;
    int si = av_find_best_stream(fmt, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    if (si < 0) goto done;
    const AVCodec *codec = avcodec_find_decoder(fmt->streams[si]->codecpar->codec_id);
    if (!codec || !(dec = avcodec_alloc_context3(codec))) goto done;
    if (avcodec_parameters_to_context(dec, fmt->streams[si]->codecpar) < 0 || avcodec_open2(dec, codec, NULL) < 0) goto done;
    bool got = false;
    while (!got && av_read_frame(fmt, pkt) >= 0) {
        if (pkt->stream_index == si && avcodec_send_packet(dec, pkt) >= 0) got = avcodec_receive_frame(dec, frame) >= 0;
        av_packet_unref(pkt);
    }
    if (!got && avcodec_send_packet(dec, NULL) >= 0) got = avcodec_receive_frame(dec, frame) >= 0;
    if (!got || frame->width <= 0 || frame->height <= 0) goto done;
    int w = frame->width, h = frame->height;
    if (w > 256 || h > 256) {
        if (w >= h) h = h * 256 / w, w = 256;
        else w = w * 256 / h, h = 256;
    }
    struct SwsContext *sws = sws_getContext(frame->width, frame->height, frame->format, w, h, AV_PIX_FMT_RGBA,
                                            SWS_BICUBIC, NULL, NULL, NULL);
    if (!sws) goto done;
    s = SDL_CreateSurface(w, h, SDL_PIXELFORMAT_RGBA32);
    if (s) {
        uint8_t *dst[4] = {s->pixels};
        int pitch[4] = {s->pitch};
        sws_scale(sws, (const uint8_t *const *)frame->data, frame->linesize, 0, frame->height, dst, pitch);
    }
    sws_freeContext(sws);
done:
    av_frame_free(&frame);
    av_packet_free(&pkt);
    avcodec_free_context(&dec);
    avformat_close_input(&fmt);
    return s;
}

void ui_window_icon(SDL_Window *window) {
    char path[4096];
    if (!find_icon(path, sizeof path)) {
        LOG("[ui] window icon: none found (the menu entry's icon is the project's SVG)\n");
        return;
    }
    SDL_Surface *s = decode(path);
    if (!s) {
        LOG("[ui] window icon: %s could not be read\n", path);
        return;
    }
    if (!SDL_SetWindowIcon(window, s)) LOG("[ui] window icon: %s\n", SDL_GetError());
    else LOG("[ui] window icon from %s (%dx%d)\n", path, s->w, s->h);
    SDL_DestroySurface(s);
}
