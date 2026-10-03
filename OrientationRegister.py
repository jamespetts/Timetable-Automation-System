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

import jmri, os, json
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
    
def save():
    # Writes the list of strings as JSON through a temporary file, so a crash
    # mid-write cannot truncate the stored file. Refuses to overwrite a stored file
    # that was never read successfully, so a session that failed to load cannot
    # destroy data at shutdown.
    global _load_ok
    if _had_file and not _load_ok:
        print("Warning: not saving OrientationRegister.json: "
              "the stored file was never read successfully")
        return
    tmp_path = _SAVE_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(list(orientation), f)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        try:
            from java.nio.file import Files, Paths, StandardCopyOption
            Files.move(
                Paths.get(tmp_path), Paths.get(_SAVE_PATH),
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE
            )
        except Exception:
            try:
                if os.path.exists(_SAVE_PATH):
                    os.remove(_SAVE_PATH)
            except Exception:
                pass
            os.rename(tmp_path, _SAVE_PATH)
    except Exception as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        print("Warning: failed to save OrientationRegister.json: {}".format(e))

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
