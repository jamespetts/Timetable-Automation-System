Read when: Task concerns WTTDisplay.py, StationWorking.py, PID*.py displays, TRUST-TRJA.py, NSEClock.py, signaller displays, public displays, display discovery tags.

# Displays

Display scripts are of three groups: working timetable display, station working display, public information displays, signaller displays, clock display.

WTTDisplay.py defines a Working Timetable UI with class WTTCellRenderer, ZebraTable, WheelPager, VerticalLabel, VerticalHeaderRenderer. Function LoadServicesMaster(csv_path) returns a list of dicts with keys rep, arr, dep, origin, dest, plat, cls, load, trigger, tp, days, dir, note. WTTDisplay.py uses Memories WTT_PAGE_MODE, WTT_TIME_24H, WTT_TIME_SEPARATOR, WTT_ECS_LABEL, WTT_TIMING_LOAD_LABEL, WTT_REP_NO_LABEL, WTT_ECS_DEST_MATCH, WTT_DIRECTION_SPLIT, WTT_OD_HEADER_VERTICAL, WTT_TP_NAME_DOT_LEADERS, TASPAPERCOLOUR, TASWTTBANDLIGHT, TASWTTBANDDARK, TAS_FONT_FAMILY, CURRENTTIMETABLE.

StationWorking.py defines a station working display with tag <<SIG-DISP-NAME: Station working>>. Function LoadServicesMaster(csvPath) returns dicts with keys rep, dir, trigger, arr, dep, origin, dest, plat, notes, remarks, forms, calling, special, via, tp, days. StationWorking.py expands {calling pattern}, {notes}, {forms}, {special}, {via} in remarks. StationWorking.py listens to Memories CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE through addPropertyChangeListener.

PID pattern: each PID*.py file contains header comment tags <<PID-DISP-NAME: ...>>, <<DESCRIPTION: ...>>, <<SETTING DESCRIPTION NUMBER/BOOLEAN/STRING/COLOR: ...>>. TASSetup.py scans these tags with regex _PID_TAG_RE, _SIG_TAG_RE, _DESC_TAG_RE, _SETTING_DESC_RE, _SETTING_ENUMVALS_RE. Example PIDLarge.py tag is <<PID-DISP-NAME: Orange LED multi-platform display>>. Example PIDSolari.py tag is <<PID-DISP-NAME: Departure board (solari/split flap)>>. Example PIDCRTPlatformSingleColour.py tag is <<PID-DISP-NAME: Colour CRT platform display>>. PID files read Memories CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE, PID_DEPARTURE_TP, PID_PLATFORM_OVERRIDES, plus TAS_USER_SETTING_ plus setting key. PID files read timetable CSV through TASPathResolver.GetTimetableCsvPath and use TimingRegister.getTiming and listTimingPoints, PlatformAllocationRegister.getPlatform and addPlatformListener, DisruptionRegister.getDisruption.

Signaller display tags use <<SIG-DISP-NAME: ...>>. Observed values: Station working in StationWorking.py, Message notebook in NotebookDisruption.py, Teleprinter in TeleprinterDisruption.py, TRUST TRJA output in TRUST-TRJA.py.

TRUST-TRJA.py defines a TRUST TRJA output display with JFrame title WinVV Session 1. It reads Memories CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE. It uses TASUtil.IsDefaultReportingNumber to hide default reporting numbers in the Train column.

NSEClock.py defines an NSE clock with tag <<PID-DISP-NAME: Network SouthEast clock>> and setting <<SETTING DESCRIPTION BOOLEAN: Debranded>>. Memory TAS_USER_SETTING_DEBRANDED stores the value. NSEClock.py uses jmri.InstanceManager.getDefault(jmri.Timebase) and javax.swing.Timer with 1000 ms interval.

PUBLICDISPLAYLIST Memory stores the list of public display scripts. SIGNALLERDISPLAYLIST Memory stores the list of signaller display scripts. TimetableAutomation.py RunConfiguredPublic and RunConfiguredSignallers read these lists and call RunExternalScript for each entry.

Detailed topics:
- ai/details/wttdisplay.md
- ai/details/stationworking.md
- ai/details/pid-pattern.md
- ai/details/trust-nseclock.md
