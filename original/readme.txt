PocketNES Menu Maker version 1.2a
 by Titney/MrUnown titney@pocketheaven.com http://www.pocketnes.org
 2003-03-10

DISCLAIMER:
 This software is provided as is, no guarantees. Use at your own risk.

UPDATES:
 1.2a
 Variable comments are displayed
 Database updated with more variables
 Mapper list updated to PocketNES v9

FEATURES:
- GUI (Graphical User Interface)
- Creates a complete PocketNES menu file for flashing
- Works with zipped roms
- Alphabetizes and numbers the menu
- Manual sorting of the menu
- Finds the correct names of the games from a database
- Check for bad and incompatible roms
- Marks small games for link play
- Assigns sprite follow variables from database using checksums (filenames don't matter.)
- Manually edit names and vars for each rom
- Cleans up the menu list, removes the "junk", (U) [a1] etc, from the names.
- Pads the the file to the nearest power of 2 size for multibooting on the 128mbit flash card.
- Adds splash screen.

BASIC USAGE:
- Unzip program and included files to a directory
- Put pocketnes.gba and a bunch of nes roms/zips in that same directory
- Open pnesmmw.exe
- Press "Make Rom" button to create menu rom
- Flash PocketNESMenu.gba

GUI EXPLAINED:
Rom List:
- Info
Lists the roms with original file names and any additional info, such as variables
  bad dump info, etc
These are the codes used:
 [inc] = incompatible, uses a mapper that PocketNES doesn't support
 [ovr] = overdump, overdumped rom, might work ok but takes up unecessary space
 [bad] = bad dump, a bad corrupt rom, might not work correctly, remove/replace if possible
 [ex] = excluded, a rom that's been selected for exclusion in rom info
 [unk] = unknown, a rom thats not known to the database
- Menu
 Lists the menu exactly as it would look on the GBA, with numbering, clean names, etc
 Any excluded roms will be displayed as a white space, this will of course not be visible
  on the actual GBA.
- Up and Down arrows
 Select a rom and use the buttons to move it up and down the list.
 Changes in rom order are not saved when the program is closed or the list refreshed.
Rom Info:
 Any changes made in the rom info will be saved even after you close the program.
 Check expert mode in the options to disable the OK alert after changes.
- Rom Name
 By default taken from the vars list, edit to change.
 The name under the editable name is from the database (if enabled.)
- Exclude Rom
 When checked the rom will not be included in the menu
- Enable PPP Hack (1)
 Turn on speed hack, makes some roms run faster/better
- Disable CPU Hack (2)
 This hack is turned on by default but some roms run better with it off
- Enable PAL Timing (4)
 This enables a hack for PAL, European (E) roms, not working 100%
- Follow Memory (32)
 By default sprite following uses sprite number value, so to use those
  (16 in the old vars format) just enter the number in the Sprite Value box.
 To follow a memory value (32 in the old format) check the Follow Memory (32) checkbox
  and enter the value in the box which is now named Memory Value.
Output File Info:
- Total Roms
 The total number of Roms included in the menu
- Total Size
 The total size of the menu rom including splash screen and padding if enabled
 Check "Show sizes in megabytes" in Options if you want mbyte instead of mbit.
Buttons:
- Make Rom
 Compiles the actual menu rom for flashing, default filename is PocketNESMenu.gba
- Refresh
 Refreshes the rom list from the directory in options.
 Re-alphabetizes if you changed rom names or moved roms.
- .. (Browse)
 Change the rom directory
- Options
 Opens to Options window to change paths and options
- Help
 Opens window with quick help and info about the program. Click view Read Me to see this file.
- Exit
 Shuts the program down

OPTIONS:
Options:
- Number Roms
  Turn on for numbered menu: 1. Arkanoid 2. Balloon Fight etc.
- Mark Small Roms
  Games under 192k will be marked by a * in the menu. (for single cart link play)
- Look Up Database Name
  Use names from the database in the menu.
  That is, even if your rom file is named "smb.nes" it will be "Super Mario Bros" in the menu.
- Clean Rom Names
  Clean up the list, removes the "junk" from the GoodNES filenames;
  ie: "Legend of Zelda, The (PRG 0) (U)" becomes "Legend of Zelda" in the menu.
- Use Variables List
  Assign variables for sprite following.
  Extracts variables from the vars list and adds them to the menu.
  Uses checksums to find vars so filenames doesn't matter.
- Pad Rom Size
  The size of the file is padded to the nearest power of 2 size for multibooting on the turbo
  flash cards. For the pro cards or newer padding is not necessary.
- Use Splash Screen
  Adds the splash screen image defined in paths to the menu.
- Show Sizes in Mbyte
  Will show the Output File Info size in Mbytes instead of Mbits.
Custom Names/Variables:
- Clear
 This deletes ALL the changes you have done to rom names and variables.
 Note that the main database will not be affected by this.
Paths:
 If you unzip this program to the same directory where you keep your roms you don't
 need to change any paths.
 To browse for the file/path just click the little button with ".." next to each path.
- Rom Path
  This is the path to a directory with the .nes roms (or zipped nes roms) you want to include
- PocketNES Rom
  The path and filename of the original pocketnes.gba emulator rom
- Output Rom File
  Path and filename to the final pocketnes menu rom
- Variables List
  Path and filename of the main database of names and vars.
  By default in the same directory with the program,
  get latest update from http://nes.pocketheaven.com
- Splash File
  Path and filename of splash screen file

ADVANCED:
- Change mappers by editing the pnesmmw.ini
 At the bottom of the pnesmmw.ini file is the list of mappers that PocketNES supports.
 You can remove the # in front of the longer flubba list if you use that hack (make sure only
 ONE list of mappers is in use though).
 For newer (or older) versions you can add or remove mapper numbers as you wish, just make sure
 the line ends in |
 The list is only used for compatibility checking, so it's not really crucial to update it.
- Rename ini and db to keep several sets of roms
 If you want to keep several sets of roms with their own custom db you can rename the ini and
 custom db. Just edit one set you want to keep, then exit the program and change pnesmmw.ini
 to pnesmmw_set1.ini or similar and pnesmmw.cdb to pnesmmw_set1.cdb. Then you can open the
 program again, and change anything that you want and those earlier files will be untouched.
 When you want to use them again simply name them back to the earlier names.

MAIN DATABASE:
If you for some reason should want to edit the main database, here's some info on it.
It is much easier, and recommended, to just use the custom database.
Quick FAQ on Vars List and how to enter values into the vars list
  crc|name|romflags|autoscrollvalue
crc = crc32 of the rom (you shouldn't need this at all)
name = full goodnes name of rom (modify this if you dont like the goodnes names and want 
  a differnt name to display (though its easier to rename your roms and turn off name look up)
romflags = enable/disable cpu hacks/paltiming/autoscroll settings
autoscrollvalue = sprite number / memroy location to follow
  how to set up rom flags?
simple just work out which options you want and look up the values in the table
then just add them all up and enter as the romflag value
  PPU hack        = 1 for on   0 for off
  CPU hack        = 2 for off  0 for on (on by default)
  PAL timing      = 4 for on   0 for off
  Following       = 32 for mem 0 for sprite *
the old value 16 for following sprites is no longer needed / used to use sprite following you 
  just enable (auto) on unscalled mode in emu and set bit 5 to 0 (ie dont add 32) 
next enter any sprite number / memory adress to follow in the autoscrollvalue

HISTORY:
1.1
Completely reworked GUI
Visible rom list/menu list
See filename/size/bad dumps/incompatible mappers in rom list
Edit individual roms names and variables
Exclude roms from the menu
Save rom name/variable changes from the GUI
Move roms up and down the list
Change options from GUI
Tooltips in GUI
Database updated to GoodNES 1.1
1.0
Windows GUI (Graphical User Interface)
Source is no longer open
List menu without creating rom
0.9b (unreleased)
Optional paths
added a few minor bug fixes
added total rom size report
added report for "possible unsupported mappers" (mapper list based on those listed in pnes 
source - other games/mappers may work though)
0.8b
added new vars list format and new option to look up rom name from a database (based on goodnes)
(it now finds vars regardless of filenames)
updated vars to match new pnes v8 version (no more sram vars)
added reports for bad roms and stuff
0.7b
Support for zipped roms (you need to have only one file in each zip for it to work)
0.6b
Added optional marking of roms smaller than 190k
Variables list is now a separate file from the compatibility list
0.51b
Fixed bug with SRAM variables and games listed without variables
0.5b
Complete rewrite in C, partly based on prototype maker by loopy
Updated menu building for v7A
Only includes .nes files if they have actual nes header
Outputs info about roms and variables added at the prompt since a menu.txt isn't created
The ini file is now optional as the default filenames and options are hardcoded
0.4b (unreleased)
Added optional numbering of the menu.
0.3b
Fixed stupid bug not identifying .nes extention if it wasn't lowercase.
0.2b
now pads file to correct power of 2 size for multibooting
added check for pocketnes.gba source file
cleaned up check for ini file

THANKS:
SkyBaby, able, Cowering's GoodNES database

CONTACT:
For bugs, improvements, comments, suggestions, anything, contact me via e-mail or on the
message board at http://nes.pocketheaven.com
