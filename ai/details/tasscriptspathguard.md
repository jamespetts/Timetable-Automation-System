Read when: Task modifies or debugs TASScriptsPathGuard.py or scripts path update decisions.

# TASScriptsPathGuard.py

File: TASScriptsPathGuard.py. Lines: 114.

Purpose: pure Python logic for scripts path decisions with no JMRI dependency.

Functions:
- CanonicalLower(path)
- PathsEqual(a, b)
- PathLooksLikeProgramDir(path)
- IsWritableDir(path)
- NeedsScriptsPathUpdate(currentScriptsPath, thisScriptDir)
- EnsureScriptsPathChanged(setScriptsPathFunc, thisScriptDir)

Implementation uses os.path.normcase, os.path.realpath, os.path.abspath, os.sep, os.path.isdir, tempfile.mkstemp.

Behavior: CanonicalLower normalises case and path separators. PathsEqual compares canonical forms. PathLooksLikeProgramDir detects program directory location. NeedsScriptsPathUpdate returns true when current scripts path differs from the directory containing the TAS scripts. EnsureScriptsPathChanged calls the provided setter function when an update is needed.

Caller: TimetableAutomation._EnsureTasScriptsPath imports TASScriptsPathGuard and calls NeedsScriptsPathUpdate and EnsureScriptsPathChanged.

Testability: functions are pure and selected modules can be tested outside JMRI without JMRI imports.

Open question: none. Facts verified against file content read in this session.
