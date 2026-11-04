# GX → aurora bridge

`aurora_bridge.cpp` turns the Wii GX command stream that the Wii Party engine captures into
the stream [aurora](https://github.com/patchzyy/aurora-wiicompiled) renders (aurora is the
renderer of WiiCompiled, Super Paper Mario PC, NSMB Wii PC...). See the header for the
translation table. It produces bytes only and is unit tested without a GPU:

```sh
sh tests/bridge/run.sh
```

Status: translation done and tested; next is wiring it into the engine (aurora owns the window,
VI retrace → aurora frames, aurora draw-done → GPU finish interrupt). See docs/ROADMAP.md.
