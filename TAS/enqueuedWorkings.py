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
# Note that each entry is a tuple of reportingNumber and direction

import jmri, os, json
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

workings = []

_SAVE_PATH = None
try:
    # Use JMRI scheme resolution (still profile-root; non-breaking)
    _SAVE_PATH = FileUtil.getExternalFilename("profile:enqueuedWorkings.json")
except Exception:
    _SAVE_PATH = None
if not _SAVE_PATH:
    _SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "enqueuedWorkings.json")
def enqueueWorking(reportingNumber, direction):
    if (reportingNumber, direction) not in workings:
        workings.append((reportingNumber, direction))
    else:
        print("Warning: attempting to append a duplicate working to the workings queue " + reportingNumber + " with direction " + direction)
    
def getEnqueuedWorking(index):
    return workings[index]

def dequeueWorking(reportingNumber, direction):
     workings.remove((reportingNumber, direction))
     
def popWorking(reportingNumber, direction):
    try:
        idx = workings.index((reportingNumber, direction))
    except ValueError:
        return (None, None)
    
    return workings.pop(idx)

def getEnqueuedWorkingsCopy():
    return workings[:]
     
def countWorkings():
    return len(workings)
    
def ClearWorkings():
    workings[:] = []
   

def save():
    # Tuples are JSON-serialised as lists
    data = list(workings)  # shallow copy to avoid surprises

    tmp_path = _SAVE_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass

        # Prefer Java NIO atomic replace if available
        try:
            from java.nio.file import Files, Paths, StandardCopyOption
            Files.move(
                Paths.get(tmp_path), Paths.get(_SAVE_PATH),
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE
            )
        except Exception:
            # Fallback: best-effort replace
            try:
                if os.path.exists(_SAVE_PATH):
                    os.remove(_SAVE_PATH)
            except Exception:
                pass
            os.rename(tmp_path, _SAVE_PATH)

    except Exception as e:
        # Clean up temp on failure
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        print("Warning: failed to save enqueuedWorkings.json: {}".format(e))

def load():
    if not os.path.exists(_SAVE_PATH):
        return

    # Try a couple of times in case we race a writer or see a transient empty file
    import time
    attempts = 3
    for _ in range(attempts):
        try:
            with open(_SAVE_PATH, "r") as f:
                loaded = json.load(f)
            # Convert lists back to tuples so membership/remove work consistently
            workings[:] = [tuple(x) for x in loaded]
            return
        except ValueError:
            # JSON incomplete/empty; brief backoff and retry
            time.sleep(0.1)
            continue
        except Exception as e:
            print("Warning: failed to load enqueuedWorkings.json: {}".format(e))
            return

    # Final fallback: start empty rather than crash the importer
    print("Warning: enqueuedWorkings.json not readable (giving up); starting with empty queue")
    workings[:] = []

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

# Register to save on shutdown and load on import
_register_shutdown()
load()
