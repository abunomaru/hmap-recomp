"""hmap.py - one entry point for the whole pipeline.

    python hmap.py doctor                 check tools and the engine checkout
    python hmap.py setup                  link the game into the engine, fetch nodtool + dtk
    python hmap.py extract DISC           unpack your disc image (ISO/WBFS/RVZ/WIA/CISO)
    python hmap.py analyze [--dolphin-map FILE]
    python hmap.py patch [--list]         apply patches/ to main.dol (original kept)
    python hmap.py fps-scan               report where the 30 fps lock probably lives
    python hmap.py find-dsp [--dump FILE] locate the audio microcode for ahead-of-time translation
    python hmap.py recompile              DOL (+ RELs, + DSP) -> C++
    python hmap.py build [--headless]     compile the native executable
    python hmap.py run [-- ARGS]          start it
    python hmap.py all DISC               setup + extract + analyze + patch + recompile + build
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import analyze, compress, disc, dsp_finder, fps_scan, patches, project, symbols, toolchain
from .dol import Dol


def _python() -> str:
    return sys.executable


def _engine_env() -> dict[str, str]:
    env = dict(os.environ)
    env["WP_GAME"] = project.GAME_KEY
    return env


def _run(cmd: list[str], **kwargs) -> None:
    print("+ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def _game_id() -> str:
    if project.boot_bin().exists():
        return disc.identify(project.boot_bin()).game_id
    raise SystemExit("no extracted disc yet - run `hmap.py extract <your disc image>` first")


def _original_dol() -> Path:
    """The unpatched DOL, preserved the first time it is needed."""
    original = project.original_dol()
    if not original.exists():
        if not project.main_dol().exists():
            raise SystemExit("no extracted disc yet - run `hmap.py extract <your disc image>` first")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project.main_dol(), original)
    return original


# ------------------------------------------------------------------ commands


def cmd_doctor(args) -> int:
    ok = True

    def check(label, good, hint=""):
        nonlocal ok
        ok &= bool(good)
        print(f"  [{'ok' if good else '!!'}] {label}" + ("" if good or not hint else f"  -> {hint}"))

    print("hmap-recomp doctor")
    check(f"Python {sys.version.split()[0]} (need 3.11+)", sys.version_info >= (3, 11))
    check("engine submodule (extern/wiiparty-recomp)", project.engine_present(), "git submodule update --init")
    check(f"game linked into engine ({project.link_mode()})", project.link_mode() != "missing", "python hmap.py setup")
    for tool in ("cmake", "ninja", "git"):
        check(tool, shutil.which(tool), "install it with your package manager")
    compiler = shutil.which("g++") or shutil.which("c++") or shutil.which("clang++")
    check(f"C++ compiler ({compiler or 'none'})", compiler, "GCC 13+ (MinGW-w64 on Windows) or Clang 17+")
    if shutil.which("cmake"):
        version = subprocess.run(["cmake", "--version"], capture_output=True, text=True).stdout.split()[2]
        major, minor = (int(x) for x in version.split(".")[:2])
        check(f"CMake {version} (need 3.24+ for LINK_GROUP)", (major, minor) >= (3, 24))
    for tool in toolchain.TOOLS:
        found = toolchain.find(tool)
        check(f"{tool}: {found or 'not installed'}", found, "python hmap.py setup")
    check(f"disc extracted ({project.extracted()})", project.main_dol().exists(), "python hmap.py extract <disc>")
    if project.boot_bin().exists():
        info = disc.identify(project.boot_bin())
        release = info.release
        check(f"game id {info.game_id} rev {info.revision}: {release.region if release else 'UNKNOWN RELEASE'}", release)
    for name in ("dol_functions.csv", "symbols.csv"):
        check(f"analysis/{name}", (project.analysis() / name).exists(), "python hmap.py analyze")
    check("generated code", (project.generated() / "dol").exists(), "python hmap.py recompile")
    check(f"executable {project.executable()}", project.executable().exists(), "python hmap.py build")
    return 0 if ok else 1


def cmd_setup(args) -> int:
    mode = project.link_game()
    print(f"game folder linked into the engine ({mode})")
    for tool in toolchain.TOOLS:
        if toolchain.find(tool) and not args.force:
            print(f"{tool}: {toolchain.find(tool)}")
        else:
            print(f"{tool}: {toolchain.install(tool, force=args.force)}")
    return 0


def cmd_extract(args) -> int:
    image = Path(args.disc).expanduser().resolve()
    info = disc.identify(image)
    release = info.release
    print(f"{image.name}: {info.game_id} rev {info.revision} '{info.title}' ({info.container})")
    if release is None:
        message = f"{info.game_id} is not a known Harvest Moon: Animal Parade release ({', '.join(disc.KNOWN_RELEASES)})"
        if not args.any_game:
            raise SystemExit(message + " - pass --any-game to continue anyway")
        print("warning: " + message)
    else:
        print(f"recognised: {release.title} {release.region} ({release.video})")
    project.link_game()
    target = project.extracted()
    if target.exists():
        if not args.force:
            raise SystemExit(f"{target} already exists - pass --force to replace it")
        shutil.rmtree(target)
    project.original_dol().unlink(missing_ok=True)
    nodtool = toolchain.require("nodtool")
    _run([nodtool, "extract", image, target])
    if not project.main_dol().exists():
        raise SystemExit("extraction finished but sys/main.dol is missing")
    _original_dol()
    digest = toolchain.sha256(project.original_dol())
    (project.WORK / "inputs.json").write_text(json.dumps({
        "image": image.name, "game_id": info.game_id, "revision": info.revision,
        "main_dol_sha256": digest,
    }, indent=2) + "\n")
    print(f"main.dol sha256 {digest}")
    unpacked = unpack_modules()
    print(f"code modules (.rel): {len(unpacked)}" + (f" -> {project.modules_dir()}" if unpacked else ""))
    return 0


def unpack_modules() -> list[Path]:
    """Find REL modules anywhere on the disc, decompressing Yaz0/LZ10/LZ11 ones."""
    out_dir = project.modules_dir()
    found = []
    files_root = project.extracted() / "files"
    candidates = [p for p in files_root.rglob("*") if p.is_file() and ".rel" in p.name.lower()] if files_root.exists() else []
    for source in sorted(candidates):
        raw = source.read_bytes()
        kind = compress.detect(raw) if not source.name.lower().endswith(".rel") else None
        data = compress.decompress(raw) if kind else raw
        stem = source.name.split(".rel")[0] if ".rel" in source.name else source.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{stem}.rel"
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        found.append(target)
    return found


def cmd_info(args) -> int:
    dol = Dol.load(_original_dol())
    print(f"game id {_game_id()}, entry {dol.entry:#010x}, bss {dol.bss_address:#010x}+{dol.bss_size:#x}")
    for section in dol.sections:
        print(f"  {section.name:<7} {section.address:#010x}-{section.address + section.size:#010x} "
              f"({section.size:#x} bytes, file offset {section.offset:#x})")
    modules = sorted(project.modules_dir().glob("*.rel")) if project.modules_dir().exists() else []
    print(f"REL modules: {len(modules)}")
    for module in modules[:50]:
        print(f"  {module.name} ({module.stat().st_size} bytes)")
    return 0


def cmd_analyze(args) -> int:
    game_id = _game_id()
    original = _original_dol()
    dol = Dol.load(original)
    if args.skip_dtk:
        dtk_symbols = analyze.bl_target_scan(dol)
    else:
        try:
            dtk_symbols = analyze.run_dtk(original, project.WORK / "dtk")
        except (subprocess.CalledProcessError, OSError, RuntimeError) as error:
            print(f"decomp-toolkit failed ({error}); falling back to a bl-target scan")
            dtk_symbols = analyze.bl_target_scan(dol)
    dolphin_map = Path(args.dolphin_map).expanduser() if args.dolphin_map else None
    if dolphin_map is None:
        default = project.REPO_GAME / "reference" / f"{game_id}.map"
        dolphin_map = default if default.exists() else None
    hle = symbols.read_csv_list(project.analysis() / "hle_functions.csv")
    result = analyze.analyse(dol, dtk_symbols, dolphin_map, project.analysis() / "manual_symbols.csv", hle)
    analyze.save(result, game_id)
    project.sync_game()
    print("\n".join(result.report))
    print(f"\n{len(result.table.functions)} functions, {len(result.table.names)} names -> {project.analysis()}")
    if result.missing:
        print("\nSTILL MISSING: " + ", ".join(result.missing))
        print("Add them to games/hmap/analysis/manual_symbols.csv (address,name), or export a Dolphin map\n"
              "(Symbols > Generate Symbols From > Signature Database, then Save Symbol Map) and pass --dolphin-map.")
        return 2
    return 0


def cmd_patch(args) -> int:
    game_id = _game_id()
    found = patches.discover(project.PATCHES)
    if args.list:
        for patch in found:
            state = "on " if patch.applies_to(game_id) else "off"
            print(f"  [{state}] {patch.name}: {len(patch.writes)} writes - {patch.description}")
        return 0
    dol = Dol.load(_original_dol())
    if args.reset:
        shutil.copy2(project.original_dol(), project.main_dol())
        print("main.dol restored to the original")
        return 0
    report = patches.apply(dol, found, game_id)
    project.main_dol().write_bytes(dol.to_bytes())
    for line in report.applied:
        print(f"applied  {line}")
    for line in report.skipped:
        print(f"skipped  {line}")
    for line in report.warnings:
        print(f"warning  {line}")
    print(f"main.dol rebuilt from the original with {len(report.applied)} patch(es); run `hmap.py recompile` next")
    return 0


def cmd_fps_scan(args) -> int:
    dol = Dol.load(_original_dol())
    functions = project.analysis() / "dol_functions.csv"
    if not functions.exists():
        raise SystemExit("run `hmap.py analyze` first")
    with open(functions, newline="") as handle:
        starts = [int(row["address"], 16) for row in csv.DictReader(handle)]
    names = {s.address: s.name for s in symbols.read_csv_names(project.analysis() / "symbols.csv")}
    result = fps_scan.scan(dol, names, starts)
    print(fps_scan.format_report(result, names))
    out = project.WORK / "fps_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_json(), indent=2) + "\n")
    print(f"\nfull report: {out}")
    return 0


def cmd_find_dsp(args) -> int:
    dol = Dol.load(_original_dol())
    target = project.analysis() / "dsp_ucode.csv"
    if args.dump:
        candidate = dsp_finder.from_dump(dol, Path(args.dump).read_bytes())
        if candidate is None:
            raise SystemExit("that microcode image is not stored verbatim in main.dol (it may live in a REL or be built at run time)")
        dsp_finder.write_csv(target, args.name, candidate)
        project.sync_game()
        print(f"{args.name}: DOL offset {candidate.dol_offset:#x}, {candidate.size:#x} bytes, checksum {candidate.checksum:08x} -> {target}")
        return 0
    candidates = dsp_finder.scan(dol)
    if not candidates:
        print("no microcode-like vector tables found; use the dump method (see docs/PIPELINE.md)")
        return 1
    for c in candidates[:10]:
        print(f"  offset {c.dol_offset:#08x}  size {c.size:#x}  checksum {c.checksum:08x}  score {c.score}")
    print("Confirm with: WP_DUMP_DSP_CODE=<dir> python hmap.py run, then python hmap.py find-dsp --dump <dir>/dsp_<n>.bin")
    return 0


def _analysis_ready() -> None:
    sdk = analyze.read_sdk(project.REPO_GAME / "game.toml")
    if not sdk.get("os_save_context") or not sdk.get("setjmp"):
        raise SystemExit("game.toml [sdk] addresses are not filled in - run `hmap.py analyze` until it reports nothing missing")
    for name in ("dol_functions.csv", "symbols.csv", "hle_functions.csv"):
        if not (project.analysis() / name).exists():
            raise SystemExit(f"analysis/{name} is missing - run `hmap.py analyze`")


def cmd_recompile(args) -> int:
    project.link_game()
    project.sync_game()
    _analysis_ready()
    if not project.main_dol().exists():
        raise SystemExit("no extracted disc yet")
    recompiler = project.ENGINE / "recompiler"
    env = _engine_env()
    modules = unpack_modules()
    _run([_python(), recompiler / "recomp.py"], cwd=project.ENGINE, env=env)
    if modules:
        _run([_python(), recompiler / "recomp_rel.py", "--all"], cwd=project.ENGINE, env=env)
        # Second DOL pass: entries discovered from module calls into the DOL.
        _run([_python(), recompiler / "recomp.py"], cwd=project.ENGINE, env=env)
    dsp_rows = symbols.read_csv_list(project.analysis() / "dsp_ucode.csv")
    dsp_out = project.generated() / "dsp"
    if dsp_rows:
        _run([_python(), recompiler / "dsp" / "recomp_dsp.py"], cwd=project.ENGINE, env=env)
    elif dsp_out.exists():
        shutil.rmtree(dsp_out)
    if not dsp_rows:
        print("no dsp_ucode.csv entries: audio will use the DSP interpreter (slower; see `hmap.py find-dsp`)")
    return 0


def cmd_build(args) -> int:
    project.link_game()
    project.sync_game()
    if not (project.generated() / "dol").exists():
        raise SystemExit("no generated code - run `hmap.py recompile` first")
    if sys.platform == "win32":
        _run([_python(), project.ENGINE / "tools" / "fetch_sdl.py"], cwd=project.ENGINE)
    configure = [
        "cmake", "-S", project.ENGINE, "-B", project.cmake_dir(), "-G", "Ninja",
        f"-DCMAKE_BUILD_TYPE={'Debug' if args.debug else 'Release'}",
        f"-DWP_GAME={project.GAME_KEY}",
        f"-DWP_CODE_OPT={args.code_opt}",
    ]
    if args.headless:
        configure += ["-DWP_FETCH_SDL3=OFF", "-DWP_REQUIRE_SDL3=OFF"]
    else:
        configure.append("-DWP_REQUIRE_SDL3=ON")
    if args.console:
        configure.append("-DWP_CONSOLE=ON")
    _run(configure, cwd=project.ENGINE)
    build = ["cmake", "--build", project.cmake_dir(), "--target", project.GAME_KEY]
    if args.jobs:
        build += ["--parallel", str(args.jobs)]
    _run(build, cwd=project.ENGINE)
    print(f"built {project.executable()}")
    return 0


def cmd_run(args) -> int:
    exe = project.executable()
    if not exe.exists():
        raise SystemExit("not built yet - run `hmap.py build`")
    env = dict(os.environ)
    if args.dump_dsp:
        Path(args.dump_dsp).mkdir(parents=True, exist_ok=True)
        env["WP_DUMP_DSP_CODE"] = str(Path(args.dump_dsp).resolve())
    extra = [a for a in args.args if a != "--"]
    return subprocess.run([str(exe), str(project.extracted()), *extra], cwd=project.ENGINE, env=env).returncode


def cmd_all(args) -> int:
    cmd_setup(argparse.Namespace(force=False))
    if not project.main_dol().exists() or args.force:
        cmd_extract(argparse.Namespace(disc=args.disc, force=args.force, any_game=False))
    status = cmd_analyze(argparse.Namespace(dolphin_map=args.dolphin_map, skip_dtk=False))
    if status:
        return status
    cmd_patch(argparse.Namespace(list=False, reset=False))
    cmd_recompile(argparse.Namespace())
    return cmd_build(argparse.Namespace(headless=args.headless, debug=False, console=False, jobs=None, code_opt="-O1"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hmap.py", description="Harvest Moon: Animal Parade recompilation pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the environment").set_defaults(func=cmd_doctor)
    p = sub.add_parser("setup", help="link the game into the engine and fetch nodtool + dtk")
    p.add_argument("--force", action="store_true", help="re-download the tools")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("extract", help="unpack a disc image")
    p.add_argument("disc")
    p.add_argument("--force", action="store_true")
    p.add_argument("--any-game", action="store_true", help="allow a game id that is not Animal Parade")
    p.set_defaults(func=cmd_extract)

    sub.add_parser("info", help="show DOL sections and REL modules").set_defaults(func=cmd_info)

    p = sub.add_parser("analyze", help="function list, SDK addresses, symbols")
    p.add_argument("--dolphin-map", help="symbol map saved by Dolphin (Symbols > Save Symbol Map)")
    p.add_argument("--skip-dtk", action="store_true", help="use the simple bl-target scan instead of decomp-toolkit")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("patch", help="apply patches/ to main.dol")
    p.add_argument("--list", action="store_true")
    p.add_argument("--reset", action="store_true", help="restore the original main.dol")
    p.set_defaults(func=cmd_patch)

    sub.add_parser("fps-scan", help="find the 30 fps frame lock").set_defaults(func=cmd_fps_scan)

    p = sub.add_parser("find-dsp", help="locate the audio microcode")
    p.add_argument("--dump", help="dsp_<checksum>.bin written by a run with WP_DUMP_DSP_CODE")
    p.add_argument("--name", default="ax")
    p.set_defaults(func=cmd_find_dsp)

    sub.add_parser("recompile", help="translate the game code to C++").set_defaults(func=cmd_recompile)

    p = sub.add_parser("build", help="compile the native executable")
    p.add_argument("--headless", action="store_true", help="allow a build without SDL3 (no window, for servers/CI)")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--console", action="store_true", help="Windows: keep a console window for logs")
    p.add_argument("--jobs", type=int)
    p.add_argument("--code-opt", default="-O1", help="optimisation flag for translated code (engine default -O1)")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("run", help="run the built game")
    p.add_argument("--dump-dsp", metavar="DIR", help="write uploaded DSP microcode images to DIR")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("all", help="everything from a disc image to an executable")
    p.add_argument("disc")
    p.add_argument("--dolphin-map")
    p.add_argument("--force", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    if args.command != "doctor":
        project.link_game()  # idempotent: symlink (or synced copy) of games/hmap inside the engine
    try:
        return args.func(args) or 0
    except patches.PatchError as error:
        print(f"patch error: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}", file=sys.stderr)
        return error.returncode or 1
