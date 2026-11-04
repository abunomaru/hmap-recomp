"""Minimal PowerPC (Gekko/Broadway) instruction helpers.

Only what the analysis passes need: field extraction, a handful of matchers and
encoders (the encoders are used by the tests to build synthetic code).
"""

from __future__ import annotations

BLR = 0x4E800020
BLRL = 0x4E800021
RFI = 0x4C000064
MFLR_R0 = 0x7C0802A6

SPR_XER = 1
SPR_LR = 8
SPR_CTR = 9
SPR_SRR0 = 26
SPR_SRR1 = 27
SPR_GQR0 = 912


def opcode(word: int) -> int:
    return (word >> 26) & 0x3F


def rd(word: int) -> int:
    return (word >> 21) & 0x1F


def ra(word: int) -> int:
    return (word >> 16) & 0x1F


def rb(word: int) -> int:
    return (word >> 11) & 0x1F


def xo(word: int) -> int:
    return (word >> 1) & 0x3FF


def simm(word: int) -> int:
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def uimm(word: int) -> int:
    return word & 0xFFFF


def spr(word: int) -> int:
    field = (word >> 11) & 0x3FF
    return ((field & 0x1F) << 5) | (field >> 5)


def is_mfspr(word: int, number: int | None = None) -> bool:
    return opcode(word) == 31 and xo(word) == 339 and (number is None or spr(word) == number)


def is_mtspr(word: int, number: int | None = None) -> bool:
    return opcode(word) == 31 and xo(word) == 467 and (number is None or spr(word) == number)


def is_gqr(number: int) -> bool:
    return SPR_GQR0 <= number <= SPR_GQR0 + 7


def is_stmw(word: int, reg: int | None = None, base: int | None = None, offset: int | None = None) -> bool:
    return _d_form(word, 47, reg, base, offset)


def is_lmw(word: int, reg: int | None = None, base: int | None = None, offset: int | None = None) -> bool:
    return _d_form(word, 46, reg, base, offset)


def _d_form(word: int, op: int, reg, base, offset) -> bool:
    return (
        opcode(word) == op
        and (reg is None or rd(word) == reg)
        and (base is None or ra(word) == base)
        and (offset is None or simm(word) == offset)
    )


def is_mffs(word: int) -> bool:
    return opcode(word) == 63 and xo(word) == 583


def is_mfcr(word: int) -> bool:
    return opcode(word) == 31 and xo(word) == 19


def is_mtcrf(word: int) -> bool:
    return opcode(word) == 31 and xo(word) == 144


def is_mr(word: int, dst: int, src: int) -> bool:
    """`mr dst, src` is `or dst, src, src`."""
    return opcode(word) == 31 and xo(word) == 444 and ra(word) == dst and rd(word) == src and rb(word) == src


def is_lis(word: int) -> bool:
    return opcode(word) == 15 and ra(word) == 0


def is_addi(word: int) -> bool:
    return opcode(word) == 14


def is_ori(word: int) -> bool:
    return opcode(word) == 24


def is_bl(word: int) -> bool:
    return opcode(word) == 18 and (word & 3) == 1


def branch_target(word: int, address: int) -> int:
    """Target of an I-form branch (b/bl) located at `address`."""
    offset = word & 0x03FFFFFC
    if offset & 0x02000000:
        offset -= 0x04000000
    if word & 2:
        return offset & 0xFFFFFFFF
    return (address + offset) & 0xFFFFFFFF


def is_clrlwi(word: int, dst: int, src: int, n: int) -> bool:
    """`clrlwi dst, src, n` is `rlwinm dst, src, 0, n, 31`."""
    return (
        opcode(word) == 21
        and ra(word) == dst
        and rd(word) == src
        and rb(word) == 0
        and ((word >> 6) & 0x1F) == n
        and ((word >> 1) & 0x1F) == 31
    )


# ---------------------------------------------------------------- encoders (tests)


def _spr_field(number: int) -> int:
    return ((number & 0x1F) << 5) | ((number >> 5) & 0x1F)


def enc_mfspr(reg: int, number: int) -> int:
    return (31 << 26) | (reg << 21) | (_spr_field(number) << 11) | (339 << 1)


def enc_mtspr(number: int, reg: int) -> int:
    return (31 << 26) | (reg << 21) | (_spr_field(number) << 11) | (467 << 1)


def enc_d(op: int, rt: int, base: int, offset: int) -> int:
    return (op << 26) | (rt << 21) | (base << 16) | (offset & 0xFFFF)


def enc_stmw(reg: int, offset: int, base: int) -> int:
    return enc_d(47, reg, base, offset)


def enc_lmw(reg: int, offset: int, base: int) -> int:
    return enc_d(46, reg, base, offset)


def enc_stw(reg: int, offset: int, base: int) -> int:
    return enc_d(36, reg, base, offset)


def enc_lwz(reg: int, offset: int, base: int) -> int:
    return enc_d(32, reg, base, offset)


def enc_stwu(reg: int, offset: int, base: int) -> int:
    return enc_d(37, reg, base, offset)


def enc_stfd(reg: int, offset: int, base: int) -> int:
    return enc_d(54, reg, base, offset)


def enc_lfd(reg: int, offset: int, base: int) -> int:
    return enc_d(50, reg, base, offset)


def enc_li(reg: int, value: int) -> int:
    return enc_d(14, reg, 0, value)


def enc_addi(reg: int, base: int, value: int) -> int:
    return enc_d(14, reg, base, value)


def enc_lis(reg: int, value: int) -> int:
    return enc_d(15, reg, 0, value)


def enc_ori(dst: int, src: int, value: int) -> int:
    return (24 << 26) | (src << 21) | (dst << 16) | (value & 0xFFFF)


def enc_mr(dst: int, src: int) -> int:
    return (31 << 26) | (src << 21) | (dst << 16) | (src << 11) | (444 << 1)


def enc_mfcr(reg: int) -> int:
    return (31 << 26) | (reg << 21) | (19 << 1)


def enc_mtcrf(mask: int, reg: int) -> int:
    return (31 << 26) | (reg << 21) | (mask << 12) | (144 << 1)


def enc_mffs(reg: int) -> int:
    return (63 << 26) | (reg << 21) | (583 << 1)


def enc_mtlr(reg: int) -> int:
    return enc_mtspr(SPR_LR, reg)


def enc_mflr(reg: int) -> int:
    return enc_mfspr(reg, SPR_LR)


def enc_clrlwi(dst: int, src: int, n: int) -> int:
    return (21 << 26) | (src << 21) | (dst << 16) | (0 << 11) | (n << 6) | (31 << 1)


def enc_bl(source: int, target: int) -> int:
    return (18 << 26) | ((target - source) & 0x03FFFFFC) | 1


def enc_b(source: int, target: int) -> int:
    return (18 << 26) | ((target - source) & 0x03FFFFFC)


def enc_stwu_r1(frame: int) -> int:
    return enc_stwu(1, -frame, 1)
