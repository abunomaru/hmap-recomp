# Your files go here

Nothing in this folder is ever uploaded to GitHub (see `.gitignore`), except this README.

| Put here | What |
|---|---|
| `your-disc.iso` / `.rvz` / `.wbfs` / `.wia` / `.ciso` | **Required.** Your own dump of *Harvest Moon: Animal Parade* (NTSC-U `RBIEE9` recommended; PAL `RBIP99` and Japanese `RBIJ99` are recognised). Exactly one disc image. |
| `patches/*.xdelta` | Optional disc patches, applied in file-name order before the game is built, e.g. **Harvest Moon: Pride Parade** (`v0.2` or `v0.2b`). They need the clean NTSC-U disc they were made from. |
| `textures/` | Optional texture packs in Dolphin format: folders of `.png` files or `.zip` files (e.g. the Pride Parade replacement textures). |

Then double-click **`play.bat`** in the main folder (Windows), or run `python hmap.py play`.
The first run takes a while (extracting, translating and compiling the game); later runs only
redo what changed. `assets/build/` holds converted/patched disc images and can be deleted.
