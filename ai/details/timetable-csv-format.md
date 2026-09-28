Read when: Task modifies or debugs timetable CSV parsing, columns, delimiters, or example timetables.

# Timetable CSV Format

Delimiter: tab character. Files RunWTT.py, WorkingCreator.py, TASWorkingsUi.py, retryEnqueuedWorkings.py, TimingRegister.py, CheckTimingPoints.py use csv.DictReader with delimiter tab. WTTDisplay.py and StationWorking.py read a sample and use tab when tab is present, else comma.

Row numbering: header is row 1. First data row is row 2. enumerate(reader, start=2) is used in RunWTT.py and retryEnqueuedWorkings.py.

Columns observed in Example timetables/Timetable 2017.csv:
Reporting number, Direction, Trigger, Arr, Dep, TPArr Tondu, TPDep Tondu, TPArr Bridgend, TPDep Bridgend, TPArr Cardiff Central, TPDep Cardiff Central, TPDep Ebbw Jn, TPArr Newport, TPDep Newport, TP1Arr Cross Keys, TP1Dep Cross Keys, TP1Arr Ebbw Vale Parkway, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday, Forms, Platform, Timing load, Disruption group, Notes, Remarks, Origin, Destination, Company, Special, Via, Calling pattern.

Columns observed in Example timetables/Timetable 2016.csv:
Reporting number, Direction, Arr, Dep, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday, Forms, Platform, Timing load, Disruption group, Notes, Origin, Destination, Calling pattern.

Semantics:
- Reporting number empty means default. Default is TAS plus row number through TASUtil.MakeDefaultReportingNumberFromRow.
- Direction is working direction text.
- Trigger time takes precedence over Arr in RunWTT.py. When direction is Arr and Trigger cell is non-empty, RunWTT.py skips the Arr entry.
- Arr, Dep, Trigger, TPArr <name>, TPDep <name>, TP<n>Arr <name>, TP<n>Dep <name> contain time text. Time parsing accepts 13:15, 13:15:00, trailing h, 1:15 PM, 1:15PM, 24:xx as 00:xx. Parsed times are normalised to minutes since midnight.
- Day cells contain true or false. Value true in lower case means the row runs. Display code also accepts T, 1, Y, YES.
- Forms contains the reporting number of the next working.
- Timing point header pattern is ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive.

Documentation scope per user decision 2026-09-28: record the pattern only. Do not duplicate example timetable content. Refer to Example timetables/*.csv for instances.
