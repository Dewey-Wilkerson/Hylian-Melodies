# Development environment

Recorded 2026-11-12 on the development machine. Re-check with the commands at the end when the machine changes.

| Item | Value |
|---|---|
| OS / kernel | CachyOS (Arch-based), Linux 7.3.3-1-cachyos, glibc 2.44 |
| CPU | AMD Ryzen 7 9700X, 8 cores / 16 threads; x86-64-v4 (AVX2, FMA, BMI2, MOVBE, F16C, AVX-512F) |
| RAM | 30 GiB + 30 GiB swap |
| GPU | AMD Radeon RX 7600 XT (Navi 33, RADV), plus Radeon 610M iGPU (RADV) |
| Vulkan | instance/driver API 1.4.354, Mesa 26.2.6; loader and headers 1.4.363 |
| Python | 3.14.9 (system); `lz4` and `capstone` 5.0.7 installed, no `pycryptodome` |
| Compilers | clang 23.1.4, ld.lld 23.1.4, gcc 16.2.1, ninja 1.13.2, cmake 4.4.5, GNU make 4.4.1 |
| Shader tools | glslangValidator 16.6.0, spirv-opt (SPIRV-Tools) |
| Other toolchains | dotnet 10.0.114, cargo/rustc 1.99.1, ImageMagick 7.1.2 |
| Libraries (pkg-config) | SDL3 3.4.18, opus 1.6.1, libvpx 1.17.0, libzstd 1.5.7, FFmpeg libavcodec 63.1.102, VMA header in `/usr/include/vk_mem_alloc.h` |
| hactool | `/opt/devkitpro/tools/bin/hactool` (exploration only; the project builds its own, see `tools/build_hactool.py`) |
| Disk | `/home`: 5.5 TiB, 2.2 TiB free |
| Session | `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-1` (both set) |

Trap found on this machine: the devkitPro hactool reads `~/.switch/prod.keys` by default and its warnings print key
values. Every hactool call in this project passes `-k <file>` explicitly and filters its output (see
`installer/hactool.py`); never run hactool with unfiltered output in a terminal whose log may be shared.

Commands used:

```bash
uname -r; ldd --version | head -1; grep -m1 'model name' /proc/cpuinfo
/lib/ld-linux-x86-64.so.2 --help | grep x86-64-v
vulkaninfo --summary | grep -E 'apiVersion|deviceName|driverInfo'
pkg-config --modversion sdl3 opus vpx libzstd vulkan
clang --version; ld.lld --version; ninja --version; gcc --version; python3 --version
df -h ~; echo "$DISPLAY $WAYLAND_DISPLAY"
```
