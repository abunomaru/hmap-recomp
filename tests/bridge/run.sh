#!/usr/bin/env sh
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$ROOT/build/tests"
c++ -std=c++17 -O1 -Wall -Wextra -o "$ROOT/build/tests/test_bridge" "$ROOT/tests/bridge/test_bridge.cpp" "$ROOT/bridge/aurora_bridge.cpp"
"$ROOT/build/tests/test_bridge"
