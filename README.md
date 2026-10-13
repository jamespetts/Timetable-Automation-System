# Timetable Automation System (TAS)

A suite of Jython scripts for [JMRI](https://www.jmri.org/) that runs a model railway to a timetable, using JMRI's Dispatcher and fast clock for automation and timing. Automation is optional. Also included are timetable-integrated public information displays, signallers' displays, weather forecasts, and a day/night cycle that drives layout, building and street lighting from the time of day.

Trains run to the timetable; whenever no automatic trains are running, the Time warp button advances the clock to the next scheduled train.

Requires JMRI 5.16 or later. For automatic running of trains, the layout must also work with JMRI's Dispatcher using Auto Active Trains, and you need one or more JMRI Train Info files (Dispatcher > New Train > Save Train Info).

## Links

- Download (latest release): https://github.com/jamespetts/Timetable-Automation-System/releases
- Source code: https://github.com/jamespetts/Timetable-Automation-System
- Licence: GPL version 3, see [TAS/Licence.txt](TAS/Licence.txt) and https://www.gnu.org/licenses/
- Support: ask on the [JMRI users group](https://groups.io/g/jmriusers) with the `#timetableautomationsystem` tag
- JMRI: https://www.jmri.org/

## Installation

1. Download the `TAS.zip` asset from the latest release (see the download link above). Do not use the "Source code" zip: that contains the whole development project, not just TAS.
2. Unzip it. You will see a single `TAS` folder containing `.py` files and subfolders (`tashelp/`, `config/`, `Example timetables/`). A `workings/` subfolder is created later, when you first save a working script.
3. Find your JMRI profile's `jython` folder. In JMRI, open Help > Locations, open the profile location, then open the `jython` folder inside it. It looks like `.../JMRI/<YourProfileName>.jmri/jython`.
4. Copy the `TAS` folder into that `jython` folder, so that you have `.../jython/TAS/TimetableAutomation.py`.
5. Important: do not copy it into the JMRI program folder (for example `C:\Program Files (x86)\JMRI\jython`). That folder holds JMRI's built-in example scripts and is normally unwritable. If TAS files end up in both places, TAS will warn you: keep the profile copy and delete the other.
6. In JMRI, go to Scripting > Run Script and run `TimetableAutomation.py` from the `TAS` folder in step 4. The TAS main menu appears.
7. On first run, TAS checks the JMRI scripts directory (the `scripts:` location). If it is still the unwritable default, TAS asks to change it to your `TAS` folder. Click OK, then restart JMRI as instructed.
8. If TAS is not in your JMRI Start Up list, it shows a reminder explaining how to add it (Preferences > Start Up > Add > Run script > select `TimetableAutomation.py`), so that it starts automatically with JMRI. You can mute that reminder.
9. If you are updating from a version before 1.5, where the TAS files sat directly in the `jython` folder, TAS detects the old files on startup and offers to move them into the `TAS` folder and update your Start Up entries automatically. Your timetable files, working scripts and settings are kept.

TAS is installed per JMRI profile: repeat steps 3-4 for each profile that should use it. It can be configured differently for each profile.

## Updating from previous versions

You can ignore this section if this is a fresh install.

Updating is automatic:

1. Download the new release zip (the `TAS.zip` asset, not "Source code") and unzip it anywhere (for example Downloads).
2. In JMRI, run the new copy's `TimetableAutomation.py` (Scripting > Run Script). TAS detects that it is newer than your installed copy and offers "Update installed copy".
3. Click "Update installed copy". Your workings, configuration and settings are kept; replaced files are backed up under `_TAS-migration-backup/update` in the profile `jython` folder. Restart JMRI when prompted.

If the automatic update fails, or TAS does not work correctly afterwards, update manually instead: copy `TAS/workings/` somewhere safe, delete the old `TAS` folder from the profile `jython` folder, copy in the new one, then copy `workings` back. Your timetable files (in the profile `timetable` folder, outside `TAS`) and settings (stored in JMRI Memories) are not touched either way, but take a backup of the `jython` folder before updating.

## First steps after installing

1. Create a timetable as a tab-separated `.csv` spreadsheet file (see Help > Timetable in the main menu). Save it in your profile's `timetable` folder (`.../JMRI/<YourProfileName>.jmri/timetable/`): the timetable selector in Setup only accepts files in that folder. `Example timetables/` contains working examples to copy there.
2. In the main menu, click Setup and follow the setup wizard. It configures the timetable, workings, displays and the background scripts.
3. Press Help in the main menu for the full documentation of every feature.

## Features

- Timetable: a tab-separated `.csv` from a spreadsheet, with Arr/Dep/Trigger times (12h or 24h), per-day-of-week operation, reporting numbers, stock formations, directions, platforms, calling patterns and timing points. Keep several timetables and switch between them (for example one per era); a working timetable display shows the current one.
- Automatic running (optional): starts trains through JMRI's Dispatcher at timetable times, choosing suitable trains and transits, forming departures from arriving stock, waiting for delayed stock and retrying workings whose train is not ready. Working scripts are created in a wizard from your Train Info files and roster; no programming is needed.
- Time warp: one button skips the fast clock to the next due working; with a paused clock it steps a manually operated layout through the timetable.
- Public information displays: period departure boards (CRT, Solari, fingerboard, LED, lightbox, Network SouthEast clock and more) driven by the timetable, the clock and disruption state.
- Signallers' displays: a TRUST/TRJA-style train running display, a station working book that highlights the current working, and teleprinter or handwritten-notebook disruption messages.
- Disruption (optional): randomised delays, early running and cancellations, tunable per group; with timing points defined, delays are reported only as trains pass them.
- Day/night cycle and weather (optional): layout, building and street lighting follow configurable sunrise/sunset and climate presets, with dynamic cloud cover and period weather forecast displays.
- Fast clock: resumes at the saved time and day of week after a restart.
- Extras: DCC track power on at start-up and off at close-down, occupancy sensor flicker monitor, RailCom train detection setup, and train location and orientation tracking.

## Support and bug reports

When reporting a problem on the JMRI users group (see the support link above), include your JMRI version, operating system, TAS version (About in the main menu), what you were doing, and the text from the JMRI system console (the `[TAS]` lines in particular).

## Licence

GPL version 3 (see the licence links above). The full licence text is also shown under About in the main menu.
