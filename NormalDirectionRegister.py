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
# NormalDirectionRegister: lightweight mapping of RosterID -> "normal" direction (string).
# - ASCII only
# - Portable paths (JMRI profile)
# - Minimal surface area; durable JSON persistence

import os, json
import jmri
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

# Internal map:
# Keys: roster IDs normalised to lowercase for case-insensitive matching
# Values: direction string (stored verbatim as provided, after stripping)
_dirMap = {}

# Persist to the active profile folder (no absolute paths)
_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "normalDirectionRegister.json")


# --- Helpers -----------------------------------------------------------------

def _NormId(s):
    # Case-insensitive keys as per James's general rule
    try:
        return str(s).strip().lower()
    except:
        return ""

def _CleanDirection(s):
    # Keep verbatim, but strip surrounding whitespace
    try:
        return str(s).strip()
    except:
        return ""


# --- Public API (CamelCase) ---------------------------------------------------

def SetNormalDirection(RosterId, Direction):
    """
    Set or update the normal direction string for the given roster ID.
    """
    k = _NormId(RosterId)
    if k == "":
        return
    _dirMap[k] = _CleanDirection(Direction)

def GetNormalDirection(RosterId, Default=None):
    """
    Get the normal direction string for the given roster ID (case-insensitive).
    Returns Default (None if not supplied) if no mapping exists.
    """
    k = _NormId(RosterId)
    if k == "":
        return Default
    return _dirMap.get(k, Default)
    

def ToggleNormalDirection(RosterId, A="UP", B="DOWN"):
    """
    Toggle the stored direction for the given roster ID between A and B.

    Behaviour:
    - If current value equals A (case-insensitive), switch to B.
    - If current value equals B (case-insensitive), switch to A.
    - If no value exists or it is neither A nor B, set to A.
    Returns the new direction string.
    """
    k = _NormId(RosterId)
    if k == "":
        return None

    a = _CleanDirection(A)
    b = _CleanDirection(B)
    cur = _dirMap.get(k, "")

    curNorm = _CleanDirection(cur).lower()
    if curNorm == a.lower():
        _dirMap[k] = b
        return b
    elif curNorm == b.lower():
        _dirMap[k] = a
        return a
    else:
        _dirMap[k] = a
        return a


def RemoveNormalDirection(RosterId):
    """
    Remove any stored direction for the given roster ID; no error if missing.
    """
    k = _NormId(RosterId)
    if k in _dirMap:
        try:
            del _dirMap[k]
        except Exception:
            pass

def ClearAll():
    """
    Remove all mappings.
    """
    _dirMap.clear()

def Count():
    """
    Number of mappings stored.
    """
    return len(_dirMap)

def GetCopy():
    """
    Return a shallow copy of the current map as a Python dict:
    { lowercased_roster_id : direction_string }
    """
    return dict(_dirMap)

def ListIds():
    """
    Return a list of all (lowercased) roster IDs present in the register.
    """
    return list(_dirMap.keys())


# --- Persistence --------------------------------------------------------------

def Save():
    """
    Persist the map to JSON in the profile folder; best-effort atomic replace.
    """
    tmp_path = _SAVE_PATH + ".tmp"
    try:
        # Write temp file first
        with open(tmp_path, "w") as f:
            json.dump(_dirMap, f)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass

        # Prefer Java NIO atomic move when available
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
        print("Warning: failed to save normalDirectionRegister.json: {0}".format(e))

def Load():
    """
    Load the map from JSON, if present. Starts empty if not readable.
    """
    if not os.path.exists(_SAVE_PATH):
        return
    import time
    attempts = 3
    for _ in range(attempts):
        try:
            with open(_SAVE_PATH, "r") as f:
                loaded = json.load(f)
                # Ensure dict-of-strings only; ignore malformed entries
                if isinstance(loaded, dict):
                    _dirMap.clear()
                    for k, v in loaded.items():
                        nk = _NormId(k)
                        if nk != "":
                            _dirMap[nk] = _CleanDirection(v)
                return
        except ValueError:
            # Possibly a concurrently written/empty file; brief backoff and retry
            time.sleep(0.1)
            continue
        except Exception as e:
            print("Warning: failed to load normalDirectionRegister.json: {0}".format(e))
            return
    # Final fallback
    print("Warning: normalDirectionRegister.json not readable (giving up); starting empty")
    _dirMap.clear()


# --- Shutdown registration (like your enqueuedWorkings) -----------------------

def _RegisterShutdown():
    try:
        ShutDownManager.instance().addShutdownTask(Save)
        return
    except Exception:
        pass
    try:
        class _Saver(Runnable):
            def run(self):
                try:
                    Save()
                except Exception:
                    pass
        Runtime.getRuntime().addShutdownHook(Thread(_Saver()))
    except Exception:
        pass


# Load at import, save on shutdown
_RegisterShutdown()
Load()
