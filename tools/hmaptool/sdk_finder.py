"""Locate the Revolution SDK / MSL functions the engine needs by code pattern.

The Wii Party engine replaces a handful of hardware-bound functions with native
handlers and treats two more specially:

  replaced (hle_functions.csv)       OSRealModeCall, OSPanic, OSLoadContext,
                                     OSSwitchFiber, longjmp
  special-cased by the translator    OSSaveContext, setjmp

Their addresses differ per game (and per region), so they are found here from
instruction patterns that follow from what each function *does* - which does not
change between SDK builds - instead of byte signatures from one build.

Each finder returns every match. Exactly one match means the result is used;
zero or several means the name must be supplied by a Dolphin map or by hand in
games/hmap/analysis/manual_symbols.csv (the CLI prints the candidates).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from . import ppc
from .dol import Dol

MAX_FUNCTION_WORDS = 0x800


@dataclass
class Match:
    name: str
    address: int
    evidence: str


@dataclass
class Result:
    name: str
    matches: list[Match] = field(default_factory=list)

    @property
    def address(self) -> int | None:
        return self.matches[0].address if len(self.matches) == 1 else None


class Code:
    """Function-boundary aware view of the DOL's code sections."""

    def __init__(self, dol: Dol, function_starts: list[int] | None = None):
        self.dol = dol
        self.starts = sorted(set(function_starts or []))

    def _boundary_before(self, address: int, strict: bool) -> bool:
        """True if a function cannot continue from address-4 into address.

        Always: padding (a zero word) or leaving the code section. A blr/rfi only
        counts when the next word looks like a prologue (strict), or always when
        there is no function list to go by (not strict)."""
        previous = self.dol.word(address - 4)
        current = self.dol.word(address)
        if previous is None or not self.dol.is_code(address - 4) or previous == 0 or current == 0:
            return True
        if previous in (ppc.BLR, ppc.RFI):
            if not strict:
                return True
            return current == ppc.MFLR_R0 or (ppc.opcode(current) == 37 and ppc.rd(current) == 1 and ppc.ra(current) == 1)
        return False

    def function_start(self, address: int) -> int:
        known = None
        if self.starts:
            index = bisect.bisect_right(self.starts, address) - 1
            if index >= 0 and address - self.starts[index] < MAX_FUNCTION_WORDS * 4:
                known = self.starts[index]
        cursor = address
        for _ in range(MAX_FUNCTION_WORDS):
            if cursor == known or self._boundary_before(cursor, strict=known is not None):
                return cursor
            cursor -= 4
        return known if known is not None else cursor

    def function_end(self, start: int) -> int:
        limit = start + MAX_FUNCTION_WORDS * 4
        if self.starts:
            index = bisect.bisect_right(self.starts, start)
            if index < len(self.starts):
                limit = min(limit, self.starts[index])
        cursor = start + 4
        while cursor < limit:
            if self._boundary_before(cursor, strict=True):
                return cursor
            cursor += 4
        return limit

    def body(self, start: int) -> list[int]:
        return self.dol.words(start, self.function_end(start))

    def instructions(self):
        for begin, end in self.dol.code_ranges():
            for address in range(begin, end, 4):
                yield address, self.dol.word(address)


def _unique(matches: list[Match]) -> list[Match]:
    seen = {}
    for match in matches:
        seen.setdefault(match.address, match)
    return [seen[a] for a in sorted(seen)]


# ---------------------------------------------------------------- the finders


def find_os_save_context(code: Code) -> Result:
    out = []
    for address, word in code.instructions():
        if not ppc.is_stmw(word, 13, 3, 0x34):
            continue
        start = code.function_start(address)
        body = code.body(start)
        gqr_reads = sum(1 for w in body if ppc.is_mfspr(w) and ppc.is_gqr(ppc.spr(w)))
        if gqr_reads >= 3 and ppc.RFI not in body:
            out.append(Match("OSSaveContext", start, f"stmw r13,0x34(r3) at {address:#010x}, {gqr_reads} GQR reads, no rfi"))
    return Result("OSSaveContext", _unique(out))


def find_os_load_context(code: Code) -> Result:
    out = []
    for address, word in code.instructions():
        if not ppc.is_lmw(word, 13, 3, 0x34):
            continue
        start = code.function_start(address)
        body = code.body(start)
        gqr_writes = sum(1 for w in body if ppc.is_mtspr(w) and ppc.is_gqr(ppc.spr(w)))
        if ppc.RFI in body and gqr_writes >= 3 and any(ppc.is_mtspr(w, ppc.SPR_SRR0) for w in body):
            out.append(Match("OSLoadContext", start, f"lmw r13,0x34(r3) at {address:#010x}, {gqr_writes} GQR writes, mtsrr0 + rfi"))
    return Result("OSLoadContext", _unique(out))


def find_setjmp(code: Code) -> Result:
    out = []
    for address, word in code.instructions():
        if not ppc.is_stmw(word, 13, 3, 0x10):
            continue
        start = code.function_start(address)
        body = code.body(start)
        if any(ppc.is_mfcr(w) for w in body) and ppc.enc_li(3, 0) in body and not any(ppc.is_lmw(w) for w in body):
            out.append(Match("setjmp", start, f"stmw r13,0x10(r3) at {address:#010x} with mfcr and li r3,0"))
    return Result("setjmp", _unique(out))


def find_longjmp(code: Code) -> Result:
    out = []
    for address, word in code.instructions():
        if not ppc.is_lmw(word, 13, 3, 0x10):
            continue
        start = code.function_start(address)
        body = code.body(start)
        if any(ppc.is_mtcrf(w) for w in body) and not any(ppc.is_stmw(w) for w in body):
            out.append(Match("longjmp", start, f"lmw r13,0x10(r3) at {address:#010x} with mtcrf"))
    return Result("longjmp", _unique(out))


def find_os_switch_fiber(code: Code) -> Result:
    """OSSwitchFiber(pc, newsp): saves r1, moves the stack to r4, calls r3 with blrl."""
    out = []
    for address, word in code.instructions():
        if not ppc.is_mr(word, 1, 4):
            continue
        start = code.function_start(address)
        body = code.body(start)
        if (
            len(body) <= 20
            and ppc.BLRL in body
            and any(ppc.is_mr(w, 5, 1) for w in body)
            and any(ppc.is_mtspr(w, ppc.SPR_LR) and ppc.rd(w) == 3 for w in body)
        ):
            out.append(Match("OSSwitchFiber", start, f"mr r1,r4 at {address:#010x}, mtlr r3 + blrl in a {len(body)}-word function"))
    return Result("OSSwitchFiber", _unique(out))


def find_os_real_mode_call(code: Code) -> Result:
    """The cache library's RealMode(fn): clrlwi r3,r3,2; mtsrr0 r3; ...; rfi."""
    out = []
    for address, word in code.instructions():
        if not ppc.is_clrlwi(word, 3, 3, 2):
            continue
        nxt = code.dol.word(address + 4)
        if nxt is None or not ppc.is_mtspr(nxt, ppc.SPR_SRR0) or ppc.rd(nxt) != 3:
            continue
        tail = code.dol.words(address, address + 4 * 10)
        if ppc.RFI in tail:
            start = code.function_start(address)
            out.append(Match("OSRealModeCall", start, f"clrlwi r3,r3,2; mtsrr0 r3 ... rfi at {address:#010x}"))
    return Result("OSRealModeCall", _unique(out))


OSPANIC_STRINGS = (
    b" in \"%s\" on line %d.\n",
    b"\nAddress:      Back Chain    LR Save\n",
)


def string_references(code: Code, target: int, window: int = 8) -> list[int]:
    """Code addresses that build `target` with a lis/addi (or lis/ori) pair."""
    refs = []
    for address, word in code.instructions():
        if not ppc.is_lis(word):
            continue
        reg = ppc.rd(word)
        high = ppc.uimm(word) << 16
        for step in range(1, window + 1):
            follow = code.dol.word(address + 4 * step)
            if follow is None:
                break
            if ppc.is_addi(follow) and ppc.ra(follow) == reg:
                value = (high + ppc.simm(follow)) & 0xFFFFFFFF
            elif ppc.is_ori(follow) and ppc.rd(follow) == reg:
                value = high | ppc.uimm(follow)
            else:
                continue
            if value == target:
                refs.append(address)
                break
    return refs


def find_os_panic(code: Code) -> Result:
    """OSPanic prints both strings; OSDumpContext may share the stack-trace one,
    so a function that references both wins, then one that references the first."""
    per_needle = []
    for needle in OSPANIC_STRINGS:
        found = []
        for string_address in code.dol.find_bytes(needle):
            for ref in string_references(code, string_address):
                start = code.function_start(ref)
                found.append(Match("OSPanic", start, f"references {needle!r} at {string_address:#010x} from {ref:#010x}"))
        per_needle.append(_unique(found))
    both = {m.address for m in per_needle[0]} & {m.address for m in per_needle[1]}
    if len(both) == 1:
        return Result("OSPanic", [m for m in per_needle[0] if m.address in both])
    if per_needle[0]:
        return Result("OSPanic", per_needle[0])
    return Result("OSPanic", per_needle[1])


FINDERS = {
    "OSSaveContext": find_os_save_context,
    "OSLoadContext": find_os_load_context,
    "setjmp": find_setjmp,
    "longjmp": find_longjmp,
    "OSSwitchFiber": find_os_switch_fiber,
    "OSRealModeCall": find_os_real_mode_call,
    "OSPanic": find_os_panic,
}

REQUIRED = tuple(FINDERS)


def find_all(dol: Dol, function_starts: list[int] | None = None, names=REQUIRED) -> dict[str, Result]:
    code = Code(dol, function_starts)
    return {name: FINDERS[name](code) for name in names}
