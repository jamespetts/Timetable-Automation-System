Read when: Task modifies or debugs RunWTT.py, CheckWhenTimeChanges.py, CheckTimingPoints.py, or automatic working triggering.

# RunWTT and Time Change Checks

File RunWTT.py lines: 210. File CheckWhenTimeChanges.py lines: 74. File CheckTimingPoints.py lines: 153.

RunWTT.py:
- Reads Memories CURRENTTIMETABLE, CURRENTTIME, DAYOFWEEK through TASBeanLookup.ProvideMemoryBySuffix.
- Defines parseTimeToMinutes(timeStr) inside module. Accepts 13:15, 13:15:00, trailing h, 1:15 PM, 1:15PM. Maps 24:xx to 00:xx. Returns hour*60+minute or None.
- Iterates directions ["Trigger", "Arr", "Dep"] with csv.DictReader delimiter tab.
- Skips row when direction column absent or empty after strip.
- Skips Arr entry when Trigger column exists and is non-empty after strip.
- Checks day column row.get(currentDay). Lowercased value must equal "true" to trigger. Values other than true, false, empty produce a warning.
- Reporting number empty uses TASUtil.MakeDefaultReportingNumberFromRow(rowNumber).
- Forms empty uses None. formsNext is reset to None for each direction.
- Calls TASPathResolver.GetTimetableCsvPath(timetableName) and TASPathResolver.ResolveWorkingScriptReadPath(direction, reportingNumber).
- Calls import DisruptionGenerator as DG with reload(DG) then DG.updateDisruptions().
- Calls execfile(scriptName) for matched working script. Prints "No working script found" only when file is missing.

CheckWhenTimeChanges.py:
- Defines class CheckWhenTimeChanges extends java.beans.PropertyChangeListener with method propertyChange(self, event). Checks event.getPropertyName() == "value".
- Reads Memory TASAUTOWORKING through TASBeanLookup.FindMemoryBySuffix. Value lowercased in ["true", "1", "yes", "on"] enables auto working.
- Registers listener on Memory CURRENTTIME through TASBeanLookup.FindMemoryBySuffix.
- On change, when auto working is enabled, calls execfile on RunWTT.py and retryEnqueuedWorkings.py through TASPathResolver.ResolveScriptReadPath.
- Always calls execfile on CheckTimingPoints.py.
- Uses jmri.util.FileUtil.getScriptsPath and jmri.InstanceManager.getDefault(jmri.MemoryManager).

CheckTimingPoints.py:
- Defines sync_timing_points_from_timetable(verbose=True).
- Reads Memories DAYOFWEEK and CURRENTTIMETABLE through TASBeanLookup.SafeGetMemoryValue.
- Reads timetable CSV with csv.DictReader delimiter tab.
- Timing point pattern is ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive.
- Calls TimingRegister.listTimingPoints, ensureTimingPoint, getBlocks, deleteTimingPoint, clearTimings, removeByDay, getMeta("lastMaintenanceDay"), setMeta.
- Uses jmri.InstanceManager.getDefault(jmri.MemoryManager) and jmri.util.FileUtil.getExternalFilename("profile:timetable/" + name + ".csv").

Deprecated file CheckTimetable.py lines: 100. Header states DEPRECATED, FAULTY. It uses jmri.jmrit.automat.AbstractAutomaton and LogixNG table Timetable. It is not part of the current RunWTT flow.

Open question: none. Facts verified against file content read in this session.
