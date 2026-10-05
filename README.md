# pnesmmw

An updated, cross platform version of **PocketNES Menu Maker** (originally v1.2a by Titney/Mr Unown, 2003). It builds a PocketNES compilation ROM: the `pocketnes.gba` emulator, an optional splash screen and a menu of NES games, ready to flash to a GBA flash cart.

The 2003 program was a closed-source Windows binary. This version is a rewrite in Python with the same features, the same `pnesmmw.ini` settings and the same `pnesmmw.mdb` database. It runs natively on Linux, and on Windows it is packaged as a normal `.exe`. The original program and its readme are kept in [`original/`](original/) for reference.

## Getting it

**Windows.** Download `pnesmmw-windows` from the latest run of the [Build workflow](../../actions/workflows/build.yml), or `pnesmmw-windows.zip` from Releases, and unzip it to a folder. `pnesmmw.exe` is the graphical program and `pnesmmw-cli.exe` is the command-line version. No Python install is needed. To build the exe yourself, install Python 3 from python.org and run `build_windows.bat`.

**Linux.** You need Python 3.8 or newer with Tk (`sudo apt install python3-tk` on Debian/Ubuntu, `sudo dnf install python3-tkinter` on Fedora, `sudo pacman -S tk` on Arch). Then run `./pnesmmw.py` from the folder. Nothing else needs installing, because the program only uses the Python standard library. Without Tk the command-line mode still works. macOS works the same way.

## Basic usage

Put `pocketnes.gba` and your `.nes` roms (or zipped roms) in the program folder. Start the program, press **Make Rom**, then flash the resulting `PocketNESMenu.gba`. To keep roms somewhere else, press the `..` button next to Refresh or set the paths under **Options**.

Select a rom in the Rom List to see its mapper, size, region and CRC in the Rom Info panel. You can rename it, exclude it or set its PocketNES flags and sprite-follow value there. **Apply** saves the change to the custom database (`pnesmmw.cdb`), so it is kept between sessions. **Reset** drops it. The arrow buttons change the menu order for the current build, and **Refresh** re-alphabetizes. The **Menu** view shows the list exactly as it will appear on the GBA.

Codes in the rom list:

| Code | Meaning |
|---|---|
| `[inc]` | Incompatible: the mapper is not supported by current PocketNES (the list can be changed with `mappers=` in `pnesmmw.ini`) |
| `[ovr]` | Overdump: the file is bigger than its header says (trimmed automatically) |
| `[bad]` | Bad dump: the file is truncated, or the database marks it `[b]` |
| `[ex]` | Excluded from the menu |
| `[unk]` | Unknown: not found in the database by CRC |

## Command line

The same engine runs without a GUI, which is handy for scripts or headless machines. On Windows use `pnesmmw-cli.exe` in place of `pnesmmw.py`.

```
pnesmmw.py list                         show roms, menu names, flags and total size
pnesmmw.py build                        build the menu rom with the saved settings
pnesmmw.py build -r ~/roms/nes -o menu.gba --set number=1 --set padsize=1
pnesmmw.py build -s splash.bmp --set usesplash=1 --save
pnesmmw.py --ini set2.ini build         use a different settings file (and set2.cdb)
```

`--set option=0|1` changes any option for one run. `--save` writes the given options and paths back to the ini file.

## Options

Options and paths are kept in `pnesmmw.ini` next to the program. The file isn't shipped: the defaults below are used until you change something in the Options window (or use `--save`), which creates it. An ini from the 1.2a program also works.

| ini key | Option | Default |
|---|---|---|
| `number` | Number the menu (`1. Arkanoid`, `2. Balloon Fight`) | off |
| `showsmall` | Mark roms under 192 KB with `*` (single cart link play) | off |
| `lookupname` | Use the database name instead of the file name | on |
| `cleanlist` | Remove `(U)`, `[!]`, `[a1]` and similar markers from names | on |
| `usevars` | Use sprite follow and hack variables from the database | on |
| `padsize` | Pad the rom to a power of 2 size (turbo flash carts) | off |
| `usesplash` | Add a splash screen | off |
| `usembyte` | Show sizes in Mbyte instead of Mbit | off |
| `expert` | Skip confirmation prompts | off |
| `showsize` | Show file sizes in the rom list | off |
| `trimoverdump` | Cut overdumped roms down to the size in their header (new) | on |
| `fixheader` | Clean garbage such as `DiskDude!` from iNES headers (new) | on |
| `autopal` | Turn on PAL timing for European roms with no database vars (new) | off |

Paths in the ini can be relative to the program folder, and an empty `rompath` means the program folder. If a path from an old ini doesn't exist on this machine, the default file in the program folder is used. This covers Windows `C:\` paths on Linux and Wine `Z:\` paths.

## What changed from 1.2a

The program now runs natively on Linux and macOS as well as Windows, and it adds a command-line mode. The supported mapper list is updated to current PocketNES (Dwedit's builds): 5, 10, 30, 40, 42, 64, 74, 77, 85, 88, 118, 119, 140, 158, 163, 178, 184, 187, 206, 218, 245, 249, 252 and 254 are added. The PocketNES v9 list is still in the ini as a comment.

The flag value `16` in the database meant "follow sprite" for old PocketNES versions. Current PocketNES uses bit 16 for Dendy timing, so the database's legacy `16` is no longer passed through. Otherwise many games would wrongly start in Dendy mode. The Rom Info panel can still set the new 50 fps (8) and Dendy (16) flags by hand.

Overdumps are trimmed and dirty iNES headers are cleaned by default. Both save space and avoid wrong mapper detection. Zips holding several `.nes` files add all of them. The splash screen can be a 240x160 `.bmp` (8, 24 or 32 bit) as well as a raw GBA bitmap. The program warns when the output exceeds 256 Mbit, or when the selected `pocketnes.gba` already contains roms (that is, a menu rom was picked by mistake). Hex follow values (`0x4A0` or `$4A0`) are accepted in the Rom Info panel.

The custom database is now a plain text file (`crc|name|flags|follow|exclude`). Custom settings made in the old 1.2a program aren't carried over.

## Rom format

For anyone writing their own tools, each game in the output is a 48-byte header followed by the iNES file:

| Offset | Size | Field |
|---|---|---|
| 0 | 32 | Menu name, NUL terminated (31 characters max) |
| 32 | 4 | Size of the iNES data that follows, including its 16-byte header |
| 36 | 4 | Flags: 1 PPU hack, 2 disable CPU hack, 4 PAL, 8 50 fps, 16 Dendy, 32 follow memory |
| 40 | 4 | Sprite number or memory address to follow |
| 44 | 4 | Reserved (0) |

All values are little endian. The entries come straight after `pocketnes.gba`, or after the 76800-byte splash screen when one is used. PocketNES detects the splash screen by the missing `NES\x1a` signature.

## Tests

```
python3 -m unittest discover -s tests
```

The tests build menu roms from synthetic roms and read them back the way PocketNES does. GitHub Actions runs them on every push and then builds the Windows and Linux packages. Pushing a `v*` tag publishes a release.

## Credits

The original PocketNES Menu Maker is by Titney/Mr Unown. The database of names and variables was compiled by Titney and Mr Unown from Cowering's GoodNES database, with sprite-follow contributions from the PocketNES community. PocketNES is by loopy, FluBBa and Dwedit.
