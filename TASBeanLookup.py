# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>.
#
# Shared utility for robust JMRI bean lookup across multiple system connections.
# Works with JMRI 5.14 and later.
import jmri

_WARNED_COLLISIONS = set()

def _NormSuffix(s):
    # Normalize suffix keys to be prefix-agnostic.
    # Also strip accidental internal prefixes if a caller passes a full system name.
    try:
        t = str(s).strip().upper()
    except:
        return ""
    if t == "":
        return ""

    # If caller passed IMxxxx, strip the leading IM.
    if t.startswith("IM") and len(t) > 2:
        return t[2:]

    # If caller passed I<n>Mxxxx (e.g. I2Mxxxx), strip the leading I<n>M.
    if t.startswith("I"):
        i = 1
        while i < len(t) and t[i].isdigit():
            i += 1
        if i > 1 and i < len(t) and t[i] == "M" and (i + 1) < len(t):
            return t[i + 1:]

    return t

def _PreferredInternalPrefixes(memManager):
    # Ordered preference: IM first, then I2M, I3M, ...
    prefs = ["IM"]
    try:
        # Go far enough for practical purposes. Adjust if you ever see I10M etc.
        for i in range(2, 10):
            prefs.append("I" + str(i) + "M")
    except:
        pass

    # If the current MemoryManager prefix is something else, include it last.
    # This preserves your explicit preference for IM, then I2M/I3M..., but still
    # gives a chance to find beans in unusual internal prefixes.
    try:
        cur = memManager.getSystemNamePrefix()
        if cur is not None:
            cur = str(cur).strip().upper()
            if cur != "" and cur not in prefs:
                prefs.append(cur)
    except:
        pass

    return prefs


def _SelectBySuffixWithPreference(memManager, suffix, matches):
    # matches is a list of Memory beans whose system name endswith(suffix).
    # Prefer exact system name matches in this order: IM<suffix>, I2M<suffix>, ...
    if matches is None or len(matches) == 0:
        return None

    # Build a lookup by normalized system name
    bySys = {}
    sysNames = []
    for m in matches:
        try:
            sn = m.getSystemName()
            snu = str(sn).strip().upper()
            bySys[snu] = m
            sysNames.append(snu)
        except:
            pass

    prefs = _PreferredInternalPrefixes(memManager)
    for p in prefs:
        target = p + suffix
        if target in bySys:
            return bySys[target]

    # No preferred exact match found: fall back deterministically to the lowest system name
    # so results are stable across runs.
    try:
        # Deterministic fallback: prefer non-nested internal names over legacy nested ones.
        sysNames.sort(key=lambda n: (_IsNestedImSystemName(n), n))
        return bySys.get(sysNames[0], matches[0])
    except:
        return matches[0]

def _IsNestedImSystemName(sysNameUpper):
    # True for legacy/incorrect internal names like I2MIMxxxx, I3MIMxxxx, or IMIMxxxx.
    if sysNameUpper.startswith("IMIM"):
        return True
    if sysNameUpper.startswith("I"):
        i = 1
        while i < len(sysNameUpper) and sysNameUpper[i].isdigit():
            i += 1
        # At this point, sysNameUpper[i] should be 'M' for I<n>M...
        if i > 1 and sysNameUpper.startswith("MIM", i):
            return True
    return False

def _FindAllMatchesBySuffix(memManager, suffix):
    matches = []
    try:
        beans = memManager.getNamedBeanSet()
    except:
        beans = None

    if beans is None:
        return matches

    for mem in beans:
        try:
            sysName = mem.getSystemName()
            sysUpper = str(sysName).strip().upper()
            if sysUpper.endswith(suffix):
                matches.append(mem)
        except:
            pass

    return matches


def _WarnIfCollision(suffix, matches, chosen):
    try:
        if matches is None:
            return
        if len(matches) <= 1:
            return
            
        key = str(suffix)
        if key in _WARNED_COLLISIONS:
            return
        _WARNED_COLLISIONS.add(key)

        names = []
        for m in matches:
            try:
                names.append(str(m.getSystemName()).strip())
            except:
                pass
        try:
            names.sort()
        except:
            pass

        chosenName = "<unknown>"
        try:
            chosenName = str(chosen.getSystemName()).strip()
        except:
            pass

        print("[TASBeanLookup] WARN: Multiple Memory beans match suffix '" + suffix + "': " +
              ", ".join(names) + ". Using: " + chosenName)
    except:
        pass


def FindMemoryBySuffix(suffix):
    """
    Find a Memory bean whose System Name ends with the given suffix,
    with ordered preference for internal prefixes: IM, then I2M, I3M, ...
    Returns the Memory object or None if not found.
    """
    suffix = _NormSuffix(suffix)
    if not suffix:
        return None

    # Ensure Internal MemoryManager exists
    jmri.InstanceManager.memoryManagerInstance()
    memManager = jmri.InstanceManager.getDefault(jmri.MemoryManager)

    matches = _FindAllMatchesBySuffix(memManager, suffix)
    chosen = _SelectBySuffixWithPreference(memManager, suffix, matches)
    _WarnIfCollision(suffix, matches, chosen)
    return chosen


def SafeGetMemoryValue(suffix, default=""):
    """
    Get the value of a Memory bean by suffix, ignoring prefixes.
    Uses ordered preference for internal prefixes: IM, then I2M, I3M, ...
    Returns the value if found, otherwise returns the default.
    Does NOT create a new bean.
    """
    suffix = _NormSuffix(suffix)
    if not suffix:
        return default

    mem = FindMemoryBySuffix(suffix)
    if mem is None:
        return default

    try:
        val = mem.getValue()
        return str(val) if val is not None else default
    except:
        return default


def ProvideMemoryBySuffix(suffix, default=""):
    """
    Ensure a Memory bean exists for the given suffix (prefix-agnostic).
    If found (using ordered preference IM, then I2M, I3M, ...), return it.
    If not found, create it using the MemoryManager's current system prefix and seed with default.
    """
    suffix = _NormSuffix(suffix)
    if not suffix:
        return None

    # Ensure Internal MemoryManager is present (JMRI pattern)
    jmri.InstanceManager.memoryManagerInstance()
    memManager = jmri.InstanceManager.getDefault(jmri.MemoryManager)

    existing = FindMemoryBySuffix(suffix)
    if existing is not None:
        return existing

    # Create using the manager's current prefix (whatever it is in this environment)
    try:
        prefix = memManager.getSystemNamePrefix()
        prefix = str(prefix).strip().upper() if prefix is not None else "IM"
        if prefix == "":
            prefix = "IM"
    except:
        prefix = "IM"

    newMem = memManager.provideMemory(prefix + suffix)
    try:
        if newMem.getValue() is None:
            newMem.setValue(default)
    except:
        pass
    return newMem


def SafeGetOrCreateMemoryValue(suffix, default=""):
    """
    Get the value of a Memory bean by suffix, creating it if necessary.
    Returns the value or default if newly created.
    """
    mem = ProvideMemoryBySuffix(suffix, default)
    try:
        return mem.getValue() if mem else default
    except:
        return default


def SafeSetMemoryValue(suffix, value):
    """
    Set the value of a Memory bean identified by suffix (prefix-agnostic).
    Creates the bean if it does not exist.
    """
    mem = ProvideMemoryBySuffix(suffix, str(value))
    if mem:
        try:
            mem.setValue(str(value))
            return True
        except:
            return False
    return False
