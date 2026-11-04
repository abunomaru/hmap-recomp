// GX FIFO -> aurora FIFO bridge (hmap-recomp).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The Wii Party engine emulates the Wii below the SDK: the translated game writes real GX
// commands to the FIFO. aurora (MIT, the renderer of WiiCompiled and its ports) consumes an
// almost identical stream, except that every memory reference must be a host pointer sent
// through aurora's GX_AURORA (0x50) extension commands:
//
//   CP 0xA0-0xAF array base (physical)   -> GX_AURORA_LOAD_ARRAYBASE + n  (pointer, size, big-endian)
//   BP texture image3 (0x94-97, 0xB4-B7) -> passed on, then GX_AURORA_LOAD_TEX_POINTER (map, pointer)
//   BP 0x65 TLUT load (source in 0x64)   -> GX_AURORA_LOAD_TLUT_POINTER (tmem slot, pointer, format, count)
//   BP 0x52 EFB copy (setup in 0x49-0x4D)-> GX_AURORA_LOAD_COPY_SRC / _DST / _DEST, then 0x52
//   CALL_DL (0x40)                       -> the list's commands inlined (rewritten the same way)
//
// Everything else (XF, BP, CP state, draws, indexed XF loads) is passed through unchanged.
// The bridge only produces bytes, so it has no dependency on aurora and is unit tested on its own.

#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace hmap::aurora_bridge {

constexpr uint8_t kAuroraCommand = 0x50;  // GX_AURORA in aurora's GXCommandList.h
constexpr uint16_t kLoadArrayBase = 0x0010;
constexpr uint16_t kLoadCopySrc = 0x0035;
constexpr uint16_t kLoadCopyDst = 0x0036;
constexpr uint16_t kLoadCopyDest = 0x0037;
constexpr uint16_t kLoadTexPointer = 0x003B;
constexpr uint16_t kLoadTlutPointer = 0x003C;

// Guest memory as the engine maps it: physical address p lives at base + p.
struct GuestMemory {
    const uint8_t* base = nullptr;
    uint32_t size = 0;  // bytes of physical address space mapped at base (MEM1 + MEM2 window)
};

class Bridge {
public:
    explicit Bridge(GuestMemory memory) : m_memory(memory) {}

    // Feeds guest FIFO bytes. Complete commands are translated and appended to `out`; a
    // trailing partial command is kept and completed by the next call.
    void feed(const uint8_t* data, size_t size, std::vector<uint8_t>& out);

    // Statistics, for the engine log.
    struct Stats {
        uint64_t commands = 0;
        uint64_t draws = 0;
        uint64_t display_lists = 0;
        uint64_t rewritten = 0;  // memory references converted to pointers
        uint64_t unknown = 0;    // bytes skipped as unknown opcodes
    };
    const Stats& stats() const { return m_stats; }

    // Vertex size in bytes for vertex format `vat` with the current CP state (exposed for tests).
    uint32_t vertex_size(uint32_t vat) const;

private:
    // Translates one command at data[0..size). Returns bytes consumed, or 0 if incomplete.
    size_t translate_one(const uint8_t* data, size_t size, bool in_list, std::vector<uint8_t>& out);
    void translate_list(uint32_t address, uint32_t length, std::vector<uint8_t>& out);
    void on_cp(uint8_t reg, uint32_t value, std::vector<uint8_t>& out);
    void on_bp(uint32_t word, std::vector<uint8_t>& out);
    void emit_palette(uint32_t slot, uint32_t format, std::vector<uint8_t>& out);
    const uint8_t* pointer(uint32_t physical) const;

    struct Palette {
        uint32_t source = 0;
        uint16_t entries = 0;
        uint32_t format = 0;
        bool valid = false;
    };

    GuestMemory m_memory;
    Palette m_palettes[1024];
    std::vector<uint8_t> m_pending;
    uint32_t m_vcd_low = 0;
    uint32_t m_vcd_high = 0;
    uint32_t m_vat[3][8] = {};
    uint32_t m_bp[256] = {};
    Stats m_stats;
};

}  // namespace hmap::aurora_bridge
