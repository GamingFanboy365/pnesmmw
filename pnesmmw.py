#!/usr/bin/env python3
"""PocketNES Menu Maker (pnesmmw) - Python edition.

A cross platform rewrite of Titney/Mr Unown's PocketNES Menu Maker v1.2a.
Builds a PocketNES compilation ROM (pocketnes.gba + splash + NES roms) that
can be flashed to a GBA flash cart.

Runs with a Tk GUI by default, or from the command line:

    pnesmmw.py                 start the GUI
    pnesmmw.py list            print the rom list / menu
    pnesmmw.py build           build the menu rom without the GUI

Only the Python standard library is used (tkinter is needed for the GUI).
"""

import argparse
import binascii
import io
import os
import re
import struct
import sys
import zipfile

VERSION = "2.0"
TITLE = "PocketNES Menu Maker v" + VERSION

INES_MAGIC = b"NES\x1a"
ROMHEADER_SIZE = 48          # name[32], filesize, flags, spritefollow, reserved
NAME_SIZE = 32               # includes the terminating NUL
SPLASH_SIZE = 240 * 160 * 2  # raw 15-bit BGR, 240x160
SMALL_ROM_LIMIT = 192 * 1024
GBA_MAX_SIZE = 32 * 1024 * 1024

# PocketNES emuflags (see equates.h in the PocketNES source)
FLAG_PPUHACK = 1     # use $2002 hack
FLAG_NOCPUHACK = 2   # don't use JMP hack
FLAG_PALTIMING = 4   # PAL timing
FLAG_FPS50 = 8       # 50 fps (newer PocketNES)
FLAG_DENDY = 16      # Dendy timing (newer PocketNES). Old databases used
                     # 16 to mean "follow sprite", see LEGACY_SPRITE_FLAG
FLAG_FOLLOWMEM = 32  # follow memory address instead of sprite number
LEGACY_SPRITE_FLAG = 16

# Mappers supported by current PocketNES (Dwedit's builds, cart.s mappertbl)
MAPPERS_CURRENT = [
    0, 1, 2, 3, 4, 5, 7, 9, 10, 11, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25,
    26, 30, 32, 33, 34, 40, 42, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74,
    75, 76, 77, 78, 79, 80, 85, 86, 87, 88, 92, 93, 94, 97, 99, 105, 118, 119,
    140, 151, 152, 158, 163, 178, 180, 184, 187, 206, 218, 228, 232, 245, 249,
    252, 254,
]
# Mappers supported by PocketNES v9 (the list shipped with pnesmmw 1.2a)
MAPPERS_V9 = [
    0, 1, 2, 3, 4, 7, 9, 11, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 32,
    33, 34, 65, 66, 67, 68, 69, 70, 71, 72, 73, 75, 76, 78, 79, 80, 86, 87,
    92, 93, 94, 97, 99, 105, 151, 152, 180, 228, 232,
]

COUNTRY_CODES = [
    ("(JUE)", "World"), ("(JU)", "Japan/USA"), ("(UE)", "USA/Europe"),
    ("(JE)", "Japan/Europe"), ("(W)", "World"), ("(U)", "USA"),
    ("(E)", "Europe"), ("(J)", "Japan"), ("(G)", "Germany"),
    ("(F)", "France"), ("(S)", "Spain"), ("(I)", "Italy"), ("(Sw)", "Sweden"),
    ("(C)", "China"), ("(K)", "Korea"), ("(A)", "Australia"),
    ("(As)", "Asia"), ("(Ca)", "Canada"), ("(R)", "Russia"),
    ("(PC10)", "PlayChoice-10"), ("(VS)", "Vs. System"), ("(Unl)", "Unlicensed"),
]

PAL_CODES = ("(E)", "(UE)", "(JE)", "(G)", "(F)", "(S)", "(I)", "(Sw)",
             "(A)", "(R)")

INI_OPTIONS = [
    # key, default, comment
    ("number", 0, "1 to use numbering of the menu"),
    ("showsmall", 0, "1 to mark multibootable roms <192k in the menu"),
    ("lookupname", 1, "1 to use names in database for menu"),
    ("cleanlist", 1, "1 to clean out the ( and [ stuff from GoodNES roms"),
    ("usevars", 1, "1 to use variables from list"),
    ("padsize", 0, "1 to pad file to power of 2 size for multibooting"),
    ("usesplash", 0, "1 to use splash screen"),
    ("usembyte", 0, "1 to use megabyte for sizes"),
    ("expert", 0, "1 to use expert mode"),
    ("showsize", 0, "1 to show sizes in filelist"),
    ("trimoverdump", 1, "1 to cut overdumped roms down to their real size"),
    ("fixheader", 1, "1 to clean garbage (DiskDude! etc) from iNES headers"),
    ("autopal", 0, "1 to enable PAL timing for European roms without vars"),
]

INI_PATHS = [
    # key, default file name ("" = program directory)
    ("rompath", ""),
    ("pocketnes", "pocketnes.gba"),
    ("romfile", "PocketNESMenu.gba"),
    ("varsfile", "pnesmmw.mdb"),
    ("splashfile", "splash.raw"),
]


def program_dir():
    """Directory the program lives in (works for PyInstaller builds too)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def fmt_size(size, mbyte):
    if mbyte:
        return "%.2f mbyte" % (size / (1024.0 * 1024.0))
    return "%.2f mbit" % (size * 8 / (1024.0 * 1024.0))


# --------------------------------------------------------------------------
# Settings (pnesmmw.ini)
# --------------------------------------------------------------------------

class Settings(object):
    def __init__(self, ini_path=None):
        self.base = program_dir()
        self.ini_path = ini_path or os.path.join(self.base, "pnesmmw.ini")
        self.opts = dict((k, d) for k, d, _ in INI_OPTIONS)
        self.paths = dict((k, d) for k, d in INI_PATHS)
        self.mappers = list(MAPPERS_CURRENT)
        self.load()

    @property
    def cdb_path(self):
        root, _ = os.path.splitext(self.ini_path)
        return root + ".cdb"

    def load(self):
        if not os.path.isfile(self.ini_path):
            return
        with open(self.ini_path, "r", encoding="latin-1") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip().lower(), value.strip()
                if key in self.opts:
                    try:
                        self.opts[key] = 1 if int(value) else 0
                    except ValueError:
                        pass
                elif key in self.paths:
                    self.paths[key] = value
                elif key == "mappers":
                    nums = [int(m) for m in value.split("|") if m.strip().isdigit()]
                    if nums:
                        self.mappers = nums

    def save(self):
        out = ["# PocketNES Menu Maker ini",
               "# lines starting with # are comments ignored by program",
               "# relative paths are relative to the program directory", ""]
        for key, _, comment in INI_OPTIONS:
            out += ["# " + comment, "%s=%d" % (key, self.opts[key]), ""]
        out.append("# path to roms (empty = program directory)")
        out.append("rompath=" + self.paths["rompath"])
        out.append("# filenames to use")
        for key, _ in INI_PATHS[1:]:
            out.append("%s=%s" % (key, self.paths[key]))
        out += ["", "# Mappers to support (only used for the compatibility check)",
                "# mappers for PocketNES v9 (flubba)",
                "#mappers=" + "|".join(str(m) for m in MAPPERS_V9) + "|",
                "# mappers for current PocketNES (Dwedit)",
                "mappers=" + "|".join(str(m) for m in self.mappers) + "|", ""]
        with open(self.ini_path, "w", encoding="latin-1", newline="\r\n") as f:
            f.write("\n".join(out))

    def resolve(self, key):
        """Absolute path for a path setting.

        Paths that don't exist (for example Windows paths in an ini copied to
        Linux, or Wine Z:\\ paths) fall back to the default name in the
        program directory, the same place pnesmmw 1.2a looked by default.
        """
        value = self.paths.get(key, "")
        default = dict(INI_PATHS)[key]
        path = None
        if value:
            path = value
            if re.match(r"^[A-Za-z]:[\\/]", value) and os.sep == "/":
                # Windows path on Linux: only Wine's Z: drive maps to /
                path = value[2:].replace("\\", "/") if value[0] in "zZ" else None
            elif not os.path.isabs(value):
                path = os.path.join(self.base, value)
        if path:
            if os.path.exists(path):
                return os.path.normpath(path)
            if key == "romfile" and os.path.isdir(os.path.dirname(path) or "."):
                return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.base, default))

    def set_path(self, key, path):
        """Store a path, relative to the program directory when possible."""
        path = os.path.abspath(path)
        try:
            rel = os.path.relpath(path, self.base)
        except ValueError:  # different drive on Windows
            rel = path
        if not rel.startswith(".."):
            path = "" if rel == "." else rel
        self.paths[key] = path


# --------------------------------------------------------------------------
# Databases
# --------------------------------------------------------------------------

class DbEntry(object):
    __slots__ = ("crc", "name", "flags", "follow", "comment", "exclude")

    def __init__(self, crc, name, flags=0, follow=0, comment="", exclude=False):
        self.crc = crc
        self.name = name
        self.flags = flags
        self.follow = follow
        self.comment = comment
        self.exclude = exclude


def _parse_int(text):
    text = text.strip()
    m = re.match(r"^(0x[0-9a-fA-F]+|\$[0-9a-fA-F]+|\d+)", text)
    if not m:
        return 0, text
    num = m.group(1)
    rest = text[len(num):].strip()
    if num.startswith("0x"):
        return int(num, 16), rest
    if num.startswith("$"):
        return int(num[1:], 16), rest
    return int(num), rest


def load_main_db(path):
    """Load the main database: crc|name|romflags|followvalue (comment"""
    db = {}
    if not path or not os.path.isfile(path):
        return db
    with open(path, "r", encoding="latin-1") as f:
        for line in f:
            line = line.rstrip("\r\n")
            m = re.match(r"^([0-9a-fA-F]{8})\|", line)
            if not m:
                continue
            fields = line.split("|")
            crc = int(fields[0], 16)
            name = fields[1].strip()
            flags, follow, comment = 0, 0, ""
            if len(fields) > 2 and fields[2].strip():
                flags, _ = _parse_int(fields[2])
            if len(fields) > 3:
                # the value may be followed by a free text comment, which can
                # itself contain '|' characters
                follow, comment = _parse_int("|".join(fields[3:]))
                comment = comment.lstrip("(").strip()
            if crc not in db:
                db[crc] = DbEntry(crc, name, flags, follow, comment)
    return db


def load_custom_db(path):
    """Custom database: crc|name|flags|followvalue|exclude"""
    db = {}
    if not path or not os.path.isfile(path):
        return db
    with open(path, "r", encoding="latin-1") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not re.match(r"^[0-9a-fA-F]{8}\|", line):
                continue
            fields = (line.split("|") + ["", "", "", ""])[:5]
            crc = int(fields[0], 16)
            flags, _ = _parse_int(fields[2] or "0")
            follow, _ = _parse_int(fields[3] or "0")
            db[crc] = DbEntry(crc, fields[1], flags, follow,
                              exclude=fields[4].strip() == "1")
    return db


def save_custom_db(path, db):
    lines = ["# PNESMMW Custom DataBase",
             "# crc|menu name|flags|follow value|exclude"]
    for crc in sorted(db):
        e = db[crc]
        lines.append("%08x|%s|%d|%d|%d" % (crc, e.name.replace("|", "/"),
                                           e.flags, e.follow, 1 if e.exclude else 0))
    with open(path, "w", encoding="latin-1", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# NES roms
# --------------------------------------------------------------------------

def clean_name(name):
    """'Legend of Zelda, The (PRG 0) (U) [!]' -> 'Legend of Zelda'"""
    name = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r",\s*The$", "", name).strip()
    return name


def country_of(name):
    for code, country in COUNTRY_CODES:
        if code in name:
            return country
    return "Unknown"


class NesRom(object):
    """A NES rom found in the rom directory."""

    def __init__(self, filename, display, data):
        self.filename = filename      # file on disk
        self.display = display        # file (or zip/member) name for the list
        self.raw_size = len(data)
        self.error = None
        self.header = bytearray(data[:16])
        self.body = data[16:]
        self.mapper = 0
        self.prg = self.chr = 0
        self.trainer = False
        self.expected = 0
        self.dirty = False
        self.crc = 0
        self.crc_all = binascii.crc32(data) & 0xFFFFFFFF
        self.db = None        # main database entry
        self.custom = None    # custom database entry
        if data[:4] != INES_MAGIC:
            self.error = "no iNES header"
            return
        h = self.header
        self.prg = h[4] * 16384
        self.chr = h[5] * 8192
        self.trainer = bool(h[6] & 4)
        nes2 = (h[7] & 0x0C) == 0x08
        if not nes2 and any(h[12:16]):
            # garbage like "DiskDude!" in bytes 7-15, the mapper high nibble
            # can't be trusted (PocketNES would pick the wrong mapper)
            self.dirty = True
            self.mapper = h[6] >> 4
        else:
            self.mapper = (h[6] >> 4) | (h[7] & 0xF0)
            if nes2:
                self.mapper |= (h[8] & 0x0F) << 8
        self.expected = 16 + (512 if self.trainer else 0) + self.prg + self.chr
        real = self.body[:self.expected - 16] if self.raw_size > self.expected else self.body
        self.crc = binascii.crc32(real) & 0xFFFFFFFF

    @property
    def overdump(self):
        return self.error is None and self.raw_size > self.expected

    @property
    def underdump(self):
        return self.error is None and self.raw_size < self.expected

    def lookup(self, main_db, custom_db):
        for crc in (self.crc, self.crc_all):
            if self.db is None and crc in main_db:
                self.db = main_db[crc]
            if self.custom is None and crc in custom_db:
                self.custom = custom_db[crc]

    @property
    def key(self):
        """CRC used to store custom settings."""
        return self.db.crc if self.db else self.crc

    def output_data(self, settings):
        """iNES data as it goes into the menu rom."""
        header = bytearray(self.header)
        if self.dirty and settings.opts["fixheader"]:
            header[7:16] = b"\0" * 9
        body = self.body
        if self.overdump and settings.opts["trimoverdump"]:
            body = body[:self.expected - 16]
        data = bytes(header) + body
        if len(data) % 4:
            data += b"\0" * (4 - len(data) % 4)
        return data

    def output_size(self, settings):
        size = self.raw_size
        if self.overdump and settings.opts["trimoverdump"]:
            size = self.expected
        return (size + 3) & ~3


class MenuEntry(object):
    """A rom plus the settings used for it in the menu."""

    def __init__(self, rom, settings):
        self.rom = rom
        self.settings = settings

    @property
    def excluded(self):
        return bool(self.rom.custom and self.rom.custom.exclude)

    def base_name(self):
        rom, opts = self.rom, self.settings.opts
        if rom.custom and rom.custom.name:
            return rom.custom.name
        if opts["lookupname"] and rom.db:
            name = rom.db.name
        else:
            name = os.path.splitext(os.path.basename(rom.display))[0]
        if opts["cleanlist"]:
            name = clean_name(name) or name
        return name

    def vars(self):
        """(flags, follow) written to the rom header."""
        rom, opts = self.rom, self.settings.opts
        if rom.custom:
            return rom.custom.flags, rom.custom.follow
        flags = follow = 0
        if opts["usevars"] and rom.db:
            flags, follow = rom.db.flags, rom.db.follow
            # 16 was the old "follow sprite" flag; PocketNES now uses that
            # bit for Dendy timing, so it must not be passed through
            flags &= ~LEGACY_SPRITE_FLAG
        if opts["autopal"] and not flags & FLAG_PALTIMING:
            name = rom.db.name if rom.db else rom.display
            if any(code in name for code in PAL_CODES):
                flags |= FLAG_PALTIMING
        return flags, follow

    def menu_name(self, number):
        name = self.base_name()
        if self.settings.opts["number"]:
            name = "%d. %s" % (number, name)
        if self.settings.opts["showsmall"] and self.rom.output_size(self.settings) < SMALL_ROM_LIMIT:
            name = name[:NAME_SIZE - 3] + " *"
        return name[:NAME_SIZE - 1]

    def codes(self):
        rom, codes = self.rom, []
        if self.excluded:
            codes.append("[ex]")
        if rom.mapper not in self.settings.mappers:
            codes.append("[inc]")
        dbname = rom.db.name if rom.db else ""
        if rom.underdump or "[b" in dbname:
            codes.append("[bad]")
        if rom.overdump or "[o" in dbname:
            codes.append("[ovr]")
        if rom.db is None:
            codes.append("[unk]")
        return codes


def read_roms(rompath):
    """Find all NES roms (plain or zipped) in a directory.

    Returns (roms, problems) where problems is a list of (file, reason).
    """
    roms, problems = [], []
    try:
        names = sorted(os.listdir(rompath), key=lambda s: s.lower())
    except OSError as e:
        return roms, [(rompath, str(e))]
    for fn in names:
        path = os.path.join(rompath, fn)
        ext = os.path.splitext(fn)[1].lower()
        if not os.path.isfile(path) or ext not in (".nes", ".zip"):
            continue
        try:
            if ext == ".nes":
                with open(path, "rb") as f:
                    found = [(fn, f.read())]
            else:
                found = []
                with zipfile.ZipFile(path) as z:
                    members = [m for m in z.namelist()
                               if m.lower().endswith(".nes")]
                    for m in members:
                        disp = fn if len(members) == 1 else fn + "/" + os.path.basename(m)
                        found.append((disp, z.read(m)))
                if not found:
                    problems.append((fn, "no .nes file in zip"))
        except (OSError, zipfile.BadZipFile, RuntimeError) as e:
            problems.append((fn, str(e)))
            continue
        for disp, data in found:
            rom = NesRom(path, disp, data)
            if rom.error:
                problems.append((disp, rom.error))
            else:
                roms.append(rom)
    return roms, problems


# --------------------------------------------------------------------------
# Splash screen
# --------------------------------------------------------------------------

def load_splash(path):
    """Load a splash screen: raw 240x160 GBA bitmap or a 240x160 BMP."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"BM":
        return bmp_to_gba(data)
    if len(data) < SPLASH_SIZE:
        raise ValueError("splash file must be %d bytes (240x160 15-bit raw)" % SPLASH_SIZE)
    return data[:SPLASH_SIZE]


def bmp_to_gba(data):
    """Convert an uncompressed 240x160 BMP (8/24/32 bit) to GBA raw format."""
    offset, = struct.unpack_from("<I", data, 10)
    width, height, _, bpp, compression = struct.unpack_from("<iiHHI", data, 18)
    if width != 240 or abs(height) != 160:
        raise ValueError("splash BMP must be 240x160 pixels, not %dx%d" % (width, abs(height)))
    if compression not in (0, 3) or bpp not in (8, 24, 32):
        raise ValueError("splash BMP must be uncompressed 8, 24 or 32 bit")
    palette = []
    if bpp == 8:
        hdr_size, = struct.unpack_from("<I", data, 14)
        ncolors, = struct.unpack_from("<I", data, 46)
        pal_off = 14 + hdr_size
        for i in range(ncolors or 256):
            b, g, r = data[pal_off + i * 4: pal_off + i * 4 + 3]
            palette.append((r, g, b))
    stride = ((width * bpp + 31) // 32) * 4
    out = bytearray(SPLASH_SIZE)
    for y in range(160):
        src_y = 159 - y if height > 0 else y
        row = offset + src_y * stride
        for x in range(240):
            if bpp == 8:
                r, g, b = palette[data[row + x]]
            else:
                p = row + x * (bpp // 8)
                b, g, r = data[p], data[p + 1], data[p + 2]
            c = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
            struct.pack_into("<H", out, (y * 240 + x) * 2, c)
    return bytes(out)


# --------------------------------------------------------------------------
# Project: rom list + building
# --------------------------------------------------------------------------

class Project(object):
    def __init__(self, settings):
        self.settings = settings
        self.main_db = {}
        self.custom_db = {}
        self.entries = []
        self.problems = []

    def load_databases(self):
        self.main_db = load_main_db(self.settings.resolve("varsfile"))
        self.custom_db = load_custom_db(self.settings.cdb_path)

    def refresh(self):
        """Rescan the rom directory and sort the menu alphabetically."""
        self.load_databases()
        roms, self.problems = read_roms(self.settings.resolve("rompath"))
        self.entries = []
        for rom in roms:
            rom.lookup(self.main_db, self.custom_db)
            self.entries.append(MenuEntry(rom, self.settings))
        self.sort()

    def sort(self):
        self.entries.sort(key=lambda e: e.base_name().lower())

    def save_custom(self):
        save_custom_db(self.settings.cdb_path, self.custom_db)

    def set_custom(self, entry, name, flags, follow, exclude):
        rom = entry.rom
        e = DbEntry(rom.key, name, flags, follow, exclude=exclude)
        self.custom_db[rom.key] = e
        rom.custom = e
        self.save_custom()

    def clear_custom(self, entry=None):
        if entry is None:
            self.custom_db = {}
            for e in self.entries:
                e.rom.custom = None
        else:
            self.custom_db.pop(entry.rom.key, None)
            entry.rom.custom = None
        self.save_custom()

    def included(self):
        return [e for e in self.entries if not e.excluded]

    def menu(self):
        """[(entry, menu name)] in menu order."""
        return [(e, e.menu_name(i + 1)) for i, e in enumerate(self.included())]

    def total_size(self):
        s = self.settings
        size = 0
        pocketnes = s.resolve("pocketnes")
        if os.path.isfile(pocketnes):
            size += (os.path.getsize(pocketnes) + 3) & ~3
        if s.opts["usesplash"]:
            size += SPLASH_SIZE
        for e in self.included():
            size += ROMHEADER_SIZE + e.rom.output_size(s)
        if s.opts["padsize"]:
            size = padded_size(size)
        return size

    def build(self, progress=None):
        """Write the menu rom. Returns (output path, size, warnings)."""
        s = self.settings
        warnings = []
        pocketnes = s.resolve("pocketnes")
        if not os.path.isfile(pocketnes):
            raise BuildError("PocketNES rom not found: " + pocketnes)
        with open(pocketnes, "rb") as f:
            emu = f.read()
        pos = find_embedded_rom(emu)
        if pos is not None:
            warnings.append("%s already contains a NES rom at 0x%x; did you "
                            "select a menu rom instead of pocketnes.gba?"
                            % (os.path.basename(pocketnes), pos))
        out = io.BytesIO()
        out.write(emu)
        out.write(b"\0" * (-len(emu) % 4))
        if s.opts["usesplash"]:
            try:
                out.write(load_splash(s.resolve("splashfile")))
            except (OSError, ValueError) as e:
                raise BuildError("Splash screen: %s" % e)
        menu = self.menu()
        if not menu:
            raise BuildError("No roms to add to the menu")
        for i, (entry, name) in enumerate(menu):
            if progress:
                progress(i, len(menu), name)
            if entry.rom.mapper not in s.mappers:
                warnings.append("%s uses mapper %d which PocketNES may not support"
                                % (entry.rom.display, entry.rom.mapper))
            data = entry.rom.output_data(s)
            flags, follow = entry.vars()
            out.write(name.encode("latin-1", "replace")[:NAME_SIZE - 1]
                      .ljust(NAME_SIZE, b"\0"))
            out.write(struct.pack("<IIII", len(data), flags, follow, 0))
            out.write(data)
        if s.opts["padsize"]:
            out.write(b"\xff" * (padded_size(out.tell()) - out.tell()))
        size = out.tell()
        if size > GBA_MAX_SIZE:
            warnings.append("Rom is %s, larger than the 256 mbit GBA maximum"
                            % fmt_size(size, s.opts["usembyte"]))
        romfile = s.resolve("romfile")
        try:
            with open(romfile, "wb") as f:
                f.write(out.getvalue())
        except OSError as e:
            raise BuildError("Unable to write output file: %s" % e)
        if progress:
            progress(len(menu), len(menu), "Done")
        return romfile, size, warnings


def find_embedded_rom(data):
    """Offset of the first menu entry in data, or None.

    Some PocketNES builds contain the bytes "NES\x1a" as a constant, so a
    match only counts when it has a plausible 48 byte rom header in front.
    """
    for m in re.finditer(re.escape(INES_MAGIC), data):
        p = m.start()
        h = data[p:p + 16]
        if p < ROMHEADER_SIZE or len(h) < 16 or not h[4]:
            continue
        size, = struct.unpack_from("<I", data, p - 16)
        expected = 16 + (512 if h[6] & 4 else 0) + h[4] * 16384 + h[5] * 8192
        if expected <= size <= len(data) - p:
            return p - ROMHEADER_SIZE
    return None


class BuildError(Exception):
    pass


def padded_size(size):
    p = 256 * 1024
    while p < size:
        p *= 2
    return p


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def apply_cli_overrides(settings, args):
    for key in ("rompath", "pocketnes", "varsfile", "splashfile"):
        value = getattr(args, key, None)
        if value:
            settings.set_path(key, value)
    if getattr(args, "output", None):
        settings.set_path("romfile", args.output)
    for item in getattr(args, "set", None) or []:
        if "=" not in item:
            raise SystemExit("--set expects option=0|1, got %r" % item)
        key, value = item.split("=", 1)
        if key not in settings.opts:
            raise SystemExit("unknown option %r (choose from %s)"
                             % (key, ", ".join(settings.opts)))
        settings.opts[key] = 1 if value.strip() not in ("0", "", "off", "no") else 0


def cli_list(project):
    s = project.settings
    print("Rom path: " + s.resolve("rompath"))
    print("Database: %s (%d entries)" % (s.resolve("varsfile"), len(project.main_db)))
    print("")
    menu_names = dict((id(e), n) for e, n in project.menu())
    for e in project.entries:
        rom = e.rom
        flags, follow = e.vars()
        codes = " ".join(e.codes())
        print("%-40s %-28s map %-3d %5dKB flags %-2d follow %-5d %s" % (
            rom.display[:40], menu_names.get(id(e), "")[:28], rom.mapper,
            rom.output_size(s) // 1024, flags, follow, codes))
    for fn, why in project.problems:
        print("%-40s skipped: %s" % (fn[:40], why))
    print("")
    print("Total roms: %d   Total size: %s" % (
        len(project.included()), fmt_size(project.total_size(), s.opts["usembyte"])))


def cli_build(project):
    def progress(i, n, name):
        if i < n:
            print("  %3d/%d  %s" % (i + 1, n, name))
    try:
        path, size, warnings = project.build(progress)
    except BuildError as e:
        print("Error: %s" % e, file=sys.stderr)
        return 1
    for w in warnings:
        print("Warning: " + w, file=sys.stderr)
    print("Rom built: %s (%s, %d roms)" % (
        path, fmt_size(size, project.settings.opts["usembyte"]), len(project.included())))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pnesmmw", description=TITLE + " - builds PocketNES menu roms")
    parser.add_argument("--ini", help="settings file (default pnesmmw.ini next to the program)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="start the graphical interface (default)")
    for name, helptext in (("list", "show the rom list and menu"),
                           ("build", "build the menu rom")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("-r", "--rompath", help="directory with .nes/.zip roms")
        p.add_argument("-p", "--pocketnes", help="pocketnes.gba emulator rom")
        p.add_argument("-o", "--output", help="output menu rom")
        p.add_argument("-d", "--varsfile", help="main database (pnesmmw.mdb)")
        p.add_argument("-s", "--splashfile", help="splash screen (.raw or 240x160 .bmp)")
        p.add_argument("--set", action="append", metavar="OPTION=0|1",
                       help="change an option for this run, e.g. --set number=1 "
                            "(options: %s)" % ", ".join(k for k, _, _ in INI_OPTIONS))
        p.add_argument("--save", action="store_true",
                       help="save the paths/options given here to the ini file")
    args = parser.parse_args(argv)

    settings = Settings(os.path.abspath(args.ini) if args.ini else None)

    if args.command in ("list", "build"):
        apply_cli_overrides(settings, args)
        if args.save:
            settings.save()
        project = Project(settings)
        project.refresh()
        if args.command == "list":
            cli_list(project)
            return 0
        return cli_build(project)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is not available, so the GUI can't start.\n"
              "Install it (e.g. 'sudo apt install python3-tk') or use the "
              "command line:\n  pnesmmw.py list\n  pnesmmw.py build",
              file=sys.stderr)
        return 1
    return run_gui(settings)


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

def run_gui(settings):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    class OptionsDialog(tk.Toplevel):
        LABELS = [
            ("number", "Number roms", "Number menu: 1. Arkanoid 2. Balloon Fight"),
            ("showsmall", "Mark small roms", "Mark roms smaller than 192k (link play) with *"),
            ("lookupname", "Look up database name", "Look up rom names in database"),
            ("cleanlist", "Clean rom names", "Clean markers like (U) and [a1] from rom names"),
            ("usevars", "Use database variables", "Use sprite follow / hack variables from database"),
            ("padsize", "Pad rom size", "Pad rom to a power of 2 size for turbo flash carts"),
            ("usesplash", "Use splash screen", "Add the splash screen image"),
            ("usembyte", "Show sizes in Mbyte", "Show sizes in megabyte instead of megabits"),
            ("expert", "Expert mode", "Bypass confirmation prompts"),
            ("showsize", "Show file size in rom list", "Show file sizes in rom list"),
            ("trimoverdump", "Trim overdumps", "Cut overdumped roms down to their real size"),
            ("fixheader", "Fix dirty headers", "Clean garbage like 'DiskDude!' from iNES headers"),
            ("autopal", "Auto PAL timing", "Enable PAL timing for European roms without vars"),
        ]
        PATHS = [
            ("rompath", "Rom path", True, None),
            ("pocketnes", "PocketNES rom", False, ("PocketNES Rom", "*.gba")),
            ("romfile", "Output rom file", False, ("PocketNES Menu Rom", "*.gba")),
            ("varsfile", "Main database", False, ("Main Database", "*.mdb")),
            ("splashfile", "Splash file", False, ("Splash File", "*.raw *.bmp")),
        ]

        def __init__(self, app):
            tk.Toplevel.__init__(self, app.root)
            self.app = app
            self.title("Options")
            self.transient(app.root)
            self.resizable(True, False)
            s = app.settings
            self.vars = {}
            box = ttk.LabelFrame(self, text="Options")
            box.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
            for i, (key, label, tip) in enumerate(self.LABELS):
                v = tk.IntVar(value=s.opts[key])
                self.vars[key] = v
                cb = ttk.Checkbutton(box, text=label, variable=v)
                cb.grid(row=i % 7, column=i // 7, sticky="w", padx=6, pady=1)
                Tooltip(cb, tip)
            pbox = ttk.LabelFrame(self, text="Paths")
            pbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
            pbox.columnconfigure(1, weight=1)
            self.pathvars = {}
            for i, (key, label, isdir, ftype) in enumerate(self.PATHS):
                ttk.Label(pbox, text=label).grid(row=i, column=0, sticky="w", padx=4)
                v = tk.StringVar(value=s.resolve(key))
                self.pathvars[key] = v
                ttk.Entry(pbox, textvariable=v, width=60).grid(row=i, column=1, sticky="ew", pady=1)
                ttk.Button(pbox, text="..", width=3,
                           command=lambda k=key, d=isdir, t=ftype: self.browse(k, d, t)
                           ).grid(row=i, column=2, padx=4)
            cbox = ttk.LabelFrame(self, text="Custom names/variables")
            cbox.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
            ttk.Label(cbox, text=os.path.basename(s.cdb_path)).pack(side="left", padx=6)
            clr = ttk.Button(cbox, text="Clear", command=self.clear)
            clr.pack(side="left", padx=6, pady=4)
            Tooltip(clr, "Clear ALL entries in the custom database, this can not be undone")
            btns = ttk.Frame(self)
            btns.grid(row=3, column=0, sticky="e", padx=8, pady=8)
            ttk.Button(btns, text="OK", command=self.ok).pack(side="left", padx=4)
            ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)
            self.columnconfigure(0, weight=1)
            self.grab_set()

        def browse(self, key, isdir, ftype):
            cur = self.pathvars[key].get()
            if isdir:
                path = filedialog.askdirectory(parent=self, initialdir=cur or None)
            elif key == "romfile":
                path = filedialog.asksaveasfilename(
                    parent=self, initialfile=os.path.basename(cur),
                    initialdir=os.path.dirname(cur) or None,
                    filetypes=[ftype, ("All files", "*")], defaultextension=".gba")
            else:
                path = filedialog.askopenfilename(
                    parent=self, initialdir=os.path.dirname(cur) or None,
                    filetypes=[ftype, ("All files", "*")])
            if path:
                self.pathvars[key].set(os.path.normpath(path))

        def clear(self):
            if messagebox.askyesno("Warning!", "Delete all custom settings?\n\n"
                                   "This is permanent and can not be reversed.", parent=self):
                self.app.project.clear_custom()
                self.app.update_lists()

        def ok(self):
            s = self.app.settings
            for key, v in self.vars.items():
                s.opts[key] = v.get()
            for key, v in self.pathvars.items():
                if v.get().strip():
                    s.set_path(key, v.get().strip())
            try:
                s.save()
            except OSError as e:
                messagebox.showerror("Error!", "Unable to save INI file:\n%s" % e, parent=self)
            self.destroy()
            self.app.refresh()

    class Tooltip(object):
        def __init__(self, widget, text):
            self.widget, self.text, self.tip = widget, text, None
            widget.bind("<Enter>", self.show, add="+")
            widget.bind("<Leave>", self.hide, add="+")

        def show(self, _event=None):
            if self.tip or not self.text:
                return
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry("+%d+%d" % (x, y))
            tk.Label(self.tip, text=self.text, background="#ffffe0", relief="solid",
                     borderwidth=1, padx=4, pady=2).pack()

        def hide(self, _event=None):
            if self.tip:
                self.tip.destroy()
                self.tip = None

    class App(object):
        def __init__(self, root, settings):
            self.root = root
            self.settings = settings
            self.project = Project(settings)
            self.selected = None
            root.title(TITLE)
            root.minsize(760, 480)
            root.geometry("980x600")
            self.build_ui()
            root.after(10, self.refresh)

        # ---- layout ----
        def build_ui(self):
            root = self.root
            root.columnconfigure(0, weight=1)
            root.rowconfigure(0, weight=1)

            left = ttk.LabelFrame(root, text="Rom List")
            left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=6)
            left.columnconfigure(0, weight=1)
            left.rowconfigure(1, weight=1)
            self.view = tk.StringVar(value="info")
            vb = ttk.Frame(left)
            vb.grid(row=0, column=0, columnspan=2, sticky="w")
            r1 = ttk.Radiobutton(vb, text="Info", value="info", variable=self.view,
                                 command=self.update_lists)
            r2 = ttk.Radiobutton(vb, text="Menu", value="menu", variable=self.view,
                                 command=self.update_lists)
            r1.pack(side="left", padx=4)
            r2.pack(side="left", padx=4)
            Tooltip(r1, "Show files and detailed info")
            Tooltip(r2, "Show menu as it would look on GBA")

            self.tree = ttk.Treeview(left, show="headings", selectmode="browse")
            self.tree.grid(row=1, column=0, sticky="nsew")
            sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
            sb.grid(row=1, column=1, sticky="ns")
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.bind("<<TreeviewSelect>>", self.on_select)
            self.tree.tag_configure("excluded", foreground="#909090")
            self.tree.tag_configure("problem", foreground="#c00000")

            mv = ttk.Frame(left)
            mv.grid(row=1, column=2, sticky="ns", padx=4)
            up = ttk.Button(mv, text="\u25b2", width=3, command=lambda: self.move(-1))
            dn = ttk.Button(mv, text="\u25bc", width=3, command=lambda: self.move(1))
            up.pack(pady=(40, 4))
            dn.pack()
            Tooltip(up, "Move rom up")
            Tooltip(dn, "Move rom down")

            right = ttk.Frame(root)
            right.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=6)

            info = ttk.LabelFrame(right, text="Rom Info")
            info.pack(fill="x")
            info.columnconfigure(1, weight=1)
            ttk.Label(info, text="Name:").grid(row=0, column=0, sticky="w", padx=4)
            self.name_var = tk.StringVar()
            self.name_entry = ttk.Entry(info, textvariable=self.name_var, width=28)
            self.name_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
            self.dbname = ttk.Label(info, text="", foreground="#606060", wraplength=260)
            self.dbname.grid(row=1, column=0, columnspan=2, sticky="w", padx=4)
            self.details = ttk.Label(info, text="", justify="left")
            self.details.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=2)
            self.comment = ttk.Label(info, text="", foreground="#606060", wraplength=260,
                                     justify="left")
            self.comment.grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

            self.flagvars = {}
            checks = [
                ("exclude", "Exclude rom", "Exclude rom from menu"),
                (FLAG_PPUHACK, "Enable PPU hack (1)", "Enable PPU speed hack"),
                (FLAG_NOCPUHACK, "Disable CPU hack (2)", "Disable CPU hack"),
                (FLAG_PALTIMING, "Enable PAL timing (4)", "Enable PAL timing, good for (E) games"),
                (FLAG_FPS50, "50 fps (8)", "Run at 50 fps (newer PocketNES)"),
                (FLAG_DENDY, "Dendy timing (16)", "Dendy timing (newer PocketNES)"),
                (FLAG_FOLLOWMEM, "Follow memory (32)",
                 "Enable for memory following, disable for sprite number following"),
            ]
            for i, (key, label, tip) in enumerate(checks):
                v = tk.IntVar(value=0)
                self.flagvars[key] = v
                cb = ttk.Checkbutton(info, text=label, variable=v,
                                     command=self.update_follow_label)
                cb.grid(row=4 + i, column=0, columnspan=2, sticky="w", padx=4)
                Tooltip(cb, tip)
            fr = ttk.Frame(info)
            fr.grid(row=11, column=0, columnspan=2, sticky="w", padx=4, pady=2)
            self.follow_label = ttk.Label(fr, text="Sprite value", width=13)
            self.follow_label.pack(side="left")
            self.follow_var = tk.StringVar(value="0")
            ttk.Entry(fr, textvariable=self.follow_var, width=8).pack(side="left")
            bf = ttk.Frame(info)
            bf.grid(row=12, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
            ok = ttk.Button(bf, text="Apply", command=self.apply_info)
            ok.pack(side="left")
            rs = ttk.Button(bf, text="Reset", command=self.reset_info)
            rs.pack(side="left", padx=4)
            Tooltip(ok, "Save changes to the custom database")
            Tooltip(rs, "Remove custom settings for this rom")

            out = ttk.LabelFrame(right, text="Output File Info")
            out.pack(fill="x", pady=(6, 0))
            self.total_roms = ttk.Label(out, text="Total roms: 0")
            self.total_roms.pack(anchor="w", padx=4)
            self.total_size = ttk.Label(out, text="Total size: 0")
            self.total_size.pack(anchor="w", padx=4)
            self.progress = ttk.Progressbar(out, mode="determinate")
            self.progress.pack(fill="x", padx=4, pady=4)

            bar = ttk.Frame(root)
            bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
            buttons = [
                ("Make Rom", self.make_rom, "Build PocketNES menu rom"),
                ("Refresh", self.refresh, "Refresh rom list"),
                ("..", self.choose_rompath, "Change rom directory"),
                ("Options", lambda: OptionsDialog(self), "Change options and paths"),
                ("Help", self.help, "Help and about"),
                ("Exit", root.destroy, "Exit program"),
            ]
            for text, cmd, tip in buttons:
                b = ttk.Button(bar, text=text, command=cmd, width=3 if text == ".." else None)
                b.pack(side="left", padx=2)
                Tooltip(b, tip)
            self.status = ttk.Label(bar, text="")
            self.status.pack(side="right")
            # fixed width so a long path doesn't stretch the window
            self.rompath_label = ttk.Label(bar, text="", foreground="#606060", width=30)
            self.rompath_label.pack(side="left", padx=8, fill="x", expand=True)

        # ---- data ----
        def refresh(self):
            self.root.title(TITLE + " - Loading")
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            try:
                self.project.refresh()
            finally:
                self.root.config(cursor="")
                self.root.title(TITLE)
            s = self.settings
            self.rompath_label.config(text=s.resolve("rompath"))
            if not self.project.main_db and s.opts["lookupname"] | s.opts["usevars"]:
                self.status.config(text="Main database not found")
            elif not self.project.entries:
                self.status.config(text="No roms found in rom path")
            else:
                self.status.config(text="%d roms, %d skipped" % (
                    len(self.project.entries), len(self.project.problems)))
            self.selected = None
            self.update_lists()
            self.show_info(None)

        def update_lists(self):
            tree, s = self.tree, self.settings
            sel = self.selected
            tree.delete(*tree.get_children())
            if self.view.get() == "info":
                cols = ("file", "codes", "mapper", "vars")
                heads = ("File", "Info", "Mapper", "Vars")
                widths = (290, 110, 72, 70)
            else:
                cols = ("menu",)
                heads = ("Menu (as shown on the GBA)",)
                widths = (360,)
            tree.configure(columns=cols)
            for c, h, w in zip(cols, heads, widths):
                tree.heading(c, text=h, anchor="w")
                tree.column(c, width=w, stretch=(c in ("file", "menu")))
            names = dict((id(e), n) for e, n in self.project.menu())
            for i, e in enumerate(self.project.entries):
                tags = ()
                if e.excluded:
                    tags = ("excluded",)
                elif set(e.codes()) & {"[inc]", "[bad]"}:
                    tags = ("problem",)
                if self.view.get() == "info":
                    disp = e.rom.display
                    if s.opts["showsize"]:
                        disp = "[%dKB] %s" % (e.rom.raw_size // 1024, disp)
                    flags, follow = e.vars()
                    values = (disp, " ".join(e.codes()), e.rom.mapper,
                              "%d|%d" % (flags, follow) if flags or follow else "")
                else:
                    values = (names.get(id(e), ""),)
                tree.insert("", "end", iid=str(i), values=values, tags=tags)
            if sel is not None and sel < len(self.project.entries):
                tree.selection_set(str(sel))
                tree.see(str(sel))
            inc = self.project.included()
            self.total_roms.config(text="Total roms: %d" % len(inc))
            self.total_size.config(text="Total size: " + fmt_size(
                self.project.total_size(), s.opts["usembyte"]))

        def on_select(self, _event=None):
            sel = self.tree.selection()
            if not sel:
                return
            self.selected = int(sel[0])
            self.show_info(self.project.entries[self.selected])

        def show_info(self, entry):
            for v in self.flagvars.values():
                v.set(0)
            if entry is None:
                self.name_var.set("")
                self.dbname.config(text="")
                self.details.config(text="")
                self.comment.config(text="")
                self.follow_var.set("0")
                self.update_follow_label()
                return
            rom = entry.rom
            self.name_var.set(entry.base_name())
            self.dbname.config(text=rom.db.name if rom.db else "(not in database)")
            details = [
                "Mapper: %d%s" % (rom.mapper, "" if rom.mapper in self.settings.mappers
                                  else "  (unsupported)"),
                "Size: %dKB  (PRG %dKB, CHR %dKB%s)" % (
                    rom.raw_size // 1024, rom.prg // 1024, rom.chr // 1024,
                    ", trainer" if rom.trainer else ""),
                "Country: " + country_of(rom.db.name if rom.db else rom.display),
                "CRC32: %08x" % rom.crc,
            ]
            if rom.overdump:
                details.append("Overdump: %d bytes too big" % (rom.raw_size - rom.expected))
            if rom.underdump:
                details.append("Bad dump: %d bytes missing" % (rom.expected - rom.raw_size))
            if rom.dirty:
                details.append("Dirty iNES header")
            self.details.config(text="\n".join(details))
            self.comment.config(text=rom.db.comment if rom.db and rom.db.comment else "")
            flags, follow = entry.vars()
            for bit, v in self.flagvars.items():
                if bit != "exclude":
                    v.set(1 if flags & bit else 0)
            self.flagvars["exclude"].set(1 if entry.excluded else 0)
            self.follow_var.set(str(follow))
            self.update_follow_label()

        def update_follow_label(self):
            mem = self.flagvars[FLAG_FOLLOWMEM].get()
            self.follow_label.config(text="Memory value" if mem else "Sprite value")

        def current(self):
            if self.selected is None or self.selected >= len(self.project.entries):
                return None
            return self.project.entries[self.selected]

        def confirm(self, question):
            if self.settings.opts["expert"]:
                return True
            return messagebox.askyesno(TITLE, question, parent=self.root)

        def apply_info(self):
            entry = self.current()
            if entry is None:
                return
            try:
                follow, rest = _parse_int(self.follow_var.get())
                if rest:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error!", "The follow value must be a number "
                                     "(decimal, 0x.. or $.. for hex)", parent=self.root)
                return
            flags = 0
            for bit, v in self.flagvars.items():
                if bit != "exclude" and v.get():
                    flags |= bit
            name = self.name_var.get().strip()[:NAME_SIZE - 1]
            if not self.confirm("Do you want to save custom settings?"):
                return
            if name == entry.base_name() and not (entry.rom.custom and entry.rom.custom.name):
                name = ""
            self.project.set_custom(entry, name, flags, follow,
                                    bool(self.flagvars["exclude"].get()))
            self.update_lists()
            self.show_info(entry)

        def reset_info(self):
            entry = self.current()
            if entry is None or entry.rom.custom is None:
                return
            if not self.confirm("Do you want to delete custom settings for this rom?"):
                return
            self.project.clear_custom(entry)
            self.update_lists()
            self.show_info(entry)

        def move(self, delta):
            entry = self.current()
            if entry is None:
                return
            i, j = self.selected, self.selected + delta
            ents = self.project.entries
            if 0 <= j < len(ents):
                ents[i], ents[j] = ents[j], ents[i]
                self.selected = j
                self.update_lists()

        def choose_rompath(self):
            path = filedialog.askdirectory(parent=self.root,
                                           initialdir=self.settings.resolve("rompath"))
            if path:
                self.settings.set_path("rompath", path)
                try:
                    self.settings.save()
                except OSError:
                    pass
                self.refresh()

        def make_rom(self):
            def progress(i, n, name):
                self.progress["maximum"] = max(n, 1)
                self.progress["value"] = i
                self.root.title("%s - Building Rom - %s" % (TITLE, name))
                self.root.update()
            try:
                path, size, warnings = self.project.build(progress)
            except BuildError as e:
                messagebox.showerror("Error!", str(e), parent=self.root)
                return
            finally:
                self.root.title(TITLE)
            msg = "Rom built: %s\nSize: %s\nRoms: %d" % (
                path, fmt_size(size, self.settings.opts["usembyte"]),
                len(self.project.included()))
            if warnings:
                msg += "\n\nWarnings:\n" + "\n".join(warnings[:15])
                if len(warnings) > 15:
                    msg += "\n(%d more)" % (len(warnings) - 15)
            messagebox.showinfo("Done!", msg, parent=self.root)
            self.progress["value"] = 0

        def help(self):
            messagebox.showinfo("About pnesmmw", HELP_TEXT, parent=self.root)

    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root, settings)
    root.mainloop()
    return 0


HELP_TEXT = TITLE + """
Python edition, based on v1.2a by Titney/Mr Unown

Basic usage
Put pocketnes.gba and your .nes roms (or zips) in the program directory,
then press "Make Rom" and flash PocketNESMenu.gba.

Change rom name or variables: select the rom in the Rom List, edit the
fields in Rom Info and press Apply. Changes are kept in pnesmmw.cdb.
Change paths and options: press Options.

Rom list codes
[inc] incompatible mapper
[ovr] overdump
[bad] bad dump
[ex] excluded
[unk] unknown (not in the database)

The program can also be used from the command line, run
"pnesmmw --help" for details. See README.md for more."""


if __name__ == "__main__":
    sys.exit(main())
