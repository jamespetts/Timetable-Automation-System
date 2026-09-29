Read when: Task concerns TASWindowRegistry.py, main menu button toggles, closing windows opened by a main menu button, or tracking windows opened by a script run from RunExternalScript.

# TASWindowRegistry.py

File: TASWindowRegistry.py. Lines: 188. Imported module, not a start-up script, so its names are safe from the shared Jython namespace described in ai/details/startup-power-warnings.md.

Purpose: record the windows that a main menu button opens, so that a second press of the same button closes them instead of running the script again.

Module state:
- _Tracked is a Python dict mapping a button key to a list of java.awt.Window.
- _PollTimer holds the timer of the poll that is running now, or None.
- _Claimed is a java.util.HashSet of every window ever tracked, so that a window is never tracked under two keys.
- RECORD_POLL_TICKS = 20 and RECORD_POLL_MS = 100, so a poll lasts at most two seconds.

Functions:
- _Snapshot() returns a java.util.HashSet holding every entry of java.awt.Window.getWindows().
- _IsOpen(w) returns True while w is displayable.
- _IsTrackable(w) returns True when w is displayable and, for a java.awt.Dialog, not modal. Modal dialogs are excluded because they hold the input away from the main menu. Only java.awt.Dialog declares isModal, so a plain frame is accepted without that test.
- _Prune(Key) drops the tracked windows for Key that are no longer displayable.
- OpenWindows(Key) returns the still open tracked windows for Key, oldest first.
- AnyOpenWindow(Key) returns True when Key has at least one open window.
- CloseWindows(Key) disposes every open tracked window for Key and returns True when none is left open. A window that stays open, because the user answered a close prompt, stays tracked.
- _Record(Key, Before) tracks each displayable, non-modal window that Window.getWindows() reports and that Before does not contain and that is not already in _Claimed. Returns the number recorded.
- _StartPoll(Key, Before) stops the poll that is running, then starts a repeating javax.swing.Timer that calls _Record every RECORD_POLL_MS until Key has a window or RECORD_POLL_TICKS have passed. It does nothing when Key already has an open window.
- Toggle(Key, Opener) closes the windows of Key when AnyOpenWindow(Key) is True and returns False. Otherwise it snapshots the windows, runs Opener, records the windows that appeared, starts the poll, and returns True. The record and the poll start also run when Opener raises.

Threading: every function must be called on the Event Dispatch Thread. Window.getWindows() is read only there. The main menu action listeners satisfy this because Swing runs them on the Event Dispatch Thread. Toggle posts the poll start through SwingUtilities.invokeLater when it is not on the Event Dispatch Thread.

Why the poll exists: a script may build its window on a worker thread. A class that extends jmri.jmrit.automat.AbstractAutomaton does this, because start() runs init() on a new thread. WeatherForecastUIApp.py and WeatherForecastUINewspaper.py are the two such scripts, used by the weather button. Only one key is polled at a time so that a poll that is still running cannot claim the windows of a later button press.

Closing uses java.awt.Window.dispose(). That posts a window closed event, so each script runs the same cleanup as when the user presses the window close button. TASSetupFrame.dispose() asks about unsaved working script edits and can refuse to close, which leaves the window tracked.

No JMRI API is used. The Java APIs are java.awt.Window.getWindows, isDisplayable, isModal, dispose, java.util.HashSet, javax.swing.SwingUtilities.invokeLater and isEventDispatchThread, and javax.swing.Timer.

Callers: CoverPanel.ToggleWindows in TimetableAutomation.py only. There are no other callers.

Open question: none. Facts verified against file content, against the JMRI 5.16 source of jmri.jmrit.automat.AbstractAutomaton, and against the java.awt.Window and javax.swing class documentation in this session.
