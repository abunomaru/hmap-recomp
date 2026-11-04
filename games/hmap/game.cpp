// Harvest Moon: Animal Parade - engine game description.
// SPDX-License-Identifier: GPL-3.0-or-later

#include "wp/game.h"

namespace wp::game {

namespace {

// Animal Parade has no minigame modules that switch the Wii Remote grip, so the
// Wii Party specific fields (sideways modules, instruction screen, minigame
// prefix) are left empty; the engine treats nullptr/0 as "not used".
constexpr Description kDescription = {
    "Harvest Moon: Animal Parade",  // title (window / launcher)
    "hmap",                         // short_name
    "games/hmap/extracted",         // data_directory (overridden by argv[1] from hmap.py run)
    "games/hmap/nand",              // nand_directory: saves live here, never in git
    "games/hmap/settings.ini",      // settings_file
    "games/hmap/textures",          // textures_directory (custom texture packs)
    nullptr,                        // notice_module
    nullptr,                        // sideways_modules
    0,                              // sideways_module_count
    nullptr,                        // instruction_module
    nullptr,                        // minigame_prefix
};

}  // namespace

const Description& description() {
    return kDescription;
}

}  // namespace wp::game
