Read when: Task modifies or debugs TRUST-TRJA.py or NSEClock.py.

# TRUST TRJA and NSEClock

File TRUST-TRJA.py. Header states TRUST-TRJA Enquiry Output and hides TAS-default reporting numbers in Train column.

Discovery tags in TRUST-TRJA.py:
- <<SIG-DISP-NAME: TRUST TRJA output>>
- <<DESCRIPTION: Shows a line-up of trains due at this location, simulating the BR/Network Rail TRUST TRJA output>>

Constants and functions in TRUST-TRJA.py:
- TRJA_KEEP_AFTER_DEPART_UNTIL_LAST_TP=False
- TRJA_TimeMem, TRJA_DayMem, TRJA_TimetableMem through TASBeanLookup.ProvideMemoryBySuffix for CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE with add and removePropertyChangeListener.
- TRJA_GetTimetableFile, TRJA_DaysOfWeek, TRJA_TPKeyPat = ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive.
- TRJA_GetNextDay, TRJA_GetPrevDay.
- TRJA_TimeParser with SimpleDateFormat(h:mm a), TRJA_AltParser with SimpleDateFormat(H:mm), TRJA_Out24 with SimpleDateFormat(HH:mm).
- TRJA_ParseTimeToMinutes, TRJA_FormatTo24Hour, TRJA_IsCrossMidnightWindow, TRJA_IsLateEvening, TRJA_MinutesNow.
- TRJA_FindLatestTimingForRNAtTP, TRJA_GetLastScheduledTP, TRJA_GetLastReportForTrain_Display, TRJA_ComputeOverdueReport.
- Paging TRJA_PageSize=12, TRJA_CurrentPage, TRJA_FilteredData, TRJA_TotalPages, TRJA_RebuildFilteredData, TRJA_UpdateTimetable, TRJA_UpdateHeader, TRJA_UpdateTable, TRJA_Cleanup.
- UI TRJA_Table, TRJA_Frame with JFrame title WinVV Session 1.
- Timetable read through TASPathResolver.GetTimetableCsvPath with fallback os.path.join(profile path, timetable, name + .csv) and csv.DictReader delimiter tab.
- Uses DisruptionRegister.getDisruption, TimingRegister listTimingPoints and getTiming, TASUtil.IsDefaultReportingNumber to set displayTrain to empty string for defaults, TASIcon.SetFrameClockIcon(TRJA_Frame, 32).
- Uses jmri.InstanceManager.getDefault(jmri.Timebase) with getRun, getRate, add and removePropertyChangeListener.

File NSEClock.py:
- Discovery tags: <<PID-DISP-NAME: Network SouthEast clock>>, <<DESCRIPTION: The mechanical/digital clocks installed by Network SouthEast in the 1980s>>, <<SETTING DESCRIPTION BOOLEAN: Debranded>>.
- Variable TAS_USER_SETTING_Debranded=False. Memory TAS_USER_SETTING_DEBRANDED through TASBeanLookup.SafeGetOrCreateMemoryValue.
- Classes NSECLK_HMView, NSECLK_SecView, NSECLK_MinSecDotView, NSECLK_LogoPanel, NSECLK_PlainRedPanel, NSECLK_CloseHandler.
- Functions NSECLK_Log, NSECLK_Expand, NSECLK_FileBesideScript, NSECLK_LoadDigital7TTF, NSECLK_InstalledDigitalFamily, NSECLK_GetFonts, NSECLK_GetHmsFromTimebase, NSECLK_UpdateClock.
- Globals NSECLK_Frame, NSECLK_OuterPanel, NSECLK_ClockPanel, NSECLK_FontHM, NSECLK_FontSec, NSECLK_HmView, NSECLK_MinSecDot, NSECLK_LabelSec, NSECLK_ClockHolder, NSECLK_DisplayStack, NSECLK_Timer = swing.Timer(1000, NSECLK_UpdateClock).
- Config file digital-7 (mono).ttf beside script or override path or candidate TTF paths.
- Uses jmri.InstanceManager.getDefault(jmri.Timebase), javax.swing JFrame JPanel Timer JComponent, java.awt GraphicsEnvironment RenderingHints Font, java.io File FileInputStream, java.util Date Calendar.

Open question: none. Facts verified against file content read in this session.
