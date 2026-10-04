Read when: Task modifies or debugs TASFastClockStartup.py saved fast-clock startup.

# TASFastClockStartup.py

File: TASFastClockStartup.py. Lines: 480.

Purpose: persist fast-clock time and Memory DAYOFWEEK on shutdown, restore on start when saved-startup is enabled.

Constants:
- IMFastClockUseSavedStartup = TASFASTCLOCKUSESAVEDSTARTUP
- IMFastClockSavedTime = TASSAVEDFASTCLOCKTIME
- IMDayOfWeek = DAYOFWEEK
- _DAY_NAMES = Monday through Sunday
- STATE_FILE = profile:jython/TAS/config/TASFastClockState.txt
- _ShutdownTaskJvmKey = tas.fastclockstartup.shutdown.registered
- _ApplyJvmKey = tas.fastclockstartup.apply.started
- Globals TAS_FASTCLOCK_STARTUP_LIVE_ONLY, TAS_FASTCLOCK_STARTUP_REGISTER_ONLY

Functions:
- _ParseBoolText, NormalizeDayOfWeek
- GetLiveOnlyMode, GetJvmFlag, SetJvmFlag, GetRegisterOnlyMode, GetShutDownManager, LoadState, SaveState, PersistUseSavedStartupChoice, SyncSavedStartupChoiceToMemory, Log, SafeGetMemoryValue, SafeSetMemoryValue, GetStateFilePath, EnsureStateDir, GetTimebase, UseSavedStartupEnabled, FormatDateToClockText, ParseClockTextToDate, LoadSavedClockText, SaveSavedClockText, LoadSavedDayOfWeek, SaveSavedDayOfWeek, RegisterShutdownTaskOnce, EnsureShutdownTaskRegistered, ApplySavedStartupTimeOnce
- Class PersistFastClockTask extends jmri.implementation.AbstractShutDownTask with method run. run must not return a value: AbstractShutDownTask.run is a Java void method, so returning True raises TypeError "None required for void return" at shutdown.

Memories: TASFASTCLOCKUSESAVEDSTARTUP, TASSAVEDFASTCLOCKTIME, DAYOFWEEK with IM prefix fallback in local wrappers. Local SafeGetMemoryValue and SafeSetMemoryValue prefer TASBeanLookup.SafeGetOrCreateMemoryValue and TASBeanLookup.SafeSetMemoryValue when TASBeanLookup import succeeds.

File: profile:jython/TAS/config/TASFastClockState.txt with keys useSavedStartup=, clockText=, dayOfWeek= through jmri.util.FileUtil.getExternalFilename(STATE_FILE).

JMRI APIs:
- jmri.InstanceManager.getDefault(jmri.ShutDownManager) with register(PersistFastClockTask)
- jmri.InstanceManager.getDefault(jmri.MemoryManager) with getMemory(IM + name) and provideMemory(IM + name)
- jmri.InstanceManager.getDefault(jmri.Timebase) with getTime, userSetTime, setTime, getIsInitialized
- jmri.implementation.AbstractShutDownTask, javax.swing.Timer, java.util.Calendar and Date, java.lang.System.getProperty and setProperty

Execution: module runs SyncSavedStartupChoiceToMemory(), RegisterShutdownTaskOnce(), ApplySavedStartupTimeOnce() at import unless register-only or live-only modes are set. Listed in TimetableAutomation._TASStartUpScriptNames.

Open question: none. Facts verified against file content read in this session.
