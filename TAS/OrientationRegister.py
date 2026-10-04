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
# Note that each entry is a tuple of reportingNumber and direction

import jmri, os, json, sys, threading, time
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

orientation = []
_load_ok = False
_had_file = False
_SAVE_PATH = None
try:
    # Use JMRI scheme resolution (still profile-root; non-breaking)
    _SAVE_PATH = FileUtil.getExternalFilename("profile:OrientationRegister.json")
except Exception:
    _SAVE_PATH = None
if not _SAVE_PATH:
    _SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "OrientationRegister.json")
_SAVE_LOCK = threading.RLock()
# Move retry policy. A layout power cycle makes every RailCom reporter
# announce at once, so several saves run in quick succession while file
# scanners or sync tools can briefly hold the stored file open on Windows.
# The atomic move is always attempted first on every attempt.
_MOVE_ATTEMPTS = 3
_MOVE_RETRY_DELAY = 0.2
def AddTrain(rosterID):
    if rosterID not in orientation:
        orientation.append(rosterID)
    else:
        print("Warning: attempting to append a duplicate train to the orientation register: " + rosterID)
    
def GetTrain(index):
    return orientation[index]

def RemoveTrain(rosterID):
     orientation.remove(rosterID)
     
def GetOrientationRegisterCopy():
    return orientation[:]
     
def CountTrains():
    return len(orientation)
    
def IsContained(rosterID):
    return rosterID in orientation
    
def _error_text(default):
    # Describes the error being handled. Never raises, so it is safe to
    # call from any handler, including handlers for Java errors. A bare
    # except is used throughout this file because Java errors are not
    # Python Exception types, so except Exception does not catch them.
    try:
        detail = sys.exc_info()[1]
        if detail is None:
            return default
        return "{}: {}".format(default, detail)
    except:
        return default

def _warn(text):
    # Writes text on the console. Never raises.
    try:
        print(text)
    except:
        pass

def _warn_save_failed():
    _warn(_error_text("Warning: failed to save OrientationRegister.json"))

def _cleanup_tmp(tmp_path):
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except:
        pass

def _move_tmp_into_place(tmp_path, dest_path):
    # Moves tmp_path onto dest_path. Returns None on success, else an error
    # description. The atomic move is attempted first on every attempt, with
    # a short delay between attempts when the file is briefly held open.
    from java.nio.file import Files, Paths, StandardCopyOption
    last_error = "move failed"
    attempt = 0
    while attempt < _MOVE_ATTEMPTS:
        attempt += 1
        try:
            Files.move(
                Paths.get(tmp_path), Paths.get(dest_path),
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE
            )
            return None
        except:
            last_error = _error_text("move failed")
        try:
            Files.move(
                Paths.get(tmp_path), Paths.get(dest_path),
                StandardCopyOption.REPLACE_EXISTING
            )
            return None
        except:
            last_error = _error_text("move failed")
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(tmp_path, dest_path)
            return None
        except:
            last_error = _error_text("move failed")
        if attempt < _MOVE_ATTEMPTS:
            try:
                time.sleep(_MOVE_RETRY_DELAY)
            except:
                pass
    return "move failed after {} attempts: {}".format(_MOVE_ATTEMPTS, last_error)

def save():
    # Writes the list of strings as JSON through a temporary file, so a crash
    # mid-write cannot truncate the stored file. Refuses to overwrite a stored file
    # that was never read successfully, so a session that failed to load cannot
    # destroy data at shutdown. Never raises: callers include a LocoNet listener
    # running on the AWT event dispatch thread, where a raised error is reported
    # as an uncaught exception.
    try:
        _save_inner()
    except:
        _warn_save_failed()

def _save_inner():
    global _load_ok
    if _had_file and not _load_ok:
        print("Warning: not saving OrientationRegister.json: "
              "the stored file was never read successfully")
        return
    tmp_path = _SAVE_PATH + ".tmp"
    try:
        with _SAVE_LOCK:
            with open(tmp_path, "w") as f:
                json.dump(list(orientation), f)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except:
                    pass
            move_error = _move_tmp_into_place(tmp_path, _SAVE_PATH)
            if move_error is not None:
                _cleanup_tmp(tmp_path)
                _warn("Warning: failed to save OrientationRegister.json: {}".format(move_error))
    except:
        _cleanup_tmp(tmp_path)
        _warn_save_failed()

def load():
    # Load list of strings directly. A failed read keeps existing memory rather than
    # wiping it, so a transient failure can never destroy data at shutdown.
    global _load_ok, _had_file
    if not os.path.exists(_SAVE_PATH):
        _had_file = False
        _load_ok = True
        orientation[:] = []
        return
    _had_file = True
    try:
        with open(_SAVE_PATH, "r") as f:
            loaded = json.load(f)
        # Ensure the loaded data is a list of strings; swap only on success
        fresh = [str(x) for x in loaded]
        orientation[:] = fresh
        _load_ok = True
    except Exception as e:
        print("Warning: failed to load OrientationRegister.json: {}".format(e))
        print("Warning: keeping orientation data already in memory")

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
