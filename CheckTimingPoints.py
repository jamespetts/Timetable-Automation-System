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
# Synchronize timing points between the active timetable and the TimingRegister,
# and perform weekly day-based maintenance robustly (including time warps).

import jmri, os, csv, re
from jmri.util import FileUtil

# --- utils ---
def _mm():
    return jmri.InstanceManager.getDefault(jmri.MemoryManager)

def _get_mem(name):
    mm = _mm()
    m = mm.getMemory(name)
    return None if m is None else m.getValue()

def _days_between_inclusive(start_day, end_day, days):
    """Return the list of days strictly after start_day up to and including end_day, wrapping as needed.
       If start_day == end_day -> [] (no change)."""
    if start_day not in days or end_day not in days:
        return []
    if start_day == end_day:
        return []
    si = days.index(start_day)
    ei = days.index(end_day)
    out = []
    i = si
    while True:
        i = (i + 1) % len(days)
        out.append(days[i])
        if i == ei:
            break
    return out

# --- main work ---
def sync_timing_points_from_timetable(verbose=True):
    import TimingRegister as TR
    # Reload if available in this Jython environment (safe no-op otherwise)
    try:
        reload  # py2
    except NameError:
        pass
    try:
        reload(TR)
    except Exception:
        pass

    # 1) Read current day (source of truth) and timetable name
    current_day = _get_mem("IMDAYOFWEEK")
    timetable_name = _get_mem("IMCURRENTTIMETABLE")

    if timetable_name is None or (isinstance(timetable_name, basestring) and timetable_name.strip() == ""):
        if verbose: print("[TPSync] No IMCURRENTTIMETABLE set; nothing to do.")
        return

    # 2) Build full path to timetable (TSV)
    profile_path = FileUtil.getProfilePath()
    tt_path = os.path.join(profile_path, "timetable", str(timetable_name) + ".csv")
    if not os.path.exists(tt_path):
        if verbose: print("[TPSync] Timetable file not found: {}".format(tt_path))
        # We still do day-roll maintenance if needed
    # 3) Discover timing points in the timetable header (case-insensitive)
    timetable_tp_case = {}  # lower_name -> original header case name
    if os.path.exists(tt_path):
        try:
            with open(tt_path, "r") as f:
                # DictReader will read header even if there are no rows
                reader = csv.DictReader(f, delimiter="\t")
                headers = reader.fieldnames or []
                # Pattern: TPArr <name> / TPDep <name> (case-insensitive)
                pat = re.compile(r"^TP(?:Arr|Dep)\s+(.+)$", re.IGNORECASE)
                for h in headers:
                    if not h:
                        continue
                    m = pat.match(h.strip())
                    if m:
                        tp_name = m.group(1).strip()
                        if tp_name:
                            timetable_tp_case[tp_name.lower()] = tp_name
        except Exception as e:
            print("[TPSync] Warning: failed to read timetable header: {}".format(e))

    # 4) Ensure timetable timing points exist in register (case-insensitive match)
    existing = TR.listTimingPoints()  # actual keys
    existing_by_lower = dict((k.lower(), k) for k in existing)

    # Create missing
    for low, as_in_header in timetable_tp_case.items():
        actual_key = existing_by_lower.get(low)
        if actual_key is None:
            TR.ensureTimingPoint(as_in_header)
            if verbose: print("[TPSync] Created timing point '{}'".format(as_in_header))

    # 5) For register timing points not present in timetable: delete or clear timings
    #    (Preserve blocks iff non-empty)
    timetable_lowers = set(timetable_tp_case.keys())
    for tp in TR.listTimingPoints():
        if tp.lower() not in timetable_lowers:
            blocks = TR.getBlocks(tp)
            empty_blocks = (blocks is None) or (isinstance(blocks, list) and len(blocks) == 0)
            if empty_blocks:
                deleted = TR.deleteTimingPoint(tp)
                if verbose and deleted: print("[TPSync] Deleted obsolete timing point '{}' (no blocks)".format(tp))
            else:
                removed = TR.clearTimings(tp)
                if verbose: print("[TPSync] Cleared {} timings for '{}' (kept blocks)".format(removed, tp))

    # 6) Day-roll maintenance (behaviour B): clear entries for all crossed days
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    try:
        last = TR.getMeta("lastMaintenanceDay", None)
    except Exception:
        last = None

    if isinstance(current_day, basestring):
        current_day = current_day.strip()
    if last is None:
        # First run in this session/file: record and do not delete anything yet
        if current_day in days:
            TR.setMeta("lastMaintenanceDay", current_day)
            if verbose: print("[TPSync] Set lastMaintenanceDay -> {}".format(current_day))
    else:
        if current_day in days and last in days and current_day != last:
            crossed = _days_between_inclusive(last, current_day, days)  # excludes last, includes current
            total_removed = 0
            for d in crossed:
                try:
                    removed = TR.removeByDay(d)
                    total_removed += int(removed or 0)
                    if verbose: print("[TPSync] Maintenance: cleared {} entries for '{}'".format(removed, d))
                except Exception as e:
                    print("[TPSync] Warning: removeByDay('{}') failed: {}".format(d, e))
            TR.setMeta("lastMaintenanceDay", current_day)
            if verbose: print("[TPSync] Updated lastMaintenanceDay -> {}; removed {} total".format(current_day, total_removed))

# Optional: allow direct run for quick testing
if __name__ == "__main__":
    sync_timing_points_from_timetable(verbose=True)