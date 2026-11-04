"""Find where the game locks itself to 30 fps.

Animal Parade renders at 30 fps (25 on PAL/50 Hz). A 30 fps Revolution SDK game
usually does one of these, and each leaves a static trace this scanner reports:

  A. waits for two vertical retraces per frame
     -> a function that calls VIWaitForRetrace twice, or once inside a loop
  B. compares a retrace counter against 2
     -> VIGetRetraceCount() followed by a cmpwi/cmplwi with immediate 2 (or 1)
  C. keeps its own frame-time constants
     -> float/double 30, 60, 1/30, 1/60 (and the 25/50 PAL variants) in data,
        and lis/lfs pairs that load them in code

None of these are proof on their own. The report is a list of places to set
breakpoints on in Dolphin (or to log in the recompiled build) - see docs/60FPS.md.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field

from . import ppc
from .dol import Dol

VI_FUNCTIONS = (
    "VIWaitForRetrace",
    "VIGetRetraceCount",
    "VISetNextFrameBuffer",
    "VIFlush",
    "VISetPreRetraceCallback",
    "VISetPostRetraceCallback",
    "VIGetNextField",
    "GXCopyDisp",
    "GXDrawDone",
    "GXSetDrawDone",
    "OSGetTick",
    "OSGetTime",
)

FRAME_CONSTANTS = {
    "30.0": 30.0,
    "60.0": 60.0,
    "1/30": 1 / 30,
    "1/60": 1 / 60,
    "25.0 (PAL)": 25.0,
    "50.0 (PAL)": 50.0,
    "1/25 (PAL)": 1 / 25,
    "1/50 (PAL)": 1 / 50,
    "2.0 (retraces per frame?)": 2.0,
}


@dataclass
class CallSite:
    callee: str
    site: int
    caller: int | None


@dataclass
class Finding:
    kind: str
    address: int
    detail: str


@dataclass
class ScanResult:
    calls: list[CallSite] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    constants: list[Finding] = field(default_factory=list)

    def to_json(self):
        def hexify(value):
            if isinstance(value, dict):
                return {k: hexify(v) for k, v in value.items()}
            if isinstance(value, list):
                return [hexify(v) for v in value]
            if isinstance(value, int) and value >= 0x80000000:
                return f"0x{value:08x}"
            return value

        return hexify(asdict(self))


def _caller(function_starts: list[int], address: int) -> int | None:
    best = None
    for start in function_starts:
        if start <= address:
            best = start
        else:
            break
    return best


def scan(dol: Dol, names: dict[int, str], function_starts: list[int]) -> ScanResult:
    result = ScanResult()
    starts = sorted(function_starts)
    wanted = {address: name for address, name in names.items() if name in VI_FUNCTIONS}

    # Call sites of the VI/GX/time functions.
    for begin, end in dol.code_ranges():
        for address in range(begin, end, 4):
            word = dol.word(address)
            if word is None or not ppc.is_bl(word):
                continue
            target = ppc.branch_target(word, address)
            if target in wanted:
                result.calls.append(CallSite(wanted[target], address, _caller(starts, address)))

    # A: VIWaitForRetrace twice in one function, or inside a backward loop.
    by_caller: dict[int | None, list[CallSite]] = {}
    for call in result.calls:
        by_caller.setdefault(call.caller, []).append(call)
    for caller, calls in by_caller.items():
        waits = [c for c in calls if c.callee == "VIWaitForRetrace"]
        if len(waits) >= 2:
            result.findings.append(Finding("double-retrace-wait", caller or waits[0].site,
                                           f"{len(waits)} calls to VIWaitForRetrace in one function"))
        for wait in waits:
            for offset in range(4, 4 * 24, 4):
                word = dol.word(wait.site + offset)
                if word is None:
                    break
                if ppc.opcode(word) == 16:  # bc
                    displacement = ppc.simm(word & 0xFFFC)
                    if displacement < 0 and wait.site + offset + displacement <= wait.site:
                        result.findings.append(Finding("retrace-wait-loop", wait.site,
                                                       f"VIWaitForRetrace inside a loop closed at {wait.site + offset:#010x}"))
                        break

    # B: retrace counter compared against 1 or 2.
    for call in result.calls:
        if call.callee != "VIGetRetraceCount":
            continue
        for offset in range(4, 4 * 16, 4):
            word = dol.word(call.site + offset)
            if word is None:
                break
            if ppc.opcode(word) in (10, 11) and ppc.simm(word) in (1, 2, 3):
                result.findings.append(Finding("retrace-count-compare", call.site + offset,
                                               f"compare with {ppc.simm(word)} after VIGetRetraceCount at {call.site:#010x}"))
                break

    # C: frame-time constants in data, plus code that loads them.
    for label, value in FRAME_CONSTANTS.items():
        for raw, width in ((struct.pack(">f", value), "float"), (struct.pack(">d", value), "double")):
            for address in dol.find_bytes(raw):
                section = dol.section_at(address)
                if section is None or section.executable or address % len(raw):
                    continue
                result.constants.append(Finding(f"constant {label}", address, f"{width} in {section.name}"))
    return result


def format_report(result: ScanResult, names: dict[int, str]) -> str:
    def name(address):
        if address is None:
            return "?"
        return f"{address:#010x}" + (f" {names[address]}" if address in names else "")

    lines = ["== Calls to VI / GX / timing functions =="]
    if not result.calls:
        lines.append("  (none found - run `hmap.py analyze` with a Dolphin map so these functions have names)")
    for call in sorted(result.calls, key=lambda c: (c.callee, c.site)):
        lines.append(f"  {call.callee:<26} from {call.site:#010x} in {name(call.caller)}")
    lines.append("")
    lines.append("== Frame-lock candidates ==")
    if not result.findings:
        lines.append("  (none)")
    for finding in result.findings:
        lines.append(f"  [{finding.kind}] {name(finding.address)}: {finding.detail}")
    lines.append("")
    lines.append(f"== Frame-time constants in data ({len(result.constants)}) ==")
    for finding in result.constants[:200]:
        lines.append(f"  {finding.address:#010x} {finding.kind} ({finding.detail})")
    if len(result.constants) > 200:
        lines.append(f"  ... {len(result.constants) - 200} more in the JSON report")
    return "\n".join(lines)
