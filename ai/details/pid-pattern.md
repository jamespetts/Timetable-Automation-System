Read when: Task creates a new PID display or modifies PID discovery tags, PID settings, or shared PID data logic.

# PID Pattern

Files: PID*.py, 21 files observed. List:
PIDCRTSummaryColour.py, PIDCRTSummaryArrivals.py, PIDCRTSummary.py, PIDCRTSingle.py, PIDCRTPlatformSingleColour.py, PIDFingerboard.py, PIDCRTSummaryColourArrivals.py, PIDFingerboardBR.py, PIDLarge.py, PIDSolariSingle.py, PIDRotorSingle.py, PIDSolari.py, PIDSmall.py, PIDRotaryLarge.py, PIDLightboxSingleArrow.py, PIDUndergroundLED.py, PIDLightboxSingle.py, PIDSolariSingleTwoTrains.py, PIDVFD.py, PIDLargeSingle.py, PIDLightbox.py.

Discovery tags at top of each file:
- <<PID-DISP-NAME: ...>> defines display name.
- <<DESCRIPTION: ...>> defines description.
- <<SETTING DESCRIPTION NUMBER: ...>> defines numeric setting.
- <<SETTING DESCRIPTION BOOLEAN: ...>> defines boolean setting.
- <<SETTING DESCRIPTION STRING: ...>> defines string setting.
- <<SETTING DESCRIPTION COLOR: ...>> defines color setting.

Examples:
- PIDLarge.py <<PID-DISP-NAME: Orange LED multi-platform display>> with settings Number of departures to show, Page interval (seconds), Platform/status flip interval (seconds), Hide platform until allocated, Special text scroll speed (px per second), Special text scroll pause (ms).
- PIDSolari.py <<PID-DISP-NAME: Departure board (solari/split flap)>> with settings Strip columns, Solari scale percent, Solari width expand percent, Solari anim ms per half, Solari digit fps, Solari chatter steps, Solari blank hold ms, Solari blank chatter steps, Solari board cascade ms, Solari future window minutes, Solari stagger row ms, Solari stagger jitter ms, Solari extra word steps max, Solari extra digit cycles max, Hide platform until allocated, Delay threshold minutes, Delay via banner top, Delay via banner bottom, Delay special banner top, Delay special banner bottom, ECS message, Solari special default fg, Solari special default bg, Solari special alt fg, Solari special alt bg, Solari special keywords.
- PIDCRTPlatformSingleColour.py <<PID-DISP-NAME: Colour CRT platform display>> with settings Colour CRT platform display: Due window (minutes), Colour CRT platform display: ECS filter terms.

Shared data logic in sampled files:
- Functions ParseMinutes, FormatHHmm, MinutesToHHmm, TimetablePath, CsvRows, CaseInsensitive, PlatformField, ParseOverrides, GetOverride, ActiveProfileBaseTPName, DepartureTPList, HasDepartedAtConfiguredTP, ResolveDelayWithInheritance.
- Memories CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE, PID_DEPARTURE_TP, PID_PLATFORM_OVERRIDES, plus TAS_USER_SETTING_ plus setting key, plus PID_CRT_PAGE_SECONDS, PID_COMPANY_NAME, PID_CRT_WITHIN_MINUTES, PID_ECS_FILTER_TERMS in CRT file.
- Timetable read through TASPathResolver.GetTimetableCsvPath with csv.DictReader delimiter tab.
- Timing through TimingRegister.getTiming and listTimingPoints.
- Platform through PlatformAllocationRegister.getPlatform and addPlatformListener.
- Disruption through DisruptionRegister.getDisruption.
- Window icon through TASIcon.SetFrameClockIcon.
- Listeners through java.beans.PropertyChangeListener and java.awt.event.WindowAdapter.

TASSetup.py scans display scripts with regex _PID_TAG_RE, _SIG_TAG_RE, _DESC_TAG_RE, _SETTING_DESC_RE, _SETTING_ENUMVALS_RE and function ScanDisplayScripts.

Rule for new display: create PID<Name>.py with the tags listed above, implement data reading as in PIDLarge.py or PIDSolari.py, use TASBeanLookup for Memories, use TASPathResolver for timetable path, use TASIcon.SetFrameClockIcon for the frame.

Documentation scope per user decision 2026-09-28: keep the 3-file sample. Do not duplicate full per-file setting lists. Refer to code for complete settings.
