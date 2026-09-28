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
# RN -> RosterID association, one-to-one by roster, many RNs allowed over time but only one active at once.
# ASCII only; keep it simple and thread-aware.

import threading
import json
import os
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

# Internal map and lock
_register = {}
_lock = threading.RLock()

_SAVE_PATH = None
try:
    # Use JMRI scheme resolution (still profile-root; non-breaking)
    _SAVE_PATH = FileUtil.getExternalFilename("profile:train_locator_register.json")
except Exception:
    _SAVE_PATH = None
if not _SAVE_PATH:
    _SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "train_locator_register.json")

def registerTrain(reportingNumber, rosterId):
    # Overwrite RN->RosterId, and remove any other RN that points to this rosterId.
    if reportingNumber is None or rosterId is None:
        return
    rn = str(reportingNumber).strip()
    rid = str(rosterId).strip()
    if rn == "" or rid == "":
        return
    with _lock:
        # Remove any other RN mapped to the same rosterId
        stale = [k for k, v in _register.items() if v == rid and k != rn]
        for k in stale:
            try:
                del _register[k]
            except Exception:
                pass
        # Set/overwrite this RN
        _register[rn] = rid

def deregisterTrain(reportingNumber):
    if reportingNumber is None:
        return
    rn = str(reportingNumber).strip()
    if rn == "":
        return
    with _lock:
        try:
            del _register[rn]
        except Exception:
            pass

def deregisterByRosterId(rosterId):
    if rosterId is None:
        return
    rid = str(rosterId).strip()
    if rid == "":
        return
    with _lock:
        stale = [k for k, v in _register.items() if v == rid]
        for k in stale:
            try:
                del _register[k]
            except Exception:
                pass

def getRosterId(reportingNumber):
    if reportingNumber is None:
        return None
    rn = str(reportingNumber).strip()
    if rn == "":
        return None
    with _lock:
        return _register.get(rn)

def reverseLookup(rosterId):
    # Return the RN currently mapped to rosterId (or None)
    if rosterId is None:
        return None
    rid = str(rosterId).strip()
    if rid == "":
        return None
    with _lock:
        for k, v in _register.items():
            if v == rid:
                return k
    return None

def snapshot():
    # Shallow copy for diagnostics
    with _lock:
        return dict(_register)


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
    with _lock:
        d = {}
        for k, v in _register.items():
            d[str(k)] = str(v)
    tmpPath = _SAVE_PATH + ".tmp"
    try:
        with open(tmpPath, "w") as f:
            json.dump(d, f)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        if not _AtomicReplace(tmpPath, _SAVE_PATH):
            try:
                if os.path.exists(tmpPath):
                    os.remove(tmpPath)
            except Exception:
                pass
            print("Warning: failed to save train_locator_register.json: atomic replace failed")
    except Exception as e:
        try:
            if os.path.exists(tmpPath):
                os.remove(tmpPath)
        except Exception:
            pass
        print("Warning: failed to save train_locator_register.json: " + str(e))


def load():
    if not os.path.exists(_SAVE_PATH):
        return
    try:
        with open(_SAVE_PATH, "r") as f:
            d = json.load(f)
    except Exception as ex:
        try:
            from java.lang import System
            stamp = str(System.currentTimeMillis())
        except Exception:
            import time
            stamp = str(int(time.time() * 1000))
        badPath = _SAVE_PATH + ".bad." + stamp
        try:
            _AtomicReplace(_SAVE_PATH, badPath)
        except Exception:
            pass
        print("Warning: failed to load train_locator_register.json from " + str(_SAVE_PATH) + ": " + str(ex))
        with _lock:
            _register.clear()
        return
    with _lock:
        _register.clear()
        if isinstance(d, dict):
            for k, v in d.items():
                _register[str(k)] = str(v)


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