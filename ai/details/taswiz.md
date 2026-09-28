Read when: Task modifies or debugs TASWiz.py setup wizard.

# TASWiz.py

File: TASWiz.py. Header states TAS Setup Wizard, wizard-style setup helper, ASCII-only, portable paths, thread-safe, designed for JMRI 5.14 and Jython 2.7.

Functions and classes:
- LogInfo, LogWarn, LogError, ApplyTheme
- _GetInstalledFontFamiliesLowerSet, _FirstInstalledFont, MakePaperPanel, MakeHeading, MakeWrappedTextArea, MakeScrollForText
- _ResolveWizardImageProfilePath, _CandidateWizardImageProfilePaths, _LoadWizardImage
- Class WizardSidebarImagePanel extends JPanel
- LoadWorkingsUiModule, MakeWrappedLabel, LoadWorkingCreatorModule, ProfileJythonFilePath
- _LoadNamedPresetsFromConfigCsv, _LoadClimateNames, _LoadDayNightNames
- Class RestrictedCsvChooserWizard extends JFileChooser
- LoadFontCheckModule, CountMissingFonts, OpenFontCheckUi
- Class RunnableAdapter implements Runnable
- Class TASWizardDialog extends JDialog with _CompanyOptionsForYear, _RegionOptionsForCompany, _RefreshCompanyOptionsForYear, _OnCompanyChanged, _GetStep5CompanyValue, _GetStep5RegionValue, _ApplyRailwayDetailsFromStep5, _WeatherAccuracyForYear, _ApplyDefaultsFromStep6, _GetAutoWorkingEnabled, _SetAutoWorkingEnabled, _ListRosterIds, _NormalDirectionRegisterSetLower, _GetRosterIdsWithoutNormalDirectionRegister, _HasRosterIdsWithoutNormalDirectionRegister, _ValidateTimetableFile, _ParseTimetableTimeToMinutes, _GetDayNightEnabled, _SetDayNightEnabled, _GetOrientationSensingEnabled, _SetOrientationSensingEnabled, _RefreshStep2fUi, _ApplyLightingAddressesFromStep2e
- Constants FONT_CHECK_SCRIPT=TASFontCheck.py, WORKING_CREATOR_SCRIPT=WorkingCreator.py, WORKINGS_UI_SCRIPT=TASWorkingsUi.py, DEFAULT_WIZARD_IMAGE_PROFILE_PATH=profile:jython/TASWizard.png, TAG=[TASWiz]

Memories: TAS_FONT_FAMILY, TASPAPERCOLOUR, TAS_WIZARD_IMAGE, TAS_WIZARD_TEST_MISSINGFONTS, RAILWAYCO, REGION, SECTION, WX_UI, WX_NEWS_STYLE, WX_FORECAST_ACCURACY, WTT_TIME_24H, WTT_TIME_SEPARATOR, WTT_REP_NO_LABEL, WTT_TIMING_LOAD_LABEL, WTT_OD_HEADER_VERTICAL, WTT_ECS_LABEL, WTT_PAGE_MODE, TASCOVERCOLOUR, TASINNERCOLOUR, TASINKCOLOUR, TASWTTBANDLIGHT, TASWTTBANDDARK, TASCOVERINKCOLOUR, SIGNALLERDISPLAYLIST, PUBLICDISPLAYLIST, TASAUTOWORKING, LOWCTTHROTTLEADDR, HIGHCTTHROTTLEADDR, WX_CLIMATE, DAYNIGHT_PRESET, CURRENTTIMETABLE, ALLOWDELAYS, ALLOWCANCELLATIONS through TASBeanLookup SafeGetOrCreateMemoryValue SafeGetMemoryValue SafeSetMemoryValue.

Files: FileUtil.getExternalFilename(profile:jython/ + name), FileUtil.getExternalFilename(profile:timetable), TASPathResolver GetProfileJythonDir GetTimetableCsvPath ResolveWorkingScriptReadPath, FileUtil.getExternalFilename(profile:jython/TASHelp.py), config CSVs profile:jython/config/climate.csv and daynight.csv, wizard images profile:jython/TASWizard.png, profile:jython/TASWizardSidebar.png, profile:jython/TASWizardLeft.png.

JMRI APIs: jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager), jmri.profile.ProfileManager.getDefault with getActiveProfile getActiveProfileName getName setName, jmri.util.startup.PerformScriptModel with setFileName setEnabled isEnabled getFileName, jmri.jmrit.roster.Roster with matchingList toArray getId getDccAddress, FileUtil.getExternalFilename, GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames().

Calls: TASBeanLookup as TBL, TASPathResolver as TPR, TASIcon.SetFrameClockIcon(self, 32), NormalDirectionRegister as NDR with NDR.GetCopy(), execfile for HardwareDirectionConfig.py, imp.load_source for TASWorkingsUi_i WorkingCreator_i TASFontCheck_i, TASHelp.

Roster normalisation: str(k).strip().lower() and str(rid).strip().lower() for comparison to NormalDirectionRegister. Comment states case-insensitive comparison.

LoadWorkingCreatorModule loads WORKING_CREATOR_SCRIPT through ProfileJythonFilePath and imp.load_source. Prior value WorkingCreator_HeadlessAudit_20260106_v2.py was stale. Current value is WorkingCreator.py. WorkingCreator.py defines GetWorkingsStatusForTimetable and ShowWorkingCreator. The function retains a fallback lookup to WorkingCreator.py.

Open question: none. WORKING_CREATOR_SCRIPT corrected to WorkingCreator.py on 2026-09-28 per user confirmation that the headless audit file must not exist.
