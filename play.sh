#!/usr/bin/env sh
# Harvest Moon: Animal Parade - build (first time) and play. Put your disc in assets/ first.
cd "$(dirname "$0")" && exec python3 hmap.py play "$@"
