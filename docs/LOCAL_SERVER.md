# Running the pipeline on a home server

The slow steps (analysis, recompiling, compiling about a million lines of C++) can run on a
server. Playing needs a machine with a display and OpenGL 4.1, so the usual setup is:
**build on the server, play on the laptop** (or build on the laptop directly).

## Docker

```bash
git clone --recursive https://github.com/abunomaru/hmap-recomp && cd hmap-recomp
docker build -t hmap-recomp docker/
# put your disc in ./disc (git-ignored), then:
docker run --rm -it -v "$PWD:/work" -w /work hmap-recomp python3 hmap.py all disc/hmap.rvz --headless
```

The container has the full SDL3 build dependencies, so you can also drop `--headless` to get a
build with a window, which runs on a Linux desktop with the same libraries.

A headless build (`--headless`) has no window, sound or gamepad. It is useful to check that
the game boots (logs on stderr) and for automated testing with `WP_INPUT_SCRIPT`.

## Without Docker

Any Linux box with the packages from the README works. Run the same `python hmap.py …`
commands over SSH.

## Moving the result to the laptop

The executable runs from the engine folder and reads the extracted disc. The simplest way is to
clone the repo on the laptop and build there too, which takes about the same time as the server
on a modern CPU. Only the disc dump needs copying: `hmap.py extract` gives byte-identical output
on every machine.
