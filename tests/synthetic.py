"""A synthetic DOL that contains hand-assembled versions of the SDK functions the
finders look for, plus distractors. No Nintendo code is involved: every function
is written here from what it does, so the tests run anywhere without game data."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from hmaptool import dol as dolmod  # noqa: E402
from hmaptool import ppc as p  # noqa: E402

TEXT = 0x80004000
DATA = 0x80300000

PANIC_STRING = b" in \"%s\" on line %d.\n\0\0\0"
TRACE_STRING = b"\nAddress:      Back Chain    LR Save\n\0\0"


def save_context():
    body = [p.enc_stmw(13, 0x34, 3)]
    for i in range(1, 8):
        body += [p.enc_mfspr(4, p.SPR_GQR0 + i), p.enc_stw(4, 0x1A4 + 4 * i, 3)]
    body += [p.enc_mfcr(0), p.enc_stw(0, 0x80, 3), p.enc_mflr(0), p.enc_stw(0, 0x84, 3),
             p.enc_li(3, 0), p.BLR]
    return body


def load_context():
    body = [p.enc_lmw(13, 0x34, 3)]
    for i in range(1, 8):
        body += [p.enc_lwz(4, 0x1A4 + 4 * i, 3), p.enc_mtspr(p.SPR_GQR0 + i, 4)]
    body += [p.enc_lwz(4, 0x198, 3), p.enc_mtspr(p.SPR_SRR0, 4), p.enc_lwz(4, 0x19C, 3),
             p.enc_mtspr(p.SPR_SRR1, 4), p.RFI]
    return body


def exception_handler_distractor():
    # Saves GQRs too, but with stmw r6,0x18(r4) - must not be taken for OSSaveContext.
    body = [p.MFLR_R0, p.enc_stwu_r1(0x20), p.enc_stmw(6, 0x18, 4)]
    for i in range(1, 8):
        body += [p.enc_mfspr(0, p.SPR_GQR0 + i), p.enc_stw(0, 0x1A4 + 4 * i, 4)]
    body += [p.BLR]
    return body


def setjmp():
    body = [p.enc_mflr(5), p.enc_mfcr(6), p.enc_stw(5, 0, 3), p.enc_stw(6, 4, 3), p.enc_stw(1, 8, 3),
            p.enc_stw(2, 12, 3), p.enc_stmw(13, 0x10, 3), p.enc_mffs(0)]
    body += [p.enc_stfd(14 + i, 0x58 + 8 * i, 3) for i in range(18)]
    body += [p.enc_li(3, 0), p.BLR]
    return body


def longjmp():
    body = [p.enc_lwz(5, 0, 3), p.enc_lwz(6, 4, 3), p.enc_mtlr(5), p.enc_mtcrf(255, 6), p.enc_lwz(1, 8, 3),
            p.enc_lwz(2, 12, 3), p.enc_lmw(13, 0x10, 3)]
    body += [p.enc_lfd(14 + i, 0x58 + 8 * i, 3) for i in range(18)]
    body += [p.enc_mr(3, 4), p.BLR]
    return body


def switch_fiber():
    return [p.MFLR_R0, p.enc_mr(5, 1), p.enc_stwu(5, -8, 4), p.enc_mr(1, 4), p.enc_stw(0, 4, 5),
            p.enc_mtlr(3), p.BLRL, p.enc_lwz(5, 0, 1), p.enc_lwz(0, 4, 5), p.enc_mtlr(0), p.enc_mr(1, 5), p.BLR]


def real_mode():
    return [p.enc_clrlwi(3, 3, 2), p.enc_mtspr(p.SPR_SRR0, 3), 0x7C6000A6, 0x5463076C,  # mfmsr; rlwinm
            p.enc_mtspr(p.SPR_SRR1, 3), p.RFI]


def panic(string_address):
    hi = (string_address + 0x8000) >> 16
    lo = string_address - (hi << 16)
    return [p.MFLR_R0, p.enc_stwu_r1(0x80), p.enc_lis(3, hi), p.enc_addi(3, 3, lo), 0x60000000, p.BLR]


def vi_wait():
    return [p.enc_li(3, 0), p.BLR]


def vi_get_count():
    return [p.enc_li(3, 0), p.BLR]


class Builder:
    def __init__(self):
        self.code = []
        self.labels = {}

    def add(self, name, words):
        self.labels[name] = TEXT + 4 * len(self.code)
        self.code += words
        self.code += [0, 0]  # padding between functions

    def addr(self, name):
        return self.labels[name]


def build():
    data = bytearray(64)
    panic_string = DATA + len(data)
    data += PANIC_STRING
    trace_string = DATA + len(data)
    data += TRACE_STRING
    while len(data) % 8:
        data.append(0)
    thirty = DATA + len(data)
    data += struct.pack(">f", 30.0) + bytes(4)

    b = Builder()
    b.add("entry", [p.enc_li(3, 0), p.BLR])
    b.add("OSSaveContext", save_context())
    b.add("handler", exception_handler_distractor())
    b.add("OSLoadContext", load_context())
    b.add("setjmp", setjmp())
    b.add("longjmp", longjmp())
    b.add("OSSwitchFiber", switch_fiber())
    b.add("RealMode", real_mode())
    b.add("OSPanic", panic(panic_string) + [])
    # the scheduler: saves the current context, then loads the next one
    sel = TEXT + 4 * len(b.code)
    b.add("OSSelectThread", [p.MFLR_R0, p.enc_stwu_r1(0x20),
                             p.enc_bl(sel + 8, b.addr("OSSaveContext")),
                             (11 << 26) | (0 << 23) | (3 << 16) | 0,  # cmpwi r3, 0
                             p.enc_bl(sel + 16, b.addr("OSLoadContext")),
                             p.BLR])
    b.add("VIWaitForRetrace", vi_wait())
    b.add("VIGetRetraceCount", vi_get_count())
    # game main loop: two retrace waits, then a counter compare against 2
    loop = TEXT + 4 * len(b.code)
    words = [p.MFLR_R0, p.enc_stwu_r1(0x20)]
    words.append(p.enc_bl(loop + 4 * len(words), b.addr("VIWaitForRetrace")))
    words.append(p.enc_bl(loop + 4 * len(words), b.addr("VIWaitForRetrace")))
    words.append(p.enc_bl(loop + 4 * len(words), b.addr("VIGetRetraceCount")))
    words.append((10 << 26) | (0 << 23) | (3 << 16) | 2)  # cmplwi r3, 2
    words.append(p.BLR)
    b.add("main_loop", words)
    # make the panic function reference the trace string too
    trace_ref = TEXT + 4 * len(b.code)
    hi = (trace_string + 0x8000) >> 16
    b.add("dump_context", [p.MFLR_R0, p.enc_stwu_r1(0x20), p.enc_lis(4, hi), p.enc_addi(4, 4, trace_string - (hi << 16)), p.BLR])
    del trace_ref

    text = b"".join(struct.pack(">I", w) for w in b.code)
    image = dolmod.build([(TEXT, text, True), (DATA, bytes(data), False)], entry=b.addr("entry"))
    return image, b.labels, {"panic_string": panic_string, "trace_string": trace_string, "thirty": thirty}
