// Unit tests for the GX -> aurora FIFO bridge (bridge/aurora_bridge.cpp). No GPU needed.
#include <cstdio>
#include <cstring>
#include <vector>

#include "../../bridge/aurora_bridge.h"

using namespace hmap::aurora_bridge;

namespace {

int g_failures = 0;

void expect(bool condition, const char* what) {
    std::printf("%s %s\n", condition ? "ok  " : "FAIL", what);
    g_failures += condition ? 0 : 1;
}

struct Stream {
    std::vector<uint8_t> bytes;
    Stream& u8(uint8_t v) { bytes.push_back(v); return *this; }
    Stream& u16(uint16_t v) { return u8(uint8_t(v >> 8)).u8(uint8_t(v)); }
    Stream& u32(uint32_t v) { return u16(uint16_t(v >> 16)).u16(uint16_t(v)); }
    Stream& u64(uint64_t v) { return u32(uint32_t(v >> 32)).u32(uint32_t(v)); }
    Stream& cp(uint8_t reg, uint32_t value) { return u8(0x08).u8(reg).u32(value); }
    Stream& bp(uint8_t reg, uint32_t value) { return u8(0x61).u32((uint32_t(reg) << 24) | (value & 0xFFFFFF)); }
    Stream& aurora(uint16_t sub) { return u8(0x50).u16(sub); }
};

std::vector<uint8_t> run(Bridge& bridge, const Stream& in) {
    std::vector<uint8_t> out;
    bridge.feed(in.bytes.data(), in.bytes.size(), out);
    return out;
}

}  // namespace

int main() {
    std::vector<uint8_t> ram(64 << 20);
    GuestMemory memory{ram.data(), uint32_t(ram.size())};
    const uint64_t base = reinterpret_cast<uint64_t>(ram.data());

    {
        Bridge bridge(memory);
        auto out = run(bridge, Stream().cp(0xA0, 0x00123460));
        Stream want;
        want.aurora(kLoadArrayBase + 0).u64(base + 0x123460).u32(uint32_t(ram.size()) - 0x123460).u8(0);
        expect(out == want.bytes, "CP array base -> GX_AURORA_LOAD_ARRAYBASE with host pointer and size");
    }
    {
        Bridge bridge(memory);
        auto out = run(bridge, Stream().cp(0xA9, 0x80001000));
        Stream want;
        want.aurora(kLoadArrayBase + 9).u64(base + 0x1000).u32(uint32_t(ram.size()) - 0x1000).u8(0);
        expect(out == want.bytes, "cached/uncached virtual bits are masked to the physical address");
    }
    {
        // Position direct, 3 x f32; colour 0 direct RGBA8; one tex coord index16.
        Bridge bridge(memory);
        Stream setup;
        setup.cp(0x50, (1u << 9) | (1u << 13)).cp(0x60, 3u).cp(0x70, 1u | (4u << 1) | (1u << 13) | (5u << 14) | (1u << 21) | (3u << 22));
        run(bridge, setup);
        expect(bridge.vertex_size(0) == 12 + 4 + 2, "vertex size: f32 xyz + RGBA8 colour + index16 tex coord = 18");
        Stream draw;
        draw.u8(0x90).u16(3);  // triangles, VAT 0, 3 vertices
        for (int i = 0; i < 3 * 18; i++) draw.u8(uint8_t(i));
        auto out = run(bridge, draw);
        expect(out == draw.bytes, "draws pass through byte for byte");
    }
    {
        // A command split across two feeds is held back until complete.
        Bridge bridge(memory);
        Stream bp;
        bp.bp(0x41, 0x123456);
        std::vector<uint8_t> out;
        bridge.feed(bp.bytes.data(), 3, out);
        bool none_yet = out.empty();
        bridge.feed(bp.bytes.data() + 3, bp.bytes.size() - 3, out);
        expect(none_yet && out == bp.bytes, "partial command completed by the next feed");
    }
    {
        // Display list in guest memory: a BP write and a CP array base inside it.
        Bridge bridge(memory);
        Stream list;
        list.bp(0x42, 0x000111).cp(0xA1, 0x00002000).u8(0x00).u8(0x00);
        std::memcpy(ram.data() + 0x40000, list.bytes.data(), list.bytes.size());
        auto out = run(bridge, Stream().u8(0x40).u32(0x80040000).u32(uint32_t(list.bytes.size())));
        Stream want;
        want.bp(0x42, 0x000111).aurora(kLoadArrayBase + 1).u64(base + 0x2000).u32(uint32_t(ram.size()) - 0x2000).u8(0);
        expect(out == want.bytes, "CALL_DL is inlined and its contents rewritten");
        expect(bridge.stats().display_lists == 1, "display list counted");
    }
    {
        Bridge bridge(memory);
        auto out = run(bridge, Stream().bp(0xB5, 0x000200));  // map 5 image3, address 0x200 << 5
        Stream want;
        want.bp(0xB5, 0x000200).aurora(kLoadTexPointer).u8(5).u64(base + (0x200u << 5));
        expect(out == want.bytes, "texture image3 -> BP passed on + GX_AURORA_LOAD_TEX_POINTER");
    }
    {
        Bridge bridge(memory);
        Stream in;
        in.bp(0x49, 10 | (20 << 10)).bp(0x4A, 63 | (31 << 10)).bp(0x4B, 0x0400).bp(0x43, 0);
        uint32_t copy = (1u << 9) | ((4u * 2) << 3);  // half size, RGB565 (code 4 -> coded 8)
        in.bp(0x52, copy);
        auto out = run(bridge, in);
        Stream want;
        want.bp(0x49, 10 | (20 << 10)).bp(0x4A, 63 | (31 << 10)).bp(0x4B, 0x0400).bp(0x43, 0);
        want.aurora(kLoadCopySrc).u32(10).u32(20).u32(64).u32(32);
        want.aurora(kLoadCopyDst).u32(32).u32(16).u32(4).u8(0);
        want.aurora(kLoadCopyDest).u64(base + (0x400u << 5));
        want.bp(0x52, copy);
        expect(out == want.bytes, "EFB copy to texture -> COPY_SRC, COPY_DST (half, RGB565), COPY_DEST, then 0x52");
    }
    {
        Bridge bridge(memory);
        Stream in;
        uint32_t copy = (1u << 14) | (1u << 11);  // copy to the external framebuffer, with clear
        in.bp(0x49, 0).bp(0x4A, 639 | (527 << 10)).bp(0x52, copy);
        auto out = run(bridge, in);
        Stream want;
        want.bp(0x49, 0).bp(0x4A, 639 | (527 << 10)).aurora(kLoadCopySrc).u32(0).u32(0).u32(640).u32(528).bp(0x52, copy);
        expect(out == want.bytes, "display copy -> COPY_SRC only, then 0x52");
        expect(bridge.stats().display_copies == 1, "display copy counted");
    }
    {
        Bridge bridge(memory);
        Stream in;
        in.bp(0x64, 0x0800).bp(0x65, 0x10 | (16u << 10));  // source 0x800 << 5, slot 0x10, 16 lines
        in.bp(0x98, 0x10 | (2u << 10));                        // map 0 uses slot 0x10, RGB5A3
        auto out = run(bridge, in);
        Stream want;
        want.bp(0x64, 0x0800).bp(0x65, 0x10 | (16u << 10));
        want.aurora(kLoadTlutPointer).u8(0x10).u64(base + (0x800u << 5)).u32(0).u16(256);
        want.bp(0x98, 0x10 | (2u << 10));
        want.aurora(kLoadTlutPointer).u8(0x10).u64(base + (0x800u << 5)).u32(2).u16(256);
        expect(out == want.bytes, "TLUT load -> palette pointer, re-sent with the texture's format");
    }
    {
        Bridge bridge(memory);
        auto out = run(bridge, Stream().u8(0x00).u8(0x44).u8(0x48).u8(0x7F));
        expect(out.size() == 1 && out[0] == 0x48 && bridge.stats().unknown == 1, "NOP/metrics dropped, invalidate kept, unknown byte counted");
    }
    return g_failures == 0 ? 0 : 1;
}
