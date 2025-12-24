# -*- coding: utf-8 -*-
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
# Disruption generation/updates with support for VIRTUAL TIMING POINTS.
import os, csv, random, re, math
import jmri
from jmri.util import FileUtil
# Registers
from DisruptionRegister import registerDisruption, updateDisruption, getDisruption, deregisterDisruption
import DisruptionRegister as DR # enumerate all registered reporting numbers safely
import TimingRegister as TR
import TASUtil as TU
import TrainLocatorRegister as TLR
import TASBeanLookup as TBL
import PlatformAllocationRegister as PAR  # clear previous day's platform allocation on first disruption
# -------------------------------------------------------------------------------------------------
# In-memory, per-session state (NOT persisted)
# Resets cleanly at layout-day rollover (IMDAYOFWEEK changes).
# -------------------------------------------------------------------------------------------------
_state = {"_day": None, "trains": {}}
_lastCullDay = None
_lastCullMinute = None
# -------------------------------------------------------------------------------------------------
# Memory helpers + auto-default provisioning for new knobs
# -------------------------------------------------------------------------------------------------
def _readMem(suffix):
    m = TBL.FindMemoryBySuffix(suffix)
    return None if m is None else m.getValue()

def _readMemStr(suffix, default=None):
    v = _readMem(suffix)
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default

def _readMemBool(suffix, default=True):
    v = _readMem(suffix)
    if v is None:
        return default
    return str(v).strip().lower() in ("true", "1", "yes", "on", "enabled")

def _ensureMemDefault(suffix, value):
    # Ensure a memory exists (prefix-agnostic) and seed it if blank/None.
    m = TBL.ProvideMemoryBySuffix(suffix, str(value))
    cur = None
    try:
        cur = m.getValue()
    except:
        cur = None
    if cur is None or (isinstance(cur, basestring) and str(cur).strip() == ""):
        try:
            m.setValue(str(value))
        except:
            pass
            
def _provisionDefaults():
    _ensureMemDefault("TP_WEIGHT_DELAY_PRE_FIRSTTP", "0.70")
    _ensureMemDefault("TP_WEIGHT_EARLY_PRE_FIRSTTP", "0.70")
    _ensureMemDefault("TP_P_LATE_DEPART_ON_EARLY", "0.10")
    _ensureMemDefault("TP_MIN_DWELL_LE_2_MIN", "0.5")  # minutes (30s)
    _ensureMemDefault("TP_MIN_DWELL_LE_5_MIN", "1.0")
    _ensureMemDefault("TP_MIN_DWELL_GT_5_MIN", "2.0")

    # Post-publication grace (minutes) after the last scheduled time.
    # Outside this window, do NOT generate disruption or timing for that RN.
    _ensureMemDefault("TP_POST_GRACE_MINUTES", "2")

# -------------------------------------------------------------------------------------------------
# Time parsing & formatting
# -------------------------------------------------------------------------------------------------
def parseTimeToMinutes(text):
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
def minutesToStrHMM(mn):
    if mn is None:
        return ""
    if isinstance(mn, float):
        mn = int(round(mn))
    mn = max(0, min(24*60-1, int(mn)))
    h = mn // 60
    m = mn % 60
    return ("%d:%02d" % (h, m))
# -------------------------------------------------------------------------------------------------
# CSV & timetable helpers
# -------------------------------------------------------------------------------------------------
def timetablePathFromMemory():
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    name = _readMemStr("CURRENTTIMETABLE")
    if not name:
        return None
    return os.path.join(profilePath, "timetable", name + ".csv")
def loadDisruptionGroups():
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    path = os.path.join(profilePath, "timetable", "Disruption.csv")
    groups = {}
    if not os.path.exists(path):
        return groups
    with open(path, "r") as f:
        r = csv.DictReader(f, delimiter='\t')
        for row in r:
            name = (row.get("Disruption group","") or "").strip()
            if not name:
                continue
            def ffloat(k, d=0.0):
                try: return float(row.get(k, d) or d)
                except: return float(d)
            def fint(k, d=0):
                try: return int(float(row.get(k, d) or d))
                except: return int(d)
            groups[name] = dict(
                pDelay = ffloat("Delay probability", 0.0),
                maxDelay = fint("Max delay", 0),
                pEarly = ffloat("Early probability", 0.0),
                maxEarly = fint("Max early", 0),
                pCancel = ffloat("Cancellation probability", 0.0),
                checkMax = fint("Minutes before to check max", 120),
                checkMin = fint("Minutes before to check min", 30),
                cancelIfLaterThan = fint("Cancel if later than", -1),
                maxRecoveryRate = ffloat("Max recovery mins/min", 0.0),
            )
    return groups
    
def iterTodayRows(timetablePath, dayName):
    """
    Robust iterator over rows for the given day.
    - Snapshots the entire CSV (prevents generator-time races / NPE).
    - Tolerates DictReader restkey/restval (None).
    - When the 'Reporting number' cell is blank, synthesize TAS<rowNumber> where
      rowNumber is the spreadsheet row number (header counted; header = 1).
    """
    if not (timetablePath and os.path.exists(timetablePath)):
        return
    dn = (dayName or "").strip()
    if dn == "":
        return
    try:
        with open(timetablePath, "r") as f:
            reader = csv.DictReader(f, delimiter='\t')
            try:
                rows = list(reader)
            except Exception:
                rows = []
    except Exception:
        return

    # Enumerate with spreadsheet semantics: header row is 1, first data row is 2
    for rowIndex, row in enumerate(rows, start=2):
        try:
            if not isinstance(row, dict):
                continue
            dayField = row.get(dn, "")
            if str(dayField).strip().upper() != "TRUE":
                continue

            rnField = row.get("Reporting number", "")
            rn = (str(rnField) if rnField is not None else "").strip()
            if rn == "":
                rn = TU.MakeDefaultReportingNumberFromRow(rowIndex)  # e.g., TAS40

            yield row, rn
        except Exception:
            continue
# -------------------------------------------------------------------------------------------------
# Seeds & helpers
# -------------------------------------------------------------------------------------------------
# Session salt: randomised at module import using system time
try:
    from java.lang import System as _JSystem
    _sessionSalt = int(_JSystem.currentTimeMillis() & 0xFFFFFFFF)
except Exception:
    import time as _pyTime
    _sessionSalt = int((_pyTime.time() * 1000)) & 0xFFFFFFFF

def _currentSeedBase():
    """
    Return the current base seed, reading IMDISRUPTIONSEEDBASE if present;
    otherwise use the session salt. Robust against blank/invalid values.
    """
    s = _readMemStr("DISRUPTIONSEEDBASE", None)
    if s is None:
        return _sessionSalt
    t = str(s).strip()
    if t == "":
        return _sessionSalt
    try:
        return int(float(t)) & 0xFFFFFFFF
    except Exception:
        return _sessionSalt

def seedFor(rn, dayName, timetableName):
    """
    Deterministic per RN/day/timetable, but now mixed with a session/override seed.
    Resetting disruption data sets IMDISRUPTIONSEEDBASE to current time, so outcomes change.
    """
    base = "%s\n%s\n%s\n%s" % (rn, dayName, timetableName, _currentSeedBase())
    h = 0
    for ch in base:
        h = (h*131 + ord(ch)) & 0xFFFFFFFF
    # Mix once more with the numeric seed to spread bits
    h ^= (_currentSeedBase() & 0xFFFFFFFF)
    return (h or 1) & 0xFFFFFFFF
def rngUniformInt(seed, lo, hi):
    rnd = random.Random(seed)
    return rnd.randint(lo, hi)
def rngPickGeometric(seed, maxMag):
    if maxMag <= 1:
        return 1 if maxMag == 1 else 0
    rRatio = 0.1 ** (1.0 / (maxMag - 1.0))
    weights = [rRatio**(m-1) for m in range(1, maxMag+1)]
    total = sum(weights)
    rnd = random.Random(seed)
    x = rnd.random() * total
    cum = 0.0
    for m, w in enumerate(weights, start=1):
        cum += w
        if x <= cum:
            return m
    return maxMag
# --- Helper: check if a timing (optionally for a specific time) already exists for (TP, RN, day) ---
def _HasTimingForRNAtTP(tpName, rn, dayName, timeStr=None):
    try:
        entries = TR.getTiming(tpName) or []
    except Exception:
        return False
    for rec in entries:
        try:
            rnr = rec[0]; dirn = rec[1]; tStr = rec[2]; dStr = rec[3]
        except Exception:
            continue
        if str(rnr) != str(rn):
            continue
        if str(dStr) != str(dayName):
            continue
        if timeStr is None:
            return True
        if str(tStr) == str(timeStr):
            return True
    return False
    
def _HasAnyTimingToday(rn, dayName):
    """
    Return True iff ANY timing point has at least one tuple for (rn, dayName),
    regardless of minute or TP. Defensive against register shape issues.
    """
    try:
        tps = TR.listTimingPoints() or []
    except Exception:
        tps = []
    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except Exception:
            entries = []
        for rec in entries:
            try:
                rnr = rec[0]; dStr = rec[3]
            except Exception:
                continue
            if str(rnr) == str(rn) and str(dStr) == str(dayName):
                return True
    return False

# -------------------------------------------------------------------------------------------------
# Dispatcher API
# -------------------------------------------------------------------------------------------------
from jmri.jmrit.dispatcher import ActiveTrain as _AT
def _dispatcher():
    try:
        return jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)
    except Exception:
        return None
def _getActiveTrainByName(trainName):
    df = _dispatcher()
    if df is None:
        return None
    lst = df.getActiveTrainsList()
    try:
        size = lst.size()
    except Exception:
        size = len(lst)
    for i in range(size):
        try:
            at = lst.get(i) if hasattr(lst, "get") else lst[i]
            if at is not None and str(at.getActiveTrainName()) == str(trainName):
                return at
        except Exception:
            pass
    return None
def _absStartMinute(at):
    try:
        hr = at.getDepartureTimeHr()
        mn = at.getDepartureTimeMin()
        if hr is None or mn is None:
            return None
        hr = int(hr); mn = int(mn)
        if hr < 0 or mn < 0:
            return None
        return hr*60 + mn
    except Exception:
        return None
def _isDelayedStart(at, nowMins):
    if at is None:
        return (False, None)
    try:
        status = at.getStatus()
    except Exception:
        return (False, None)
    if status != _AT.WAITING:
        return (False, None)
    startAbs = _absStartMinute(at)
    if startAbs is not None and startAbs > nowMins:
        return (True, startAbs)
    rel = 0
    try:
        rel = at.getDelayedStart()
    except Exception:
        rel = 0
    if rel and rel > 0:
        return (True, startAbs)
    return (False, startAbs)
# -------------------------------------------------------------------------------------------------
# TP extraction & classification
# -------------------------------------------------------------------------------------------------
# NOTE: use OR, not a newline, between Arr and Dep
_TP_PATTERN = re.compile(r"^TP(?:Arr|Dep)\s+(.+)$", re.IGNORECASE)

def _build_tp_events(row):
    events_raw = []
    for k, v in row.items():
        if not k or not v:
            continue
        m = _TP_PATTERN.match(str(k).strip())
        if not m:
            continue
        tpName = m.group(1).strip()
        sched = parseTimeToMinutes(v)
        if sched is None:
            continue
        kind = "Arr" if str(k).lower().startswith("tparr") else "Dep"
        blocks = TR.getBlocks(tpName)
        isVirtual = (blocks is None) or (isinstance(blocks, list) and len(blocks) == 0)
        events_raw.append({"name": tpName, "kind": kind, "sched": sched, "isVirtual": isVirtual})

    # Establish 'main' strictly from base columns (Arr/Dep/Trigger), not TP columns
    arr = parseTimeToMinutes((row.get("Arr","") or "").strip()) if "Arr" in row else None
    dep = parseTimeToMinutes((row.get("Dep","") or "").strip()) if "Dep" in row else None
    if arr is not None:
        main = arr
    elif dep is not None:
        main = dep
    else:
        trig = parseTimeToMinutes((row.get("Trigger","") or "").strip()) if "Trigger" in row else None
        if trig is not None:
            main = trig
        else:
            main = None

    # IMPORTANT: do NOT override 'main' by scanning all TP columns
    return events_raw, {"arr": arr, "dep": dep, "main": main}

def _classify_working(events, mainTimes):
    arr = mainTimes.get("arr")
    dep = mainTimes.get("dep")
    main = mainTimes.get("main")
    if main is None:
        return "NONE", {"pre": [], "phys_pre": [], "phys_post": [], "post": []}, []
    earlier = [e for e in events if e["sched"] < main]
    later = [e for e in events if e["sched"] > main]
    same = [e for e in events if e["sched"] == main]
    warnings = []
    for e in same:
        warnings.append("[DG] Warning: Ignoring TP '{}' at same minute as main time.".format(e["name"]))
    if earlier and not later:
        klass = "INBOUND"
    elif later and not earlier:
        klass = "OUTBOUND"
    elif earlier and later:
        klass = "THROUGH"
    else:
        klass = "NONE"
    def _sorted_ev(evts):
        return sorted(evts, key=lambda x: (x["sched"], 0 if x["kind"]=="Arr" else 1))
    pre_virtual = _sorted_ev([e for e in earlier if e["isVirtual"]])
    pre_physical = _sorted_ev([e for e in earlier if not e["isVirtual"]])
    post_physical = _sorted_ev([e for e in later if not e["isVirtual"]])
    post_virtual = _sorted_ev([e for e in later if e["isVirtual"]])
    # Defensive filters: only use min/max when both sides non-empty
    def _filter_inbound(pv, pp):
        if pv and pp:
            pv_sched = [v.get("sched") for v in pv if "sched" in v]
            pp_sched = [p.get("sched") for p in pp if "sched" in p]
            if pv_sched and pp_sched:
                if min(pp_sched) <= max(pv_sched):
                    warnings.append("[DG] Warning: INBOUND ordering violated; ignoring overlapping virtual/physical.")
                v_max = min(pp_sched) - 1
                pv = [e for e in pv if e.get("sched") is not None and e["sched"] <= v_max]
        return pv, pp
    def _filter_outbound(pp, pv):
        if pv and pp:
            pv_sched = [v.get("sched") for v in pv if "sched" in v]
            pp_sched = [p.get("sched") for p in pp if "sched" in p]
            if pv_sched and pp_sched:
                if min(pv_sched) <= max(pp_sched):
                    warnings.append("[DG] Warning: OUTBOUND ordering violated; ignoring early virtuals.")
                v_min = max(pp_sched) + 1
                pv = [e for e in pv if e.get("sched") is not None and e["sched"] >= v_min]
        return pp, pv
    def _filter_through(pre_v, pre_p, post_p, post_v):
        if pre_v and pre_p:
            pre_v_sched = [v.get("sched") for v in pre_v if "sched" in v]
            pre_p_sched = [p.get("sched") for p in pre_p if "sched" in p]
            if pre_v_sched and pre_p_sched:
                if min(pre_p_sched) <= max(pre_v_sched):
                    warnings.append("[DG] Warning: THROUGH pre-order violated; pruning overlaps.")
                v_max = min(pre_p_sched) - 1
                pre_v = [e for e in pre_v if e.get("sched") is not None and e["sched"] <= v_max]
        if post_v and post_p:
            post_v_sched = [v.get("sched") for v in post_v if "sched" in v]
            post_p_sched = [p.get("sched") for p in post_p if "sched" in p]
            if post_v_sched and post_p_sched:
                if min(post_v_sched) <= max(post_p_sched):
                    warnings.append("[DG] Warning: THROUGH post-order violated; pruning overlaps.")
                v_min = max(post_p_sched) + 1
                post_v = [e for e in post_v if e.get("sched") is not None and e["sched"] >= v_min]
        return pre_v, pre_p, post_p, post_v
    if klass == "INBOUND":
        pre_virtual, pre_physical = _filter_inbound(pre_virtual, pre_physical)
        return klass, {"pre": pre_virtual, "phys_pre": pre_physical, "phys_post": [], "post": []}, warnings
    if klass == "OUTBOUND":
        post_physical, post_virtual = _filter_outbound(post_physical, post_virtual)
        return klass, {"pre": [], "phys_pre": [], "phys_post": post_physical, "post": post_virtual}, warnings
    if klass == "THROUGH":
        pre_virtual, pre_physical, post_physical, post_virtual = _filter_through(pre_virtual, pre_physical, post_physical, post_virtual)
        return klass, {"pre": pre_virtual, "phys_pre": pre_physical, "phys_post": post_physical, "post": post_virtual}, warnings
    return "NONE", {"pre": [], "phys_pre": [], "phys_post": [], "post": []}, warnings
# -------------------------------------------------------------------------------------------------
# Evolution / stop rules / publish (unchanged)
# -------------------------------------------------------------------------------------------------
def _apply_step_evolution(rn, g, seed0, t, firstTpMinute, allowDelays, allowCancel):
    cur = getDisruption(rn)
    try:
        cur = int(cur) if cur is not None else 0
    except:
        cur = 0
    if cur > 1440:
        return cur
    if allowCancel and g and g.get("cancelIfLaterThan", -1) >= 0:
        if t >= (firstTpMinute - g.get("checkMin", 30)) and cur > g["cancelIfLaterThan"]:
            return 1442
    if not allowDelays or not g:
        return cur
    minutesToGo = max(0, firstTpMinute - t)
    pace = 10 if minutesToGo > 30 else (5 if minutesToGo >= 10 else 2)
    rnd = random.Random(seed0 ^ (t << 4))
    if cur > 0:
        rate = max(0.0, float(g.get("maxRecoveryRate", 0.0)))
        effective = rate * pace
        if effective > 0.0:
            N = int(round(1.0 / effective)); N = max(N, 1)
            if N == 1 or rnd.randint(1, N) == 1:
                cur = cur - 1
        return cur
    elif cur < 0:
        v = rnd.random()
        if v < 0.70:
            step = max(1, pace // 5)
            cur = min(0, cur + step)
        elif v < 0.85:
            step = max(1, pace // 5)
            cur = max(-g.get("maxEarly", 0), cur - step)
        return cur
    else:
        w = rnd.random()
        if w < 0.05 and g.get("maxDelay", 0) > 0:
            mag = max(1, int(round(rnd.uniform(1, min(3, g["maxDelay"])))))
            cur = mag
        elif w < 0.08 and g.get("maxEarly", 0) > 0:
            mag = max(1, int(round(rnd.uniform(1, min(2, g["maxEarly"])))))
            cur = -mag
        return cur
def _min_dwell_minutes(schedDwellMin):
    d_le2 = float(_readMemStr("TP_MIN_DWELL_LE_2_MIN", "0.5"))
    d_le5 = float(_readMemStr("TP_MIN_DWELL_LE_5_MIN", "1.0"))
    d_gt5 = float(_readMemStr("TP_MIN_DWELL_GT_5_MIN", "2.0"))
    if schedDwellMin <= 2.0:
        return d_le2
    if schedDwellMin <= 5.0:
        return d_le5
    return d_gt5
def _apply_stop_rules(arrSched, depSched, arriveActualMin, g, planned, allowDelays):
    schedDwell = depSched - arrSched if (arrSched is not None and depSched is not None) else 0.0
    minDwell = _min_dwell_minutes(schedDwell)
    if arriveActualMin <= arrSched:
        depActual = float(depSched)
        if allowDelays and planned and planned.get("type") != "delay":
            try:
                pLate = float(_readMemStr("TP_P_LATE_DEPART_ON_EARLY", "0.10"))
            except:
                pLate = 0.10
            seed0 = planned.get("seed0", 1)
            rnd = random.Random(seed0 ^ int(arriveActualMin) ^ 0x4455)
            if rnd.random() < max(0.0, min(1.0, pLate)):
                maxD = 2
                if g and g.get("maxDelay", 0) > 0:
                    maxD = min(2, int(g["maxDelay"]))
                bump = rngPickGeometric(seed0 ^ 0x4466, maxD)
                depActual = depActual + float(bump)
        return depActual
    else:
        if arriveActualMin + minDwell <= depSched:
            return float(depSched)
        else:
            return float(arriveActualMin + minDwell)
def _publish_at_virtual_tp(tpEvent, row, rn, dayName, actualMinute, curDelay):
    # Always write a disruption value when we publish a TP.
    # If the RN has no record yet, use registerDisruption; otherwise updateDisruption.
    tpName = tpEvent["name"]
    direction = (row.get("Direction","") or "").strip()
    timeStr = minutesToStrHMM(actualMinute)
    try:
        existing = getDisruption(rn)
        if isinstance(curDelay, int) and curDelay == 1442:
            # Promote to cancelled (1441) at this TP       
        if existing is None:
            try: 
                PAR.deregisterPlatform(rn)
            except Exception: 
                pass
            registerDisruption(rn, 1441)
            else:
                updateDisruption(rn, 1441)
            try:
                _propagateCancellation(rn, dayName)
            except Exception:
                pass
        else:
            val = int(curDelay or 0)
            if existing is None:
                try: 
                    PAR.deregisterPlatform(rn)
                except Exception: 
                    pass
                registerDisruption(rn, val)
            else:
                updateDisruption(rn, val)
    except Exception as e:
        print("[DG] Warning: failed to update DisruptionRegister at VTP: {}".format(e))
    # Only Dep logs a timing
    if tpEvent["kind"] != "Dep":
        return
    try:
        TR.ensureTimingPoint(tpName)
        TR.registerTiming(tpName, rn, direction, timeStr, dayName)
    except Exception as e:
        print("[DG] Warning: failed to register timing for '{}': {}".format(tpName, e))
# -------------------------------------------------------------------------------------------------
# Formation helpers
# -------------------------------------------------------------------------------------------------
def _getFormationChildren(timetablePath, dayName):
    children_map = {}
    today_rns = set()
    rows = []
    for row, rn in iterTodayRows(timetablePath, dayName):
        rows.append((row, rn))
        today_rns.add(rn)
    for row, rn in rows:
        forms_field = (row.get("Forms", "") or "").strip()
        if not forms_field:
            continue
        childs = [tok for tok in re.split(r"[^A-Za-z0-9]+", forms_field) if tok]
        for ch in childs:
            if ch in today_rns:
                children_map.setdefault(rn, []).append(ch)
    return children_map
def _propagateCancellation(root_rn, dayName):
    timetablePath = timetablePathFromMemory()
    if not timetablePath or not os.path.exists(timetablePath):
        return
    graph = _getFormationChildren(timetablePath, dayName)
    if not graph:
        return
    seen = set()
    stack = [root_rn]
    while stack:
        p = stack.pop()
        for child in graph.get(p, []):
            if child in seen:
                continue
            seen.add(child)
            try:
                if not isActive(child):
                    cur = getDisruption(child)
                    try:
                        ci = int(cur) if cur is not None else None
                    except:
                        ci = None
                    if ci is None:
                        registerDisruption(child, 1441)
                    elif ci < 1441:
                        updateDisruption(child, 1441)
            except Exception:
                pass
            stack.append(child)
# -------------------------------------------------------------------------------------------------
# ActiveTrain presence
# -------------------------------------------------------------------------------------------------
def isActive(rn):
    df = _dispatcher()
    if df is None:
        return False
    lst = df.getActiveTrainsList()
    try:
        size = lst.size()
    except Exception:
        size = len(lst)

    rnStr = str(rn)
    # 1) Fast path: exact name match (covers non-default RNs)
    for i in range(size):
        try:
            at = lst.get(i) if hasattr(lst, "get") else lst[i]
            if at is None:
                continue
            if str(at.getActiveTrainName()) == rnStr:
                return True
        except Exception:
            pass

    # 2) Locator path: RN -> RosterID -> scan ActiveTrains by roster id
    try:
        rid = TLR.getRosterId(rnStr)
    except Exception:
        rid = None
    if not rid:
        return False

    for i in range(size):
        try:
            at = lst.get(i) if hasattr(lst, "get") else lst[i]
            if at is None:
                continue
            re = at.getRosterEntry()
            if re is None:
                continue
            if str(re.getId()) == str(rid):
                return True
        except Exception:
            pass

    return False
# -------------------------------------------------------------------------------------------------
# Day helpers
# -------------------------------------------------------------------------------------------------
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
def _NextDay(dayName):
    try:
        i = _DAYS.index(dayName)
        return _DAYS[(i + 1) % 7]
    except Exception:
        return None
# -------------------------------------------------------------------------------------------------
# Culling (unchanged logic)
# -------------------------------------------------------------------------------------------------
def cullSpuriousDisruptions():
    """
    Delete entries:
    - not in today or immediate next day; or
    - first scheduled time is beyond group's checkMax horizon from 'now'
    (with cross-midnight handling for next day).
    """
    nowStr = _readMemStr("CURRENTTIME")
    dayName = _readMemStr("DAYOFWEEK")
    if not (nowStr and dayName):
        return
    nowMins = parseTimeToMinutes(nowStr)
    if nowMins is None:
        return
    ttPath = timetablePathFromMemory()
    if not (ttPath and os.path.exists(ttPath)):
        return
    groups = loadDisruptionGroups()
    def _buildMapFor(day):
        m = {}
        if not day:
            return m
        for row, rn in iterTodayRows(ttPath, day):
            first = _first_time_in_row(row)
            gname = (row.get("Disruption group", "") or "").strip()
            m[rn] = (first, gname)
        return m
    todayMap = _buildMapFor(dayName)
    nextDay = _NextDay(dayName)
    nextMap = _buildMapFor(nextDay)
    remainingToday = max(0, 1440 - nowMins)
    try:
        allKeys = list(DR.register.keySet().toArray())
    except Exception:
        allKeys = []
    def _h(gname):
        g = groups.get(gname, {}) if gname else {}
        try:
            return int(g.get("checkMax", 120))
        except Exception:
            return 120
    for rn in allKeys:
        inToday = rn in todayMap
        inNext = rn in nextMap
        if not inToday and not inNext:
            try: deregisterDisruption(rn)
            except: pass
            continue
        if inToday:
            first, gname = todayMap[rn]
            if first is None:
                try: deregisterDisruption(rn)
                except: pass
                continue
            if (first - nowMins) > _h(gname):
                try: deregisterDisruption(rn)
                except: pass
                continue
        if inNext:
            firstN, gname = nextMap[rn]
            if firstN is None:
                try: deregisterDisruption(rn)
                except: pass
                continue
            if (remainingToday + firstN) > _h(gname):
                try: deregisterDisruption(rn)
                except: pass
# -------------------------------------------------------------------------------------------------
# Main entry
# -------------------------------------------------------------------------------------------------
def updateDisruptions():
    global _state, _lastCullDay, _lastCullMinute
    _provisionDefaults()
    nowStr = _readMemStr("CURRENTTIME")
    dayName = _readMemStr("DAYOFWEEK")
    ttName = _readMemStr("CURRENTTIMETABLE")
    if not (nowStr and dayName and ttName):
        return
    nowMins = parseTimeToMinutes(nowStr)
    if nowMins is None:
        return
    # Run culler routinely
    try:
        cullSpuriousDisruptions()
    except Exception as e:
        print("[DG] Warning: cullSpuriousDisruptions failed: {}".format(e))
    allowDelays = _readMemBool("ALLOWDELAYS", True)
    allowCancel = _readMemBool("ALLOWCANCELLATIONS", True)
    if _state["_day"] != dayName:
        _state = {"_day": dayName, "trains": {}}
        try:
            cullSpuriousDisruptions()
        except Exception as e:
            print("[DG] Warning: day-change cull failed: {}".format(e))
    timetablePath = timetablePathFromMemory()
    if not (timetablePath and os.path.exists(timetablePath)):
        return
    groups = loadDisruptionGroups()
    # Stale cancellations: keep visible slightly AFTER the scheduled time
    # Clear when firstTime <= (now - 5)
    fiveAgo = max(0, nowMins - 5)
    for rowX, rnX in iterTodayRows(timetablePath, dayName):
        firstTimeX = _first_time_in_row(rowX)
        if firstTimeX is None:
            continue
        if firstTimeX <= fiveAgo:
            curX = getDisruption(rnX)
            if curX is None:
                continue
            try:
                curXi = int(curX)
            except:
                continue
            if curXi > 1440:
                try: deregisterDisruption(rnX)
                except: pass
    # Per-train
    for row, rn in iterTodayRows(timetablePath, dayName):
        events_raw, mainTimes = _build_tp_events(row)
        klass, segs, warnings = _classify_working(events_raw, mainTimes)
        for w in warnings:
            print(w)                  
        # -- HARD GATE: stop generating ONLY for long-past services that have NO existing disruption AND NO timing
        try:
            postGrace = int(float(_readMemStr("TP_POST_GRACE_MINUTES", "2")))
        except:
            postGrace = 2
        lastRowTime = _last_time_in_row(row)
        hasDisruptionAlready = False
        try:
            cur = getDisruption(rn)
            hasDisruptionAlready = (cur is not None)
        except Exception:
            hasDisruptionAlready = False
        hasAnyTimingToday = _HasAnyTimingToday(rn, dayName)
        activeNow = isActive(rn)  # <-- NEW: ActiveTrain exemption
        if (lastRowTime is not None) and (nowMins > (lastRowTime + postGrace)) \
           and (not hasDisruptionAlready) and (not hasAnyTimingToday) and (not activeNow):
            # Only block generation for orphaned, long-past services
            continue
     
        hasAnyTP = bool(events_raw)
        if (not hasAnyTP) or klass == "NONE":
            _legacy_per_train(nowMins, row, rn, groups, allowDelays, allowCancel, ttName, dayName)
            continue
        st = _state["trains"].get(rn)
        if st is None:
            st = _init_state_for_train(row, rn, groups, ttName, dayName, mainTimes, klass, segs,
                                       allowDelays, allowCancel, nowMins)
            _state["trains"][rn] = st
        at = _getActiveTrainByName(rn)
        if at is not None:
            delayed, startAbs = _isDelayedStart(at, nowMins)
            if delayed:
                st["activeDelayedStart"]["known"] = True
                st["activeDelayedStart"]["startMin"] = startAbs
            else:
                if st["activeDelayedStart"]["known"]:
                    trigger = st["activeDelayedStart"]["startMin"]
                    if trigger is None:
                        trigger = nowMins
                    if nowMins >= trigger:
                        _backfill_missed_pre_virtuals(st, row, rn, dayName)
                        continue
        _advance_internal(nowMins, row, rn, st, groups, allowDelays, allowCancel)
        _publish_due_virtuals(nowMins, row, rn, dayName, st, segment="pre", allowDelays=allowDelays)
        _check_crossed_into_layout(nowMins, st)
        # Suppress post-segment virtual timing points before the train exists (prevents final TP pre-start).
        # When an ActiveTrain is present, post-segment logging is handled elsewhere or can be added later.
        # (Intentional no-op here while at is None.)
        # if at is None:
        #     _publish_due_virtuals(nowMins, row, rn, dayName, st, segment="post", allowDelays=allowDelays)
# -------------------------------------------------------------------------------------------------
# Support routines
# -------------------------------------------------------------------------------------------------
def _first_time_in_row(row):
    cand = []
    for k, v in row.items():
        if k is None:
            continue
        if not v: continue
        kl = str(k).lower()
        if kl in ("trigger","arr","dep") or ("arr" in kl) or ("dep" in kl):
            mm = parseTimeToMinutes(v)
            if mm is not None:
                cand.append(mm)
    return min(cand) if cand else None
    
def _last_time_in_row(row):
    """
    Return the latest (max) scheduled minute in the row across Arr/Dep/Trigger
    and any TPArr/TPDep columns. None if no times are present.
    """
    cand = []
    for k, v in row.items():
        if k is None or not v:
            continue
        kl = str(k).lower()
        if (kl in ("trigger", "arr", "dep")) or ("arr" in kl) or ("dep" in kl):
            mm = parseTimeToMinutes(v)
            if mm is not None:
                cand.append(mm)
    return max(cand) if cand else None

def _find_row_by_rn(timetablePath, dayName, reportingNumber):
    """
    Return the CSV row (dict) for rn on dayName, or None if not found.
    """
    for row, rn in iterTodayRows(timetablePath, dayName):
        if str(rn) == str(reportingNumber):
            return row
    return None
   
def _legacy_per_train(nowMins, row, rn, groups, allowDelays, allowCancel, ttName, dayName):
    firstTp = _first_time_in_row(row)
    if firstTp is None:
        return
    groupName = (row.get("Disruption group","") or "").strip()
    g = groups.get(groupName) if groupName else None
    seed0 = seedFor(rn, dayName, ttName)
    _ensure_initialized(nowMins, rn, firstTp, g, allowDelays, allowCancel, seed0)
    if isActive(rn):
        return
    if nowMins < firstTp and g:
        _apply_cadenced_updates(rn, g, seed0, nowMins, firstTp, allowDelays, allowCancel)
        
def _ensure_initialized(nowMins, rn, firstTp, g, allowDelays, allowCancel, seed0):
    if g:
        a = max(0, int(g.get("checkMax", 60))); b = max(0, int(g.get("checkMin", 30)))
    else:
        a, b = 60, 30
    if b > a: a, b = b, a
    initMinute = max(0, firstTp - rngUniformInt(seed0 ^ 0xA5A5, b, a))
    cur = getDisruption(rn)
    if cur is None:
        if nowMins >= initMinute or nowMins >= firstTp:
            _master_initialize(rn, g, allowDelays, allowCancel, seed0)
            
def _master_initialize(rn, g, allowDelays, allowCancel, seed0): 
    # Clear platform allocation at the moment that we first create disruption 
    #(or register the lack thereof) for this reporting number
    try: PAR.deregisterPlatform(rn)
    except Exception: pass
    if not g:
        registerDisruption(rn, 0); return
    pDelay = g["pDelay"] if allowDelays else 0.0
    pEarly = g["pEarly"] if allowDelays else 0.0
    pCancel = g["pCancel"] if allowCancel else 0.0
    pOn = max(0.0, 1.0 - (pDelay + pEarly + pCancel))
    S = float(pDelay + pEarly + pCancel + pOn) or 1.0
    probs = [pDelay/S, pEarly/S, pCancel/S, pOn/S]
    rnd = random.Random(seed0 ^ 0x5C5C)
    x = rnd.random()
    outcome = "on"; cum = 0.0
    for tag, w in (("delay",probs[0]), ("early",probs[1]), ("cancel",probs[2]), ("on",probs[3])):
        cum += w
        if x <= cum:
            outcome = tag
            break
    if outcome == "cancel" and allowCancel:
        registerDisruption(rn, 1441)
    elif outcome == "delay" and allowDelays and g["maxDelay"] > 0:
        mag = rngPickGeometric(seed0 ^ 0x1717, g["maxDelay"])
        registerDisruption(rn, mag)
    elif outcome == "early" and allowDelays and g["maxEarly"] > 0:
        mag = rngPickGeometric(seed0 ^ 0x2727, g["maxEarly"])
        registerDisruption(rn, -mag)
    else:
        registerDisruption(rn, 0)
def _apply_cadenced_updates(rn, g, seed0, nowMins, firstTp, allowDelays, allowCancel):
    a = max(0, int(g.get("checkMax", 60))); b = max(0, int(g.get("checkMin", 30)))
    if b > a: a, b = b, a
    start = max(0, firstTp - a)
    lastDone = _state["trains"].get(rn, {}).get("lastUpdateLegacy", start - 1)
    t = max(start, lastDone + 1)
    while t <= min(nowMins - 1, firstTp - 1):
        curAfter = _apply_step_evolution(rn, g, seed0, t, firstTp, allowDelays, allowCancel)
        if curAfter is not None:
            updateDisruption(rn, int(curAfter))
        t += 1
    _state["trains"].setdefault(rn, {})["lastUpdateLegacy"] = min(nowMins - 1, firstTp - 1)
def _init_state_for_train(row, rn, groups, ttName, dayName, mainTimes, klass, segs,
                          allowDelays, allowCancel, nowMins):
    st = {
        "mode": "fluid",
        "planned": None,
        "tpList": segs,
        "nextIndexPre": 0,
        "nextIndexPost": 0,
        "lastSimMinute": None,
        "firstRelevantMinute": None,
        "class": klass,
        "mainTimes": mainTimes,
        "pendingCancelAfterTP": False,
        "activeDelayedStart": {"known": False, "startMin": None},
        "postedPreSegmentDone": False,
        "publishStartPre": nowMins,
        "publishStartPost": nowMins,
        # NEW: ensures the at_tp planned outcome applies only once
        "manifestedAtTP": False,
    }
    seed0 = seedFor(rn, dayName, ttName)
    groupName = (row.get("Disruption group","") or "").strip()
    g = groups.get(groupName) if groupName else None
    # Master outcome as before
    if g:
        pDelay = g["pDelay"] if allowDelays else 0.0
        pEarly = g["pEarly"] if allowDelays else 0.0
        pCancel = g["pCancel"] if allowCancel else 0.0
        pOn = max(0.0, 1.0 - (pDelay + pEarly + pCancel))
        S = float(pDelay + pEarly + pCancel + pOn) or 1.0
        probs = [pDelay/S, pEarly/S, pCancel/S, pOn/S]
        rnd = random.Random(seed0 ^ 0x5C5C)
        x = rnd.random()
        outcome = "on"; cum = 0.0
        for tag, w in (("delay",probs[0]),("early",probs[1]),("cancel",probs[2]),("on",probs[3])):
            cum += w
            if x <= cum:
                outcome = tag
                break
        try:
            wDelayPre = float(_readMemStr("TP_WEIGHT_DELAY_PRE_FIRSTTP", "0.70"))
        except:
            wDelayPre = 0.70
        try:
            wEarlyPre = float(_readMemStr("TP_WEIGHT_EARLY_PRE_FIRSTTP", "0.70"))
        except:
            wEarlyPre = 0.70
        if outcome == "delay":
            manifest = "pre" if random.Random(seed0 ^ 0xD0D0).random() < max(0.0, min(1.0, wDelayPre)) else "at_tp"
        elif outcome == "early":
            manifest = "pre" if random.Random(seed0 ^ 0xE0E0).random() < max(0.0, min(1.0, wEarlyPre)) else "at_tp"
        elif outcome == "cancel":
            manifest = "pre"
        else:
            manifest = None
        if outcome == "delay" and g["maxDelay"] > 0:
            mag = rngPickGeometric(seed0 ^ 0x1717, g["maxDelay"])
        elif outcome == "early" and g["maxEarly"] > 0:
            mag = rngPickGeometric(seed0 ^ 0x2727, g["maxEarly"])
        else:
            mag = 0
        st["planned"] = {"type": outcome, "mag": int(mag), "manifest": manifest, "seed0": seed0}
    else:
        st["planned"] = {"type": "on", "mag": 0, "manifest": None, "seed0": seed0}
    # First-relevant minute (as before)
    firstPre = st["tpList"]["pre"][0]["sched"] if st["tpList"]["pre"] else None
    firstRelevant = firstPre if firstPre is not None else mainTimes.get("main")
    st["firstRelevantMinute"] = firstRelevant
    st["lastSimMinute"] = firstRelevant
    # Window-gated initialisation
    if getDisruption(rn) is None and firstRelevant is not None:    
            # Clear platform allocation from the previous working just before we first register disruption
            try: 
                PAR.deregisterPlatform(rn)
            except Exception: 
                pass
        if g:
            a = max(0, int(g.get("checkMax", 60))); b = max(0, int(g.get("checkMin", 30)))
        else:
            a, b = 60, 30
        if b > a: a, b = b, a
        initMinute = max(0, firstRelevant - rngUniformInt(seed0 ^ 0xA5A5, b, a))
        if initMinute < firstRelevant and nowMins >= initMinute and nowMins < firstRelevant:
            if st["planned"]["type"] == "cancel":
                registerDisruption(rn, 1441)
            elif st["planned"]["type"] == "delay" and st["planned"]["manifest"] == "pre" and st["planned"]["mag"] != 0:
                registerDisruption(rn, st["planned"]["mag"])
            elif st["planned"]["type"] == "early" and st["planned"]["manifest"] == "pre" and st["planned"]["mag"] != 0:
                registerDisruption(rn, -st["planned"]["mag"])
            else:
                # 'on' or at-tp manifestations -> 0 is valid within the pre-TP window
                registerDisruption(rn, 0)
        else:
            # Leave as None; TP events will write later
            pass
    return st
def _advance_internal(nowMins, row, rn, st, groups, allowDelays, allowCancel):
    groupName = (row.get("Disruption group","") or "").strip()
    g = groups.get(groupName) if groupName else None
    seed0 = st["planned"]["seed0"] if (st.get("planned") and "seed0" in st["planned"]) else seedFor(rn, _state["_day"], _readMemStr("CURRENTTIMETABLE") or "")
    firstTp = st.get("firstRelevantMinute") or nowMins
    if st["lastSimMinute"] is None:
        st["lastSimMinute"] = firstTp
    t = st["lastSimMinute"]
    if t > nowMins:
        st["lastSimMinute"] = nowMins
        return
    while t < nowMins:
        curAfter = _apply_step_evolution(rn, g, seed0, t, firstTp, allowDelays, allowCancel)
        if curAfter is not None:
            updateDisruption(rn, int(curAfter))
            if isinstance(curAfter, int) and curAfter == 1442:
                st["pendingCancelAfterTP"] = True
        t += 1
    st["lastSimMinute"] = nowMins
    
def _publish_due_virtuals(nowMins, row, rn, dayName, st, segment, allowDelays):
    # Publish virtual timing points due up to 'nowMins'. One function; no duplicates.
    events = st["tpList"]["pre"] if segment == "pre" else st["tpList"]["post"]
    if not events:
        return

    idxKey  = "nextIndexPre"   if segment == "pre"  else "nextIndexPost"
    gateKey = "publishStartPre" if segment == "pre" else "publishStartPost"

    i = st[idxKey]
    publishStart = st.get(gateKey, nowMins)

    groupName = (row.get("Disruption group","") or "").strip()
    g = loadDisruptionGroups().get(groupName) if groupName else None

    while i < len(events):
        e = events[i]

        # Current disruption value (may still be None/0)
        cur = getDisruption(rn)
        try:
            curInt = int(cur) if cur is not None else 0
        except:
            curInt = 0

        # --- Missed-"pre" fallback: if planned "pre", now beyond firstRelevant, and still neutral, apply once.
        try:
            firstRel = st.get("firstRelevantMinute")
        except Exception:
            firstRel = None
        if (st.get("planned") and st["planned"].get("manifest") == "pre"
            and firstRel is not None and nowMins >= firstRel and curInt == 0):
            pType = st["planned"].get("type")
            try:
                mag = int(st["planned"].get("mag") or 0)
            except Exception:
                mag = 0          
        if pType == "delay" and mag > 0 and allowDelays:
            if getDisruption(rn) is None:
                try: PAR.deregisterPlatform(rn)
                except Exception: pass
                registerDisruption(rn, mag)
            else:
                updateDisruption(rn, mag)
            curInt = mag
        elif pType == "early" and mag > 0 and allowDelays:
            val = -mag
            if getDisruption(rn) is None:
                try: PAR.deregisterPlatform(rn)
                except Exception: pass
                registerDisruption(rn, val)
            else:
                updateDisruption(rn, val)
            curInt = val

        # --- Materialise planned at_tp outcome exactly once, if not yet manifested ---
        if st.get("planned") and st["planned"].get("manifest") == "at_tp" and not st.get("manifestedAtTP", False):
            pType = st["planned"].get("type")
            mag = int(st["planned"].get("mag", 0) or 0)
            if pType in ("delay","early") and mag > 0 and curInt == 0:
                apply = mag if pType == "delay" else -mag
                try:
                    existing = getDisruption(rn)
                    if existing is None:
                        registerDisruption(rn, apply)
                    else:
                        updateDisruption(rn, apply)
                    curInt = apply
                    st["manifestedAtTP"] = True
                except Exception as ex:
                    print("[DG][ATTP][ERROR] {}: {}".format(rn, ex))

        # Compute actual minute for this event
        actualMinute = float(e["sched"] + curInt)
                      
        # Do not publish timing for far-past events unless the RN already has disruption OR any timing today
        try:
            postGrace = int(float(_readMemStr("TP_POST_GRACE_MINUTES", "2")))
        except:
            postGrace = 2
        try:
            cur = getDisruption(rn)
            hasDisruptionAlready = (cur is not None)
        except Exception:
            hasDisruptionAlready = False
        hasAnyTimingToday = _HasAnyTimingToday(rn, dayName)
        activeNow = isActive(rn)  # <-- NEW
        if ((nowMins - int(actualMinute)) > postGrace) and (not hasDisruptionAlready) and (not hasAnyTimingToday) and (not activeNow):
            # Skip very-old events for orphaned services; advance i and continue
            i += 1
            continue

        # If this is a Dep paired with an Arr at same TP, apply dwell/stop rules
        if e["kind"] == "Dep":
            arrEv = None
            for back in range(i-1, -1, -1):
                if events[back]["name"] == e["name"] and events[back]["kind"] == "Arr":
                    arrEv = events[back]
                    break
            if arrEv is not None:
                arriveActual = float(arrEv["sched"] + curInt)
                actualMinute = _apply_stop_rules(arrEv["sched"], e["sched"], arriveActual, g, st.get("planned"), allowDelays)

        # --- Publish-gate: if overdue because of a warp, publish exactly once instead of skipping ---        
        if (actualMinute < publishStart) and ((int(publishStart) - int(actualMinute)) <= postGrace or hasDisruptionAlready or hasAnyTimingToday or activeNow):
            if st["pendingCancelAfterTP"]:
                curInt = 1442
                st["pendingCancelAfterTP"] = False
            _publish_at_virtual_tp(e, row, rn, dayName, actualMinute, curInt)
            i += 1
            continue

        # Publish if due
        if actualMinute <= nowMins:
            if st["pendingCancelAfterTP"]:
                curInt = 1442
                st["pendingCancelAfterTP"] = False
            _publish_at_virtual_tp(e, row, rn, dayName, actualMinute, curInt)
            i += 1
        else:
            break

        st[idxKey]  = i
        st[gateKey] = nowMins


def _check_crossed_into_layout(nowMins, st):
    if st["postedPreSegmentDone"]:
        return
    main = st["mainTimes"]["main"]
    if main is not None and nowMins >= main:
        st["postedPreSegmentDone"] = True
def _backfill_missed_pre_virtuals(st, row, rn, dayName):
    pre = st["tpList"]["pre"]
    idx = st["nextIndexPre"]
    if idx < len(pre):
        print("[DG][ERROR] ActiveTrain started but {} pre-main virtual timing point(s) were unlogged for {}. Backfilling now.".format(len(pre) - idx, rn))
        nowMins = parseTimeToMinutes(_readMemStr("CURRENTTIME"))
        for i in range(idx, len(pre)):
            e = pre[i]
            cur = getDisruption(rn)
            try:
                curInt = int(cur) if cur is not None else 0
            except:
                curInt = 0
            # Missed "pre" window fallback: if planned pre, now beyond firstRelevant, and still neutral, apply once.
            try:
                firstRel = st.get("firstRelevantMinute")
            except Exception:
                firstRel = None
            if (st.get("planned") and st["planned"].get("manifest") == "pre"
                and firstRel is not None and nowMins >= firstRel and curInt == 0):
                pType = st["planned"].get("type")
                try:
                    mag = int(st["planned"].get("mag") or 0)
                except Exception:
                    mag = 0
                if pType == "delay" and mag > 0 and allowDelays:
                    if getDisruption(rn) is None:
                        registerDisruption(rn, mag)
                    else:
                        updateDisruption(rn, mag)
                    curInt = mag
                elif pType == "early" and mag > 0 and allowDelays:
                    val = -mag
                    if getDisruption(rn) is None:
                        registerDisruption(rn, val)
                    else:
                        updateDisruption(rn, val)
                    curInt = val
            actualMinute = float(e["sched"] + curInt)
            if actualMinute >= nowMins:
                actualMinute = max(0.0, actualMinute - 1.0)
            _publish_at_virtual_tp(e, row, rn, dayName, actualMinute, curInt)
        st["nextIndexPre"] = len(pre)