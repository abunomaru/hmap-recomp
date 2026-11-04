# Build environment for hmap-recomp (Ubuntu 24.04: GCC 13, CMake 3.28, Python 3.12).
# Contains tools only - no game data. Mount the repo at /work (see docs/LOCAL_SERVER.md).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ cmake ninja-build python3 git curl ca-certificates \
        libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxss-dev libxtst-dev \
        libxkbcommon-dev libwayland-dev wayland-protocols libdecor-0-dev libegl-dev libgl-dev \
        libpulse-dev libasound2-dev libudev-dev libdbus-1-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git config --global --add safe.directory '*'
WORKDIR /work
CMD ["python3", "hmap.py", "doctor"]
