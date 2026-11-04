// Checks fast-forward (engine-patches/0008): the guest time base runs `factor` times
// faster while set, and stays monotonic across speed changes.
#include <chrono>
#include <cstdio>
#include <thread>

#include "wp/cpu.h"
#include "wp/runtime.h"

namespace {

int g_failures = 0;

void expect(bool condition, const char* what) {
    std::printf("%s %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) {
        g_failures++;
    }
}

double ticks_per_ms(int ms) {
    uint64_t a = wp::time_base();
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    uint64_t b = wp::time_base();
    return static_cast<double>(b - a) / ms;
}

}  // namespace

int main() {
    double normal = ticks_per_ms(100);
    wp::set_speed(4);
    uint64_t before = wp::time_base();
    double fast = ticks_per_ms(100);
    wp::set_speed(1);
    uint64_t after = wp::time_base();
    double back = ticks_per_ms(100);
    double ratio = fast / normal;
    std::printf("     time base: %.0f ticks/ms normal, %.0f fast (x%.2f), %.0f after\n", normal, fast, ratio, back);
    expect(ratio > 3.5 && ratio < 4.5, "time base runs about 4x faster while fast-forwarding");
    expect(back / normal > 0.8 && back / normal < 1.25, "back to normal speed afterwards");
    expect(after >= before, "time base never goes backwards across speed changes");
    expect(wp::speed() == 1, "speed() reports the current factor");
    return g_failures == 0 ? 0 : 1;
}
