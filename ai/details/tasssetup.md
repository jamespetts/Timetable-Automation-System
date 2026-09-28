Read when: Task modifies or debugs TASSetup.py configuration UI.

# TASSetup.py

File: TASSetup.py. Header states tabs General, Display configuration, Day/night cycle. ASCII-only, portable paths, thread-safe.

Tabs built in TASSetupFrame init: General setup, Timetable, Workings, Timing points, Orientation, Display configuration, Day/night cycle, Interface.

Functions and classes:
- LogInfo, LogWarn, LogError, RunSetupWizard
- _RgbStrToColorOrDefault, _ColorToRgbStr, GetMemoryBool, SetMemoryBool, ScriptExists, ApplyTheme, MakePaperPanel, MakeHeading, MakeWrappedLabel, GetDefaultFontFamily, GetDefaultBackgroundRGB
- GetFastClockTimebase, FastClockDateToText, FastClockTextToDate, GetNativeFastClockStartupInfo, ApplyNativeFastClockStartupInfo
- GetTimetableDirFile, StripCsvExt, ProfileJythonFilePath, _LoadFastClockStateDict, _SaveFastClockStateDict, PersistFastClockSavedStartupChoice, GetPersistedFastClockSavedStartupChoice
- _HasAnyWorkingScriptsUnder, _GetWorkingsBaseDirInfo, _NormRN = str(s).strip().upper(), _StartupMgr, _ActiveProfile, _CanonLower, _MatchScriptPath, _FindPerformScriptModelFor, _IsScriptEnabled, _EnsureScriptEnabled
- IsDayNightEnabled, IsStreetLightControllerEnabled, IsWeatherEnabled, IsTimeActionsEnabled
- _MakeDefaultRN(rowNumber) = TAS plus int(rowNumber)
- _ParseTimeToMinutes, _TimetableFilePath, _ValidateTimetable, _CheckWorkingScripts
- Class RestrictedCsvChooser extends JFileChooser
- MakeDualListPanel
- _UserSettingMemoryName returns TAS_USER_SETTING_ plus key
- _ScanSettingsForScript, ScanDisplayOptions, _ReadDisplayScriptText, _ScanOneDisplayScript, ScanDisplayScripts
- Class TASSetupFrame extends jmri.util.JmriJFrame with BuildGeneralTab, BuildDisplayTab, UpdateRunAutoControls, CheckTimetableOnStartup
- Tag regexes _PID_TAG_RE, _SIG_TAG_RE, _DESC_TAG_RE, _SETTING_DESC_RE, _SETTING_ENUMVALS_RE
- Constants TAG=[TASSetup] , TASFastClockStartupScript=TASFastClockStartup.py, TASFastClockStateFile=profile:jython/config/TASFastClockState.txt

Memory constants: CURRENTTIMETABLE, ALLOWDELAYS, ALLOWCANCELLATIONS, PUBLICDISPLAYLIST, SIGNALLERDISPLAYLIST, WTT_PAGE_MODE, WTT_TIME_24H, WTT_TIME_SEPARATOR, WTT_TP_NAME_DOT_LEADERS, WTT_ECS_LABEL, WTT_ECS_DEST_MATCH, WTT_TIMING_LOAD_LABEL, WTT_REP_NO_LABEL, WTT_DIRECTION_SPLIT, WTT_OD_HEADER_VERTICAL, LOWCTTHROTTLEADDR, HIGHCTTHROTTLEADDR, DAYNIGHT_PRESET, WX_CLIMATE, CLOUDCOVERPCT, WX_UI, WX_NEWS_STYLE, TIMEWARPBLACKOUTSECONDS, TIMEWARPTHRESHOLDMINUTES, TASAUTOWORKING, TASFASTCLOCKUSESAVEDSTARTUP, TASSAVEDFASTCLOCKTIME. Literals TAS_FONT_FAMILY, TASPAPERCOLOUR, TASCOVERCOLOUR, TASINNERCOLOUR, TASINKCOLOUR, TASCOVERINKCOLOUR, TASWTTBANDLIGHT, TASWTTBANDDARK, RAILWAYCO, REGION, SECTION, DISRUPTIONSEEDBASE, MINNIGHTGLOW, WX_NEWS_PAPERNAME, WX_FORECAST_ACCURACY, dynamic TAS_USER_SETTING_ plus key.

Files: FileUtil.getExternalFilename(profile:timetable), FileUtil.getExternalFilename(profile:jython/ + name), FileUtil.getExternalFilename(TASFastClockStateFile), FileUtil.getExternalFilename(profile:jython/workings), FileUtil.getExternalFilename(profile:jython), FileUtil.getExternalFilename(profile:timetable/ + name + .csv), FileUtil.getExternalFilename(profile:jython/config/climate.csv), FileUtil.getExternalFilename(profile:jython/config/daynight.csv), jmri.util.FileUtil.getScriptsPath for legacy workings fallback.

JMRI APIs: jmri.InstanceManager.getDefault(jmri.Timebase) with getStartSetTime, getStartTime, setStartSetTime, getTime; jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager) with getActions, addAction, savePreferences; jmri.util.startup.PerformScriptModel with getFileName, setFileName, isEnabled, setEnabled; jmri.profile.ProfileManager.getDefault with getActiveProfile; jmri.InstanceManager.getDefault(jmri.MemoryManager); jmri.util.JmriJFrame; jmri.jmrit.roster.Roster; BlockManager; jmri.util.FileUtil.

Calls: TASBeanLookup SafeGetOrCreateMemoryValue SafeGetMemoryValue SafeSetMemoryValue; TASIcon.SetFrameClockIcon(self, 32); execfile for TASWiz.py; execfile for display preview and HardwareDirectionConfig.py; imp.load_source for TASFontCheck_i and TASWorkingsUi_i; lazy import DisruptionRegister as DR with DR.register.clear and DR.save; import TimingRegister as TR with listTimingPoints deleteTimingPoint save; import enqueuedWorkings as EW with countWorkings ClearWorkings.

Open question: none. Facts verified against file content read in this session.
