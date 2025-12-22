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
# Note that each entry is a tuple of reportingNumber, direction, time and day of the week
import jmri, os, json, csv, re
from jmri.util import FileUtil
from java.util import Hashtable
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager
from java.util.concurrent.locks import ReentrantReadWriteLock
import TASBeanLookup as TBL

_rwlock = ReentrantReadWriteLock()
_rlock = _rwlock.readLock()
_wlock = _rwlock.writeLock()

timingRegister = Hashtable()
_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "timingRegister.json")

try:
    _meta  # if already defined, don't overwrite
except NameError:
    _meta = {}  # dict of simple key -> value, persisted by save()/load()

# --- small helpers (local; ASCII only) -----------------------------------------------------------
def _mm():
    return jmri.InstanceManager.getDefault(jmri.MemoryManager)

def _parseTimeToMinutes(text):
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    up = s.upper()
    if (up.endswith("AM") or up.endswith("PM")) and len(s) >= 4 and s[-3] != ' ':
        s = s[:-2] + ' ' + s[-2:]
    m = re.match(r'^\s*(\d{1,2}):(\d{2})\s*$', s)
    if m:
        h = int(m.group(1)); mm = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h*60 + mm
        return None
    m = re.match(r'^\s*(\d{1,2}):(\d{2})\s*([AP]\s*M)\s*$', s, re.IGNORECASE)
    if m:
        h = int(m.group(1)); mm = int(m.group(2))
        ap = m.group(3).replace(" ", "").upper()
        if h == 12:
            h = 0
        if ap.startswith("P"):
            h += 12
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h*60 + mm
        return None
    return None

def _activeProfileBaseTP():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except Exception:
        return ""

def _ttPath():
    # CURRENTTIMETABLE stores the timetable name as the Memory value (suffix-based lookup).
    ttName = str(TBL.SafeGetMemoryValue("CURRENTTIMETABLE", "")).strip()
    if not ttName:
        return None
    return os.path.join(FileUtil.getProfilePath(), "timetable", ttName + ".csv")

def _todayName():
    # DAYOFWEEK stores the current day name as the Memory value (suffix-based lookup).
    return str(TBL.SafeGetMemoryValue("DAYOFWEEK", "")).strip()

def _findRowForRNToday(reader, rnWantedLower, dayName):
    # First row with dayName == TRUE (case-insensitive) and RN match (exact string, case-insensitive)
    if not isinstance(dayName, basestring):
        dayName = str(dayName) if dayName is not None else ""
    dayKey = dayName.strip()
    for row in reader:
        try:
            if not isinstance(row, dict):
                continue
            dayField = row.get(dayKey, "")
            if str(dayField).strip().upper() != "TRUE":
                continue
            rn = (row.get("Reporting number", "") or "").strip()
            if rn.lower() == rnWantedLower:
                return row
        except Exception:
            continue
    return None

def _schedMinutesFromRow(row, tpName, isDep):
    # Choose scheduled cell case-insensitively.
    # Base TP -> use "Arr"/"Dep" columns. Non-base -> "TPArr <name>"/"TPDep <name>".
    want = "Dep" if isDep else "Arr"
    baseName = _activeProfileBaseTP()
    # Collect viable header keys (lower -> actual)
    keys = {}
    for k in row.keys():
        if not k:
            continue
        ks = str(k).strip()
        keys[ks.lower()] = ks
    if tpName and baseName and tpName.strip().lower() == baseName.lower():
        # Prefer Dep at the base; fall back to Arr if Dep blank/missing
        depK = keys.get("dep")
        arrK = keys.get("arr")
        if want == "Dep" and depK:
            m = _parseTimeToMinutes(row.get(depK))
            if m is not None:
                return m
        if arrK:
            m = _parseTimeToMinutes(row.get(arrK))
            if m is not None:
                return m
        if depK:
            m = _parseTimeToMinutes(row.get(depK))
            if m is not None:
                return m
        return None
    # Non-base TP
    low = ("tp%s %s" % (want, tpName)).lower()
    alt = ("tp%s %s" % ("dep" if want=="Arr" else "arr", tpName)).lower()
    kMain = keys.get(low)
    if kMain:
        m = _parseTimeToMinutes(row.get(kMain))
        if m is not None:
            return m
    # Fallback: if Arr missing at that TP, try Dep (or vice versa)
    kAlt = keys.get(alt)
    if kAlt:
        m = _parseTimeToMinutes(row.get(kAlt))
        if m is not None:
            return m
    return None

def registerTiming(timingPointName, reportingNumber, direction, time, day):
    print("Registering", reportingNumber, "at timing point", timingPointName, "at", time)
    _wlock.lock()
    try:
        register = timingRegister.get(timingPointName)
        if register is None:
            register = {"timings": [], "blocks": []}
            timingRegister.put(timingPointName, register)

        # Overwrite semantics:
        # Keep a single tuple per (RN, Direction, Day) at this timing point.
        rnKey = ("" if reportingNumber is None else str(reportingNumber).strip())
        dirKey = ("" if direction is None else str(direction).strip())
        dayKey = ("" if day is None else str(day).strip())

        timings = register.get("timings", [])
        if timings is None:
            timings = []
            register["timings"] = timings

        # Remove any existing entries with same RN+Dir+Day (duplicate aware)
        i = len(timings) - 1
        while i >= 0:
            try:
                rec = timings[i]
                rnr = ("" if rec[0] is None else str(rec[0]).strip())
                drr = ("" if rec[1] is None else str(rec[1]).strip())
                dyy = ("" if rec[3] is None else str(rec[3]).strip())
                if rnr == rnKey and drr == dirKey and dyy == dayKey:
                    del timings[i]
                i -= 1
            except Exception:
                i -= 1

        # Append the fresh record
        timings.append((reportingNumber, direction, time, day))
    finally:
        _wlock.unlock()

    # --- Compute and write disruption from timetable vs actual --------------------------------
    try:
        # 1) Resolve inputs
        ttPath = _ttPath()
        if not (ttPath and os.path.exists(ttPath)):
            return
        today = _todayName()
        if not today:
            return
        rnLower = (str(reportingNumber) if reportingNumber is not None else "").strip().lower()
        if rnLower == "":
            return
        actualMin = _parseTimeToMinutes(time)
        if actualMin is None:
            return

        # 2) Load first matching row for RN today
        with open(ttPath, "r") as f:
            reader = csv.DictReader(f, delimiter='\t')
            row = _findRowForRNToday(reader, rnLower, today)
        if row is None:
            return

        # 3) Decide Arr/Dep for schedule lookup.
        #    Our system logs Dep timings at virtual TPs; to be robust we prefer Dep, fallback Arr.
        #    direction here is "Up/Down"; not used to choose Arr/Dep.
        #    We detect base vs TP by name.
        tpName = (timingPointName or "").strip()
        isDepPreferred = True  # prefer Dep; fallback Arr if needed
        sched = _schedMinutesFromRow(row, tpName, isDepPreferred)
        if sched is None:
            # last resort: try Arr side
            sched = _schedMinutesFromRow(row, tpName, False)
        if sched is None:
            return

        delay = int(actualMin - sched)

        # 4) Update DisruptionRegister (respect cancellations)
        from DisruptionRegister import registerDisruption, updateDisruption, getDisruption
        try:
            cur = getDisruption(reportingNumber)
        except Exception:
            cur = None
        # Do not overwrite cancellations (>= 1441)
        try:
            curInt = int(cur) if cur is not None else None
        except Exception:
            curInt = None
        if (curInt is not None) and (curInt >= 1441):
            return
        if cur is None:
            registerDisruption(reportingNumber, delay)
        else:
            updateDisruption(reportingNumber, delay)
    except Exception as e:
        # Never allow disruption calc to break timing storage
        print("Warning: Timing->Disruption update failed for {} at '{}': {}".format(reportingNumber, timingPointName, e))


def assignBlocks(timingPointName, blocks):
    _wlock.lock()
    try:
        register = timingRegister.get(timingPointName)
        if register is None:
            register = {"timings": [], "blocks": []}
            timingRegister.put(timingPointName, register)
        register["blocks"] = [str(b) for b in blocks] if blocks is not None else []
    finally:
        _wlock.unlock()

def clearBlocks(timingPointName):
    _wlock.lock()
    try:
        register = timingRegister.get(timingPointName)
        if register is not None:
            register["blocks"] = None
    finally:
        _wlock.unlock()

def getBlocks(timingPointName):
    _rlock.lock()
    try:
        entry = timingRegister.get(timingPointName)
        if entry is None:
            return None
        blocks = entry.get("blocks", None)
        return None if blocks is None else list(blocks)
    finally:
        _rlock.unlock()

def getTiming(timingPointName):
    # Note: returns a copy
    _rlock.lock()
    try:
        register = timingRegister.get(timingPointName)
        if register is None:
            return None
        entry = register.get("timings", [])
        if entry is None:
            return []
        return list(entry)
    finally:
        _rlock.unlock()

def removeByDay(day):
    # Remove all tuples whose day matches 'day' (case/space-normalised)
    # Returns total count removed across all timing points.
    removed = 0
    target = ("" if day is None else str(day).strip())
    _wlock.lock()
    try:
        for tp in list(timingRegister.keySet()):
            register = timingRegister.get(tp)
            if not isinstance(register, dict):
                continue
            entry = register.get("timings", [])
            if not isinstance(entry, list):
                continue
            before = len(entry)
            # Duplicate-aware: drop every match, even if there are many
            pruned = []
            for t in entry:
                try:
                    d = ("" if (len(t) < 4 or t[3] is None) else str(t[3]).strip())
                    if d != target:
                        pruned.append(t)
                except Exception:
                    # If malformed, keep it (defensive)
                    pruned.append(t)
            register["timings"] = pruned
            removed += (before - len(pruned))
    finally:
        _wlock.unlock()
    return removed
   
def ensureTimingPoint(timingPointName):
    """Ensure a register entry exists with {'timings': [], 'blocks': []} shape."""
    _wlock.lock()
    try:
        reg = timingRegister.get(timingPointName)
        if reg is None or not isinstance(reg, dict):
            timingRegister.put(timingPointName, {"timings": [], "blocks": []})
            return True  # created
        # Normalise internal shapes defensively
        if "timings" not in reg or not isinstance(reg.get("timings"), list):
            reg["timings"] = list(reg.get("timings") or [])
        if "blocks" not in reg:
            reg["blocks"] = None
        else:
            b = reg.get("blocks")
            if b is not None and not isinstance(b, list):
                reg["blocks"] = [str(b)]
        return False  # already existed
    finally:
        _wlock.unlock()

def clearTimings(timingPointName):
    """Remove all timing tuples for a timing point, preserving its blocks. Returns count removed."""
    _wlock.lock()
    try:
        reg = timingRegister.get(timingPointName)
        if reg is None or not isinstance(reg, dict):
            return 0
        t = reg.get("timings", [])
        removed = len(t) if isinstance(t, list) else 0
        reg["timings"] = []
        return removed
    finally:
        _wlock.unlock()

def deleteTimingPoint(timingPointName):
    """Delete the entire timing point entry. Returns True if it existed."""
    _wlock.lock()
    try:
        prev = timingRegister.remove(timingPointName)
        return prev is not None
    finally:
        _wlock.unlock()

def listTimingPoints():
    """Return a list of all timing point names (strings) currently in the register."""
    _rlock.lock()
    try:
        keys = list(timingRegister.keySet())
        out = []
        for k in keys:
            try:
                is_str = isinstance(k, basestring)
            except NameError:
                is_str = isinstance(k, str)
            if is_str:
                out.append(k)
        return out
    finally:
        _rlock.unlock()

def setMeta(key, value):
    """Set a small metadata value (e.g., 'lastMaintenanceDay'). Persisted by save()."""
    _wlock.lock()
    try:
        global _meta
        if not isinstance(_meta, dict):
            _meta = {}
        _meta[str(key)] = value
    finally:
        _wlock.unlock()

def getMeta(key, default=None):
    """Get a metadata value previously set with setMeta()."""
    _rlock.lock()
    try:
        if not isinstance(_meta, dict):
            return default
        return _meta.get(key, default)
    finally:
        _rlock.unlock()

# -- save/load unchanged below (omitted comments for brevity) --
def save():
    _wlock.lock()
    try:
        data_out = {}
        for tp in list(timingRegister.keySet()):
            entry = timingRegister.get(tp)
            if not isinstance(entry, dict):
                continue
            timings = entry.get("timings", []) or []
            blocks = entry.get("blocks", None)
            data_out[tp] = {
                "timings": [list(t) for t in timings],
                "blocks": None if blocks is None else list(blocks)
            }
        meta_out = {}
        if isinstance(_meta, dict):
            meta_out.update(_meta)
        out = {"__meta__": meta_out, "data": data_out}
        tmp_path = _SAVE_PATH + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(out, f)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except Exception:
                    pass
            try:
                from java.nio.file import Files, Paths, StandardCopyOption
                Files.move(
                    Paths.get(tmp_path),
                    Paths.get(_SAVE_PATH),
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
            print("Warning: failed to save timingRegister.json: {}".format(e))
    finally:
        _wlock.unlock()

def load():
    import os, time, json
    if not os.path.exists(_SAVE_PATH):
        return
    attempts = 3
    for _ in range(attempts):
        _wlock.lock()
        try:
            try:
                with open(_SAVE_PATH, "r") as f:
                    loaded = json.load(f)
                timingRegister.clear()
                global _meta
                _meta = {}
                if isinstance(loaded, dict) and "__meta__" in loaded and "data" in loaded and isinstance(loaded["data"], dict):
                    meta_in = loaded.get("__meta__", {})
                    if isinstance(meta_in, dict):
                        _meta = dict(meta_in)
                    for tp, val in loaded["data"].items():
                        try:
                            is_str = isinstance(tp, basestring)
                        except NameError:
                            is_str = isinstance(tp, str)
                        if not is_str:
                            continue
                        if isinstance(val, dict):
                            seq = val.get("timings", []) or []
                            blocks = val.get("blocks", None)
                            rebuilt = []
                            for x in seq:
                                if isinstance(x, (list, tuple)) and len(x) >= 4:
                                    rebuilt.append((x[0], x[1], x[2], x[3]))
                            if blocks is None:
                                blocks_out = None
                            elif isinstance(blocks, list):
                                blocks_out = [str(b) for b in blocks]
                            else:
                                blocks_out = [str(blocks)]
                            timingRegister.put(tp, {"timings": rebuilt, "blocks": blocks_out})
                    return
                if isinstance(loaded, dict):
                    any_dict_vals = False
                    for tp, val in loaded.items():
                        try:
                            is_str = isinstance(tp, basestring)
                        except NameError:
                            is_str = isinstance(tp, str)
                        if not is_str:
                            continue
                        if isinstance(val, dict):
                            any_dict_vals = True
                            seq = val.get("timings", []) or []
                            blocks = val.get("blocks", None)
                            rebuilt = []
                            for x in seq:
                                if isinstance(x, (list, tuple)) and len(x) >= 4:
                                    rebuilt.append((x[0], x[1], x[2], x[3]))
                            if blocks is None:
                                blocks_out = None
                            elif isinstance(blocks, list):
                                blocks_out = [str(b) for b in blocks]
                            else:
                                blocks_out = [str(blocks)]
                            timingRegister.put(tp, {"timings": rebuilt, "blocks": blocks_out})
                    if any_dict_vals:
                        return
                if isinstance(loaded, dict):
                    for tp, seq in loaded.items():
                        try:
                            is_str = isinstance(tp, basestring)
                        except NameError:
                            is_str = isinstance(tp, str)
                        if not is_str:
                            continue
                        rebuilt = []
                        if isinstance(seq, list):
                            for x in seq:
                                if isinstance(x, (list, tuple)) and len(x) >= 4:
                                    rebuilt.append((x[0], x[1], x[2], x[3]))
                        timingRegister.put(tp, {"timings": rebuilt, "blocks": None})
                    return
                timingRegister.clear()
                _meta = {}
                return
            except ValueError:
                pass
            except Exception as e:
                print("Warning: failed to load timingRegister.json: {}".format(e))
                return
        finally:
            _wlock.unlock()
        time.sleep(0.1)
    _wlock.lock()
    try:
        print("Warning: timingRegister.json not readable (giving up); starting with empty register")
        timingRegister.clear()
        _meta = {}
    finally:
        _wlock.unlock()

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