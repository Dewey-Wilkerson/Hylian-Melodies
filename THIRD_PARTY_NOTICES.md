# Third-party notices

Code copied or adapted from other projects, with source, commit and license. A row is added in the same commit that
introduces the code. Only MIT, BSD, ISC, zlib or Apache-2.0 code may be copied (CONTRIBUTING.md); GPL/AGPL code
needs the owner's approval first.

| Component | Source | Commit / version | License | Where | Notes |
|---|---|---|---|---|---|
| (history) LAS Recomp import | https://github.com/peiikai/LASRecomp | `579fdad6d736c8fbf1d21943593731eb926b6659` | MIT, Copyright (c) 2026 Peiikai | git history only (commit `9c20fa2`) | removed from the tree in M1; parts are re-added below as they are adapted |
| LAS Recomp lifter | https://github.com/peiikai/LASRecomp | `579fdad` | MIT, Copyright (c) 2026 Peiikai | `recomp/lifter.py`, `recomp/simd_c.py`, `recomp/nso.py` | copied (header added) |
| LAS Recomp generator | same | `579fdad` | MIT | `recomp/gen.py`, `recomp/jumptables.py` | adapted from `tools/gen.py`: partitioning, scan, emitter, jump-table pattern search; Unicorn replaced by our own interpreter; game-specific hooks removed |
| LAS Recomp CPU/runtime headers | same | `579fdad` | MIT | `runtime/cpu.h`, `runtime/simd.h`, `runtime/simd_fp.h`, `runtime/dispatch.c`, `runtime/rt.h` | copied (header added); adapted further from M4 |

## External tools and libraries used at build or run time (not copied)

| Component | How it is used | License |
|---|---|---|
| hactool (SciresM) | fetched at a pinned commit and built by `tools/build_hactool.py` on the user's machine; never vendored | ISC |
| SDL 3 | system library, dynamically linked | zlib |
| Vulkan loader / headers | system | Apache-2.0 |
| python-lz4 | installer/lifter dependency | BSD-3-Clause |
| Capstone | lifter dependency (disassembly) | BSD-3-Clause |

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
