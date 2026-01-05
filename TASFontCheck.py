# This file is part of the Timetable Automation System by James E. Petts
#
# Font checker helper for TAS (JMRI 5.14 / Jython 2.7).
#
# Purpose:
# - Scan profile:jython/*.py for font preference lists (prefs=[...]) and Font("Family",...) literal usages.
# - Also detect ordered candidate lists used in PickFamily(...) style selectors.
# - Detect configured font family values from Memories (e.g. TAS_FONT_FAMILY) when scripts reference them.
# - Apply equivalence/variant matching so family names that differ only by spacing or common suffixes are accepted.
# - Show a clear, color-coded report and provide clickable DuckDuckGo searches for missing fonts.
#
# NOTE: This script does NOT install fonts. It provides guidance and search links.
# Users should restart JMRI after installing all fonts.
#
# ASCII only / CamelCase / Thread-safe EDT.

import os
import java

import javax.swing as swing
from javax.swing import (JFrame, JPanel, JScrollPane, JTable, JButton, JLabel,
                         JOptionPane, JDialog, JEditorPane, ListSelectionModel)
from javax.swing.table import DefaultTableModel, DefaultTableCellRenderer
from javax.swing.event import HyperlinkListener
from java.awt import BorderLayout, Color, Dimension
from java.awt import Desktop
from java.net import URI, URLEncoder

from java.awt import GraphicsEnvironment

import jmri
from jmri.util import FileUtil

# ---------------------------
# Configuration
# ---------------------------

LOGICAL_FONTS = set(["SansSerif", "Serif", "Monospaced", "Dialog", "DialogInput"])

# Lightbox preferred equivalence group.
JOHNSTON_EQUIV = ["Johnston 100", "Johnston100", "Railway", "Railway Sans"]
LIGHTBOX_ACCEPTABLE = ["Granby"]
LIGHTBOX_FALLBACK_ONLY = ["Liberation Sans", "Helvetica", "Arial", "SansSerif"]

# Known generic fallbacks used in selector lists.
GENERIC_FALLBACKS = set(["Helvetica", "Liberation Sans", "Arial", "SansSerif", "Serif", "Dialog", "DialogInput", "Monospaced"])

READ_LIMIT = 262144

# Skip scanning our own font checker scripts to avoid self-matches.
SKIP_PREFIXES = ["TASFontCheck"]

# UI colors
OK_BG = Color(210, 245, 210)
WARN_BG = Color(255, 245, 200)
BAD_BG = Color(255, 215, 215)
NEUTRAL_BG = Color(245, 245, 245)

# ---------------------------
# Helpers
# ---------------------------

def _NormalizeFamily(fam):
    try:
        return str(fam).strip()
    except:
        return ""

def _CanonFamily(fam):
    # Canonicalize by removing spaces, hyphens and underscores and lowercasing.
    try:
        s = str(fam).strip().lower()
    except:
        s = ""
    if s == "":
        return ""
    try:
        s = s.replace(" ", "").replace("-", "").replace("_", "")
    except:
        pass
    return s

def _CanonVariants(fam):
    # Generate a small set of canonical variants to catch common family-name suffix differences
    # (e.g. ...Normal, ...Regular, ...MT) without risking broad false positives.
    base = _CanonFamily(fam)
    if base == "":
        return set([""])
    out = set([base])

    # Strip common trailing tokens.
    suffixes = ["normal", "regular", "roman", "book", "mt", "std", "tt", "ps", "medium"]

    changed = True
    cur = base
    # Iteratively strip suffixes if present.
    while changed:
        changed = False
        for suf in suffixes:
            if cur.endswith(suf) and len(cur) > len(suf) + 3:
                cur2 = cur[:-len(suf)]
                if cur2 not in out:
                    out.add(cur2)
                cur = cur2
                changed = True
                break

    return out

def _IsLogicalFont(fam):
    try:
        return _NormalizeFamily(fam) in LOGICAL_FONTS
    except:
        return False

def _LooksLikeFontName(fam):
    s = _NormalizeFamily(fam)
    if s == "":
        return False
    if len(s) < 3:
        return False
    hasAlpha = False
    for ch in s:
        try:
            if "a" <= ch.lower() <= "z":
                hasAlpha = True
                break
        except:
            pass
    if not hasAlpha:
        return False
    return True

def _ProfileJythonDir():
    try:
        return FileUtil.getExternalFilename("profile:jython")
    except:
        return None

def _ShouldSkipFile(fileName):
    try:
        fn = str(fileName or "")
    except:
        fn = ""
    low = fn.lower()
    for p in SKIP_PREFIXES:
        try:
            if low.startswith(str(p).lower()):
                return True
        except:
            pass
    return False

def _ListProfileScripts():
    jdir = _ProfileJythonDir()
    if (not jdir) or (not os.path.isdir(jdir)):
        return []
    out = []
    try:
        for fn in os.listdir(jdir):
            if not fn.lower().endswith(".py"):
                continue
            if _ShouldSkipFile(fn):
                continue
            full = os.path.join(jdir, fn)
            if os.path.isfile(full):
                out.append((fn, full))
    except:
        pass
    return out

def _ReadText(path):
    try:
        f = open(path, "r")
        try:
            raw = f.read(READ_LIMIT)
        finally:
            try:
                f.close()
            except:
                pass
        return raw.replace("\r\n", "\n").replace("\r", "\n")
    except:
        try:
            f = open(path, "rb")
            try:
                raw = f.read(READ_LIMIT)
            finally:
                try:
                    f.close()
                except:
                    pass
            try:
                return raw.decode("utf-8", "ignore").replace("\r\n", "\n").replace("\r", "\n")
            except:
                return ""
        except:
            return ""

def _AvailableFontFamilies():
    try:
        fams = GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames()
        return [str(f) for f in fams]
    except:
        return []

def _ReadMemStrSuffix(suffix, default=""):
    # Prefix-agnostic memory lookup (avoids assuming IM).
    try:
        import TASBeanLookup as TBL
        v = TBL.SafeGetMemoryValue(suffix, default)
        s = "" if v is None else str(v).strip()
        return s if s else default
    except:
        return default

# ---------------------------
# Strip docstrings (triple-quoted) and full-line comments.
# No regex used.
# ---------------------------

def _StripDocstringsAndFullLineComments(text):
    if not text:
        return ""

    # Remove full-line comments.
    lines = []
    for ln in text.split("\n"):
        try:
            if ln.lstrip().startswith("#"):
                lines.append("")
            else:
                lines.append(ln)
        except:
            lines.append(ln)
    t = "\n".join(lines)

    # Strip triple-quoted docstrings using a simple state machine.
    out = []
    i = 0
    n = len(t)
    state = "NORMAL"  # NORMAL, DOC_SQ, DOC_DQ

    while i < n:
        ch = t[i]

        if state == "NORMAL":
            if ch == "'" and i + 2 < n and t[i+1] == "'" and t[i+2] == "'":
                state = "DOC_SQ"
                out.append("   ")
                i += 3
                continue
            if ch == '"' and i + 2 < n and t[i+1] == '"' and t[i+2] == '"':
                state = "DOC_DQ"
                out.append("   ")
                i += 3
                continue
            out.append(ch)
            i += 1
            continue

        if state == "DOC_SQ":
            if ch == "'" and i + 2 < n and t[i+1] == "'" and t[i+2] == "'":
                state = "NORMAL"
                out.append("   ")
                i += 3
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if state == "DOC_DQ":
            if ch == '"' and i + 2 < n and t[i+1] == '"' and t[i+2] == '"':
                state = "NORMAL"
                out.append("   ")
                i += 3
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

    return "".join(out)

# ---------------------------
# Extractors (no regex)
# ---------------------------

def _ExtractQuotedStrings(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "'" or ch == '"':
            quote = ch
            i += 1
            buf = []
            while i < n:
                c = s[i]
                if c == "\\":
                    if i + 1 < n:
                        buf.append(s[i+1])
                        i += 2
                        continue
                    i += 1
                    continue
                if c == quote:
                    i += 1
                    break
                buf.append(c)
                i += 1
            try:
                out.append("".join(buf))
            except:
                pass
            continue
        i += 1
    return out

def _FindMatchingBracket(text, startIdx):
    # startIdx points at '['. Return index of matching ']' at same nesting level, or -1.
    i = startIdx
    n = len(text)
    depth = 0
    inQuote = None
    while i < n:
        ch = text[i]
        if inQuote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == inQuote:
                inQuote = None
                i += 1
                continue
            i += 1
            continue
        if ch == "'" or ch == '"':
            inQuote = ch
            i += 1
            continue
        if ch == '[':
            depth += 1
            i += 1
            continue
        if ch == ']':
            depth -= 1
            i += 1
            if depth == 0:
                return i - 1
            continue
        i += 1
    return -1

def _ExtractPrefsLists(codeText):
    out = []
    if not codeText:
        return out
    idx = 0
    n = len(codeText)
    while idx < n:
        p = codeText.find('prefs', idx)
        if p < 0:
            break
        before = codeText[p-1] if p > 0 else ' '
        after = codeText[p+5] if p + 5 < n else ' '
        if (before.isalnum() or before == '_') or (after.isalnum() or after == '_'):
            idx = p + 5
            continue
        eq = codeText.find('=', p+5)
        if eq < 0:
            idx = p + 5
            continue
        lb = codeText.find('[', eq+1)
        if lb < 0:
            idx = p + 5
            continue
        rb = _FindMatchingBracket(codeText, lb)
        if rb < 0:
            idx = lb + 1
            continue
        body = codeText[lb+1:rb]
        vals = _ExtractQuotedStrings(body)
        seen = set()
        ordered = []
        for v in vals:
            s = _NormalizeFamily(v)
            if not _LooksLikeFontName(s):
                continue
            if s in seen:
                continue
            seen.add(s)
            ordered.append(s)
        if ordered:
            out.append(ordered)
        idx = rb + 1
    return out

def _ExtractFontCtorFamilies(codeText):
    out = []
    if not codeText:
        return out
    idx = 0
    n = len(codeText)
    while idx < n:
        p = codeText.find('Font', idx)
        if p < 0:
            break
        before = codeText[p-1] if p > 0 else ' '
        after = codeText[p+4] if p + 4 < n else ' '
        if (before.isalnum() or before == '_') or (after.isalnum() or after == '_'):
            idx = p + 4
            continue
        q = p + 4
        while q < n and codeText[q].isspace():
            q += 1
        if q >= n or codeText[q] != '(':
            idx = p + 4
            continue
        q += 1
        while q < n and codeText[q].isspace():
            q += 1
        if q >= n:
            break
        if codeText[q] != "'" and codeText[q] != '"':
            idx = q
            continue
        quote = codeText[q]
        q += 1
        buf = []
        while q < n:
            ch = codeText[q]
            if ch == "\\":
                if q + 1 < n:
                    buf.append(codeText[q+1])
                    q += 2
                    continue
                q += 1
                continue
            if ch == quote:
                q += 1
                break
            buf.append(ch)
            q += 1
        fam = _NormalizeFamily("".join(buf))
        if _LooksLikeFontName(fam):
            out.append(fam)
        idx = q
    return out

def _ExtractPickFamilyCandidateLists(codeText):
    # Detect PickFamily(...) style selectors where the first arg is a list literal of string candidates.
    # Returns a list of candidate lists (ordered).
    out = []
    if not codeText:
        return out
    idx = 0
    n = len(codeText)
    while idx < n:
        # Find token "PickFamily"
        p = codeText.find('PickFamily', idx)
        if p < 0:
            break
        # Ensure identifier boundary (allows BR_PickFamily too; we only need the call site and list)
        # We just want to locate the '(' after it.
        q = p + len('PickFamily')
        while q < n and codeText[q].isspace():
            q += 1
        if q >= n or codeText[q] != '(':
            idx = q
            continue
        q += 1
        while q < n and codeText[q].isspace():
            q += 1
        if q >= n or codeText[q] != '[':
            idx = q
            continue
        lb = q
        rb = _FindMatchingBracket(codeText, lb)
        if rb < 0:
            idx = lb + 1
            continue
        body = codeText[lb+1:rb]
        vals = _ExtractQuotedStrings(body)
        ordered = []
        seen = set()
        for v in vals:
            s = _NormalizeFamily(v)
            if not _LooksLikeFontName(s):
                continue
            if s in seen:
                continue
            seen.add(s)
            ordered.append(s)
        # Heuristic: treat as font list only if it contains at least one generic fallback or has >=3 items.
        if ordered:
            hasGeneric = False
            for s in ordered:
                if s in GENERIC_FALLBACKS:
                    hasGeneric = True
                    break
            if hasGeneric or len(ordered) >= 3:
                out.append(ordered)
        idx = rb + 1
    return out

# ---------------------------
# Requirement model
# ---------------------------

class FontRequirement(object):
    def __init__(self, key, title, candidates, scripts, acceptable=None, fallbackOnly=None, configured=None):
        self.Key = key
        self.Title = title
        self.Candidates = list(candidates or [])
        self.Scripts = sorted(list(set(scripts or [])))
        self.Acceptable = list(acceptable or [])
        self.FallbackOnly = list(fallbackOnly or [])
        self.Configured = configured  # optional string describing configured value source

class FontCheckResult(object):
    def __init__(self, req):
        self.Requirement = req
        self.Status = "UNKNOWN"  # OK / WARN / MISSING
        self.Detail = ""
        self.MissingCandidates = []
        self.PresentCandidates = []
        self.PresentAcceptable = []
        self.PresentFallbackOnly = []
        self.CloseMatch = []

# ---------------------------
# Build requirements
# ---------------------------

def BuildRequirementsFromProfileScripts():
    scripts = _ListProfileScripts()

    prefsByFile = {}
    ctorFontsByFile = {}
    pickListsByFile = {}

    # Track scripts referencing a configurable font memory.
    memFontScripts = set()

    prefsCount = 0
    ctorCount = 0
    pickCount = 0

    for fn, full in scripts:
        txt = _ReadText(full)
        code = _StripDocstringsAndFullLineComments(txt)

        if 'TAS_FONT_FAMILY' in code:
            memFontScripts.add(fn)

        prefsLists = _ExtractPrefsLists(code)
        if prefsLists:
            prefsByFile[fn] = prefsLists[0]
            prefsCount += 1

        ct = _ExtractFontCtorFamilies(code)
        if ct:
            ctorFontsByFile[fn] = ct
            ctorCount += 1

        pl = _ExtractPickFamilyCandidateLists(code)
        if pl:
            pickListsByFile[fn] = pl
            pickCount += 1

    requirements = []

    # 1) Lightbox group: any script whose prefs contains a Johnston/Railway candidate.
    lightboxScripts = []
    equivCanon = set([_CanonFamily(x) for x in JOHNSTON_EQUIV])
    for fn, prefs in prefsByFile.items():
        found = False
        for it in (prefs or []):
            if _CanonFamily(it) in equivCanon:
                found = True
                break
        if found:
            lightboxScripts.append(fn)

    if lightboxScripts:
        requirements.append(FontRequirement(
            key="LIGHTBOX_JOHNSTON_EQUIV",
            title="Lightbox preferred: Johnston/Railway (any one)",
            candidates=list(JOHNSTON_EQUIV),
            scripts=sorted(lightboxScripts),
            acceptable=list(LIGHTBOX_ACCEPTABLE),
            fallbackOnly=list(LIGHTBOX_FALLBACK_ONLY)
        ))

    # 2) Configured font memory: TAS_FONT_FAMILY (conditional requirement).
    if memFontScripts:
        configured = _ReadMemStrSuffix('TAS_FONT_FAMILY', '')
        # If blank, we can only inform; do not require.
        if configured and (not _IsLogicalFont(configured)) and _LooksLikeFontName(configured):
            requirements.append(FontRequirement(
                key="CONFIG_TAS_FONT_FAMILY",
                title="Configured font (TAS_FONT_FAMILY): " + configured,
                candidates=[configured],
                scripts=sorted(list(memFontScripts)),
                configured="TAS_FONT_FAMILY"
            ))
        else:
            # Still show a row so users know why Gill Sans MT isn't always required.
            requirements.append(FontRequirement(
                key="CONFIG_TAS_FONT_FAMILY",
                title="Configured font (TAS_FONT_FAMILY): <not set>",
                candidates=[],
                scripts=sorted(list(memFontScripts)),
                configured="TAS_FONT_FAMILY"
            ))

    # 3) Default rule: for scripts with prefs list not lightbox, treat prefs[0] as required.
    byRequired = {}

    for fn, prefs in prefsByFile.items():
        if fn in lightboxScripts:
            continue
        if not prefs:
            continue
        primary = _NormalizeFamily(prefs[0])
        if (not primary) or _IsLogicalFont(primary) or (not _LooksLikeFontName(primary)):
            continue
        byRequired.setdefault(primary, set()).add(fn)

    # 4) Literal Font("Family", ...) uses
    for fn, fams in ctorFontsByFile.items():
        for f in fams:
            fam = _NormalizeFamily(f)
            if (not fam) or _IsLogicalFont(fam) or (not _LooksLikeFontName(fam)):
                continue
            byRequired.setdefault(fam, set()).add(fn)

    for fam in sorted(byRequired.keys(), key=lambda s: s.lower()):
        requirements.append(FontRequirement(
            key="FONT_" + fam.replace(" ", "_").replace("-", "_"),
            title="Required font: " + fam,
            candidates=[fam],
            scripts=sorted(list(byRequired[fam]))
        ))

    # 5) PickFamily(...) selector lists: treat first entry as preferred, others as fallback.
    # Create one requirement per distinct preferred font.
    byPickPreferred = {}
    for fn, lists in pickListsByFile.items():
        for ordered in (lists or []):
            if not ordered:
                continue
            preferred = _NormalizeFamily(ordered[0])
            if (not preferred) or _IsLogicalFont(preferred) or (not _LooksLikeFontName(preferred)):
                continue
            fallbacks = [x for x in ordered[1:] if x and (not _IsLogicalFont(x))]
            key = preferred
            if key not in byPickPreferred:
                byPickPreferred[key] = {"scripts": set(), "fallbacks": []}
            byPickPreferred[key]["scripts"].add(fn)
            # Merge fallbacks preserving order
            for fb in fallbacks:
                if fb not in byPickPreferred[key]["fallbacks"]:
                    byPickPreferred[key]["fallbacks"].append(fb)

    for pref in sorted(byPickPreferred.keys(), key=lambda s: s.lower()):
        info = byPickPreferred[pref]
        requirements.append(FontRequirement(
            key="PICK_" + pref.replace(" ", "_").replace("-", "_"),
            title="Preferred font (fallback available): " + pref,
            candidates=[pref],
            scripts=sorted(list(info["scripts"])),
            fallbackOnly=list(info["fallbacks"])
        ))

    meta = {
        "scriptCount": len(scripts),
        "prefsCount": prefsCount,
        "ctorCount": ctorCount,
        "pickCount": pickCount,
        "requirementCount": len(requirements)
    }

    return requirements, meta

# ---------------------------
# Evaluate
# ---------------------------

def EvaluateRequirements(requirements):
    fams = _AvailableFontFamilies()
    famsLower = set([f.lower() for f in fams])
    famsCanon = set([_CanonFamily(f) for f in fams])

    # Also build a variant-set for installed fonts.
    famsVariants = set()
    for f in fams:
        try:
            for v in _CanonVariants(f):
                if v:
                    famsVariants.add(v)
        except:
            pass

    results = []

    for req in (requirements or []):
        res = FontCheckResult(req)

        present = []
        missing = []
        close = []

        for c in (req.Candidates or []):
            norm = _NormalizeFamily(c)
            cl = norm.lower()
            # Direct match or canonical/variant match
            hit = False
            if cl and (cl in famsLower):
                hit = True
            else:
                for v in _CanonVariants(norm):
                    if v and (v in famsCanon or v in famsVariants):
                        hit = True
                        break
            if hit:
                present.append(c)
            else:
                missing.append(c)

        res.PresentCandidates = present
        res.MissingCandidates = missing

        # Acceptable alternatives
        accPresent = []
        for a in (req.Acceptable or []):
            norm = _NormalizeFamily(a)
            al = norm.lower()
            hit = False
            if al and (al in famsLower):
                hit = True
            else:
                for v in _CanonVariants(norm):
                    if v and (v in famsCanon or v in famsVariants):
                        hit = True
                        break
            if hit:
                accPresent.append(a)
        res.PresentAcceptable = accPresent

        # Fallback-only fonts
        fbPresent = []
        for a in (req.FallbackOnly or []):
            norm = _NormalizeFamily(a)
            al = norm.lower()
            hit = False
            if al and (al in famsLower):
                hit = True
            else:
                for v in _CanonVariants(norm):
                    if v and (v in famsCanon or v in famsVariants):
                        hit = True
                        break
            if hit:
                fbPresent.append(a)
        res.PresentFallbackOnly = fbPresent

        # Status rules:
        # - Configured font: missing -> MISSING (user asked for it)
        # - Preferred-with-fallback: missing but fallback present -> WARN
        # - Otherwise: missing -> MISSING
        if present:
            res.Status = "OK"
            res.Detail = "Installed: " + ", ".join(present)
        else:
            if req.Configured is not None:
                # Configured but not installed
                if req.Candidates:
                    res.Status = "MISSING"
                    res.Detail = "Configured font missing: " + ", ".join(req.Candidates)
                else:
                    res.Status = "WARN"
                    res.Detail = "No configured font set (uses script defaults)"
            elif accPresent:
                res.Status = "WARN"
                res.Detail = "Preferred missing; acceptable installed: " + ", ".join(accPresent)
            elif fbPresent:
                res.Status = "WARN"
                res.Detail = "Preferred missing; fallback installed: " + ", ".join(fbPresent)
            else:
                res.Status = "MISSING"
                res.Detail = "Missing"

        res.CloseMatch = close
        results.append(res)

    return results

# ---------------------------
# UI
# ---------------------------

class StatusCellRenderer(DefaultTableCellRenderer):
    def __init__(self):
        DefaultTableCellRenderer.__init__(self)

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, col):
        comp = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, col)
        try:
            status = "" if value is None else str(value)
        except:
            status = ""

        bg = NEUTRAL_BG
        if status == "OK":
            bg = OK_BG
        elif status == "WARN":
            bg = WARN_BG
        elif status == "MISSING":
            bg = BAD_BG

        try:
            comp.setOpaque(True)
            if isSelected:
                comp.setBackground(bg.darker())
            else:
                comp.setBackground(bg)
        except:
            pass

        return comp



def _AutoSizeColumns(table, maxColWidth=620, margin=12):
    # Auto-size columns based on header + cell preferred widths.
    # Sets AUTO_RESIZE_OFF so the table can scroll horizontally if needed.
    try:
        from javax.swing import JTable
    except:
        JTable = None

    try:
        cm = table.getColumnModel()
        rowCount = table.getRowCount()
        colCount = cm.getColumnCount()
    except:
        return

    try:
        if JTable is not None:
            table.setAutoResizeMode(JTable.AUTO_RESIZE_OFF)
    except:
        pass

    # Cap scanned rows for performance.
    try:
        scanRows = int(rowCount)
    except:
        scanRows = 0
    if scanRows > 250:
        scanRows = 250

    for col in range(int(colCount)):
        try:
            column = cm.getColumn(col)
        except:
            continue

        headerW = 0
        try:
            header = table.getTableHeader()
            renderer = column.getHeaderRenderer()
            if renderer is None and header is not None:
                renderer = header.getDefaultRenderer()
            if renderer is not None:
                comp = renderer.getTableCellRendererComponent(table, column.getHeaderValue(), False, False, -1, col)
                if comp is not None:
                    headerW = int(comp.getPreferredSize().width)
        except:
            headerW = 0

        cellW = 0
        try:
            for row in range(int(scanRows)):
                try:
                    r = table.getCellRenderer(row, col)
                    comp = table.prepareRenderer(r, row, col)
                    if comp is None:
                        continue
                    w = int(comp.getPreferredSize().width)
                    if w > cellW:
                        cellW = w
                except:
                    pass
        except:
            cellW = 0

        w = max(int(headerW), int(cellW)) + int(margin)
        try:
            if maxColWidth is not None:
                w = min(int(w), int(maxColWidth))
        except:
            pass
        try:
            column.setPreferredWidth(int(w))
        except:
            pass

class FontsFrame(object):
    def __init__(self, parent=None):
        self.Parent = parent
        self.Frame = JFrame("TAS font check")
        self.Frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        self.Frame.getContentPane().setLayout(BorderLayout())

        # TAS icon
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.Frame, 32)
        except:
            pass

        self.Requirements, self.Meta = BuildRequirementsFromProfileScripts()
        self.Results = EvaluateRequirements(self.Requirements)

        cols = ["Status", "Font requirement", "Details", "Used by scripts"]
        self.Model = DefaultTableModel(cols, 0)
        self.Table = JTable(self.Model)
        self.Table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        self.Table.setRowSelectionAllowed(True)
        self.Table.setColumnSelectionAllowed(False)
        self.Table.setFillsViewportHeight(True)
        self.Table.getColumnModel().getColumn(0).setCellRenderer(StatusCellRenderer())

        self._PopulateModel()

        # Auto-size columns on startup for readability.
        try:
            _AutoSizeColumns(self.Table)
        except:
            pass


        sp = JScrollPane(self.Table)
        sp.setPreferredSize(Dimension(1020, 360))
        self.Frame.getContentPane().add(sp, BorderLayout.CENTER)

        bottom = JPanel()
        bottom.setLayout(BorderLayout())

        metaText = "Scanned %d scripts; prefs %d; Font(...) %d; PickFamily lists %d; requirements %d" % (
            int(self.Meta.get("scriptCount", 0)),
            int(self.Meta.get("prefsCount", 0)),
            int(self.Meta.get("ctorCount", 0)),
            int(self.Meta.get("pickCount", 0)),
            int(self.Meta.get("requirementCount", 0))
        )
        note = JLabel("Install missing fonts, then restart JMRI.  " + metaText)
        bottom.add(note, BorderLayout.WEST)

        btns = JPanel()
        self.BtnHelp = JButton("How to fix...")
        self.BtnSearchAll = JButton("Search missing...")
        self.BtnRefresh = JButton("Re-scan")
        self.BtnClose = JButton("Close")
        btns.add(self.BtnHelp)
        btns.add(self.BtnSearchAll)
        btns.add(self.BtnRefresh)
        btns.add(self.BtnClose)
        bottom.add(btns, BorderLayout.EAST)

        self.Frame.getContentPane().add(bottom, BorderLayout.SOUTH)

        self.BtnClose.addActionListener(lambda e: self._OnClose())
        self.BtnRefresh.addActionListener(lambda e: self._OnRefresh())
        self.BtnHelp.addActionListener(lambda e: self._OnHelp())
        self.BtnSearchAll.addActionListener(lambda e: self._OnSearchAll())

        self.Frame.pack()
        try:
            self.Frame.setLocationRelativeTo(parent)
        except:
            pass
        self.Frame.setVisible(True)

    def _PopulateModel(self):
        try:
            while self.Model.getRowCount() > 0:
                self.Model.removeRow(0)
        except:
            pass

        if not self.Results:
            self.Model.addRow(["", "No font requirements detected", "", ""])
            return

        for r in self.Results:
            scripts = ", ".join(r.Requirement.Scripts)
            self.Model.addRow([r.Status, r.Requirement.Title, r.Detail, scripts])

    def _OnClose(self):
        try:
            self.Frame.dispose()
        except:
            pass

    def _OnRefresh(self):
        try:
            self.Requirements, self.Meta = BuildRequirementsFromProfileScripts()
            self.Results = EvaluateRequirements(self.Requirements)
            self._PopulateModel()
        except Exception as ex:
            try:
                JOptionPane.showMessageDialog(self.Frame, "Re-scan failed: " + str(ex), "Error", JOptionPane.ERROR_MESSAGE)
            except:
                pass

    def _SelectedResult(self):
        try:
            idx = self.Table.getSelectedRow()
        except:
            idx = -1
        if idx is None or int(idx) < 0 or int(idx) >= len(self.Results):
            return None
        return self.Results[int(idx)]

    def _OpenBrowser(self, url):
        try:
            if url is None:
                return
            u = str(url)
            if u.strip() == "":
                return
            if Desktop.isDesktopSupported():
                d = Desktop.getDesktop()
                if d is not None:
                    d.browse(URI(u))
                    return
        except:
            pass
        try:
            JOptionPane.showMessageDialog(self.Frame, "Could not open browser.\nURL: " + str(url), "Info", JOptionPane.INFORMATION_MESSAGE)
        except:
            pass

    def _SearchUrl(self, queryText):
        try:
            q = URLEncoder.encode(str(queryText), "UTF-8")
        except:
            q = str(queryText).replace(" ", "+")
        return "https://duckduckgo.com/?q=" + q

    def _BuildHelpHtml(self, fontNames):
        lines = []
        lines.append("<html><body style='font-family:sans-serif; font-size:12px;'>")
        lines.append("<h3>Install missing fonts</h3>")
        lines.append("<p>1) Click a link below to search for the font and download it from a trusted source.</p>")
        lines.append("<p>2) Install the font using your operating system's normal method.</p>")
        lines.append("<p><b>3) Restart JMRI after installing all fonts.</b></p>")
        lines.append("<p>Search links:</p>")
        lines.append("<ul>")
        for nm in (fontNames or []):
            q = "font \"%s\" download" % str(nm)
            url = self._SearchUrl(q)
            lines.append("<li><a href='%s'>%s</a></li>" % (url, str(nm)))
        lines.append("</ul>")
        lines.append("</body></html>")
        return "\n".join(lines)

    def _ShowHelpFor(self, resultObj):
        if resultObj is None:
            return

        names = list(resultObj.Requirement.Candidates or [])
        if resultObj.Requirement.Acceptable:
            for x in resultObj.Requirement.Acceptable:
                if x not in names:
                    names.append(x)

        dlg = JDialog(self.Frame, "How to install fonts", True)
        dlg.setLayout(BorderLayout())

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(dlg, 32)
        except:
            pass

        pane = JEditorPane("text/html", self._BuildHelpHtml(names))
        pane.setEditable(False)

        class HL(HyperlinkListener):
            def hyperlinkUpdate(innerSelf, ev):
                try:
                    if ev.getEventType().toString() == "ACTIVATED":
                        self._OpenBrowser(ev.getURL().toString())
                except:
                    pass

        try:
            pane.addHyperlinkListener(HL())
        except:
            pass

        dlg.add(JScrollPane(pane), BorderLayout.CENTER)
        btnRow = JPanel()
        btnClose2 = JButton("Close")
        btnRow.add(btnClose2)
        dlg.add(btnRow, BorderLayout.SOUTH)

        btnClose2.addActionListener(lambda e: dlg.dispose())
        dlg.setSize(700, 460)
        try:
            dlg.setLocationRelativeTo(self.Frame)
        except:
            pass
        dlg.setVisible(True)

    def _OnHelp(self):
        res = self._SelectedResult()
        if res is None:
            try:
                JOptionPane.showMessageDialog(self.Frame, "Select a row first.", "Info", JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return
        self._ShowHelpFor(res)

    def _OnSearchAll(self):
        anyOpened = False
        for r in self.Results:
            if r.Status in ["MISSING", "WARN"]:
                names = list(r.Requirement.Candidates or [])
                if names:
                    url = self._SearchUrl("font \"%s\"" % str(names[0]))
                    self._OpenBrowser(url)
                    anyOpened = True
        if not anyOpened:
            try:
                JOptionPane.showMessageDialog(self.Frame, "No missing fonts detected.", "Info", JOptionPane.INFORMATION_MESSAGE)
            except:
                pass

# ---------------------------
# Entry point
# ---------------------------

def RunFontCheckDialog(parentFrame=None):
    try:
        from javax.swing import SwingUtilities
        class R(java.lang.Runnable):
            def run(self):
                FontsFrame(parentFrame)
        SwingUtilities.invokeLater(R())
    except:
        FontsFrame(parentFrame)


# ---------------------------
# Public API for other scripts
# ---------------------------

def GetFontCheckResults():
    # Returns (results, meta) without showing any UI.
    # results is a list of FontCheckResult.
    reqs, meta = BuildRequirementsFromProfileScripts()
    res = EvaluateRequirements(reqs)
    return res, meta

def CountMissingFonts(includeWarn=False):
    # Returns an int count of missing fonts.
    # By default counts only hard missing requirements (Status == "MISSING").
    # If includeWarn=True, counts WARN rows too.
    try:
        results, meta = GetFontCheckResults()
    except:
        return 0

    missing = 0
    for r in (results or []):
        try:
            st = str(r.Status)
        except:
            st = ""
        if st == "MISSING":
            missing += 1
        elif includeWarn and st == "WARN":
            missing += 1
    return int(missing)

def RunFontCheck(silent=False, parentFrame=None):
    # If silent=True, do not show UI and return CountMissingFonts().
    # If silent=False, show the UI and also return CountMissingFonts() (computed first).
    cnt = 0
    try:
        cnt = CountMissingFonts(False)
    except:
        cnt = 0

    if not silent:
        try:
            RunFontCheckDialog(parentFrame)
        except:
            try:
                FontsFrame(parentFrame)
            except:
                pass

    # Expose as a module global for callers that use execfile.
    try:
        globals()['TASFontCheckMissingCount'] = int(cnt)
    except:
        pass

    return int(cnt)

# Backward-compatible alias
GetMissingFontsCount = CountMissingFonts

# ---------------------------
# Default behaviour when executed directly
# ---------------------------

# If another script runs this via execfile and wants it to be silent,
# it can set TASFontCheckSilent=True in the globals dict passed to execfile.

if globals().get('TASFontCheckSilent', False):
    try:
        globals()['TASFontCheckMissingCount'] = int(CountMissingFonts(False))
    except:
        pass
else:
    if __name__ == '__main__':
        try:
            RunFontCheck(silent=False, parentFrame=None)
        except:
            try:
                RunFontCheckDialog(None)
            except:
                pass
