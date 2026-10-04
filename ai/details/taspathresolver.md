Read when: Task modifies or debugs TASPathResolver.py or file location logic.

# TASPathResolver.py

File: TAS/TASPathResolver.py. Lines: 244.

Constant: TAS_SUBDIR = 'TAS'. Function GetTASDir() returns profile:jython/TAS.

Exported functions:
- GetProfileJythonDir()
- GetTASDir()
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
- profile:jython/TAS
- profile:timetable
- profile:timetable/<name>.csv
- profile:jython/TAS/<filename>
- profile:jython/<filename> (legacy flat fallback)
- scripts:<filename>
- profile:jython/TAS/workings/<direction>

Behavior: GetTimetableCsvPath returns profile:timetable/<name>.csv external filename. ResolveScriptReadPath checks profile:jython/TAS/<filename> then profile:jython/<filename> then scripts:<filename>. ResolveWorkingScriptReadPath checks workings/<direction>/<reportingNumber>.py in TAS then profile then scripts locations. GetWorkingsWriteDir returns profile:jython/TAS/workings/<direction>. FindInputStreamFor checks profile:jython/TAS/<filename> then profile:jython/<filename> then scripts:<filename> through FileUtil.findInputStream.

Open question: none. Facts verified against file content read in this session.
