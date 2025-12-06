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

# Internal map and lock
_register = {}
_lock = threading.RLock()

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