// Checks the Nunchuk extension model added by engine-patches/0002 against the
// Wii Remote protocol: status flag, extension ID read, and the 6 input bytes.
// Built and run by tests/engine/run.sh against the headless engine libraries.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

#include "wp/wiimote.h"

namespace {

std::vector<std::vector<uint8_t>> g_frames;
int g_failures = 0;

void sender(const std::vector<uint8_t>& frame) { g_frames.push_back(frame); }

void expect(bool condition, const char* what) {
    std::printf("%s %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) {
        g_failures++;
    }
}

void output(std::vector<uint8_t> report) { wp::wiimote::output_report(0, report.data(), static_cast<uint32_t>(report.size()), sender); }

void tick() {
    std::this_thread::sleep_for(std::chrono::milliseconds(6));
    wp::wiimote::update(0, sender);
}

}  // namespace

int main() {
    wp::wiimote::reset(0);
    tick();  // attaches the Nunchuk -> unsolicited status report
    expect(!g_frames.empty() && g_frames.back().size() >= 4 && g_frames.back()[1] == 0x20, "status report sent when the extension attaches");
    expect(!g_frames.empty() && (g_frames.back()[4] & 0x02) != 0, "status report has the extension-connected flag");

    g_frames.clear();
    output({0x15, 0x00});
    expect(!g_frames.empty() && (g_frames.back()[4] & 0x02) != 0, "requested status keeps the extension flag");

    // The SDK's unencrypted init, then read the 6-byte extension ID at 0xA400FA.
    std::vector<uint8_t> write_f0(22, 0);
    write_f0[0] = 0x16; write_f0[1] = 0x04; write_f0[2] = 0xA4; write_f0[3] = 0x00; write_f0[4] = 0xF0; write_f0[5] = 1; write_f0[6] = 0x55;
    output(write_f0);
    g_frames.clear();
    output({0x17, 0x04, 0xA4, 0x00, 0xFA, 0x00, 0x06});
    bool id_ok = !g_frames.empty() && g_frames.back()[1] == 0x21 && g_frames.back().size() >= 13;
    if (id_ok) {
        const uint8_t* data = g_frames.back().data() + 7;
        id_ok = data[0] == 0x00 && data[1] == 0x00 && data[2] == 0xA4 && data[3] == 0x20 && data[4] == 0x00 && data[5] == 0x00;
    }
    expect(id_ok, "extension ID reads 00 00 A4 20 00 00 (Nunchuk)");

    // Calibration checksum
    g_frames.clear();
    output({0x17, 0x04, 0xA4, 0x00, 0x20, 0x00, 0x10});
    bool cal_ok = !g_frames.empty() && g_frames.back()[1] == 0x21;
    if (cal_ok) {
        const uint8_t* data = g_frames.back().data() + 7;
        unsigned sum = 0;
        for (int i = 0; i < 14; i++) sum += data[i];
        cal_ok = data[14] == static_cast<uint8_t>(sum + 0x55) && data[15] == static_cast<uint8_t>(sum + 0xAA) && data[10] == 0x80;
    }
    expect(cal_ok, "calibration block has a valid checksum and centred stick");

    // Buttons + accel + 16 extension bytes; idle stick centred, C and Z released.
    output({0x12, 0x04, 0x35});
    g_frames.clear();
    tick();
    bool report_ok = !g_frames.empty() && g_frames.back()[1] == 0x35 && g_frames.back().size() == 2 + 2 + 3 + 16;
    if (report_ok) {
        const uint8_t* ext = g_frames.back().data() + 7;
        report_ok = ext[0] == 0x80 && ext[1] == 0x80 && (ext[5] & 0x03) == 0x03 && ext[4] == 0xB3;
    }
    expect(report_ok, "mode 0x35 report carries centred stick, released C/Z, 1 g on Z");

    // Encryption (engine patch 0004): 0xAA to 0xF0 and an all-zero key at 0x40. WiiBrew documents
    // the zero-key case as decrypted = (byte ^ 0x17) + 0x17, independent of Dolphin's tables.
    std::vector<uint8_t> enable(22, 0);
    enable[0] = 0x16; enable[1] = 0x04; enable[2] = 0xA4; enable[3] = 0x00; enable[4] = 0xF0; enable[5] = 1; enable[6] = 0xAA;
    output(enable);
    std::vector<uint8_t> key(22, 0);
    key[0] = 0x16; key[1] = 0x04; key[2] = 0xA4; key[3] = 0x00; key[4] = 0x40; key[5] = 16;
    output(key);
    g_frames.clear();
    output({0x17, 0x04, 0xA4, 0x00, 0xFA, 0x00, 0x06});
    bool enc_ok = !g_frames.empty() && g_frames.back()[1] == 0x21;
    if (enc_ok) {
        const uint8_t* data = g_frames.back().data() + 7;
        const uint8_t expected[6] = {0x00, 0x00, 0xA4, 0x20, 0x00, 0x00};
        bool differs = false;
        for (int i = 0; i < 6; i++) {
            uint8_t plain = static_cast<uint8_t>((data[i] ^ 0x17) + 0x17);
            enc_ok = enc_ok && plain == expected[i];
            differs = differs || data[i] != expected[i];
        }
        enc_ok = enc_ok && differs;
    }
    expect(enc_ok, "encrypted ID read decrypts to the Nunchuk ID (zero key)");

    g_frames.clear();
    tick();
    bool enc_report = !g_frames.empty() && g_frames.back()[1] == 0x35;
    if (enc_report) {
        const uint8_t* ext = g_frames.back().data() + 7;
        enc_report = static_cast<uint8_t>((ext[0] ^ 0x17) + 0x17) == 0x80 && static_cast<uint8_t>((ext[1] ^ 0x17) + 0x17) == 0x80 &&
                     (static_cast<uint8_t>((ext[5] ^ 0x17) + 0x17) & 0x03) == 0x03;
    }
    expect(enc_report, "encrypted data report decrypts to a centred stick with C/Z released");

    return g_failures == 0 ? 0 : 1;
}
