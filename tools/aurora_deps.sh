#!/usr/bin/env sh
# For build machines whose proxy blocks GitHub source-archive downloads (codeload): clones
# aurora's FetchContent dependencies with git and prints the -D flags that point CMake at them.
# Not needed on a normal PC, where CMake downloads them itself.
set -eu
DEST=${1:-"$(pwd)/build/aurora-deps"}
mkdir -p "$DEST"
clone() { [ -d "$DEST/$1" ] || git clone -q --depth 1 --branch "$3" "https://github.com/$2" "$DEST/$1"; }
clone abseil abseil/abseil-cpp 20240722.0
clone xxhash Cyan4973/xxHash v0.8.4
clone fmt fmtlib/fmt 12.1.0
clone zlibng zlib-ng/zlib-ng 2.3.3
clone libpng pnggroup/libpng v1.6.58
clone imgui ocornut/imgui v1.91.9b-docking
clone tracy wolfpld/tracy v0.14.1
clone sdl libsdl-org/SDL release-3.4.10
echo "-DAURORA_ENABLE_TESTS=OFF -DFETCHCONTENT_SOURCE_DIR_ABSEIL-CPP=$DEST/abseil -DFETCHCONTENT_SOURCE_DIR_XXHASH=$DEST/xxhash -DFETCHCONTENT_SOURCE_DIR_FMT=$DEST/fmt -DFETCHCONTENT_SOURCE_DIR_ZLIB=$DEST/zlibng -DFETCHCONTENT_SOURCE_DIR_PNG=$DEST/libpng -DFETCHCONTENT_SOURCE_DIR_IMGUI=$DEST/imgui -DFETCHCONTENT_SOURCE_DIR_TRACY=$DEST/tracy -DFETCHCONTENT_SOURCE_DIR_SDL=$DEST/sdl"
