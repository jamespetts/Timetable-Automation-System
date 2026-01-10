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
# Class for storing data for delays and cancellations to trains.
# Cancellation = delay of > 1440 minutes
import jmri, os, json
from java.util import Hashtable
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

# Thread safety: protect save/load and register mutation during persistence.
try:
    from threading import RLock
    _Lock = RLock()
except Exception:
    _Lock = None

register = Hashtable()
_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "disruption_register.json")

def registerDisruption(reportingNumber, delayMinutes):
    print("Registering", delayMinutes, "delay to", reportingNumber)
    if _Lock:
        _Lock.acquire()
    try:
        register.put(reportingNumber, delayMinutes)
    finally:
        if _Lock:
            _Lock.release()

def getDisruption(reportingNumber):
    return register.get(reportingNumber)

def deregisterDisruption(reportingNumber):
    if _Lock:
        _Lock.acquire()
    try:
        register.remove(reportingNumber)
    finally:
        if _Lock:
            _Lock.release()

def updateDisruption(reportingNumber, newDelayMinutes):
    if _Lock:
        _Lock.acquire()
    try:
        if register.containsKey(reportingNumber):
            register.put(reportingNumber, newDelayMinutes)
            return True  # Indicate success
        else:
            return False  # Indicate failure (train not found)
    finally:
        if _Lock:
            _Lock.release()

def _AtomicReplace(srcPath, dstPath):
    # Atomic replace where possible. On Windows, os.rename() cannot replace an existing file.
    # Use java.nio.file.Files.move with REPLACE_EXISTING (+ ATOMIC_MOVE when supported).
    try:
        from java.nio.file import Files, Paths
        from java.nio.file import StandardCopyOption
        sp = Paths.get(srcPath)
        dp = Paths.get(dstPath)
        try:
            Files.move(sp, dp, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        except Exception:
            Files.move(sp, dp, StandardCopyOption.REPLACE_EXISTING)
        return True
    except Exception:
        try:
            # Best-effort fallback
            if os.path.exists(dstPath):
                try:
                    os.remove(dstPath)
                except Exception:
                    pass
            os.rename(srcPath, dstPath)
            return True
        except Exception:
            return False

def save():
    if _Lock:
        _Lock.acquire()
    try:
        d = {}
        for k in register.keySet().toArray():
            d[str(k)] = int(register.get(k))
        # Write to a temp file then atomically replace. Prevents partial writes and JSON corruption.
        tmpPath = _SAVE_PATH + ".tmp"
        with open(tmpPath, "w") as f:
            json.dump(d, f)
            try:
                f.flush()
            except Exception:
                pass
        if not _AtomicReplace(tmpPath, _SAVE_PATH):
            # If replace failed, try to clean up tmp.
            try:
                os.remove(tmpPath)
            except Exception:
                pass
    finally:
        if _Lock:
            _Lock.release()

def load():
    if not os.path.exists(_SAVE_PATH):
        return
    if _Lock:
        _Lock.acquire()
    try:
        try:
            with open(_SAVE_PATH, "r") as f:
                d = json.load(f)
        except Exception as ex:
            # Corrupt JSON (e.g. "Extra data") can happen if a previous save was interrupted or interleaved.
            # Preserve the bad file for forensic analysis and continue with an empty register.
            try:
                from java.lang import System
                stamp = str(System.currentTimeMillis())
            except Exception:
                import time
                stamp = str(int(time.time() * 1000))
            badPath = _SAVE_PATH + ".bad." + stamp
            try:
                # Best effort: move aside.
                _AtomicReplace(_SAVE_PATH, badPath)
            except Exception:
                pass
            print("[DisruptionRegister] Warning: failed to load JSON from", _SAVE_PATH, "::", ex)
            register.clear()
            return

        register.clear()
        if isinstance(d, dict):
            for k, v in d.items():
                try:
                    register.put(k, int(v))
                except Exception:
                    register.put(k, 0)
    finally:
        if _Lock:
            _Lock.release()

# Try JMRI shutdown manager, fall back to JVM hook
def _register_shutdown():
    try:
        ShutDownManager.instance().addShutdownTask(save)
        return
    except Exception:
        pass
    try:
        class _Saver(Runnable):
            def run(self):
                try:
                    save()
                except Exception:
                    pass
        Runtime.getRuntime().addShutdownHook(Thread(_Saver()))
    except Exception:
        pass

# Register to save on shutdown on module import
_register_shutdown()

# Load on module import
load()
