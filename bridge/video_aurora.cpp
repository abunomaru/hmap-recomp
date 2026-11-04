// Video backend that renders through aurora (hmap-recomp).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Replaces the engine's Direct3D 11 / OpenGL renderers when built with -DWP_AURORA=ON:
//  * aurora owns the window (SDL3) and the GPU device (Dawn: D3D12 / Vulkan / Metal);
//  * every GX byte the game sends (gx::process) goes through the bridge into aurora's FIFO;
//  * each VI retrace (present) pumps window events and closes/opens an aurora frame.
// The engine still parses the stream itself, with the null renderer, for its interrupts
// (draw done, tokens) and register state. Everything runs on the game's thread.

#include "wp/video.h"

#include <SDL3/SDL.h>
#include <aurora/aurora.h>
#include <aurora/event.h>
#include <aurora/gfx.h>

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <string>

#include <imgui.h>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "aurora_bridge.h"
#include "wp/game.h"
#include "wp/gx.h"
#include "wp/input.h"
#include "wp/log.h"
#include "wp/memory.h"
#include "wp/settings.h"

namespace aurora::gx::fifo {
void write_data_grow(const void* data, uint32_t length);
}

namespace wp::video {

namespace {

constexpr int kLeftButton = 0x01;
constexpr int kRightButton = 0x02;
constexpr int kMiddleButton = 0x04;
constexpr int kExtraButton1 = 0x05;
constexpr int kExtraButton2 = 0x06;

hmap::aurora_bridge::Bridge* g_bridge = nullptr;
std::vector<uint8_t> g_translated;
bool g_in_frame = false;
double g_fps = 0.0;

void log_callback(AuroraLogLevel level, const char* module, const char* message, unsigned int) {
    static const char* const kLevels[] = {"debug", "info", "warning", "error", "fatal"};
    const char* name = level <= LOG_FATAL ? kLevels[level] : "?";
    if (level >= LOG_WARNING) {
        std::fprintf(stderr, "aurora %s %s: %s\n", name, module, message);
    }
    log::write("aurora", "%s %s: %s", name, module, message);
    if (level == LOG_FATAL) {
        std::fflush(stderr);
        std::abort();
    }
}

// Receives the game's GX bytes (gx::process, game thread) and forwards them, translated.
void forward(const uint8_t* data, size_t size) {
    if (!g_bridge || !g_in_frame) {
        return;
    }
    g_translated.clear();
    g_bridge->feed(data, size, g_translated);
    if (!g_translated.empty()) {
        aurora::gx::fifo::write_data_grow(g_translated.data(), static_cast<uint32_t>(g_translated.size()));
    }
}

void pump_events() {
    const AuroraEvent* event = aurora_update();
    while (event && event->type != AURORA_NONE) {
        if (event->type == AURORA_EXIT) {
            log::write("video", "window closed");
            std::fflush(stderr);
            std::exit(0);
        }
        ++event;
    }
}

struct KeyPair {
    int vk;
    SDL_Scancode scancode;
};

constexpr KeyPair kKeys[] = {
    {0x08, SDL_SCANCODE_BACKSPACE}, {0x09, SDL_SCANCODE_TAB},         {0x0D, SDL_SCANCODE_RETURN},     {0x13, SDL_SCANCODE_PAUSE},
    {0x14, SDL_SCANCODE_CAPSLOCK},  {0x1B, SDL_SCANCODE_ESCAPE},      {0x20, SDL_SCANCODE_SPACE},      {0x21, SDL_SCANCODE_PAGEUP},
    {0x22, SDL_SCANCODE_PAGEDOWN},  {0x23, SDL_SCANCODE_END},         {0x24, SDL_SCANCODE_HOME},       {0x25, SDL_SCANCODE_LEFT},
    {0x26, SDL_SCANCODE_UP},        {0x27, SDL_SCANCODE_RIGHT},       {0x28, SDL_SCANCODE_DOWN},       {0x2D, SDL_SCANCODE_INSERT},
    {0x2E, SDL_SCANCODE_DELETE},    {0x60, SDL_SCANCODE_KP_0},        {0x61, SDL_SCANCODE_KP_1},       {0x62, SDL_SCANCODE_KP_2},
    {0x63, SDL_SCANCODE_KP_3},      {0x64, SDL_SCANCODE_KP_4},        {0x65, SDL_SCANCODE_KP_5},       {0x66, SDL_SCANCODE_KP_6},
    {0x67, SDL_SCANCODE_KP_7},      {0x68, SDL_SCANCODE_KP_8},        {0x69, SDL_SCANCODE_KP_9},       {0x6A, SDL_SCANCODE_KP_MULTIPLY},
    {0x6B, SDL_SCANCODE_KP_PLUS},   {0x6D, SDL_SCANCODE_KP_MINUS},    {0x6E, SDL_SCANCODE_KP_PERIOD},  {0x6F, SDL_SCANCODE_KP_DIVIDE},
    {0xA0, SDL_SCANCODE_LSHIFT},    {0xA1, SDL_SCANCODE_RSHIFT},      {0xA2, SDL_SCANCODE_LCTRL},      {0xA3, SDL_SCANCODE_RCTRL},
    {0xA4, SDL_SCANCODE_LALT},      {0xA5, SDL_SCANCODE_RALT},        {0xBA, SDL_SCANCODE_SEMICOLON},  {0xBB, SDL_SCANCODE_EQUALS},
    {0xBC, SDL_SCANCODE_COMMA},     {0xBD, SDL_SCANCODE_MINUS},       {0xBE, SDL_SCANCODE_PERIOD},     {0xBF, SDL_SCANCODE_SLASH},
    {0xC0, SDL_SCANCODE_GRAVE},     {0xDB, SDL_SCANCODE_LEFTBRACKET}, {0xDC, SDL_SCANCODE_BACKSLASH},  {0xDD, SDL_SCANCODE_RIGHTBRACKET},
    {0xDE, SDL_SCANCODE_APOSTROPHE},
};

SDL_Scancode scancode_for(int vk) {
    if (vk >= 'A' && vk <= 'Z') return static_cast<SDL_Scancode>(SDL_SCANCODE_A + (vk - 'A'));
    if (vk >= '1' && vk <= '9') return static_cast<SDL_Scancode>(SDL_SCANCODE_1 + (vk - '1'));
    if (vk == '0') return SDL_SCANCODE_0;
    if (vk >= 0x70 && vk <= 0x7B) return static_cast<SDL_Scancode>(SDL_SCANCODE_F1 + (vk - 0x70));
    if (vk >= 0x7C && vk <= 0x87) return static_cast<SDL_Scancode>(SDL_SCANCODE_F13 + (vk - 0x7C));
    for (const KeyPair& pair : kKeys) {
        if (pair.vk == vk) return pair.scancode;
    }
    return SDL_SCANCODE_UNKNOWN;
}

bool g_menu_open = false;

// Edge-triggered key (F10, F11) read from SDL's keyboard state on the game thread.
bool pressed_once(SDL_Scancode key) {
    static bool held[SDL_SCANCODE_COUNT] = {};
    const bool* state = SDL_GetKeyboardState(nullptr);
    bool down = state && state[key];
    bool edge = down && !held[key];
    held[key] = down;
    return edge;
}

void store_number(const char* key, int value) {
    settings::store(key, std::to_string(value));
}

// F10 settings window (ImGui, drawn into the current aurora frame).
void draw_menu() {
    ImGui::SetNextWindowSize(ImVec2(420, 0), ImGuiCond_FirstUseEver);
    if (!ImGui::Begin("Harvest Moon: Animal Parade - Settings (F10)", &g_menu_open)) {
        ImGui::End();
        return;
    }
    static const char* kInterpolation[] = {"Off (30 fps)", "120 Hz", "180 Hz", "240 Hz"};
    static const int kTargets[] = {0, 120, 180, 240};
    int target = settings::number("video.interpolation", "WP_INTERPOLATION");
    int current = 0;
    for (int i = 0; i < 4; i++) {
        if (kTargets[i] == target) current = i;
    }
    if (ImGui::Combo("Frame interpolation", &current, kInterpolation, 4)) {
        store_number("video.interpolation", kTargets[current]);
    }
    ImGui::TextDisabled("Smooths camera and scenery between the game's 30 frames.\nExperimental.");
    ImGui::Separator();
    int speed = std::max(2, settings::number("system.fast_forward", "WP_FAST_FORWARD"));
    if (ImGui::SliderInt("Fast-forward speed (hold Tab)", &speed, 2, 16)) {
        store_number("system.fast_forward", speed);
    }
    bool nunchuk = settings::flag("input.nunchuk", "WP_NUNCHUK");
    if (ImGui::Checkbox("Nunchuk connected", &nunchuk)) {
        settings::store("input.nunchuk", nunchuk ? "1" : "0");
    }
    bool mute = settings::flag("audio.mute", nullptr);
    if (ImGui::Checkbox("Mute", &mute)) {
        settings::store("audio.mute", mute ? "1" : "0");
    }
    bool fullscreen = aurora_get_display_mode() != AURORA_DISPLAY_MODE_WINDOWED;
    if (ImGui::Checkbox("Fullscreen (F11)", &fullscreen)) {
        aurora_set_display_mode(fullscreen ? AURORA_DISPLAY_MODE_BORDERLESS : AURORA_DISPLAY_MODE_WINDOWED);
    }
    ImGui::Separator();
    ImGui::TextDisabled("Controls: W/A/S/D stick, C/X = C/Z, Enter/Space = A,\nBackspace = B, arrows = D-pad, Tab = fast-forward.\nKeys can be changed in games/hmap/settings.ini.");
    ImGui::End();
}

}  // namespace

void start() {
    AuroraConfig config{};
    config.appName = game::description().title;
    config.logCallback = &log_callback;
    config.vsync = false;
    // Software GPUs (llvmpipe/lavapipe) are refused unless asked for: used by tests and CI.
    config.allowCpuAdapter = std::getenv("WP_ALLOW_CPU_GPU") != nullptr;
    // Keep aurora's files (shader caches, texture_replacements/) beside the game's other files.
    static const std::string user_path = std::filesystem::absolute("games/hmap/aurora").string();
    std::filesystem::create_directories(user_path + "/texture_replacements");
    config.userPath = user_path.c_str();
    config.allowTextureReplacements = true;
    static char program[] = "hmap";
    static char* argv[] = {program, nullptr};
    AuroraInfo info = aurora_initialize(1, argv, &config);
    log::write("video", "build %s on aurora, window %ux%u", WP_BUILD, info.windowSize.width, info.windowSize.height);
    static hmap::aurora_bridge::Bridge bridge({g_memory, kPhysicalSize});
    g_bridge = &bridge;
    gx::set_fifo_tap(&forward);
    g_in_frame = aurora_begin_frame();
}

// Called on every VI retrace. An aurora frame is closed only when the game showed a new image
// (an EFB copy to the external framebuffer) - 30 per second in this game - so each aurora frame
// is one game frame, which is what frame interpolation needs. Events are pumped every retrace.
void present() {
    using Clock = std::chrono::steady_clock;
    static uint64_t shown = 0;
    static Clock::time_point last_frame = Clock::now();
    static int retraces_without_image = 0;
    gx::process();  // flushes pending GX bytes through the tap into this frame
    pump_events();
    if (pressed_once(SDL_SCANCODE_F10)) {
        g_menu_open = !g_menu_open;
    }
    if (pressed_once(SDL_SCANCODE_F11)) {
        bool windowed = aurora_get_display_mode() == AURORA_DISPLAY_MODE_WINDOWED;
        aurora_set_display_mode(windowed ? AURORA_DISPLAY_MODE_BORDERLESS : AURORA_DISPLAY_MODE_WINDOWED);
    }
    input::set_blocked(g_menu_open);
    uint64_t copies = g_bridge ? g_bridge->stats().display_copies : 0;
    bool new_image = copies != shown;
    // Screens that never copy to the display (loading) still need frames to be closed.
    if (!new_image && ++retraces_without_image < 4) {
        return;
    }
    retraces_without_image = 0;
    shown = copies;

    static const settings::LiveNumber interpolation("video.interpolation", "WP_INTERPOLATION");
    int target = interpolation();
    static int applied = -1;
    if (target != applied) {
        aurora_set_frame_interpolation_fps(static_cast<uint32_t>(target));
        applied = target;
        log::write("video", "frame interpolation %s", target ? "on" : "off");
    }
    Clock::time_point now = Clock::now();
    uint64_t interval = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(now - last_frame).count());
    interval = std::clamp<uint64_t>(interval, 16'666'667ull, 50'000'000ull);
    last_frame = now;
    if (target) {
        uint64_t now_ns = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(now.time_since_epoch()).count());
        aurora_set_present_schedule(now_ns + interval, interval);
        aurora_report_producer_paced(true);
    }
    if (g_in_frame) {
        if (g_menu_open) {
            draw_menu();
        }
        aurora_end_frame();
    }
    g_in_frame = aurora_begin_frame();
}

void update_statistics(double fps) {
    g_fps = fps;
    static int counter = 0;
    if (++counter % 2 == 0 && g_bridge) {
        const auto& stats = g_bridge->stats();
        log::write("bridge", "%.1f fps, %llu draws, %llu display lists, %llu pointers, %llu unknown bytes", fps,
                   static_cast<unsigned long long>(stats.draws), static_cast<unsigned long long>(stats.display_lists),
                   static_cast<unsigned long long>(stats.rewritten), static_cast<unsigned long long>(stats.unknown));
    }
}

void save_next_frame(const char*) {}

void* window_handle() {
    return aurora_get_window();
}

bool image_point(long x, long y, long client_width, long client_height, float& out_x, float& out_y) {
    if (client_width <= 0 || client_height <= 0) {
        return false;
    }
    double u = static_cast<double>(x) / client_width;
    double v = static_cast<double>(y) / client_height;
    if (u < 0.0 || u >= 1.0 || v < 0.0 || v >= 1.0) {
        return false;
    }
    out_x = static_cast<float>(u * 2.0 - 1.0);
    out_y = static_cast<float>(v * 2.0 - 1.0);
    return true;
}

bool window_focused() {
    SDL_Window* window = aurora_get_window();
    return window && (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) != 0;
}

bool client_size(int& width, int& height) {
    SDL_Window* window = aurora_get_window();
    return window && SDL_GetWindowSizeInPixels(window, &width, &height);
}

bool key_down(int key) {
    if (key == kLeftButton || key == kRightButton || key == kMiddleButton || key == kExtraButton1 || key == kExtraButton2) {
        SDL_MouseButtonFlags buttons = SDL_GetMouseState(nullptr, nullptr);
        uint8_t button = key == kLeftButton ? SDL_BUTTON_LEFT
                         : key == kRightButton ? SDL_BUTTON_RIGHT
                         : key == kMiddleButton ? SDL_BUTTON_MIDDLE
                         : key == kExtraButton1 ? SDL_BUTTON_X1
                                                : SDL_BUTTON_X2;
        return (buttons & SDL_BUTTON_MASK(button)) != 0;
    }
    const bool* state = SDL_GetKeyboardState(nullptr);
    if (!state) {
        return false;
    }
    switch (key) {
    case 0x10: return state[SDL_SCANCODE_LSHIFT] || state[SDL_SCANCODE_RSHIFT];
    case 0x11: return state[SDL_SCANCODE_LCTRL] || state[SDL_SCANCODE_RCTRL];
    case 0x12: return state[SDL_SCANCODE_LALT] || state[SDL_SCANCODE_RALT];
    default: {
        SDL_Scancode scancode = scancode_for(key);
        return scancode != SDL_SCANCODE_UNKNOWN && state[scancode];
    }
    }
}

bool cursor_position(long& x, long& y) {
    if (!aurora_get_window()) {
        return false;
    }
    float fx = 0.0f;
    float fy = 0.0f;
    SDL_GetMouseState(&fx, &fy);
    x = static_cast<long>(fx);
    y = static_cast<long>(fy);
    return true;
}

bool cursor_on_image(float& x, float& y) {
    SDL_Window* window = aurora_get_window();
    if (!window || SDL_GetMouseFocus() != window) {
        return false;
    }
    float fx = 0.0f;
    float fy = 0.0f;
    SDL_GetMouseState(&fx, &fy);
    int width = 0;
    int height = 0;
    SDL_GetWindowSize(window, &width, &height);
    return image_point(static_cast<long>(fx), static_cast<long>(fy), width, height, x, y);
}

}  // namespace wp::video
