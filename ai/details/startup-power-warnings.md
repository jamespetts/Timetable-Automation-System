Read when: Task modifies or debugs DccPowerOnStart.py, DccPowerOffOnClose.py, TASWarningWindow.py, BlockFlickerMonitor.py, a TAS warning window, DCC track power at start-up or close-down, disabling JMRI's built-in PowerOn.py Start-Up entry, or a TAS start-up script that shares names with another start-up script.

# Start-up power and shared warning window

## Shared Jython namespace hazard

JMRI runs every Start-Up "Run script..." action through `jmri.script.JmriScriptEngineManager.runScript(File)`, which calls the Jython JSR-223 engine. `org.python.jsr223.PyScriptEngine.eval` sets the interpreter locals to a `PyScriptEngineScope` wrapping the engine's `ScriptContext`, and `PyScriptEngineScope.__setitem__` writes to `ScriptContext.setAttribute(name, value, ScriptContext.ENGINE_SCOPE)`. JMRI sets one `ScriptContext` on the engine whose GLOBAL_SCOPE and ENGINE_SCOPE are the same `SimpleBindings` instance. Every top-level name of every start-up script therefore lands in one map, and a later start-up script overwrites an earlier script's names of the same spelling. Functions resolve free names against that map at call time, so the later script's object is what the earlier script uses at run time.

Rule for TAS start-up scripts: every top-level name must be unique across all start-up scripts. Use a per-script prefix, for example `FLICKER_` and `_Flicker` in BlockFlickerMonitor.py, `DCCPOWER_` and `_DccPower` in DccPowerOnStart.py. Also bind any object a function uses at run time as a default argument, for example `def _FlickerReport(block, _window=_FlickerWindow):`, so a later script cannot redirect it. Names inside an imported module are not affected, because a module has its own namespace.

`import jmri` alone makes `jmri.util.startup` and `jmri.profile` usable in these scripts.

## DccPowerOnStart.py

Optional startup script, off by default, enabled in TASSetup.py General tab with "Turn DCC power on at start-up (requires restart)". Listed in TimetableAutomation._TASStartUpScriptNames.

Runs at import time through `_DccPowerStart()`, which starts a daemon java.lang.Thread running _DccPowerTask so the JMRI start-up action list is not held up.

Constants: DCCPOWER_MANAGER_WAIT_SECONDS = 30, DCCPOWER_STATE_WAIT_SECONDS = 15, DCCPOWER_POLL_MSEC = 500, DCCPOWER_BUILTIN_SCRIPT = "PowerOn.py", DCCPOWER_UNKNOWN_KEY, DCCPOWER_NO_MANAGER_KEY, DCCPOWER_SET_FAILED_KEY, DCCPOWER_UNKNOWN_TEXT, DCCPOWER_NO_MANAGER_TEXT, DCCPOWER_SET_FAILED_TEXT.

Functions: _DccPowerLog, _DccPowerStateName, _DccPowerGetManager, _DccPowerReadState, _DccPowerWaitForManager, _DccPowerWaitForKnownState, _DccPowerApply, _DccPowerActiveProfile, _DccPowerDisableBuiltinScript, _DccPowerStart. Class _DccPowerTask extends java.lang.Runnable.

Rules in _DccPowerApply: no power manager within the wait shows a warning and returns. A power state of UNKNOWN is never passed to setPower. The script waits for a known state, then turns power on only when the state is OFF or IDLE. A state of ON is left unchanged. A state of UNKNOWN after the wait shows a warning and returns.

_DccPowerDisableBuiltinScript sets setEnabled(False) on every enabled PerformScriptModel whose file name is PowerOn.py, at any path, then calls mgr.savePreferences(prof). Start-Up actions belong to the active profile, so this affects the current layout only. Each disabled path is logged.

JMRI APIs used: jmri.InstanceManager.getNullableDefault(jmri.PowerManager), PowerManager getPower, setPower, and constants UNKNOWN, ON, OFF, IDLE, jmri.util.startup.StartupActionsManager getActions savePreferences, jmri.util.startup.PerformScriptModel isEnabled setEnabled getFileName, jmri.profile.ProfileManager.getDefault().getActiveProfile(), java.lang.Thread, java.lang.System.currentTimeMillis.

JMRI facts: jmri.InstanceManager.getDefault throws NullPointerException when no instance exists, so getNullableDefault is required here. PowerManager constants are UNKNOWN = NamedBean.UNKNOWN, ON = 0x02, OFF = 0x04, IDLE = 0x08. JMRI ships program:jython/PowerOn.py which calls powermanager.setPower(jmri.PowerManager.ON) unconditionally.

## TASWarningWindow.py

Shared non-modal warning window. One instance per warning feature so unrelated warnings do not share a window. This module is imported, so its names are safe from the shared-namespace hazard.

Module contents: DEFAULTS dict, class Runner extends java.lang.Runnable, function InvokeOnEdt, function Escape, class _FlashEnd extends ActionListener, class _WarningSymbolPanel extends JPanel, class _CloseReset extends WindowAdapter, class TasWarningWindow.

TasWarningWindow(config) copies DEFAULTS into a new dictionary and applies the overrides, so each instance keeps its own title and colours. Override keys: title, textWidth, textHeight, frameWidth, frameBaseHeight, frameGrowPerMessage, frameMaxHeight, fontSize, nameFontSize, background, backgroundHex, textHex, textColour, nameHex, symbolFill, symbolEdge, markColour, flashColour, flashPixels.

TasWarningWindow methods: IsOpen, MessageCount, Clear, AddNotice(key, text), AddMessage(key, name, lead, tail), Show, and private _ResetOnClose, _AddRecord, _CreateFrame, _BuildHtml, _RecomputeRanges, _RenderNow, _FlashNow, _ShowFrame.

Behaviour: one frame per instance, created on first message and disposed on close. Messages accumulate one per line. AddMessage with a key already present flashes the existing line instead of adding a line. AddNotice adds a plain line with no highlighted name. The frame grows by frameGrowPerMessage per message up to frameMaxHeight. All frame work is marshalled to the Event Dispatch Thread through InvokeOnEdt. Frame icon through TASIcon.SetFrameClockIcon.

## Per-feature appearance

BlockFlickerMonitor.py uses title "Occupancy sensor warning", nameHex "ff4040", symbolFill Color(198, 40, 40), symbolEdge Color(122, 0, 0).

DccPowerOnStart.py uses title "DCC power warning", nameHex "ffa64d", symbolFill Color(230, 126, 34), symbolEdge Color(140, 74, 0).

## BlockFlickerMonitor.py

Optional startup script, off by default. Watches Blocks for a double flicker: OCCUPIED-UNOCCUPIED-OCCUPIED or UNOCCUPIED-OCCUPIED-UNOCCUPIED, first to third state within FLICKER_GAP_MS = 3000. Module keeps _FlickerWindow, _FlickerLock, _FlickerStarted, _FlickerListeners, _FlickerStateChanges. Functions: _FlickerLog, _FlickerBlockLabel, _FlickerSensorLabel, _FlickerShowNotice, _FlickerAppendMessage, _FlickerReport, _FlickerAllBlocks, _FlickerStart, _FlickerStop, _FlickerShow. Class _FlickerBlockListener. _FlickerStart runs at import; _FlickerStop is registered with jmri.InstanceManager.getDefault(jmri.ShutDownManager) through TASWarningWindow.Runner. There are no external callers of these functions.

## DccPowerOffOnClose.py

Optional startup script, off by default, enabled in TASSetup.py General tab with "Turn DCC power off at close-down (requires restart)". Listed in TimetableAutomation._TASStartUpScriptNames. At import it registers jmri.ShutDownManager a DccPowerOffShutdownTask that waits up to DCCPOWEROFF_MANAGER_WAIT_SECONDS = 10 seconds for a power manager and then calls setPower(jmri.PowerManager.OFF). All top-level names use the DCCPOWEROFF_ or _DccPowerOff prefix.

## TASSetup.py wiring

IsDccPowerOnStartEnabled uses _IsScriptEnabled("DccPowerOnStart.py"). TASSetupFrame stores InitialDccPowerOnStart and CurrentDccPowerOnStart, the checkbox is ChkDccPowerOnStart with error label LblDccPowerOnStartError, and the close handler compares InitialDccPowerOnStart with CurrentDccPowerOnStart for the restart prompt. Help topic is tashelp/Dcc power on start.txt, discovered automatically by TASHelp.py. IsDccPowerOffOnCloseEnabled mirrors it for DccPowerOffOnClose.py; ChkDccPowerOffOnClose mirrors ChkDccPowerOnStart and sits in the same Box.createHorizontalBox row immediately to its right. Enable time-based actions checkbox self.ChkTimeActions is laid out in the right-hand column of the General tab checkbox area (Box.createHorizontalBox with left/right vertical boxes), with the other enablement checkboxes in the left column.
