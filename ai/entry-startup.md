Read when: Task concerns TimetableAutomation.py, main menu, main menu button toggles, scripts path check, dual-install check, startup actions check, RunExternalScript, About dialog, Licence text, changelog text.

# Entry and Startup

Entry script is TimetableAutomation.py. VERSION = "1.5" is defined in TimetableAutomation.py. Run method is Run(). Run() calls _CheckStartUpPathsOnce() and _CheckForDualInstallAndWarnOnce(), then displays class TASWTTStartup.

Functions in TimetableAutomation.py:
- _TasGetThisScriptDir, _TasIsWritableDir, _TasScriptsPathLooksLikeProgramDir, _EnsureTasScriptsPath
- _IsStartUpScriptEnabled, _DebugPrintStartUp
- _CanonLower, _StartupMgr, _ActiveProfile, _ProfileJythonScriptPath, _FindPerformScriptModelsByBaseName, _BuildStartUpPathMismatchReport, _ApplyStartUpPathFix, _ShowStartUpPathMismatchDialog, _CheckStartUpPathsOnce
- _DirContainsAnyOf, _DirHasAnyPyUnder, _CheckForDualInstallAndWarnOnce
- GetActiveProfileName, GetTimetableName, RunExternalScript, ReadMemStr
- PreferredFontFamily, FitFontForSingleLine, BuildTitleLines, LoadLicenceText, LoadChangeLogText
- RefreshMainMenuTheme, Run
- Class CoverPanel with MakeBtn, ToggleWindows, ShowStub, ShowAbout, IsTimeWarpAllowed, UpdateTimeWarpEnabled, OnTimeWarp, OnWeatherForecast, RunConfiguredPublic, RunConfiguredSignallers, FRIENDLY_NAME, RefreshThemeFromMemories, paintComponent
- Class AboutDialog, class TASWTTStartup

CoverPanel.ToggleWindows(key, opener) uses TASWindowRegistry.Toggle so that the buttons which open another window close it on a second press. The module is imported as TASWINREG. Details in ai/details/timetableautomation.md.

_TASStartUpScriptNames list in TimetableAutomation.py contains: TimetableAutomation.py, CheckWhenTimeChanges.py, DayTracker.py, TimeWarpChecker.py, DayNight.py, WeatherGenerator.py, LastReportedDirection.py, TASFastClockStartup.py, BlockFlickerMonitor.py, DccPowerOnStart.py, DccPowerOffOnClose.py.

RunExternalScript(path, name) uses execfile(fullPath, SafeGlobals). If identifier Show exists in globals after execfile, RunExternalScript calls the function with zero arguments or with one string argument. RunExternalScript sets TAS_MAINMENU_THEME_REFRESH_CALLBACK to RefreshMainMenuTheme before execfile when the script is TASSetup.py.

Memories read in TimetableAutomation.py: CURRENTTIMETABLE, ALLOWTIMEWARP, WX_UI, CLOUDCOVERPCT, PUBLICDISPLAYLIST, SIGNALLERDISPLAYLIST, TASCOVERCOLOUR, TASINNERCOLOUR, TASINKCOLOUR, TASCOVERINKCOLOUR, TAS_FONT_FAMILY, RAILWAYCO, REGION, SECTION.

Files read: Licence.txt and changelog.txt through TASPathResolver.FindInputStreamFor with keys scripts:Licence.txt and scripts:changelog.txt.

Detailed topics:
- ai/details/timetableautomation.md
- ai/details/taswindowregistry.md
- ai/details/tasscriptspathguard.md
- ai/details/tasfastclockstartup.md
- ai/details/startup-power-warnings.md
