# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# This is a STARTUP SCRIPT.
#
# TAS fast clock saved-startup extension.
#
# Purpose:
# - Save the current fast clock time when JMRI shuts down.
# - Restore that saved time when JMRI starts if the TAS saved-startup option is enabled.
#
# JMRI 5.14 / Jython 2.7. ASCII only. Thread-safe. No absolute paths.

import os
import re
import jmri
from java.util import Calendar, Date
from java.lang import System
from javax.swing import Timer

try:
    import TASBeanLookup as TBL
except Exception:
    TBL = None

IMFastClockUseSavedStartup = 'TASFASTCLOCKUSESAVEDSTARTUP'
IMFastClockSavedTime = 'TASSAVEDFASTCLOCKTIME'
STATE_FILE = 'profile:jython/config/TASFastClockState.txt'
_TaskRegistered = False
_ShutdownTaskJvmKey = 'tas.fastclockstartup.shutdown.registered'
_ApplyJvmKey = 'tas.fastclockstartup.apply.started'


def _ParseBoolText(value, defaultValue=None):
    try:
        if value is None:
            return defaultValue
        s = str(value).strip().lower()
    except Exception:
        return defaultValue
    if s in ['1', 'true', 'yes', 'y', 'on', 'enabled']:
        return True
    if s in ['0', 'false', 'no', 'n', 'off', 'disabled']:
        return False
    return defaultValue


def GetLiveOnlyMode():
    try:
        return bool(globals().get('TAS_FASTCLOCK_STARTUP_LIVE_ONLY', False))
    except Exception:
        return False


def GetJvmFlag(name):
    try:
        return str(System.getProperty(str(name), '')).strip().lower() == 'true'
    except Exception:
        return False


def SetJvmFlag(name):
    try:
        System.setProperty(str(name), 'true')
    except Exception:
        pass

def GetRegisterOnlyMode():
    try:
        return bool(globals().get('TAS_FASTCLOCK_STARTUP_REGISTER_ONLY', False))
    except Exception:
        return False

def GetShutDownManager():
    try:
        return jmri.InstanceManager.getDefault(jmri.ShutDownManager)
    except Exception:
        return None

def LoadState():
    state = {'useSavedStartup': None, 'clockText': None}
    path = GetStateFilePath()
    if path is None:
        return state
    try:
        if not os.path.isfile(path):
            return state
        fh = open(path, 'r')
        try:
            raw = fh.read()
        finally:
            fh.close()
    except Exception as ex:
        Log('Could not read fast clock state: ' + str(ex))
        return state
    try:
        text = '' if raw is None else str(raw)
    except Exception:
        text = ''
    lines = [ln.strip() for ln in text.replace('\r\n', '\n').replace('\r', '\n').split('\n') if ln.strip() != '']
    if len(lines) == 0:
        return state
    hasPairs = False
    for line in lines:
        if '=' in line:
            hasPairs = True
            break
    if not hasPairs:
        state['clockText'] = lines[0]
        return state
    for line in lines:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        keyLower = str(key).strip().lower()
        value = str(value).strip()
        if keyLower == 'usesavedstartup':
            state['useSavedStartup'] = _ParseBoolText(value, None)
        elif keyLower == 'clocktext':
            state['clockText'] = value
    return state


def SaveState(state):
    if state is None:
        return False
    if not EnsureStateDir():
        return False
    path = GetStateFilePath()
    if path is None:
        return False
    try:
        useSavedStartup = state.get('useSavedStartup', None)
    except Exception:
        useSavedStartup = None
    try:
        clockText = state.get('clockText', None)
    except Exception:
        clockText = None
    lines = []
    if useSavedStartup is not None:
        lines.append('useSavedStartup=' + ('true' if bool(useSavedStartup) else 'false'))
    if clockText is not None and str(clockText).strip() != '':
        lines.append('clockText=' + str(clockText).strip())
    try:
        fh = open(path, 'w')
        try:
            if len(lines) > 0:
                fh.write('\n'.join(lines) + '\n')
            else:
                fh.write('')
        finally:
            fh.close()
        return True
    except Exception as ex:
        Log('Could not write fast clock state: ' + str(ex))
        return False


def PersistUseSavedStartupChoice(enabled):
    state = LoadState()
    state['useSavedStartup'] = bool(enabled)
    SaveState(state)


def SyncSavedStartupChoiceToMemory():
    state = LoadState()
    saved = state.get('useSavedStartup', None)
    if saved is None:
        return
    try:
        SafeSetMemoryValue(IMFastClockUseSavedStartup, 'true' if bool(saved) else 'false')
    except Exception:
        pass


def Log(msg):
    try:
        print('[TASFastClock] ' + str(msg))
    except Exception:
        pass


def SafeGetMemoryValue(name, defaultValue=''):
    try:
        if TBL is not None:
            return TBL.SafeGetOrCreateMemoryValue(name, defaultValue)
    except Exception:
        pass
    try:
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        if mm is None:
            return defaultValue
        mem = None
        try:
            mem = mm.getMemory('IM' + str(name))
        except Exception:
            mem = None
        if mem is None:
            try:
                mem = mm.provideMemory('IM' + str(name))
            except Exception:
                mem = None
        if mem is None:
            return defaultValue
        val = mem.getValue()
        if val is None:
            return defaultValue
        return val
    except Exception:
        return defaultValue


def SafeSetMemoryValue(name, value):
    try:
        if TBL is not None:
            TBL.SafeSetMemoryValue(name, value)
            return
    except Exception:
        pass
    try:
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        if mm is None:
            return
        mem = None
        try:
            mem = mm.provideMemory('IM' + str(name))
        except Exception:
            mem = None
        if mem is not None:
            mem.setValue(value)
    except Exception:
        pass


def GetStateFilePath():
    try:
        return jmri.util.FileUtil.getExternalFilename(STATE_FILE)
    except Exception:
        return None


def EnsureStateDir():
    try:
        path = GetStateFilePath()
        if path is None:
            return False
        d = os.path.dirname(str(path))
        if d is None or str(d).strip() == '':
            return False
        if not os.path.isdir(d):
            os.makedirs(d)
        return True
    except Exception as ex:
        Log('Could not create state directory: ' + str(ex))
        return False


def GetTimebase():
    try:
        return jmri.InstanceManager.getDefault(jmri.Timebase)
    except Exception:
        return None


def UseSavedStartupEnabled():
    memValue = _ParseBoolText(SafeGetMemoryValue(IMFastClockUseSavedStartup, None), None)
    state = LoadState()
    stateValue = state.get('useSavedStartup', None)
    if stateValue is None:
        if memValue is not None:
            PersistUseSavedStartupChoice(bool(memValue))
            return bool(memValue)
        return False
    if memValue is None or bool(memValue) != bool(stateValue):
        try:
            SafeSetMemoryValue(IMFastClockUseSavedStartup, 'true' if bool(stateValue) else 'false')
        except Exception:
            pass
    return bool(stateValue)


def FormatDateToClockText(d):
    try:
        cal = Calendar.getInstance()
        cal.setTime(d)
        return '%02d:%02d' % (cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE))
    except Exception:
        return ''


def ParseClockTextToDate(text, fallbackDate=None):
    if fallbackDate is None:
        fallbackDate = Date()
    try:
        s = '' if text is None else str(text).strip()
    except Exception:
        s = ''
    if s == '':
        return None
    try:
        s = re.sub(r'\s+', ' ', s)
    except Exception:
        pass
    if len(s) > 0 and s[-1:].lower() == 'h':
        s = s[:-1].strip()
    m = re.match(r'^\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?\s*$', s, re.IGNORECASE)
    if m is None:
        return None
    try:
        hour = int(m.group(1))
        minute = int(m.group(2))
    except Exception:
        return None
    ampm = m.group(4)
    if minute < 0 or minute > 59 or hour < 0 or hour > 24:
        return None
    if ampm is not None:
        ap = str(ampm).strip().lower()
        if hour < 1 or hour > 12:
            return None
        hour = hour % 12
        if ap == 'pm':
            hour += 12
    else:
        if hour == 24:
            hour = 0
    cal = Calendar.getInstance()
    cal.setTime(fallbackDate)
    cal.set(Calendar.HOUR_OF_DAY, hour)
    cal.set(Calendar.MINUTE, minute)
    cal.set(Calendar.SECOND, 0)
    cal.set(Calendar.MILLISECOND, 0)
    return cal.getTime()


def LoadSavedClockText():
    state = LoadState()
    clockText = state.get('clockText', None)
    if clockText is None:
        return None
    try:
        text = str(clockText).strip()
    except Exception:
        text = ''
    return text if text != '' else None


def SaveSavedClockText(clockText):
    if clockText is None:
        return False
    state = LoadState()
    state['clockText'] = str(clockText).strip()
    return SaveState(state)

class PersistFastClockTask(jmri.implementation.AbstractShutDownTask):
    def run(self):
        try:
            if not UseSavedStartupEnabled():
                return True
            PersistUseSavedStartupChoice(True)
            tb = GetTimebase()
            if tb is None:
                Log('No timebase available during shutdown; nothing saved')
                return True
            now = tb.getTime()
            clockText = FormatDateToClockText(now)
            if clockText == '':
                Log('Could not format fast clock time during shutdown')
                return True
            SafeSetMemoryValue(IMFastClockSavedTime, clockText)
            if SaveSavedClockText(clockText):
                Log('Saved fast clock time ' + clockText)
            return True
        except Exception as ex:
            Log('Shutdown save failed: ' + str(ex))
            return True


def RegisterShutdownTaskOnce():
    global _TaskRegistered
    if _TaskRegistered or GetJvmFlag(_ShutdownTaskJvmKey):
        _TaskRegistered = True
        return
    try:
        sdm = GetShutDownManager()
        if sdm is None:
            Log('Could not register shutdown task: ShutDownManager unavailable')
            return
        sdm.register(PersistFastClockTask('TASFastClockPersistence'))
        _TaskRegistered = True
        SetJvmFlag(_ShutdownTaskJvmKey)
        Log('Registered fast clock shutdown task')
    except Exception as ex:
        Log('Could not register shutdown task: ' + str(ex))

def EnsureShutdownTaskRegistered():
    RegisterShutdownTaskOnce()

def ApplySavedStartupTimeOnce():
    if GetLiveOnlyMode():
        Log('Live-only mode: registered shutdown saver without applying saved startup time')
        return
    if GetJvmFlag(_ApplyJvmKey):
        return
    if not UseSavedStartupEnabled():
        return
    SetJvmFlag(_ApplyJvmKey)
    state = {'attempts': 0, 'done': False, 'timer': None}

    def StopTimer():
        try:
            if state['timer'] is not None:
                state['timer'].stop()
        except Exception:
            pass
        state['timer'] = None

    def Tick(e=None):
        if state['done']:
            StopTimer()
            return
        state['attempts'] += 1
        tb = GetTimebase()
        if tb is None:
            if state['attempts'] >= 20:
                StopTimer()
            return
        try:
            if hasattr(tb, 'getIsInitialized') and (not tb.getIsInitialized()):
                if state['attempts'] >= 20:
                    StopTimer()
                return
        except Exception:
            pass
        savedText = LoadSavedClockText()
        if savedText is None:
            savedText = SafeGetMemoryValue(IMFastClockSavedTime, '')
        target = ParseClockTextToDate(savedText, Date())
        if target is None:
            Log('Saved fast clock time not available; leaving native JMRI start-up setting unchanged')
            state['done'] = True
            StopTimer()
            return
        try:
            if hasattr(tb, 'userSetTime'):
                tb.userSetTime(target)
            else:
                tb.setTime(target)
            SafeSetMemoryValue(IMFastClockSavedTime, FormatDateToClockText(tb.getTime()))
            Log('Applied saved fast clock startup time ' + FormatDateToClockText(target))
        except Exception as ex:
            Log('Could not apply saved fast clock startup time: ' + str(ex))
        state['done'] = True
        StopTimer()

    try:
        state['timer'] = Timer(500, lambda e: Tick(e))
        state['timer'].setRepeats(True)
        state['timer'].start()
    except Exception:
        try:
            Tick(None)
        except Exception:
            pass


SyncSavedStartupChoiceToMemory()
RegisterShutdownTaskOnce()
if GetRegisterOnlyMode():
    Log('Register-only mode: registered shutdown saver without applying saved startup time')
else:
    ApplySavedStartupTimeOnce()
