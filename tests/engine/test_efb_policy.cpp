// Checks the EFB copy write-back policy added by engine-patches/0006 (auto mode):
// per-frame effect copies stop being written back to RAM, one-off copies are written.
#include <cstdio>

#include "gx_render_common.h"

namespace {

int g_failures = 0;

void expect(bool condition, const char* what) {
    std::printf("%s %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) {
        g_failures++;
    }
}

}  // namespace

int main() {
    using wp::gx::render::want_write_back;
    // An effect buffer copied every frame: written back for the first two frames only.
    bool first = want_write_back(0x80500000, 10);
    bool second = want_write_back(0x80500000, 11);
    bool third = want_write_back(0x80500000, 12);
    bool later = want_write_back(0x80500000, 40);  // gap: streak restarts
    expect(first && second, "first two copies of a repeating buffer are written back");
    expect(!third, "third consecutive frame: treated as an effect, GPU only");
    expect(later, "after a gap the buffer is written back again (a new one-off use)");
    // A photo: one copy to a fresh buffer.
    expect(want_write_back(0x80600000, 100), "one-off copy (photo) is written back");
    // Two passes to the same buffer in one frame (Mii-face style) are both written.
    expect(want_write_back(0x80700000, 200) && want_write_back(0x80700000, 200), "two passes in one frame are written back");
    return g_failures == 0 ? 0 : 1;
}
