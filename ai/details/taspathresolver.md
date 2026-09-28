Read when: Task modifies or debugs TASPathResolver.py or file location logic.

# TASPathResolver.py

File: TASPathResolver.py. Lines: 246.

Exported functions:
- GetProfileJythonDir()
- GetScriptsDir()
- GetTimetableDir()
- GetTimetableCsvPath(timetableName)
- _ExistsFile(path)
- _ExistsDir(path)
- EnsureDir(path)
- IsDirWritable(path)
- ResolveScriptReadPath(filename)
- ResolveWorkingScriptReadPath(direction, reportingNumber)
- GetWorkingsWriteDir(direction)
- FindInputStreamFor(key)

JMRI calls:
- jmri.util.FileUtil.getExternalFilename
- jmri.util.FileUtil.getScriptsPath
- jmri.util.FileUtil.createDirectory
- jmri.util.FileUtil.findInputStream

Path keys used:
- profile:jython
- profile:timetable
- profile:timetable/<name>.csv
- profile:jython/<filename>
- scripts:<filename>
- profile:jython/workings/<direction>

Behavior: GetTimetableCsvPath returns profile:timetable/<name>.csv external filename. ResolveScriptReadPath checks profile:jython/<filename> then scripts:<filename>. ResolveWorkingScriptReadPath checks workings/<direction>/<reportingNumber>.py in profile then scripts locations. GetWorkingsWriteDir returns profile:jython/workings/<direction>. FindInputStreamFor checks profile:jython/<filename> then scripts:<filename> through FileUtil.findInputStream.

Open question: none. Facts verified against file content read in this session.
