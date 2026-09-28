Read when: Task concerns timetable CSV format, RunWTT.py, CheckWhenTimeChanges.py, WorkingCreator.py, TASWorkingsUi.py, startTrain.py, trainFinder.py, enqueuedWorkings.py, retryEnqueuedWorkings.py, TimingRegister.py interaction with startTrain, CheckTimingPoints.py.

# Timetable and Workings

Timetable CSV files are tab-separated. RunWTT.py, WorkingCreator.py, TASWorkingsUi.py, retryEnqueuedWorkings.py, TimingRegister.py, CheckTimingPoints.py use csv.DictReader with delimiter tab. WTTDisplay.py and StationWorking.py check for tab in the file sample and use tab if present, else comma.

Example header in Example timetables/Timetable 2017.csv contains 38 columns: Reporting number, Direction, Trigger, Arr, Dep, TPArr Tondu, TPDep Tondu, TPArr Bridgend, TPDep Bridgend, TPArr Cardiff Central, TPDep Cardiff Central, TPDep Ebbw Jn, TPArr Newport, TPDep Newport, TP1Arr Cross Keys, TP1Dep Cross Keys, TP1Arr Ebbw Vale Parkway, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday, Forms, Platform, Timing load, Disruption group, Notes, Remarks, Origin, Destination, Company, Special, Via, Calling pattern.

Example header in Example timetables/Timetable 2016.csv is simpler with 18 columns and no Trigger column and no TP columns.

Column semantics:
- Reporting number: empty value means TAS plus row number. TASUtil.MakeDefaultReportingNumberFromRow(rowNumber) returns "TAS" plus rowNumber. TASUtil.IsDefaultReportingNumber(s) returns true when s starts with "TAS" and the remainder is alphanumeric. startTrain.py defines a local IsDefaultReportingNumber(s) that requires digits after TAS.
- Direction: text value for the working direction.
- Trigger, Arr, Dep: time text. Trigger takes precedence over Arr in RunWTT.py. If Arr row has non-empty Trigger, RunWTT.py skips the Arr entry.
- TPArr <name>, TPDep <name>, TP<n>Arr <name>, TP<n>Dep <name>: timing point times. Pattern is ^TP(\d*)(Arr|Dep)\s+(.+)$ with case-insensitive match.
- Monday through Sunday: day flags. Value true means the row runs on that day. RunWTT.py requires lowercased value equal to "true". Display code also accepts "T", "1", "Y", "YES".
- Forms: reporting number of the next working formed by this working.
- Other columns: Platform, Timing load, Disruption group, Notes, Remarks, Calling pattern, Special, Via, Origin, Destination, Company.

RunWTT.py reads Memories CURRENTTIMETABLE, CURRENTTIME, DAYOFWEEK through TASBeanLookup.ProvideMemoryBySuffix. RunWTT.py calls TASPathResolver.GetTimetableCsvPath(timetableName) and TASPathResolver.ResolveWorkingScriptReadPath(direction, reportingNumber). RunWTT.py imports DisruptionGenerator as DG and calls DG.updateDisruptions(). RunWTT.py calls execfile(scriptName) for each matched workings/<Direction>/<RN>.py script.

CheckWhenTimeChanges.py is a startup script. It registers a java.beans.PropertyChangeListener on Memory CURRENTTIME. On value change, if Memory TASAUTOWORKING value lowercased is one of true, 1, yes, on, it calls execfile on RunWTT.py and retryEnqueuedWorkings.py through TASPathResolver.ResolveScriptReadPath. It always calls execfile on CheckTimingPoints.py.

WorkingCreator.py provides ShowWorkingCreator(rn, direction, rowIndex, formsNext). It generates files under workings/<Direction>/<RN>.py. Generated text contains execfile calls for startTrain.py and trainFinder.py and optionally RosterSearch.py, then trainFinder(traininfoNames, rosterIds) then startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext).

TASWorkingsUi.py provides BuildWorkingsPanel and ShowWorkingsDialog and class WorkingsUiController and class WorkingItem. It validates working scripts for required strings including import jmri, from jmri.util import FileUtil, scriptsPath = jmri.util.FileUtil.getScriptsPath(), execfile for startTrain.py, execfile for trainFinder.py, trainFinder( call, startTrain( call.

startTrain.py provides startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext). It uses jmri.jmrit.dispatcher.TrainInfoFile, DispatcherFrame, BlockManager, SectionManager, ThrottleManager. It calls formationRegister, enqueuedWorkings, DisruptionRegister, OrientationRegister, TimingRegister, TrainLocatorRegister, TASUtil, TASBeanLookup, TASPathResolver.

trainFinder.py provides trainFinder(traininfoNames, rosterIds, reportingNumber). It checks transit state through jmri.Transit.IDLE and block state through jmri.Block.OCCUPIED.

enqueuedWorkings.py stores a list named workings of tuples (reportingNumber, direction). File is profile:enqueuedWorkings.json. Functions: enqueueWorking, getEnqueuedWorking, dequeueWorking, popWorking, getEnqueuedWorkingsCopy, countWorkings, ClearWorkings, save, load.

retryEnqueuedWorkings.py reads enqueuedWorkings.getEnqueuedWorkingsCopy() and calls execfile on each working script. It reads Memory CURRENTTIMETABLE and uses TASUtil.MakeDefaultReportingNumberFromRow for empty Reporting number cells.

CheckTimingPoints.py provides sync_timing_points_from_timetable. It synchronizes timing point names between the active timetable and TimingRegister.

Detailed topics:
- ai/details/runwtt-checkwhentimechanges.md
- ai/details/workingcreator-workingsui.md
- ai/details/starttrain-trainfinder-enqueued.md
- ai/details/timetable-csv-format.md
