Read when: Task concerns file paths, profile:jython, scripts:, profile:timetable, workings directories, FileUtil, TASPathResolver, TASScriptsPathGuard.

# Paths and Files

Path resolution is through TASPathResolver.py. Scripts path decisions are through TASScriptsPathGuard.py.

Functions in TAS/TASPathResolver.py:
- GetProfileJythonDir
- GetTASDir
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

TAS/TASPathResolver.py uses jmri.util.FileUtil.getExternalFilename, jmri.util.FileUtil.getScriptsPath, jmri.util.FileUtil.createDirectory, jmri.util.FileUtil.findInputStream.

Read order for TAS scripts is profile:jython/TAS then profile:jython (legacy flat installs) then scripts:. Write location for generated files is profile:jython/TAS. Timetable CSV location is profile:timetable/<name>.csv where <name> is the value of Memory CURRENTTIMETABLE.

Functions in TAS/TASScriptsPathGuard.py:
- CanonicalLower
- PathsEqual
- PathLooksLikeProgramDir
- IsWritableDir
- NeedsScriptsPathUpdate
- EnsureScriptsPathChanged

TAS/TASScriptsPathGuard.py has no JMRI dependency. It uses os.path.normcase, os.path.realpath, os.path.abspath, os.sep, os.path.isdir, tempfile.mkstemp.

Directory checks in TAS/TimetableAutomation.py use _DirContainsAnyOf and _DirHasAnyPyUnder to detect TAS files outside profile:jython/TAS (program folder, foreign scripts folder). Leftover flat files at the profile jython root are moved by _CheckTasLocationAndMigrateOnce with an explanatory dialog instead of being reported.

Workings scripts are located at profile:jython/TAS/workings/<Direction>/<RN>.py with fallbacks at legacy profile:jython/workings/<Direction>/<RN>.py and scripts:workings/<Direction>/<RN>.py. TAS/TASWorkingsUi.py reports newDir, legacyDir, newHasAny, legacyHasAny, chosenDir, chosenIsLegacy and does not mix the two locations.

Detailed topics:
- ai/details/taspathresolver.md
- ai/details/tasscriptspathguard.md
