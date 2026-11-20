# Audio (M6)

## Path

FMOD Studio (statically linked in the game) mixes the music and effects itself and hands the result to the console's
**AudioOut** service as 1024-frame buffers (21.3 ms at 48 kHz, 16-bit stereo), keeping up to three of them queued
(the game's own design, the same on console). The movie player opens a second AudioOut for a video's sound.

`runtime/services/audio.c` (`audout:u`, from LAS Recomp) gives each AudioOut an SDL3 audio stream on the default
output device. A thread per output takes the oldest queued buffer, puts it into the stream, waits until the stream
holds less than `audio_queue_ms` (default: one device period), then releases the buffer back to the game (its
"released" event and its played-sample count). So buffers go back to FMOD exactly as fast as the sound card plays
them: **the sound card is the clock**, as the console's audio hardware is.

## Settings (`hylian-melodies.ini`)

| Key | Default | Meaning |
|---|---|---|
| `audio_period` | 256 | device period asked of the audio server (PipeWire, Pulse), in frames: 256 = 5.3 ms |
| `audio_queue_ms` | 0 (= one period) | how much our stream may hold before the next game buffer is taken |

Sound and music volume are the game's own (Options > Audio); `HM_AUDIO_GAIN` scales the whole output (tests).
`HM_AUDIO_PERIOD`, `HM_AUDIO_QUEUE_MS` override them; `HM_NO_AUDIO=1` releases buffers on a timer without a device.

The game has its own audio/video calibration; use it for the remaining offset of your speakers or headphones.

## Diagnostics

- `HM_AUDIO_STATS=<seconds>`: per output, frames released per second against the wall clock, buffer size, the
  game's queue depth, our stream's fill when a buffer goes in, gaps (our stream ran empty), share of time waiting.
- `HM_AUDOUT_WAV=<prefix>`: raw s16le PCM of each output to `<prefix>-<n>.raw` (local analysis only; never commit).

## Measurements (dev machine, PipeWire, 48 kHz, RX 7600 XT box; 2026-11-13)

Measured with `HM_AUDIO_STATS`, on the title menu (music playing), output "Desk Speakers" through PipeWire
(clock 48 kHz, server quantum 1024, minimum 32).

**10-minute run** (default settings, `audio_period` 256 granted by the server):

| | Result |
|---|---|
| gaps (our stream ran empty) | 0 in 600 s |
| buffers released per second, minute by minute after start-up | 47,998.6 - 47,999.6 frames/s (minute 1, with start-up: 48,015.8) |
| sound card vs system clock | about -25 ppm: the card's 48 kHz runs ~1.2 frames/s slow, ~15 ms over 10 minutes |
| our stream's fill when a buffer goes in | 26.7 ms every minute (one period + one game buffer): no creeping latency |
| game's queue | up to 3 buffers (its own design) |
| frame rate | 61 fps throughout |

So the music cannot drift against itself (the card is the clock) and the system clock the game also reads stays
within ~25 ppm of it, well below anything audible over a session.

**Clean output**: a 45 s capture of the menu music (`HM_AUDOUT_WAV`) has no discontinuities (no sample-to-sample jump
above 20,000), no clipped samples, RMS 1,900 median per 100 ms.

**Latency budget** (from FMOD mixing a sample to the device; the server's own and the sound card's buffering come on
top and depend on the hardware):

| Part | Before (LAS Recomp defaults) | Now |
|---|---|---|
| game's queue (FMOD, up to 3 x 21.3 ms) | up to 64 ms | up to 64 ms (the game's design, as on console) |
| our stream | 43 - 64 ms | 5 - 27 ms (average ~16) |
| device period | 21.3 ms (1024 frames) | 5.3 ms (256 frames) |
| **our share** | **~64 - 85 ms** | **~11 - 32 ms** |

`audio_period = 128` also ran without gaps here (our share ~8 - 27 ms); 256 is the default for headroom on slower
machines. End-to-end latency including the server and the speakers was not measured (it needs a loopback cable or a
microphone); use the game's calibration for the rest.

Not yet checked by ear: the owner should listen to a full song and to sound effects against the beat.
