import json
import struct
import tempfile
import unittest
from pathlib import Path

import synthetic
from hmaptool import analyze, compress, disc, dsp_finder, fps_scan, patches, ppc, sdk_finder, symbols
from hmaptool.dol import Dol


class DolTests(unittest.TestCase):
    def setUp(self):
        self.image, self.labels, self.data = synthetic.build()
        self.dol = Dol(self.image)

    def test_sections_and_reads(self):
        self.assertEqual(self.dol.entry, self.labels["entry"])
        self.assertTrue(self.dol.is_code(self.labels["setjmp"]))
        self.assertFalse(self.dol.is_code(self.data["thirty"]))
        self.assertEqual(self.dol.read(self.data["thirty"], 4), struct.pack(">f", 30.0))

    def test_write_roundtrip(self):
        self.dol.write_word(self.labels["entry"], 0x60000000)
        again = Dol(self.dol.to_bytes())
        self.assertEqual(again.word(self.labels["entry"]), 0x60000000)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            Dol(b"\0" * 16)


class PpcTests(unittest.TestCase):
    def test_spr_roundtrip(self):
        for number in (8, 9, 26, 27, 912, 919):
            self.assertEqual(ppc.spr(ppc.enc_mfspr(3, number)), number)
            self.assertTrue(ppc.is_mtspr(ppc.enc_mtspr(number, 3), number))

    def test_known_encodings(self):
        self.assertEqual(ppc.enc_mflr(0), ppc.MFLR_R0)
        self.assertEqual(ppc.enc_mr(1, 4), 0x7C812378)
        self.assertEqual(ppc.enc_li(3, 0), 0x38600000)
        self.assertEqual(ppc.enc_stwu_r1(0x20), 0x9421FFE0)

    def test_branch_target(self):
        word = ppc.enc_bl(0x80004100, 0x80004000)
        self.assertTrue(ppc.is_bl(word))
        self.assertEqual(ppc.branch_target(word, 0x80004100), 0x80004000)


class SdkFinderTests(unittest.TestCase):
    def setUp(self):
        self.image, self.labels, _ = synthetic.build()
        self.dol = Dol(self.image)

    def check(self, starts):
        results = sdk_finder.find_all(self.dol, starts)
        expected = {
            "OSSaveContext": "OSSaveContext", "OSLoadContext": "OSLoadContext", "setjmp": "setjmp",
            "longjmp": "longjmp", "OSSwitchFiber": "OSSwitchFiber", "OSRealModeCall": "RealMode",
            "OSPanic": "OSPanic", "OSSelectThread": "OSSelectThread",
        }
        for name, label in expected.items():
            with self.subTest(name=name):
                self.assertEqual(results[name].address, self.labels[label],
                                 [hex(m.address) for m in results[name].matches])

    def test_with_function_list(self):
        self.check(sorted(self.labels.values()))

    def test_without_function_list(self):
        self.check(None)

    def test_ospanic_prefers_function_referencing_both_strings(self):
        # dump_context only references the trace string; OSPanic only the first. Result must be OSPanic.
        result = sdk_finder.find_os_panic(sdk_finder.Code(self.dol, sorted(self.labels.values())))
        self.assertEqual(result.address, self.labels["OSPanic"])


class SymbolsTests(unittest.TestCase):
    def test_parse_dtk(self):
        text = (
            "__start = .init:0x80004000; // type:function size:0x24 scope:global\n"
            "fn_80004030 = .text:0x80004030; // type:function size:0xC\n"
            "lbl_80300000 = .data:0x80300000; // type:object size:0x10 data:string\n"
            "garbage line\n"
        )
        parsed = symbols.parse_dtk_symbols(text)
        self.assertEqual([(s.name, s.address, s.size, s.kind) for s in parsed], [
            ("__start", 0x80004000, 0x24, "function"),
            ("fn_80004030", 0x80004030, 0xC, "function"),
            ("lbl_80300000", 0x80300000, 0x10, "object"),
        ])

    def test_parse_dolphin_map(self):
        text = (
            ".text section layout\n"
            "80004000 000024 80004000 0 __start\n"
            "80004030 00000c 80004030 0 zz_80004030_\n"
            ".data section layout\n"
            "80300000 000010 80300000 0 someTable\n"
        )
        parsed = symbols.parse_dolphin_map(text)
        self.assertEqual(parsed[0].name, "__start")
        self.assertEqual(parsed[0].kind, "function")
        self.assertEqual(parsed[2].kind, "object")
        table = symbols.SymbolTable()
        table.merge(parsed, "dolphin")
        self.assertEqual(table.names, {0x80004000: "__start", 0x80300000: "someTable"})
        self.assertEqual(sorted(table.functions), [0x80004000, 0x80004030])


class AnalyseTests(unittest.TestCase):
    def test_full_analysis_resolves_engine_names(self):
        image, labels, _ = synthetic.build()
        dol = Dol(image)
        dtk = [symbols.Symbol(a, f"fn_{a:08X}", 0, "function") for a in labels.values()]
        with tempfile.TemporaryDirectory() as tmp:
            manual = Path(tmp) / "manual.csv"
            manual.write_text("address,name\n0x%08x,VIWaitForRetrace\n" % labels["VIWaitForRetrace"])
            result = analyze.analyse(dol, dtk, None, manual, ["OSRealModeCall", "OSPanic", "OSLoadContext",
                                                              "OSSwitchFiber", "longjmp"])
        self.assertEqual(result.missing, [])
        self.assertEqual(result.sdk, {"os_save_context": labels["OSSaveContext"], "setjmp": labels["setjmp"]})
        self.assertEqual(result.table.address_of("VIWaitForRetrace"), labels["VIWaitForRetrace"])

    def test_bl_scan_finds_callees(self):
        image, labels, _ = synthetic.build()
        found = {s.address for s in analyze.bl_target_scan(Dol(image))}
        self.assertIn(labels["VIWaitForRetrace"], found)
        self.assertIn(labels["entry"], found)

    def test_game_toml_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.toml"
            path.write_text('name = "x"\nid = "RBIEE9"\n\n[sdk]\nos_save_context = 0x00000000\nsetjmp = 0x00000000\n')
            analyze.write_game_toml(path, "RBIP99", {"os_save_context": 0x80123450, "setjmp": 0x80200000})
            self.assertEqual(analyze.read_sdk(path), {"os_save_context": 0x80123450, "setjmp": 0x80200000})
            self.assertIn('id = "RBIP99"', path.read_text())


class CompressTests(unittest.TestCase):
    PAYLOAD = b"Harvest Moon " * 20 + bytes(range(256))

    def test_store_roundtrips(self):
        self.assertEqual(compress.decompress(compress.yaz0_store(self.PAYLOAD)), self.PAYLOAD)
        self.assertEqual(compress.decompress(compress.lz_store(self.PAYLOAD, 0x10)), self.PAYLOAD)
        self.assertEqual(compress.decompress(compress.lz_store(self.PAYLOAD, 0x11)), self.PAYLOAD)

    def test_yaz0_backreference(self):
        # "ab" literal, then copy 6 bytes from distance 2 -> "abababab"
        stream = b"Yaz0" + struct.pack(">I", 8) + bytes(8) + bytes([0b11000000]) + b"ab" + bytes([0x40, 0x01])
        self.assertEqual(compress.yaz0(stream), b"abababab")

    def test_yaz0_long_backreference(self):
        stream = b"Yaz0" + struct.pack(">I", 0x13) + bytes(8) + bytes([0b10000000]) + b"z" + bytes([0x00, 0x00, 0x00])
        self.assertEqual(compress.yaz0(stream), b"z" * 0x13)

    def test_lz10_backreference(self):
        # flags 0b01000000: literal 'x', then ref len 3+3=6 dist 1
        stream = bytes([0x10, 7, 0, 0, 0b01000000]) + b"x" + bytes([0x30, 0x00])
        self.assertEqual(compress.lz10(stream), b"x" * 7)

    def test_lz11_all_reference_forms(self):
        short = bytes([0x30, 0x00])                       # len 4, dist 1
        medium = bytes([0x00, 0x10, 0x00])                # len 0x11 + 1, dist 1
        long = bytes([0x10, 0x00, 0x10, 0x00])            # len 0x111 + 1, dist 1
        total = 1 + 4 + 0x12 + 0x112
        stream = bytes([0x11, total & 0xFF, total >> 8, 0, 0b01110000]) + b"q" + short + medium + long
        self.assertEqual(compress.lz11(stream), b"q" * total)

    def test_bad_reference(self):
        with self.assertRaises(ValueError):
            compress.lz10(bytes([0x10, 4, 0, 0, 0b10000000, 0x10, 0x05]))


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.image, self.labels, self.data = synthetic.build()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_toml_patch_verifies_original(self):
        entry = self.labels["entry"]
        (self.dir / "a.toml").write_text(
            '[patch]\nname = "nop"\n\n[[patch.write]]\n'
            f"address = 0x{entry:08x}\noriginal = 0x38600000\nvalue = 0x60000000\n")
        dol = Dol(self.image)
        report = patches.apply(dol, patches.discover(self.dir), "RBIEE9")
        self.assertEqual(dol.word(entry), 0x60000000)
        self.assertEqual(len(report.applied), 1)

    def test_wrong_original_is_refused_and_nothing_written(self):
        entry = self.labels["entry"]
        (self.dir / "a.toml").write_text(
            '[patch]\nname = "x"\n[[patch.write]]\n'
            f"address = 0x{entry + 4:08x}\nvalue = 0x11111111\n"
            '[[patch.write]]\n'
            f"address = 0x{entry:08x}\noriginal = 0x12345678\nvalue = 0x60000000\n")
        dol = Dol(self.image)
        before = dol.to_bytes()
        with self.assertRaises(patches.PatchError):
            patches.apply(dol, patches.discover(self.dir), "RBIEE9")
        self.assertEqual(dol.to_bytes(), before)

    def test_region_filter(self):
        (self.dir / "a.toml").write_text(
            '[patch]\nname = "pal only"\ngame_ids = ["RBIP99"]\n[[patch.write]]\n'
            f"address = 0x{self.labels['entry']:08x}\nvalue = 0x60000000\n")
        dol = Dol(self.image)
        report = patches.apply(dol, patches.discover(self.dir), "RBIEE9")
        self.assertEqual(report.applied, [])
        self.assertEqual(dol.word(self.labels["entry"]), 0x38600000)

    def test_gecko_writes(self):
        entry = self.labels["entry"]
        thirty = self.data["thirty"]
        code = (
            "$60 FPS (example)\n"
            f"{0x04000000 | (entry & 0x01FFFFFF):08X} 60000000\n"
            f"{0x02000000 | (thirty & 0x01FFFFFF):08X} 00014270\n"
            "E0000000 80008000\n"
        )
        patch = patches.parse_gecko(code, "test")
        dol = Dol(self.image)
        report = patches.apply(dol, [patch], "RBIEE9")
        self.assertEqual(dol.word(entry), 0x60000000)
        self.assertEqual(dol.read(thirty, 4), bytes.fromhex("42704270"))
        self.assertEqual(len(report.warnings), 1)  # data-section write

    def test_gecko_rejects_runtime_codes(self):
        with self.assertRaises(patches.PatchError):
            patches.parse_gecko("C2004000 00000002\n38600001 60000000\n60000000 00000000\n")

    def test_write_outside_dol_is_refused(self):
        patch = patches.parse_gecko("04500000 00000001\n")
        with self.assertRaises(patches.PatchError):
            patches.apply(Dol(self.image), [patch], "RBIEE9")

    def test_repository_patches_parse(self):
        root = Path(__file__).resolve().parents[1] / "patches"
        for patch in patches.discover(root):
            self.assertTrue(patch.name)


class FpsScanTests(unittest.TestCase):
    def test_finds_double_wait_and_compare(self):
        image, labels, data = synthetic.build()
        names = {labels["VIWaitForRetrace"]: "VIWaitForRetrace", labels["VIGetRetraceCount"]: "VIGetRetraceCount"}
        result = fps_scan.scan(Dol(image), names, sorted(labels.values()))
        kinds = {f.kind for f in result.findings}
        self.assertIn("double-retrace-wait", kinds)
        self.assertIn("retrace-count-compare", kinds)
        self.assertIn(data["thirty"], [c.address for c in result.constants])
        json.dumps(result.to_json())
        self.assertIn("VIWaitForRetrace", fps_scan.format_report(result, names))


class DiscTests(unittest.TestCase):
    def header(self, game_id=b"RBIEE9"):
        raw = bytearray(0x100)
        raw[0:6] = game_id
        raw[7] = 1
        raw[0x18:0x1C] = struct.pack(">I", disc.WII_MAGIC)
        raw[0x20:0x20 + 27] = b"Harvest Moon: Animal Parade"
        return bytes(raw)

    def test_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.iso").write_bytes(self.header() + bytes(0x1000))
            wbfs = bytearray(b"WBFS" + bytes(4) + bytes([9]) + bytes(0x1F7)) + self.header()
            (tmp / "a.wbfs").write_bytes(bytes(wbfs))
            (tmp / "a.rvz").write_bytes(b"RVZ\x01" + bytes(0x54) + self.header())
            (tmp / "a.ciso").write_bytes(b"CISO" + bytes(0x7FFC) + self.header())
            for name in ("a.iso", "a.wbfs", "a.rvz", "a.ciso"):
                with self.subTest(name=name):
                    info = disc.identify(tmp / name)
                    self.assertEqual(info.game_id, "RBIEE9")
                    self.assertEqual(info.release.region, "NTSC-U")
                    self.assertTrue(info.is_wii)

    def test_not_a_disc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.iso"
            path.write_bytes(bytes(0x200))
            with self.assertRaises(ValueError):
                disc.identify(path)


class DspTests(unittest.TestCase):
    def test_dump_lookup_and_scan(self):
        ucode = struct.pack(">" + "HH" * 8, *([0x029F, 0x0010] * 7 + [0x02FF, 0x0000])) + bytes(range(256)) * 31
        ucode = ucode[:0x2000]
        image = synthetic.dolmod.build([(0x80004000, b"\x4e\x80\x00\x20" * 8, True),
                                        (0x80300000, bytes(64) + ucode, False)], entry=0x80004000)
        dol = Dol(image)
        found = dsp_finder.from_dump(dol, ucode)
        self.assertIsNotNone(found)
        self.assertEqual(found.checksum, dsp_finder.checksum(ucode))
        self.assertIn(found.dol_offset, [c.dol_offset for c in dsp_finder.scan(dol)])


if __name__ == "__main__":
    unittest.main()


class RealWorldVariantTests(unittest.TestCase):
    """Cases seen on the real RBIEE9 disc: setjmp buffer layout, no setjmp, two panic look-alikes."""

    def _dol(self, functions, data=b""):
        code, labels = [], {}
        for name, words in functions:
            labels[name] = synthetic.TEXT + 4 * len(code)
            code += words + [0, 0]
        text = b"".join(struct.pack(">I", w) for w in code)
        sections = [(synthetic.TEXT, text, True)]
        if data:
            sections.append((synthetic.DATA, data, False))
        return Dol(synthetic.dolmod.build(sections, entry=synthetic.TEXT)), labels

    def test_setjmp_with_reserved_word(self):
        p = ppc
        setjmp = [p.enc_mflr(5), p.enc_mfcr(6), p.enc_stw(5, 0, 3), p.enc_stw(6, 4, 3), p.enc_stw(1, 8, 3),
                  p.enc_stw(2, 12, 3), p.enc_stmw(13, 0x14, 3), p.enc_li(3, 0), p.BLR]
        longjmp = [p.enc_lwz(5, 0, 3), p.enc_lwz(6, 4, 3), p.enc_mtlr(5), p.enc_mtcrf(255, 6),
                   p.enc_lmw(13, 0x14, 3), p.enc_mr(3, 4), p.BLR]
        dol, labels = self._dol([("entry", [p.BLR]), ("save", synthetic.save_context()), ("setjmp", setjmp), ("longjmp", longjmp)])
        results = sdk_finder.find_all(dol, sorted(labels.values()), ["setjmp", "longjmp", "OSSaveContext"])
        self.assertEqual(results["setjmp"].address, labels["setjmp"])
        self.assertEqual(results["longjmp"].address, labels["longjmp"])
        self.assertEqual(results["OSSaveContext"].address, labels["save"])

    def test_game_without_setjmp(self):
        dol, labels = self._dol([("entry", [ppc.BLR]), ("save", synthetic.save_context()), ("load", synthetic.load_context()),
                                 ("fiber", synthetic.switch_fiber()), ("real", synthetic.real_mode())])
        manual = Path(tempfile.mkdtemp()) / "manual.csv"
        manual.write_text("address,name\n0x%08x,OSPanic\n0x%08x,OSSelectThread\n" % (labels["entry"], labels["entry"] + 4))
        hle = ["OSRealModeCall", "OSPanic", "OSLoadContext", "OSSwitchFiber", "longjmp"]
        result = analyze.analyse(dol, [], None, manual, hle)
        self.assertEqual(result.missing, [])
        self.assertEqual(result.absent, ["setjmp", "longjmp"])
        self.assertNotIn("longjmp", result.replacements)
        self.assertNotIn("setjmp", result.sdk)

    def test_ospanic_tie_break_by_callers(self):
        data = bytearray(64) + synthetic.PANIC_STRING
        string = synthetic.DATA + 64
        dol0, labels0 = self._dol([("entry", [ppc.BLR]), ("panic", synthetic.panic(string)), ("lookalike", synthetic.panic(string))], bytes(data))
        functions = [("entry", [ppc.BLR]), ("panic", synthetic.panic(string)), ("lookalike", synthetic.panic(string))]
        # three callers of `panic`, one of `lookalike`; addresses are known from the layout above
        cursor = synthetic.TEXT + 4 * sum(len(w) + 2 for _, w in functions)
        for i, target in enumerate(["panic", "panic", "panic", "lookalike"]):
            functions.append((f"c{i}", [ppc.enc_bl(cursor, labels0[target]), ppc.BLR]))
            cursor += 4 * 4
        dol, labels = self._dol(functions, bytes(data))
        result = sdk_finder.find_os_panic(sdk_finder.Code(dol, sorted(labels.values())))
        self.assertEqual(result.address, labels["panic"])
        self.assertEqual([m.address for m in result.alternatives], [labels["lookalike"]])


class SettingsIniTests(unittest.TestCase):
    def test_set_values_keeps_other_entries(self):
        from hmaptool import project
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.ini"
            path.write_text("[video]\nscale=1\nfullscreen=0\n\n[input]\nnunchuk=1\n")
            project.set_ini_values(path, {"video.scale": "2", "audio.mute": "0"})
            text = path.read_text()
            self.assertIn("scale=2", text)
            self.assertNotIn("scale=1", text)
            self.assertIn("fullscreen=0", text)
            self.assertIn("nunchuk=1", text)
            self.assertIn("[audio]\nmute=0", text)

    def test_creates_missing_file(self):
        from hmaptool import project
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "settings.ini"
            project.set_ini_values(path, {"video.scale": "2"})
            self.assertEqual(path.read_text(), "[video]\nscale=2\n")
