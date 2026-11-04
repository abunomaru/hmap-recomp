// Checks the present policy (engine-patches/0010): an unchanged image is not presented
// again on every retrace, but the screen still refreshes every 4th retrace.
#include <cstdio>

#include "wp/gx.h"

int main() {
    int failures = 0;
    auto expect = [&](bool condition, const char* what) {
        std::printf("%s %s\n", condition ? "ok  " : "FAIL", what);
        failures += condition ? 0 : 1;
    };
    expect(wp::gx::should_present(), "first retrace presents (a new image is pending at start)");
    bool second = wp::gx::should_present();
    bool third = wp::gx::should_present();
    bool fourth = wp::gx::should_present();
    bool fifth = wp::gx::should_present();
    expect(!second && !third, "retraces without a new image are skipped");
    expect(fifth, "the screen still refreshes every 4th retrace");
    (void)fourth;
    return failures == 0 ? 0 : 1;
}
