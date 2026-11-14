// From LAS Recomp (https://github.com/peiikai/LASRecomp, 579fdad, runtime/nvn/vulkan/vma.cpp), MIT, Copyright (c) 2026 Peiikai.
// See THIRD_PARTY_NOTICES.md.
// Vulkan Memory Allocator implementation (header-only library, MSYS2 package vulkan-memory-allocator).
#define VMA_IMPLEMENTATION
#define VMA_STATIC_VULKAN_FUNCTIONS 1
#define VMA_DYNAMIC_VULKAN_FUNCTIONS 0
#include "vk_mem_alloc.h"  // (the pinned header: tools/fetch_vma.py, on the include path from tools/build_game.py)
