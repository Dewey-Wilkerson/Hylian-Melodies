// Dear ImGui's Vulkan backend on our device (the overlay menu draws inside the window image's dynamic rendering begun
// by vk_frame_begin). Adapted from LAS Recomp's runtime/nvn/vulkan/imgui_glue.cpp (MIT, THIRD_PARTY_NOTICES.md).
#include "imgui.h"
#include "imgui_impl_vulkan.h"

extern "C" {
#include "vk.h"
#include "record.h"
}

// imgui_impl_vulkan.cpp (tools/imgui/0001-dynamic-vertex-input.patch): fixed vertex input draws nothing on some AMD
// drivers while dynamic vertex input is enabled, so the backend sets it per draw when ours does.
extern "C" int hm_imgui_dyn_vertex = 0;

extern "C" bool vk_imgui_backend_init(void) {
    if (ImGui::GetIO().BackendRendererUserData) return true;
    hm_imgui_dyn_vertex = g_vk.vids;
    ImGui_ImplVulkan_InitInfo ii = {};
    ii.ApiVersion = VK_API_VERSION_1_3;
    ii.Instance = g_vk.inst;
    ii.PhysicalDevice = g_vk.phys;
    ii.Device = g_vk.dev;
    ii.QueueFamily = g_vk.qfam;
    ii.Queue = g_vk.queue;
    ii.DescriptorPoolSize = 16;
    ii.MinImageCount = 2;
    ii.ImageCount = (g_vk.sc_count > 3 ? g_vk.sc_count : 3) + 1;  // vertex buffers rotate per image: cover frames in flight
    ii.MSAASamples = VK_SAMPLE_COUNT_1_BIT;
    ii.PipelineCache = g_vk.pcache;
    ii.UseDynamicRendering = true;
    ii.PipelineRenderingCreateInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO_KHR;
    ii.PipelineRenderingCreateInfo.colorAttachmentCount = 1;
    ii.PipelineRenderingCreateInfo.pColorAttachmentFormats = &g_vk.sc_format;
    bool ok = ImGui_ImplVulkan_Init(&ii);
    if (!ok) LOG("[menu] ImGui Vulkan backend init failed\n");
    // The font texture now: ImGui uploads it with a submission and a queue wait of its own, which its NewFrame would
    // otherwise make at the first frame while the recorder thread (record.c) may be submitting. Drained first, the
    // queue is idle.
    if (ok) {
        rec_drain();
        ImGui_ImplVulkan_CreateFontsTexture();
    }
    return ok;
}
