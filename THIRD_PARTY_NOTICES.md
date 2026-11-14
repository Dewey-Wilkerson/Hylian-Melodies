# Third-party notices

Code copied or adapted from other projects, with source, commit and license. A row is added in the same commit that
introduces the code. Only MIT, BSD, ISC, zlib or Apache-2.0 code may be copied (CONTRIBUTING.md); GPL/AGPL code
needs the owner's approval first.

| Component | Source | Commit / version | License | Where | Notes |
|---|---|---|---|---|---|
| (history) LAS Recomp import | https://github.com/peiikai/LASRecomp | `579fdad6d736c8fbf1d21943593731eb926b6659` | MIT, Copyright (c) 2026 Peiikai | not in this history (dropped 2026-11-14: it held Link's Awakening data); the owner keeps a local backup | parts are re-added below as they are adapted |
| LAS Recomp lifter | https://github.com/peiikai/LASRecomp | `579fdad` | MIT, Copyright (c) 2026 Peiikai | `recomp/lifter.py`, `recomp/simd_c.py`, `recomp/nso.py` | copied (header added) |
| LAS Recomp generator | same | `579fdad` | MIT | `recomp/gen.py`, `recomp/jumptables.py` | adapted from `tools/gen.py`: partitioning, scan, emitter, jump-table pattern search; Unicorn replaced by our own interpreter; game-specific hooks removed |
| LAS Recomp CPU/runtime headers | same | `579fdad` | MIT | `runtime/cpu.h`, `runtime/simd.h`, `runtime/simd_fp.h`, `runtime/dispatch.c`, `runtime/rt.h` | copied (header added); adapted further from M4 |
| LAS Recomp runtime core | https://github.com/peiikai/LASRecomp | `579fdad` | MIT | `runtime/{kernel,ipc,loader,crash_explain,fnprof,romfs_build}.c`, `runtime/{kernel,ipc,hle,platform,rumble,romfs_build}.h`, `runtime/hle/{heaps,libc,movie,nvn_boot,swkbd,vi}.c`, `runtime/services/{acc,am,audio,hid_set,misc,time}.c`, `runtime/platform/{linux.c,linux_compat.h,posix_log.h}` | copied, then adapted (names, log paths, Link's Awakening features removed) |
| LAS Recomp NVN front end | https://github.com/peiikai/LASRecomp | `579fdad` | MIT | `runtime/nvn/{astc,cmdbuf,formats,objects,rqueue,tegra}.c`, `runtime/nvn/{astc,nvn,renderer,rqueue,tegra,tex_hash}.h` | copied (header added); `null_backend.c` is ours |
| LAS Recomp Vulkan backend and Maxwell translator | https://github.com/peiikai/LASRecomp | `579fdad` | MIT | `runtime/nvn/vulkan/*`, `runtime/nvn/maxwell/*`, `runtime/nvn/{output_scale,pace,slowframe,shader_prep,shader_seen}.c` and their headers, `runtime/nvn/{screen_filter,recolour,texpatch}.h` | copied (header added), then adapted: Link's Awakening hooks answered by `runtime/nvn/las_feature_stubs.c` (ours), its shader list and its shader-signature fix removed, TLD4 (texture gather) added to the translator (ours), window title/app id renamed |
| LAS Recomp fs service | same | `579fdad` | MIT | `runtime/services/fs.c` | host file system with crash-safe save commits kept; RomFS/DLC part rewritten |
| LAS Recomp overlay menu | https://github.com/peiikai/LASRecomp | `579fdad` | MIT | `runtime/ui/imgui_glue.cpp`, `runtime/ui/menu.cpp` | glue adapted from `runtime/nvn/vulkan/imgui_glue.cpp`; the menu follows the shape of `runtime/ui/menu.mm` (event queue, overlay hand-off, style), pages ours |
| LAS Recomp boot sequence | same | `579fdad` | MIT | `runtime/main.c` | rewritten after its `main.c` (no start screen, reboot, randomizer) |

## External tools and libraries used at build or run time (not copied)

| Component | How it is used | License |
|---|---|---|
| hactool (SciresM) | fetched at a pinned commit and built by `tools/build_hactool.py` on the user's machine; never vendored | ISC |
| Dear ImGui (ocornut/imgui) | fetched at `97428e8` (v1.91.9) by `tools/fetch_imgui.py`, never vendored; its Vulkan backend gets `tools/imgui/0001-dynamic-vertex-input.patch` (from LAS Recomp, MIT) | MIT |
| SDL 3 | system library, dynamically linked | zlib |
| Vulkan loader / headers | system | Apache-2.0 |
| python-lz4 | installer/lifter dependency | BSD-3-Clause |
| Capstone | lifter dependency (disassembly) | BSD-3-Clause |
| Vulkan Memory Allocator | system header (`/usr/include/vk_mem_alloc.h`), compiled by `runtime/nvn/vulkan/vma.cpp` | MIT |
| shaderc | system library (GLSL to SPIR-V for translated shaders) | Apache-2.0 |
| FFmpeg (libavformat, libavcodec, libavutil, libswscale) | system libraries, dynamically linked, for the game's videos (`runtime/hle/movie.c`) | LGPL-2.1+ (Arch builds it with GPL parts enabled; see docs/OPEN-QUESTIONS.md) |

## License texts

### LAS Recomp (MIT)

```
MIT License

Copyright (c) 2026 Peiikai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
