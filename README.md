# Timetable Automation System (TAS)

A suite of Jython scripts for [JMRI](https://www.jmri.org/) that runs a model railway to a timetable. It is not a separate program: it runs inside JMRI and uses JMRI's Dispatcher, fast clock, Memories and panels.

It integrates a spreadsheet-created timetable, optional automatic running of trains through JMRI's Dispatcher, period public information displays and signallers' displays, optional randomised delays and cancellations, a Time Warp clock feature, and an optional day/night lighting cycle with weather.

Requires JMRI 5.16 or later. You need a layout that already works with JMRI's Dispatcher. For automatic running of trains, the layout must also work with JMRI's Auto Active Trains, and you need one or more JMRI Train Info files (Dispatcher > New Train > Save Train Info).

## Links

- Download (latest release): https://github.com/jamespetts/Timetable-Automation-System/releases
- Source code: https://github.com/jamespetts/Timetable-Automation-System
- Licence: GPL version 3, see [TAS/Licence.txt](TAS/Licence.txt) and https://www.gnu.org/licenses/
- Support: ask on the [JMRI users group](https://groups.io/g/jmriusers) with the `#timetableautomationsystem` tag
- JMRI: https://www.jmri.org/

## Installation

1. Download the latest release zip (see the download link above).
2. Unzip it. You will see a single `TAS` folder containing `.py` files and subfolders (`tashelp/`, `config/`, `Example timetables/`, `workings/`).
3. Find your JMRI profile's `jython` folder. In JMRI, open Help > Locations, open the profile location, then open the `jython` folder inside it. It looks like `.../JMRI/<YourProfileName>.jmri/jython`.
4. Copy the `TAS` folder into that `jython` folder, so that you have `.../jython/TAS/TimetableAutomation.py`.
5. Important: do not copy it into the JMRI program folder (for example `C:\Program Files (x86)\JMRI\jython`). That folder holds JMRI's built-in example scripts and is normally unwritable. If TAS files end up in both places, TAS will warn you: keep the profile copy and delete the other.
6. In JMRI, go to Scripting > Run Script and run `TimetableAutomation.py` from the `TAS` folder in step 4. The TAS main menu appears.
7. On first run, TAS checks the JMRI scripts directory (the `scripts:` location). If it is still the unwritable default, TAS asks to change it to your `TAS` folder. Click OK, then restart JMRI as instructed.
8. If TAS is not in your JMRI Start Up list, it shows a reminder explaining how to add it (Preferences > Start Up > Add > Run script > select `TimetableAutomation.py`), so that it starts automatically with JMRI. You can mute that reminder.
9. If you are updating from a version before 1.5, where the TAS files sat directly in the `jython` folder, TAS detects the old files on startup and offers to move them into the `TAS` folder and update your Start Up entries automatically. Your timetable files, working scripts and settings are kept.

TAS is installed per JMRI profile: repeat steps 3-4 for each profile that should use it.

## Updating

1. Download the new release zip.
2. Delete the existing `TAS` folder from the profile `jython` folder first, then copy in the new `TAS` folder. Overwriting in place risks mixing old and new files, which causes errors. Your timetable files, working scripts (`TAS/workings/`) and settings (stored in JMRI Memories) are kept, but take a backup of the `jython` folder before updating.
3. Restart JMRI and run `TAS/TimetableAutomation.py` again.

## First steps after installing

1. Create a timetable as a tab-separated `.csv` spreadsheet file (see Help > Timetable in the main menu). `Example timetables/` contains working examples to copy.
2. In the main menu, click Setup and follow the setup wizard. It configures the timetable, workings, displays and the background scripts.
3. Press Help in the main menu for the full documentation of every feature.

## Features

- Timetable: created in a spreadsheet and saved as tab-separated `.csv`. Supports Arr, Dep and Trigger times in 12h or 24h format, seven day-of-week columns, reporting numbers (for example `1A01`), Forms for stock diagrams, Directions, platforms, origins, destinations, calling patterns, and timing points for realistic delay reporting. Several timetables can be kept and switched between, for example one per modelled era.
- Automatic running: starts trains through JMRI's Dispatcher at timetable times. Chooses suitable available trains and transits from your lists, forms departures from the stock of arrivals, waits for delayed stock, tracks train locations and orientations (RailCom assistance optional), shows reporting numbers in Layout Editor block values, and retries workings whose trains are not ready yet via enqueued workings.
- Time Warp: advances the fast clock to the next due working at the press of a button, so quiet periods pass while running stays at real speed otherwise. Works with a paused clock to run a sequence on a manually operated layout.
- Public information displays: recreations of real departure boards (CRT, large board, Solari, fingerboard, LED and more) driven by the timetable, the clock and disruption status. Configured under Setup > Display configuration.
- Signallers' displays: including a TRUST/TRJA style display and a station working book that highlights the current working and can guide operators on a manually operated layout.
- Disruption (optional): independently enabled delays/early running and cancellations, tuned per disruption group. With timing points defined, delays are reported only as trains pass them, as on the real railway.
- Day/night cycle and weather (optional): drives layout and building lighting from DCC motor decoders with configurable climate and sunrise/sunset presets, dynamic cloud cover and weather forecast displays, plus dawn/dusk street light groups.
- Fast clock handling: can resume at the saved clock time and day of week after a restart.
- Optional extras: DCC track power on at start-up and off at close-down, occupancy sensor flicker monitor, RailCom train detection setup, and orientation tracking.

## Support and bug reports

When reporting a problem on the JMRI users group (see the support link above), include your JMRI version, operating system, TAS version (About in the main menu), what you were doing, and the text from the JMRI system console (the `[TAS]` lines in particular).

## Licence

GPL version 3 (see the licence links above). The full licence text is also shown under About in the main menu.
