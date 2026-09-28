Read when: Task concerns file paths, profile:jython, scripts:, profile:timetable, workings directories, FileUtil, TASPathResolver, TASScriptsPathGuard.

# Paths and Files

Path resolution is through TASPathResolver.py. Scripts path decisions are through TASScriptsPathGuard.py.

Functions in TASPathResolver.py:
- GetProfileJythonDir
- GetScriptsDir
- GetTimetableDir
- GetTimetableCsvPath
- _ExistsFile
- _ExistsDir
- EnsureDir
- IsDirWritable
- ResolveScriptReadPath
- ResolveWorkingScriptReadPath
- GetWorkingsWriteDir
- FindInputStreamFor

TASPathResolver.py uses jmri.util.FileUtil.getExternalFilename, jmri.util.FileUtil.getScriptsPath, jmri.util.FileUtil.createDirectory, jmri.util.FileUtil.findInputStream.

Read order for scripts is profile:jython then scripts:. Write location for generated files is profile:jython. Timetable CSV location is profile:timetable/<name>.csv where <name> is the value of Memory CURRENTTIMETABLE.

Functions in TASScriptsPathGuard.py:
- CanonicalLower
- PathsEqual
- PathLooksLikeProgramDir
- IsWritableDir
- NeedsScriptsPathUpdate
- EnsureScriptsPathChanged

TASScriptsPathGuard.py has no JMRI dependency. It uses os.path.normcase, os.path.realpath, os.path.abspath, os.sep, os.path.isdir, tempfile.mkstemp.

Directory checks in TimetableAutomation.py use _DirContainsAnyOf and _DirHasAnyPyUnder to detect scripts in both profile:jython and scripts: locations. If scripts exist in both locations, TAS displays a dual-install warning.

Workings scripts are located at profile:jython/workings/<Direction>/<RN>.py or legacy scripts:workings/<Direction>/<RN>.py. TASWorkingsUi.py reports newDir, legacyDir, newHasAny, legacyHasAny, chosenDir, chosenIsLegacy and does not mix the two locations.

Detailed topics:
- ai/details/taspathresolver.md
- ai/details/tasscriptspathguard.md
