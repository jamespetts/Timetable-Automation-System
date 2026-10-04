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
# Class for storing data as to what trains are specified
# to form what next services (e.g., the 2L41 0641 down arrival 
# forms the 2N05 0643 up departure).

import jmri, os, json
from java.util import Hashtable
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

register = Hashtable()
_SAVE_PATH = None
try:
    # Use JMRI scheme resolution (still profile-root; non-breaking)
    _SAVE_PATH = FileUtil.getExternalFilename("profile:formation_register.json")
except Exception:
    _SAVE_PATH = None
if not _SAVE_PATH:
    _SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "formation_register.json")

def registerNextFormation(nextReportingNumber, rosterId):
    register.put(nextReportingNumber, rosterId)


def getTrainForFormation(nextReportingNumber):
    return register.get(nextReportingNumber)


def deregisterTrain(nextReportingNumber):
    register.remove(nextReportingNumber)


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
    d = {}
    for k in register.keySet().toArray():
        d[str(k)] = str(register.get(k))
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
            print("Warning: failed to save formation_register.json: atomic replace failed")
    except Exception as e:
        try:
            if os.path.exists(tmpPath):
                os.remove(tmpPath)
        except Exception:
            pass
        print("Warning: failed to save formation_register.json: " + str(e))


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
        print("Warning: failed to load formation_register.json from " + str(_SAVE_PATH) + ": " + str(ex))
        register.clear()
        return
    register.clear()
    if isinstance(d, dict):
        for k, v in d.items():
            register.put(k, v)


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
