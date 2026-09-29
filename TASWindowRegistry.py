
# -*- coding: ascii -*-
# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the 
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General 
# Public License for more details.

# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>. 
#
#
# Window registry for the main menu toggle buttons.
# JMRI 5.12 / Jython 2.7. ASCII only.
#
# The main menu buttons run other scripts. Each of those scripts builds and
# shows its own window or windows. This module records the windows that appear
# while a script runs, keyed by main menu button, so that a second press of the
# same button closes those windows instead of running the script again.
#
# Windows are found by comparing java.awt.Window.getWindows() before and after
# the script runs, so no change to the individual scripts is required.
# Every function here must be called on the Event Dispatch Thread.

import java.util
from java.awt import Dialog, Window
from javax.swing import SwingUtilities, Timer

# A script may build its window on a worker thread, so recording is repeated for a
# short time after the script has run.
RECORD_POLL_TICKS = 20
RECORD_POLL_MS = 100

# Key -> list of tracked java.awt.Window objects
_Tracked = {}

# The timer of the poll that is running now, or None
_PollTimer = [None]

# Windows already tracked under some key, so that a window is never tracked twice
_Claimed = java.util.HashSet()

def _Snapshot():
    # Set of the windows that exist now
    try:
        known = java.util.HashSet()
        for w in Window.getWindows():
            known.add(w)
        return known
    except Exception:
        return java.util.HashSet()

def _IsOpen(w):
    # True while the window still exists on screen
    try:
        if w is None:
            return False
        return bool(w.isDisplayable())
    except Exception:
        return False

def _IsTrackable(w):
    # True for a window that a main menu button can close. Modal dialogs are
    # excluded: they take the input away from the main menu, so they cannot be
    # left open by a button press. Only java.awt.Dialog has isModal.
    if not _IsOpen(w):
        return False
    try:
        if isinstance(w, Dialog):
            return not bool(w.isModal())
    except Exception:
        pass
    return True

def _Prune(Key):
    # Forget windows that the user has already closed
    try:
        kept = []
        for w in _Tracked.get(Key, []):
            if _IsOpen(w):
                kept.append(w)
        _Tracked[Key] = kept
    except Exception:
        pass

def OpenWindows(Key):
    # The tracked windows for Key that are still open, oldest first
    _Prune(Key)
    return list(_Tracked.get(Key, []))

def AnyOpenWindow(Key):
    return len(OpenWindows(Key)) > 0

def CloseWindows(Key):
    # Dispose every tracked window for Key. Each window runs the same cleanup as
    # when the user closes it with the window close button.
    # Windows that stay open, because the user answered a close prompt, remain
    # tracked so that the next press offers to close them again.
    # Returns True when Key no longer has an open window.
    windows = OpenWindows(Key)
    for w in windows:
        try:
            w.dispose()
        except Exception:
            pass
    _Prune(Key)
    return len(windows) > 0 and len(OpenWindows(Key)) == 0

def _Record(Key, Before):
    # Track the displayable windows that appeared since the Before snapshot and
    # that are not already tracked. Returns the number of windows recorded.
    count = 0
    try:
        for w in Window.getWindows():
            try:
                if w is None:
                    continue
                if Before.contains(w):
                    continue
                if _Claimed.contains(w):
                    continue
                if not _IsTrackable(w):
                    continue
                _Claimed.add(w)
                _Tracked.setdefault(Key, []).append(w)
                count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count

def _StartPoll(Key, Before):
    # Record on a timer until the first window for Key is found. This covers a
    # script that builds its window on a worker thread. A class that extends
    # jmri.jmrit.automat.AbstractAutomaton does this, because start() runs init()
    # on a new thread.
    # Only one key is polled at a time. A poll that is still running when another
    # button opens its windows is dropped, so that it cannot claim their windows.
    try:
        if _PollTimer[0] is not None:
            _PollTimer[0].stop()
            _PollTimer[0] = None
    except Exception:
        pass
    if AnyOpenWindow(Key):
        return
    ticks = [RECORD_POLL_TICKS]
    def _Tick(e):
        _Record(Key, Before)
        ticks[0] -= 1
        if ticks[0] <= 0 or AnyOpenWindow(Key):
            try:
                if _PollTimer[0] is not None:
                    _PollTimer[0].stop()
            except Exception:
                pass
    try:
        timer = Timer(RECORD_POLL_MS, _Tick)
        timer.setRepeats(True)
        _PollTimer[0] = timer
        timer.start()
    except Exception:
        pass

def Toggle(Key, Opener):
    # Close the windows that Key opened, or run Opener and track what it opens.
    # Returns True when Opener ran, False when windows were closed.
    if AnyOpenWindow(Key):
        CloseWindows(Key)
        return False
    before = _Snapshot()
    try:
        Opener()
    finally:
        _Record(Key, before)
        try:
            if SwingUtilities.isEventDispatchThread():
                _StartPoll(Key, before)
            else:
                SwingUtilities.invokeLater(lambda: _StartPoll(Key, before))
        except Exception:
            pass
    return True
