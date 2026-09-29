Read when: Task concerns DccPowerOnStart.py, TASWarningWindow.py, BlockFlickerMonitor.py, DCC track power at start-up, the TAS warning window, or disabling JMRI's built-in PowerOn.py Start-Up entry.

# Start-up power and shared warning window

## DccPowerOnStart.py

Optional startup script, off by default, enabled in TASSetup.py General tab with "Turn DCC power on at start-up (requires restart)". Listed in TimetableAutomation._TASStartUpScriptNames.

Runs at import time through Start(), which starts a daemon java.lang.Thread running _PowerOnTask so the JMRI start-up action list is not held up.

Constants: MANAGER_WAIT_SECONDS = 30, STATE_WAIT_SECONDS = 15, POLL_MSEC = 500, BUILTIN_POWER_SCRIPT = "PowerOn.py", UNKNOWN_KEY, NO_MANAGER_KEY, SET_FAILED_KEY, UNKNOWN_TEXT, NO_MANAGER_TEXT, SET_FAILED_TEXT.

Functions: _Log, _StateName, _GetPowerManager, _ReadState, _WaitForPowerManager, _WaitForKnownState, _ApplyPower, _ActiveProfile, _DisableBuiltinPowerScript, Start. Class _PowerOnTask extends java.lang.Runnable.

Rules in _ApplyPower: no power manager within the wait shows a warning and returns. A power state of UNKNOWN is never changed by setPower. The script waits for a known state, then turns power on only when the state is OFF or IDLE. A state of ON is left unchanged. A state of UNKNOWN after the wait shows a warning and returns.

_DisableBuiltinPowerScript sets setEnabled(False) on every enabled PerformScriptModel whose file name is PowerOn.py, at any path, then calls mgr.savePreferences(prof). Start-Up actions belong to the active profile, so this affects the current layout only. Each disabled path is logged.

JMRI APIs used: jmri.InstanceManager.getNullableDefault(jmri.PowerManager), PowerManager getPower, setPower, and constants UNKNOWN, ON, OFF, IDLE, jmri.util.startup.StartupActionsManager getActions savePreferences, jmri.util.startup.PerformScriptModel isEnabled setEnabled getFileName, jmri.profile.ProfileManager.getDefault().getActiveProfile(), java.lang.Thread, java.lang.System.currentTimeMillis.

JMRI facts: jmri.InstanceManager.getDefault throws NullPointerException when no instance exists, so getNullableDefault is required here. PowerManager constants are UNKNOWN = NamedBean.UNKNOWN, ON = 0x02, OFF = 0x04, IDLE = 0x08. JMRI ships program:jython/PowerOn.py which calls powermanager.setPower(jmri.PowerManager.ON) unconditionally.

## TASWarningWindow.py

Shared non-modal warning window. One instance per warning feature so unrelated warnings do not share a window.

Module contents: DEFAULTS dict, class Runner extends java.lang.Runnable, function InvokeOnEdt, function Escape, class _FlashEnd extends ActionListener, class _WarningSymbolPanel extends JPanel, class _CloseReset extends WindowAdapter, class TasWarningWindow.

TasWarningWindow(config) takes a dictionary of overrides on DEFAULTS: title, textWidth, textHeight, frameWidth, frameBaseHeight, frameGrowPerMessage, frameMaxHeight, fontSize, nameFontSize, background, backgroundHex, textHex, textColour, nameHex, symbolFill, symbolEdge, markColour, flashColour, flashPixels.

TasWarningWindow methods: IsOpen, MessageCount, Clear, AddNotice(key, text), AddMessage(key, name, lead, tail), Show, and private _ResetOnClose, _AddRecord, _CreateFrame, _BuildHtml, _RecomputeRanges, _RenderNow, _FlashNow, _ShowFrame.

Behaviour: one frame per instance, created on first message and disposed on close. Messages accumulate one per line. AddMessage with a key already present flashes the existing line instead of adding a line. AddNotice adds a plain line with no highlighted name. The frame grows by frameGrowPerMessage per message up to frameMaxHeight. All frame work is marshalled to the Event Dispatch Thread through InvokeOnEdt. Frame icon through TASIcon.SetFrameClockIcon.

## BlockFlickerMonitor.py

Optional startup script, off by default. Watches Blocks for a short drop from OCCUPIED to UNOCCUPIED and back within FLICKER_GAP_MS = 3000. Uses TASWarningWindow with a red triangle, nameHex ff4040, title "Occupancy sensor warning". Module keeps _window, _lock, _started, _listeners, _lastInactiveMs. Functions: _Log, _BlockLabel, _SensorLabel, _ShowNoticeNow, _AppendMessage, _ReportFlicker, _AllBlocks, Start, Stop, Show. Class _BlockListener. Start runs at import; Stop is registered with jmri.InstanceManager.getDefault(jmri.ShutDownManager) through TASWarningWindow.Runner.

## TASSetup.py wiring

IsDccPowerOnStartEnabled uses _IsScriptEnabled("DccPowerOnStart.py"). TASSetupFrame stores InitialDccPowerOnStart and CurrentDccPowerOnStart, the checkbox is ChkDccPowerOnStart with error label LblDccPowerOnStartError, and the close handler compares InitialDccPowerOnStart with CurrentDccPowerOnStart for the restart prompt. Help topic is tashelp/Dcc power on start.txt, discovered automatically by TASHelp.py.
