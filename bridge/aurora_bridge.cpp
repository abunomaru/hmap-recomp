// GX FIFO -> aurora FIFO bridge (hmap-recomp). See aurora_bridge.h.
// SPDX-License-Identifier: GPL-3.0-or-later

#include "aurora_bridge.h"

#include <cstring>

namespace hmap::aurora_bridge {

namespace {

constexpr uint8_t kNop = 0x00;
constexpr uint8_t kLoadCp = 0x08;
constexpr uint8_t kLoadXf = 0x10;
constexpr uint8_t kCallList = 0x40;
constexpr uint8_t kMetrics = 0x44;
constexpr uint8_t kInvalidate = 0x48;
constexpr uint8_t kLoadBp = 0x61;
constexpr uint8_t kDrawMask = 0x80;
constexpr uint32_t kAddressMask = 0x1FFFFFFF;

uint32_t be32(const uint8_t* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

uint32_t be16(const uint8_t* p) {
    return (uint32_t(p[0]) << 8) | p[1];
}

void put8(std::vector<uint8_t>& out, uint8_t v) {
    out.push_back(v);
}

void put16(std::vector<uint8_t>& out, uint16_t v) {
    out.push_back(uint8_t(v >> 8));
    out.push_back(uint8_t(v));
}

void put32(std::vector<uint8_t>& out, uint32_t v) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        out.push_back(uint8_t(v >> shift));
    }
}

void put64(std::vector<uint8_t>& out, uint64_t v) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        out.push_back(uint8_t(v >> shift));
    }
}

void aurora(std::vector<uint8_t>& out, uint16_t sub) {
    put8(out, kAuroraCommand);
    put16(out, sub);
}

uint32_t component_size(uint32_t format) {
    return format <= 1 ? 1 : (format <= 3 ? 2 : 4);
}

uint32_t color_size(uint32_t format) {
    static const uint32_t kSizes[] = {2, 3, 4, 2, 3, 4, 4, 4};
    return kSizes[format & 7];
}

uint32_t attribute_size(uint32_t mode, uint32_t direct) {
    switch (mode) {
    case 1: return direct;  // GX_DIRECT
    case 2: return 1;       // GX_INDEX8
    case 3: return 2;       // GX_INDEX16
    default: return 0;      // GX_NONE
    }
}

// GXTexFmt for an EFB copy, from the copy register's format code (bits 3-6), its intensity
// bit (15) and whether the EFB holds depth (BP 0x43 pixel format Z24).
uint32_t copy_texture_format(uint32_t copy, bool depth) {
    uint32_t coded = (copy >> 3) & 15;
    uint32_t code = coded / 2 + (coded & 1) * 8;
    bool intensity = (copy >> 15) & 1;
    if (depth) {
        return (code == 1 || code == 3 || code == 6) ? (0x10 | code) : (0x30 | code);  // GX_TF_Z* / GX_CTF_Z*
    }
    if (code >= 4 && code <= 6) {
        return code;  // RGB565, RGB5A3, RGBA8
    }
    if (intensity && code <= 3) {
        return code;  // I4, I8, IA4, IA8
    }
    return 0x20 | code;  // GX_CTF_R4 ... GX_CTF_GB8
}

}  // namespace

const uint8_t* Bridge::pointer(uint32_t physical) const {
    uint32_t offset = physical & kAddressMask;
    if (!m_memory.base || offset >= m_memory.size) {
        return nullptr;
    }
    return m_memory.base + offset;
}

uint32_t Bridge::vertex_size(uint32_t vat) const {
    uint32_t a = m_vat[0][vat & 7];
    uint32_t b = m_vat[1][vat & 7];
    uint32_t c = m_vat[2][vat & 7];
    uint32_t low = m_vcd_low;
    uint32_t high = m_vcd_high;
    uint32_t size = (low & 1) ? 1 : 0;                  // position/normal matrix index
    size += __builtin_popcount((low >> 1) & 0xFF);     // texture matrix indices
    uint32_t position_components = (a & 1) ? 3 : 2;
    size += attribute_size((low >> 9) & 3, position_components * component_size((a >> 1) & 7));
    uint32_t normal_components = (a & 0x200) ? 9 : 3;
    size += attribute_size((low >> 11) & 3, normal_components * component_size((a >> 10) & 7));
    size += attribute_size((low >> 13) & 3, color_size((a >> 14) & 7));
    size += attribute_size((low >> 15) & 3, color_size((a >> 18) & 7));
    const uint32_t counts[8] = {(a >> 21) & 1, b & 1, (b >> 9) & 1, (b >> 18) & 1, (b >> 27) & 1, (c >> 5) & 1, (c >> 14) & 1, (c >> 23) & 1};
    const uint32_t formats[8] = {(a >> 22) & 7, (b >> 1) & 7, (b >> 10) & 7, (b >> 19) & 7, (b >> 28) & 7, (c >> 6) & 7, (c >> 15) & 7, (c >> 24) & 7};
    for (uint32_t i = 0; i < 8; i++) {
        size += attribute_size((high >> (2 * i)) & 3, (counts[i] + 1) * component_size(formats[i]));
    }
    return size;
}

void Bridge::on_cp(uint8_t reg, uint32_t value, std::vector<uint8_t>& out) {
    if (reg == 0x50) {
        m_vcd_low = value;
    } else if (reg == 0x60) {
        m_vcd_high = value;
    } else if (reg >= 0x70 && reg < 0x98) {
        m_vat[(reg >> 4) - 7][reg & 7] = value;
    }
    if (reg >= 0xA0 && reg < 0xB0) {
        // Array base: aurora needs a host pointer and the readable size behind it.
        uint32_t offset = value & kAddressMask;
        const uint8_t* host = pointer(value);
        aurora(out, uint16_t(kLoadArrayBase + (reg - 0xA0)));
        put64(out, reinterpret_cast<uint64_t>(host));
        put32(out, host ? m_memory.size - offset : 0);
        put8(out, 0);  // big-endian data
        m_stats.rewritten++;
        return;
    }
    put8(out, kLoadCp);
    put8(out, reg);
    put32(out, value);
}

void Bridge::on_bp(uint32_t word, std::vector<uint8_t>& out) {
    uint8_t reg = uint8_t(word >> 24);
    uint32_t value = word & 0xFFFFFF;
    m_bp[reg] = value;

    if (reg == 0x52) {
        // EFB copy: aurora ignores the hardware copy-setup registers; send its commands first.
        uint32_t source = m_bp[0x49];
        uint32_t extent = m_bp[0x4A];
        int32_t left = int32_t(source & 0x3FF);
        int32_t top = int32_t((source >> 10) & 0x3FF);
        int32_t width = int32_t(extent & 0x3FF) + 1;
        int32_t height = int32_t((extent >> 10) & 0x3FF) + 1;
        aurora(out, kLoadCopySrc);
        put32(out, uint32_t(left));
        put32(out, uint32_t(top));
        put32(out, uint32_t(width));
        put32(out, uint32_t(height));
        bool to_display = (value >> 14) & 1;
        if (to_display) {
            m_stats.display_copies++;
        } else {
            bool half = (value >> 9) & 1;
            bool depth = (m_bp[0x43] & 7) == 3;
            aurora(out, kLoadCopyDst);
            put32(out, uint32_t(half ? width / 2 : width));
            put32(out, uint32_t(half ? height / 2 : height));
            put32(out, copy_texture_format(value, depth));
            put8(out, 0);  // mipmap flag (unused by aurora)
            aurora(out, kLoadCopyDest);
            put64(out, reinterpret_cast<uint64_t>(pointer((m_bp[0x4B] & 0xFFFFFF) << 5)));
            m_stats.rewritten++;
        }
    }

    put8(out, kLoadBp);
    put32(out, word);

    // Texture image3 (data address) for maps 0-3 and 4-7: point aurora at guest memory.
    if ((reg >= 0x94 && reg <= 0x97) || (reg >= 0xB4 && reg <= 0xB7)) {
        uint8_t map = uint8_t((reg & 3) + (reg >= 0xB4 ? 4 : 0));
        aurora(out, kLoadTexPointer);
        put8(out, map);
        put64(out, reinterpret_cast<uint64_t>(pointer(value << 5)));
        m_stats.rewritten++;
    }

    // TLUT load: remember where each TMEM palette slot came from.
    if (reg == 0x65) {
        uint32_t slot = value & 0x3FF;
        Palette& palette = m_palettes[slot];
        palette.source = (m_bp[0x64] & 0x1FFFFF) << 5;
        palette.entries = uint16_t(((value >> 10) & 0x7FF) * 16);
        palette.valid = true;
        emit_palette(slot, palette.format, out);
    }

    // Texture TLUT setting (0x98-0x9B maps 0-3, 0xB8-0xBB maps 4-7): slot and format. aurora
    // takes the format from the palette, so resend the slot with this texture's format.
    if ((reg >= 0x98 && reg <= 0x9B) || (reg >= 0xB8 && reg <= 0xBB)) {
        uint32_t slot = value & 0x3FF;
        uint32_t format = (value >> 10) & 3;
        Palette& palette = m_palettes[slot];
        if (palette.valid && palette.format != format) {
            palette.format = format;
            emit_palette(slot, format, out);
        }
    }
}

void Bridge::emit_palette(uint32_t slot, uint32_t format, std::vector<uint8_t>& out) {
    const Palette& palette = m_palettes[slot];
    aurora(out, kLoadTlutPointer);
    put8(out, uint8_t(slot));
    put64(out, reinterpret_cast<uint64_t>(pointer(palette.source)));
    put32(out, format);
    put16(out, palette.entries);
    m_stats.rewritten++;
}

void Bridge::translate_list(uint32_t address, uint32_t length, std::vector<uint8_t>& out) {
    const uint8_t* list = pointer(address);
    uint32_t offset = address & kAddressMask;
    if (!list || uint64_t(offset) + length > m_memory.size) {
        m_stats.unknown++;
        return;
    }
    m_stats.display_lists++;
    size_t done = 0;
    while (done < length) {
        size_t used = translate_one(list + done, length - done, true, out);
        if (used == 0) {
            break;  // truncated command at the end of the list: ignored, as on hardware
        }
        done += used;
    }
}

size_t Bridge::translate_one(const uint8_t* data, size_t size, bool in_list, std::vector<uint8_t>& out) {
    uint8_t command = data[0];
    if (command == kNop || command == kMetrics) {
        return 1;
    }
    if (command == kInvalidate) {
        put8(out, command);
        return 1;
    }
    if (command == kLoadCp) {
        if (size < 6) return 0;
        on_cp(data[1], be32(data + 2), out);
        m_stats.commands++;
        return 6;
    }
    if (command == kLoadXf) {
        if (size < 5) return 0;
        uint32_t count = (be32(data + 1) >> 16) + 1;
        size_t total = 5 + 4 * size_t(count);
        if (size < total) return 0;
        out.insert(out.end(), data, data + total);
        m_stats.commands++;
        return total;
    }
    if ((command & 0xE7) == 0x20) {  // indexed XF loads (A..D), resolved by aurora via the array bases
        if (size < 5) return 0;
        out.insert(out.end(), data, data + 5);
        m_stats.commands++;
        return 5;
    }
    if (command == kCallList) {
        if (size < 9) return 0;
        if (!in_list) {
            translate_list(be32(data + 1), be32(data + 5), out);
        }
        m_stats.commands++;
        return 9;
    }
    if (command == kLoadBp) {
        if (size < 5) return 0;
        on_bp(be32(data + 1), out);
        m_stats.commands++;
        return 5;
    }
    if (command & kDrawMask) {
        if (size < 3) return 0;
        uint32_t count = be16(data + 1);
        size_t total = 3 + size_t(count) * vertex_size(command & 7);
        if (size < total) return 0;
        out.insert(out.end(), data, data + total);
        m_stats.draws++;
        m_stats.commands++;
        return total;
    }
    m_stats.unknown++;
    return 1;
}

void Bridge::feed(const uint8_t* data, size_t size, std::vector<uint8_t>& out) {
    const uint8_t* input = data;
    size_t available = size;
    if (!m_pending.empty()) {
        m_pending.insert(m_pending.end(), data, data + size);
        input = m_pending.data();
        available = m_pending.size();
    }
    size_t done = 0;
    while (done < available) {
        size_t used = translate_one(input + done, available - done, false, out);
        if (used == 0) {
            break;
        }
        done += used;
    }
    std::vector<uint8_t> rest(input + done, input + available);
    m_pending.swap(rest);
}

}  // namespace hmap::aurora_bridge
