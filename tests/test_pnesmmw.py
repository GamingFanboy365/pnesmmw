"""Tests for pnesmmw.py using synthetic NES roms.

Run with:  python3 -m unittest discover -s tests
"""

import binascii
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pnesmmw  # noqa: E402

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def make_nes(prg_banks=2, chr_banks=1, mapper=0, fill=0x11, extra=b"", trainer=False,
             tail=b"\0\0\0\0\0\0\0\0\0"):
    flags6 = ((mapper & 0x0F) << 4) | (4 if trainer else 0)
    header = b"NES\x1a" + bytes([prg_banks, chr_banks, flags6, mapper & 0xF0]) + tail[:8]
    header = header.ljust(16, b"\0")
    body = (b"\0" * 512 if trainer else b"") + bytes([fill]) * (prg_banks * 16384 + chr_banks * 8192)
    return header + body + extra


def parse_menu(data, splash=False):
    """Walk a menu rom the way PocketNES does (main.c / rommenu.c)."""
    nes_id = struct.unpack("<I", b"NES\x1a")[0]

    def find_nes_header(pos):
        for i in range(64):
            p = pos + i * 4
            if p + 4 <= len(data) and struct.unpack_from("<I", data, p)[0] == nes_id:
                return p - 48
        return None

    textstart = data.index(b"PNESEMU-END") + len(b"PNESEMU-END") + 1  # see make_emu
    if find_nes_header(textstart) is None:
        assert splash
        textstart += 76800
    roms = []
    p = find_nes_header(textstart)
    while p is not None and struct.unpack_from("<I", data, p + 48)[0] == nes_id:
        name = data[p:p + 32].split(b"\0")[0].decode("latin-1")
        size, flags, follow, reserved = struct.unpack_from("<IIII", data, p + 32)
        roms.append((name, size, flags, follow, data[p + 48:p + 48 + size]))
        p = find_nes_header(p + size + 48)
    return roms


OLD_INI = """# PocketNES Menu Maker ini
# lines starting with # are comments ignored by program

# 1 to use numbering of the menu
number=1

# 1 to use names in database for menu
lookupname=1

# path to roms
rompath=Z:\\nonexistent\\pnesmmw12a\\
# filenames to use
pocketnes=Z:\\nonexistent\\pnesmmw12a\\pocketnes.gba
romfile=Z:\\nonexistent\\pnesmmw12a\\PocketNESMenu.gba
varsfile=Z:\\nonexistent\\pnesmmw12a\\pnesmmw.mdb
splashfile=Z:\\nonexistent\\pnesmmw12a\\splash.raw

# Mappers to support
mappers=0|1|2|3|4|7|9|11|15|16|17|18|19|21|22|23|24|25|26|32|33|34|65|66|67|68|69|70|71|72|73|75|76|78|79|80|86|87|92|93|94|97|99|105|151|152|180|228|232|
"""


def make_emu():
    # fake emulator binary, 4 byte aligned
    return b"\x2e\0\0\xea" + b"\0" * 200 + b"PNESEMU-END" + b"\0"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.romdir = os.path.join(self.dir, "roms")
        os.mkdir(self.romdir)
        with open(os.path.join(self.dir, "pocketnes.gba"), "wb") as f:
            f.write(make_emu())
        self.ini = os.path.join(self.dir, "pnesmmw.ini")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, name, data):
        with open(os.path.join(self.romdir, name), "wb") as f:
            f.write(data)

    def write_db(self, lines):
        path = os.path.join(self.dir, "pnesmmw.mdb")
        with open(path, "w", newline="\r\n") as f:
            f.write("PocketNES - test db\n\n- Sprite following Variables\n\n")
            f.write("\n".join(lines) + "\n")
        return path

    def settings(self, **opts):
        s = pnesmmw.Settings(self.ini)
        s.base = self.dir
        s.set_path("rompath", self.romdir)
        s.opts.update(opts)
        return s

    def build(self, **opts):
        project = pnesmmw.Project(self.settings(**opts))
        project.refresh()
        path, size, warnings = project.build()
        with open(path, "rb") as f:
            return project, f.read(), warnings


class TestBuild(Base):
    def test_basic_menu(self):
        a = make_nes(fill=0xAA)
        b = make_nes(prg_banks=8, chr_banks=0, mapper=2, fill=0xBB)
        self.write("Zelda.nes", a)
        self.write("Arkanoid.nes", b)
        project, data, warnings = self.build()
        roms = parse_menu(data)
        self.assertEqual([r[0] for r in roms], ["Arkanoid", "Zelda"])
        self.assertEqual(roms[0][4], b)
        self.assertEqual(roms[1][4], a)
        self.assertEqual(roms[1][1], len(a))
        self.assertEqual(len(data), project.total_size())
        self.assertEqual(warnings, [])

    def test_database_names_vars_and_flags(self):
        rom = make_nes(fill=0x42)
        crc = binascii.crc32(rom[16:]) & 0xFFFFFFFF
        self.write_db(["%08x|Legend of Zelda, The (PRG 0) (U)|16|12 (sprite follow (x)" % crc])
        self.write("zelda.nes", rom)
        _, data, _ = self.build()
        name, size, flags, follow, _ = parse_menu(data)[0]
        self.assertEqual(name, "Legend of Zelda")
        self.assertEqual(flags, 0)      # legacy 16 stripped (it means Dendy now)
        self.assertEqual(follow, 12)

        _, data, _ = self.build(cleanlist=0)
        self.assertEqual(parse_menu(data)[0][0], "Legend of Zelda, The (PRG 0)")  # 29 chars max
        _, data, _ = self.build(lookupname=0)
        self.assertEqual(parse_menu(data)[0][0], "zelda")
        _, data, _ = self.build(usevars=0)
        self.assertEqual(parse_menu(data)[0][2:4], (0, 0))

    def test_memory_follow(self):
        rom = make_nes(fill=0x43)
        crc = binascii.crc32(rom[16:]) & 0xFFFFFFFF
        self.write_db(["%08x|Game (E)|33|1120 (comment|with pipe" % crc])
        self.write("game.nes", rom)
        _, data, _ = self.build()
        self.assertEqual(parse_menu(data)[0][2:4], (33, 1120))

    def test_numbering_small_and_truncation(self):
        self.write("A Very Long Name That Does Not Fit In The Menu.nes", make_nes(fill=1))
        self.write("Big.nes", make_nes(prg_banks=16, chr_banks=16, fill=2))
        _, data, _ = self.build(number=1, showsmall=1)
        names = [r[0] for r in parse_menu(data)]
        # PocketNES draws 29 characters, so the marker must fit in those
        self.assertEqual(names[0], "1. A Very Long Name That Do *")
        self.assertEqual(names[1], "2. Big")
        self.assertTrue(all(len(n) <= 29 for n in names))

    def test_accented_file_names(self):
        self.write("Pok\u00e9mon Caf\u00e9.nes", make_nes(fill=3))
        _, data, _ = self.build(lookupname=0)
        self.assertEqual(parse_menu(data)[0][0], "Pokemon Cafe")

    def test_zip_and_bad_files(self):
        rom = make_nes(fill=0x55)
        with zipfile.ZipFile(os.path.join(self.romdir, "Zipped (U).zip"), "w") as z:
            z.writestr("Zipped (U).nes", rom)
        self.write("junk.nes", b"not a rom")
        project, data, _ = self.build()
        roms = parse_menu(data)
        self.assertEqual([(r[0], r[4]) for r in roms], [("Zipped", rom)])
        self.assertEqual([p[0] for p in project.problems], ["junk.nes"])

    def test_overdump_trim_and_dirty_header(self):
        rom = make_nes(fill=0x66, mapper=4, extra=b"\x99" * 1000, tail=b"DiskDude!")
        self.write("over.nes", rom)
        project, data, _ = self.build()
        entry = project.entries[0]
        self.assertTrue(entry.rom.overdump)
        self.assertTrue(entry.rom.dirty)
        self.assertEqual(entry.rom.mapper, 4)
        self.assertIn("[ovr]", entry.codes())
        out = parse_menu(data)[0][4]
        self.assertEqual(len(out), len(rom) - 1000)
        self.assertEqual(out[7:16], b"\0" * 9)

        _, data, _ = self.build(trimoverdump=0, fixheader=0)
        out = parse_menu(data)[0][4]
        self.assertEqual(out, rom)

    def test_bad_and_incompatible(self):
        self.write("bad.nes", make_nes(fill=1)[:-100])
        self.write("inc.nes", make_nes(fill=2, mapper=6))
        project, data, warnings = self.build()
        codes = dict((e.rom.display, e.codes()) for e in project.entries)
        self.assertIn("[bad]", codes["bad.nes"])
        self.assertIn("[inc]", codes["inc.nes"])
        self.assertEqual(len(warnings), 1)
        # rom sizes stay 4-byte aligned so PocketNES finds the next header
        self.assertEqual(len(parse_menu(data)), 2)

    def test_splash_and_padding(self):
        with open(os.path.join(self.dir, "splash.raw"), "wb") as f:
            f.write(b"\x1f\x00" * (240 * 160))
        self.write("a.nes", make_nes())
        project, data, _ = self.build(usesplash=1, padsize=1)
        self.assertEqual(len(data), 256 * 1024)
        self.assertEqual(len(data), project.total_size())
        self.assertEqual(len(parse_menu(data, splash=True)), 1)
        emu = make_emu()
        self.assertEqual(data[len(emu):len(emu) + 4], b"\x1f\x00\x1f\x00")

    def test_bmp_splash(self):
        # 24 bit bottom-up BMP, solid red
        stride = 240 * 3
        pixels = b"\x00\x00\xff" * 240 * 160
        hdr = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        dib = struct.pack("<IiiHHIIiiII", 40, 240, 160, 1, 24, 0, len(pixels), 0, 0, 0, 0)
        raw = pnesmmw.bmp_to_gba(hdr + dib + pixels)
        self.assertEqual(len(raw), pnesmmw.SPLASH_SIZE)
        self.assertEqual(raw[:2], struct.pack("<H", 0x1f))
        self.assertEqual(stride % 4, 0)

    def test_custom_db_and_exclude(self):
        self.write("a.nes", make_nes(fill=1))
        self.write("b.nes", make_nes(fill=2))
        project = pnesmmw.Project(self.settings())
        project.refresh()
        a, b = project.entries
        project.set_custom(a, "Renamed", pnesmmw.FLAG_PALTIMING | pnesmmw.FLAG_PPUHACK, 7, False)
        project.set_custom(b, "", 0, 0, True)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "pnesmmw.cdb")))

        project, data, _ = self.build()
        roms = parse_menu(data)
        self.assertEqual([(r[0], r[2], r[3]) for r in roms], [("Renamed", 5, 7)])

        project.clear_custom()
        project.refresh()
        self.assertEqual(len(project.included()), 2)

    def test_manual_order(self):
        for n in ("a", "b", "c"):
            self.write(n + ".nes", make_nes(fill=ord(n)))
        project = pnesmmw.Project(self.settings())
        project.refresh()
        e = project.entries
        e[0], e[2] = e[2], e[0]
        project.build()
        with open(project.settings.resolve("romfile"), "rb") as f:
            names = [r[0] for r in parse_menu(f.read())]
        self.assertEqual(names, ["c", "b", "a"])

    def test_warns_when_pocketnes_is_a_menu_rom(self):
        self.write("a.nes", make_nes())
        _, data, _ = self.build()
        with open(os.path.join(self.dir, "pocketnes.gba"), "wb") as f:
            f.write(data)
        _, _, warnings = self.build()
        self.assertTrue(any("already contains" in w for w in warnings))

    def test_no_warning_for_signature_constant_in_emulator(self):
        # some PocketNES builds have "NES\x1a" in a literal pool
        with open(os.path.join(self.dir, "pocketnes.gba"), "wb") as f:
            f.write(make_emu()[:100] + b"\0" * 48 + b"NES\x1a\x4e\x45\x53" + make_emu()[100:])
        self.write("a.nes", make_nes())
        _, _, warnings = self.build()
        self.assertEqual(warnings, [])

    def test_no_pocketnes(self):
        os.remove(os.path.join(self.dir, "pocketnes.gba"))
        self.write("a.nes", make_nes())
        project = pnesmmw.Project(self.settings())
        project.refresh()
        with self.assertRaises(pnesmmw.BuildError):
            project.build()


class TestSettings(Base):
    def test_old_ini_with_wine_paths(self):
        # an ini written by pnesmmw 1.2a running under Wine
        with open(self.ini, "w", newline="\r\n") as f:
            f.write(OLD_INI)
        s = pnesmmw.Settings(self.ini)
        s.base = self.dir
        self.assertEqual(s.opts["number"], 1)
        self.assertIn(105, s.mappers)
        # the Z:\ paths don't exist here, so defaults in the program dir are used
        self.assertEqual(s.resolve("pocketnes"), os.path.join(self.dir, "pocketnes.gba"))
        self.assertEqual(s.resolve("rompath"), os.path.normpath(self.dir))

    def test_default_mappers_match_fork(self):
        s = pnesmmw.Settings(self.ini)
        for m in (28, 38, 41, 89, 113, 146, 185, 225):
            self.assertIn(m, s.mappers)

    def test_save_roundtrip(self):
        s = self.settings(number=1, padsize=1)
        s.mappers = [0, 1, 2]
        s.save()
        t = pnesmmw.Settings(self.ini)
        t.base = self.dir
        self.assertEqual(t.opts["number"], 1)
        self.assertEqual(t.opts["padsize"], 1)
        self.assertEqual(t.mappers, [0, 1, 2])
        self.assertEqual(t.paths["rompath"], "roms")
        self.assertEqual(t.resolve("rompath"), self.romdir)


class TestRealDatabase(unittest.TestCase):
    def test_load_shipped_mdb(self):
        db = pnesmmw.load_main_db(os.path.join(REPO, "pnesmmw.mdb"))
        self.assertGreater(len(db), 8000)
        e = db[0x171251e3]
        self.assertEqual((e.name, e.flags, e.follow), ("1942 (JU)", 16, 12))
        e = db[0xd3bff72e]  # value followed by a comment containing '|'
        self.assertEqual((e.flags, e.follow), (16, 12))

    def test_menu_names_are_ascii(self):
        self.assertEqual(pnesmmw.to_ascii("Pok\u00e9mon Caf\u00e9"), "Pokemon Cafe")
        self.assertEqual(pnesmmw.to_ascii("Mickey\u2019s \u2013 Zoo"), "Mickey's - Zoo")
        self.assertEqual(pnesmmw.to_ascii("\u65e5\u672c"), "??")

    def test_clean_names(self):
        self.assertEqual(pnesmmw.clean_name("Legend of Zelda, The (PRG 0) (U)"), "Legend of Zelda")
        self.assertEqual(pnesmmw.clean_name("Super Mario Bros. (W) [!]"), "Super Mario Bros.")
        self.assertEqual(pnesmmw.clean_name("1942 (JU) [o1]"), "1942")
        self.assertEqual(pnesmmw.clean_name("Tetris_USA_(Rev_A)"), "Tetris USA")


if __name__ == "__main__":
    unittest.main()
