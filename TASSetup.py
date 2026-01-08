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
# Tabs: General, Display configuration, Day/night cycle.
# ASCII-only, portable paths, thread-safe.

import os, csv, re
import java
import traceback
from java.awt import (BorderLayout, Color, Dimension, Font,
    GridBagConstraints, GridBagLayout, Insets, RenderingHints)
from java.awt.image import BufferedImage
from java.io import File  # canonical path comparisons
from java.lang import Runnable
from java.awt.event import FocusAdapter, MouseAdapter, MouseEvent
from javax.swing import (Box, JButton, JCheckBox, JFileChooser, JLabel, JDialog,
    JList, JOptionPane, JPanel, JScrollPane, JTabbedPane, JTextField,
    ListSelectionModel, SwingUtilities, UIManager, DefaultListModel,
    DefaultListCellRenderer, BorderFactory, JComboBox, JRadioButton, ButtonGroup,
    JSpinner, SpinnerNumberModel, Timer)
from javax.swing.filechooser import FileNameExtensionFilter
from javax.swing import JTextPane
from javax.swing.event import DocumentListener, ListSelectionListener, ChangeListener
from javax.swing.text import StyleContext, StyledDocument, SimpleAttributeSet, StyleConstants
from java.awt.event import KeyAdapter, KeyEvent
from java.awt import GridLayout
import TASBeanLookup as TBL

# JMRI
import jmri
from jmri.util import FileUtil  # portable profile/scripts paths

from java.awt import GraphicsEnvironment
from javax.swing import JColorChooser

# ------------------------------- Logging -------------------------------
TAG = "[TASSetup] "
def LogInfo(msg, alsoDialog=False, title="Info"):
    try: print(TAG + str(msg))
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.INFORMATION_MESSAGE)
        except: pass
def LogWarn(msg, alsoDialog=False, title="Warning"):
    try: print(TAG + "WARN: " + str(msg))
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.WARNING_MESSAGE)
        except: pass
def LogError(msg, ex=None, alsoDialog=True, title="Error"):
    try:
        print(TAG + "ERROR: " + str(msg))
        if ex is not None:
            print(TAG + "TRACEBACK:")
            traceback.print_exc()
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.ERROR_MESSAGE)
        except: pass
        
        
# Helper: run the Setup wizard if present (safe wrapper)
def RunSetupWizard(onClosed=None):
    try:
        path = ProfileJythonFilePath("TASWiz.py")
        if not os.path.isfile(path):
            LogWarn("Setup wizard not found: " + str(path), alsoDialog=True)
            return False
        g = {}
        try:
            if onClosed is not None:
                g['TAS_SETUP_WIZARD_CLOSED_CALLBACK'] = onClosed
        except:
            pass
        execfile(path, g)
        return True
    except Exception as ex:
        LogError("Setup wizard failed: " + str(ex), ex=ex, alsoDialog=True)
        return False
        
# -------------------- Colour helpers --------------------
def _RgbStrToColorOrDefault(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3: return defaultColor
        r,g,b = [max(0, min(255, int(float(x)))) for x in parts]
        return Color(r, g, b)
    except:
        return defaultColor

def _ColorToRgbStr(c):
    try:
        return "%d,%d,%d" % (c.getRed(), c.getGreen(), c.getBlue())
    except:
        return GetDefaultBackgroundRGB()

# --------------------------- Memory helpers ---------------------------
def GetMemoryBool(Name, Default=False):
    s=TBL.SafeGetOrCreateMemoryValue(Name,"")
    if isinstance(s,bool): return s
    t=str(s).strip().lower()
    if t in ["1","true","yes","y","on","enabled"]: return True
    if t in ["0","false","no","n","off","disabled"]: return False
    return Default

def SetMemoryBool(Name, Value):
    TBL.SafeSetMemoryValue(Name, "true" if bool(Value) else "false")
    
def ScriptExists(scriptName):
    try:
        path = ProfileJythonFilePath(scriptName)
        return os.path.isfile(path)
    except:
        return False    

# ------------------------------- Theme --------------------------------
THEME_FONT_FAMILY = TBL.SafeGetOrCreateMemoryValue("TAS_FONT_FAMILY", "Gill Sans MT")
THEME_TEXT_COLOR = Color(30, 30, 30)
THEME_PAPER = _RgbStrToColorOrDefault(TBL.SafeGetOrCreateMemoryValue("TASPAPERCOLOUR", "249,246,238"), Color(249, 246, 238))
THEME_ACCENT = Color(80, 80, 80)
LIST_SEL_BG = Color(210, 225, 235)
LIST_SEL_FG = Color(20, 20, 20)

def ApplyTheme(component):
    try: component.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
    except: pass

def MakePaperPanel():
    class PaperPanel(JPanel):
        def __init__(self):
            JPanel.__init__(self)
            self.setOpaque(True); self.setBackground(THEME_PAPER)
            self.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createMatteBorder(1,1,1,1, Color(180,170,150)),
                BorderFactory.createEmptyBorder(12,12,12,12)))
            self.texture = self._makeTexture()
        def _makeTexture(self):
            w,h=64,64
            img=BufferedImage(w,h,BufferedImage.TYPE_INT_ARGB); g=img.createGraphics()
            g.setColor(THEME_PAPER); g.fillRect(0,0,w,h)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.setColor(Color(200,196,184,22))
            for i in range(150):
                x=int(java.lang.Math.random()*w); y=int(java.lang.Math.random()*h)
                g.fillRect(x,y,1,1)
            g.dispose(); return img
        def paintComponent(self,g):
            super(PaperPanel,self).paintComponent(g)
            iw=self.texture.getWidth(); ih=self.texture.getHeight()
            for y in range(0,self.getHeight(),ih):
                for x in range(0,self.getWidth(),iw):
                    g.drawImage(self.texture,x,y,None)
    p=PaperPanel(); ApplyTheme(p); return p

def MakeHeading(text):
    lbl=JLabel(text)
    lbl.setForeground(THEME_ACCENT)
    lbl.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 16))
    return lbl

def MakeWrappedLabel(htmlText, widthPx=560, lineHeight=1.25, bold=False):
    """
    Create a JLabel that wraps text using HTML with an explicit width and tuned line-height.
    - widthPx: wrapping width in pixels
    - lineHeight: CSS line-height multiplier for compact spacing (e.g., 1.20-1.30)
    - bold: True for heading-style weight/size; False for body copy style
    """
    # Build HTML with controlled width and line-height.
    # Keep ASCII-only content for Jython compatibility.
    html = "<html><div style='width:{0}px; line-height:{1};'>{2}</div></html>".format(
        int(widthPx), float(lineHeight), htmlText
    )
    lbl = JLabel(html)
    try:
        style = Font.BOLD if bold else Font.PLAIN
        size = 16 if bold else 13
        lbl.setFont(Font(THEME_FONT_FAMILY, style, size))
        lbl.setForeground(THEME_TEXT_COLOR if not bold else THEME_ACCENT)
    except:
        pass
    return lbl

# --- Force the chosen font on all controls (recursive) ---
from java.awt import Container
from javax.swing import JTable, JList, JScrollPane, JTabbedPane

def _SetFontIfPossible(comp, family, style=Font.PLAIN, size=13):
    try:
        comp.setFont(Font(family, style, size))
    except:
        pass

def _ApplyFontRecursive(comp, family):
    # Apply to this component
    _SetFontIfPossible(comp, family)

    # Special cases / nested internals
    try:
        # JTable header
        if isinstance(comp, JTable):
            hdr = comp.getTableHeader()
            if hdr is not None:
                _SetFontIfPossible(hdr, family, Font.BOLD, 13)
        # JList cell renderer might need a nudge
        if isinstance(comp, JList):
            rnd = comp.getCellRenderer()
            if rnd is not None:
                try: rnd.setFont(Font(family, Font.PLAIN, 13))
                except: pass
        # JScrollPane: also set viewport view
        if isinstance(comp, JScrollPane):
            vp = comp.getViewport()
            if vp is not None:
                view = vp.getView()
                if view is not None: _SetFontIfPossible(view, family)
        # JTabbedPane: set tab component fonts if present
        if isinstance(comp, JTabbedPane):
            try:
                count = comp.getTabCount()
                for i in range(count):
                    tab = comp.getTabComponentAt(i)
                    if tab is not None: _SetFontIfPossible(tab, family, Font.BOLD, 13)
            except:
                pass
    except:
        pass

    # Recurse into children if Container
    try:
        if isinstance(comp, Container):
            for child in comp.getComponents():
                _ApplyFontRecursive(child, family)
    except:
        pass

def ApplyTheme(component):
    # Preserve original semantics but use the recursive applier
    try:
        _ApplyFontRecursive(component, THEME_FONT_FAMILY)
    except:
        pass

# -------------------- TAS Interface Defaults (minimal) --------------------
def GetDefaultFontFamily():
    # Safe default (TimetableAutomation will still guard its own fallback)
    return "Gill Sans MT"

def GetDefaultBackgroundRGB():
    # CoverPanel default background (Color(240,238,220))
    return "240,238,220"

# ------------------------------- Keys ---------------------------------
IMCurrentTimetable   = "CURRENTTIMETABLE"
IMAllowDelays        = "ALLOWDELAYS"
IMAllowCANCELLATIONS = "ALLOWCANCELLATIONS"
IMPublicDisplayList  = "PUBLICDISPLAYLIST"
IMSignallerDisplayList = "SIGNALLERDISPLAYLIST"

# Timetable (WTTDisplay) parameter memories
IMWTT_PageMode        = "WTT_PAGE_MODE"          # str: "WEEKDAYS_SAT_SUN" / "SEVEN_DAYS" / "MONSAT_PLUS_SUN" / "ALL_WEEK"
IMWTT_Time24          = "WTT_TIME_24H"          # bool: true/false
IMWTT_TimeSeparator   = "WTT_TIME_SEPARATOR"     # str: single character (":" or " " or ".")
IMWTT_TpNameDotLeaders = "WTT_TP_NAME_DOT_LEADERS"  # bool: true/false (dot leaders after TP names)
IMWTT_EcsLabel        = "WTT_ECS_LABEL"         # str: e.g., "ECS"
IMWTT_EcsMatch        = "WTT_ECS_DEST_MATCH"    # str: comma-separated tokens (lowercased)
IMWTT_TimingLoadLabel = "WTT_TIMING_LOAD_LABEL" # str: label for timing load and alternate column header
IMWTT_RepNoLabel = "WTT_REP_NO_LABEL" # str: label for reporting number row in WTT display
IMWTT_DirectionSplit  = "WTT_DIRECTION_SPLIT"     # bool: true/false
IMWTT_OdHeaderVertical = "WTT_OD_HEADER_VERTICAL" # bool: true/false (unchecked=horizontal default)

# Day/Night & Weather (UI values consumed by DayNight/Weather scripts)
IMLowThrottleAddr = "LOWCTTHROTTLEADDR"
IMHighThrottleAddr = "HIGHCTTHROTTLEADDR"
IMDayNightPreset = "DAYNIGHT_PRESET"
IMWxClimate   = "WX_CLIMATE"
IMWxCloudPct  = "CLOUDCOVERPCT"
IMWxUiChoice  = "WX_UI"     # "App" or "Newspaper"
IMWxNewsStyle = "WX_NEWS_STYLE" # "Old" or "Modern"

# DayNight time-warp blackout configuration (matches DayNight.py)
IMTimeWarpBlackoutSeconds = "TIMEWARPBLACKOUTSECONDS"
IMTimeWarpThresholdMinutes = "TIMEWARPTHRESHOLDMINUTES"

# NEW: Auto-working enable memory switch (non-startup, no restart)
IMTASAutoWorking = "TASAUTOWORKING"

# --------------------------- Portable paths ---------------------------
def GetTimetableDirFile():
    path = FileUtil.getExternalFilename("profile:timetable")
    return File(path)

def StripCsvExt(name):
    s=str(name).strip()
    return s[:-4] if s.lower().endswith(".csv") else s

def ProfileJythonFilePath(name):
    try:
        return FileUtil.getExternalFilename("profile:jython/" + name)
    except:
        return "jython/" + name

def _NormRN(s):
    # Case-insensitive matching for reporting numbers; blank -> ""
    try:
        return str(s).strip().upper()
    except Exception:
        return ""


# -------- Start-Up detection & mutation (authoritative, robust) -------
# APIs: StartupActionsManager.getActions(), .addAction(), .savePreferences(Profile)
# StartupModel.isEnabled()/setEnabled(...); PerformScriptModel.getFileName()/setFileName(...)
# Paths via jmri.util.FileUtil "profile:" scheme.

def _StartupMgr():
    try:
        return jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
    except:
        return None

def _ActiveProfile():
    try:
        pm = jmri.profile.ProfileManager.getDefault()
        return pm.getActiveProfile()
    except:
        return None

def _CanonLower(p):
    try:
        return File(p).getCanonicalPath().lower()
    except:
        return str(p).lower()

def _MatchScriptPath(model, scriptFileName):
    """True iff model's script path points to profile:jython/<scriptFileName>."""
    try:
        path = model.getFileName()
        if path is None: return False
        pcanon = _CanonLower(str(path))
        target = _CanonLower(ProfileJythonFilePath(scriptFileName))
        base = File(scriptFileName).getName().lower()
        if pcanon == target: return True
        if pcanon.endswith(File.separator + base): return True
        if pcanon.endswith("/" + base): return True
        if pcanon.endswith("\\\\" + base): return True
        return False
    except:
        return False

def _FindPerformScriptModelFor(scriptFileName):
    mgr = _StartupMgr()
    if mgr is None: return None
    try:
        actions = mgr.getActions()
    except:
        return None
    for m in actions:
        try:
            if not isinstance(m, jmri.util.startup.PerformScriptModel):
                continue
            if _MatchScriptPath(m, scriptFileName):
                return m
        except:
            continue
    return None

def _IsScriptEnabled(scriptFileName):
    m = _FindPerformScriptModelFor(scriptFileName)
    return (m is not None) and bool(m.isEnabled())

def _EnsureScriptEnabled(scriptFileName, enabled):
    """Create/toggle PerformScriptModel, then save to active profile."""
    mgr = _StartupMgr()
    if mgr is None:
        LogWarn("StartupActionsManager unavailable")
        return False
    model = _FindPerformScriptModelFor(scriptFileName)
    if model is None and enabled:
        try:
            model = jmri.util.startup.PerformScriptModel()
            model.setFileName(ProfileJythonFilePath(scriptFileName))
            model.setEnabled(True)
            mgr.addAction(model)
        except Exception as ex:
            LogError("Could not add startup script: " + scriptFileName + " :: " + str(ex), ex=ex)
            return False
    elif model is not None:
        try:
            model.setEnabled(bool(enabled))
        except Exception as ex:
            LogError("Could not change enabled state: " + scriptFileName + " :: " + str(ex), ex=ex)
            return False
    else:
        pass  # model missing and enabling False -> nothing to do

    try:
        prof = _ActiveProfile()
        if prof is not None:
            mgr.savePreferences(prof)
        return True
    except Exception as ex:
        LogError("Could not save Start-Up preferences: " + str(ex), ex=ex)
        return False

def IsDayNightEnabled():
    return _IsScriptEnabled("DayNight.py")

def IsWeatherEnabled():
    return _IsScriptEnabled("WeatherGenerator.py")

def IsTimeActionsEnabled():
    return _IsScriptEnabled("CheckWhenTimeChanges.py") and _IsScriptEnabled("DayTracker.py") and _IsScriptEnabled("TimeWarpChecker.py")

# ---------------------- Timetable validation helpers -------------------
def _MakeDefaultRN(rowNumber):
    # Default reporting number: header row is 1, first data row is 2 -> TAS<rowNumber>
    return "TAS" + str(int(rowNumber))

def _ParseTimeToMinutes(timeStr):
    """
    Parse 12h/24h times to minutes since midnight.
    Accepts: "13:15", "13:15:00", "1:15 PM", "01:15 pm", optional seconds, optional trailing 'h'.
    Returns int or None.
    """
    if timeStr is None: return None
    s = str(timeStr).strip()
    if not s: return None
    s = re.sub(r"\s+", " ", s)
    if s.lower().endswith('h'):
        s = s[:-1].strip()
    m = re.match(r'^\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?\s*$', s, flags=re.IGNORECASE)
    if not m: return None
    hour = int(m.group(1)); minute = int(m.group(2)); ampm = m.group(4).lower() if m.group(4) else None
    if minute >= 60 or hour > 24 or hour < 0 or minute < 0: return None
    if ampm:
        hour = hour % 12
        if ampm == 'pm': hour += 12
    else:
        if hour == 24: hour = 0
    return hour*60 + minute

def _TimetableFilePath():
    name = TBL.SafeGetOrCreateMemoryValue(IMCurrentTimetable, "").strip()
    if not name: return None
    ttDir = FileUtil.getExternalFilename("profile:timetable")
    return os.path.join(ttDir, name + ".csv")

def _ValidateTimetable():
    """
    Returns (isValid, firstMessage, headerInfo)
    headerInfo: dict with keys:
    - hasTrigger, hasArr, hasDep, hasAnyDayColumn
    Row rule: a row is valid if it has at least one of Trigger/Arr/Dep filled; any filled time must parse.
    """
    path = _TimetableFilePath()
    if path is None:
        return (False, "No valid timetable set.", None)
    if not os.path.isfile(path):
        return (False, "Timetable file does not exist: " + path, None)
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            header = reader.fieldnames or []
            hasTrigger = ("Trigger" in header)
            hasArr = ("Arr" in header)
            hasDep = ("Dep" in header)
        
            # Read rows once and compute formation mapping for this timetable
            rows = list(reader)

            formedBy = {}  # destination RN (norm) -> forming RN (original case)
            for idx, r in enumerate(rows, start=2):
                rnCell = (r.get("Reporting number", "") or "").strip()
                formingRN = rnCell if rnCell != "" else _MakeDefaultRN(idx)
                formsCell = (r.get("Forms", "") or "").strip()
                if formsCell != "":
                    formedBy[_NormRN(formsCell)] = formingRN
                   
            if not (hasTrigger or hasArr or hasDep):
                return (False, "Missing time columns: need at least one of 'Trigger', 'Arr' or 'Dep'.",
                        {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":False})
            dayCols = [c for c in header if c.lower() in
                       ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]]
            hasAnyDayColumn = (len(dayCols) > 0)
            sawData = False
            for rowIndex, row in enumerate(rows, start=2):
                sawData = True
                cells = []
                if hasTrigger:
                    v = (row.get("Trigger","") or "").strip()
                    if v != "": cells.append(("Trigger", v))
                if hasArr:
                    v = (row.get("Arr","") or "").strip()
                    if v != "": cells.append(("Arr", v))
                if hasDep:
                    v = (row.get("Dep","") or "").strip()
                    if v != "": cells.append(("Dep", v))
                if len(cells) == 0:
                    return (False, "Row %d: no time in Trigger/Arr/Dep." % rowIndex,
                            {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
                for col, val in cells:
                    if _ParseTimeToMinutes(val) is None:
                        return (False, "Row %d: invalid %s time '%s'." % (rowIndex, col, val),
                                {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
            if not sawData:
                return (False, "Timetable has no data rows.",
                        {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
            return (True, "", {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
    except Exception as ex:
        return (False, "Error reading timetable: " + str(ex), None)

def _CheckWorkingScripts():
    """
    Returns (isValid, firstMessage)
    For each row:
    - If Trigger present -> require scripts/workings/Trigger/<RN>.py
    - Else if Arr present -> require scripts/workings/Arr/<RN>.py
    - Else if Dep present -> require scripts/workings/Dep/<RN>.py
    RN = explicit 'Reporting number' or default TAS<rowNumber>.
    """
    path = _TimetableFilePath()
    if path is None or not os.path.isfile(path):
        return (False, "No valid timetable file to check working scripts.")
    scriptsPath = jmri.util.FileUtil.getScriptsPath()
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            header = reader.fieldnames or []
            hasTrigger = ("Trigger" in header); hasArr = ("Arr" in header); hasDep = ("Dep" in header)
            for rowIndex, row in enumerate(reader, start=2):
                direction = None               
                triggerPresent = hasTrigger and (row.get("Trigger","") or "").strip() != ""
                arrPresent = hasArr and (row.get("Arr","") or "").strip() != ""
                depPresent = hasDep and (row.get("Dep","") or "").strip() != ""

                # If trigger and dep present but no arr > require only trigger script
                if triggerPresent:
                    direction = "Trigger"
                elif arrPresent:
                    direction = "Arr"
                elif depPresent:
                    direction = "Dep"
                else:
                    return (False, "Row %d: no time in Trigger/Arr/Dep; cannot determine working script directory." % rowIndex)
                rnCell = (row.get("Reporting number","") or "").strip()
                rn = rnCell if rnCell != "" else _MakeDefaultRN(rowIndex)
                scriptPath = os.path.join(scriptsPath, "workings", direction, rn + ".py")
                if not os.path.isfile(scriptPath):
                    return (False, "Row %d: missing working script for RN %s in %s directory." % (rowIndex, rn, direction))
            return (True, "")
    except Exception as ex:
        return (False, "Error checking working scripts: " + str(ex))

# ------------------------- Dual-list panel -----------------------------
class RestrictedCsvChooser(JFileChooser):
    def __init__(self, baseDir):
        JFileChooser.__init__(self, baseDir)
        self.baseDir = baseDir.getCanonicalFile()
        self.setDialogTitle("Select timetable CSV")
        self.setFileSelectionMode(JFileChooser.FILES_ONLY)
        self.setAcceptAllFileFilterUsed(False)
        self.addChoosableFileFilter(FileNameExtensionFilter("CSV files (*.csv)", ["csv"]))
    def approveSelection(self):
        sel = self.getSelectedFile()
        if sel is None: return
        try:
            canonical = sel.getCanonicalFile()
            if not canonical.getName().lower().endswith(".csv"):
                LogWarn("Rejected non-CSV selection: " + canonical.getName(), alsoDialog=True)
                return
            allowed = self.baseDir.getPath()
            cpath = canonical.getPath()
            if not (cpath == allowed or cpath.startswith(allowed + File.separator)):
                LogWarn("Rejected selection outside timetable folder: " + cpath, alsoDialog=True)
                return
        except Exception as ex:
            LogError("Error validating selection: " + str(ex), ex=ex, alsoDialog=True)
            return
        JFileChooser.approveSelection(self)

def MakeDualListPanel(TitleText, AvailableNames, NameMap, DescMap, InitialSelectedNames, OnChangeCallback, OnSelectCallback=None, OnPreviewCallback=None):
    panel = MakePaperPanel()
    panel.setLayout(GridBagLayout())
    gbc = GridBagConstraints()
    gbc.insets = Insets(4,4,4,4)
    gbc.fill = GridBagConstraints.BOTH
    gbc.weightx = 1.0
    gbc.weighty = 0.0
    gbc.gridx = 0
    gbc.gridy = 0

    title = MakeHeading(TitleText)
    panel.add(title, gbc)

    availModel = DefaultListModel()
    selectedModel = DefaultListModel()

    # Normalize and filter any junk entries (blank or "...")
    def _NormName(x):
        try:
            return str(x).strip()
        except:
            return ""

    selectedSet = set([_NormName(x) for x in (InitialSelectedNames or []) if _NormName(x) not in ["", "..."]])

    # Populate available list (exclude anything already selected)
    for fname in (AvailableNames or []):
        f = _NormName(fname)
        if f in ["", "..."]:
            continue
        if f not in selectedSet:
            availModel.addElement(f)

    # Keep any pre-selected names even if they are no longer available (lets user remove them)
    for fname in (InitialSelectedNames or []):
        f = _NormName(fname)
        if f in ["", "..."]:
            continue
        selectedModel.addElement(f)

    class FriendlyRenderer(DefaultListCellRenderer):
        def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
            # WorkingItem support (used elsewhere) remains intact
            if hasattr(value, "Label"):
                labelText = value.Label()
            else:
                try:
                    key = str(value)
                except:
                    key = value
                try:
                    labelText = str(NameMap.get(key, key))
                except:
                    labelText = str(key)

            comp = DefaultListCellRenderer.getListCellRendererComponent(
                self, lst, labelText, index, isSelected, cellHasFocus
            )
            comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))

            # Preserve color logic for WorkingItem objects
            if hasattr(value, "IsExtra") and getattr(value, "IsExtra", False):
                comp.setForeground(Color(128, 128, 128))  # Grey for extra scripts
            elif hasattr(value, "HasScript") and not value.HasScript:
                comp.setForeground(Color(255, 0, 0))  # Red for missing
            elif hasattr(value, "ValidScript") and not value.ValidScript:
                comp.setForeground(Color(255, 140, 0))  # Orange for invalid
            else:
                comp.setForeground(THEME_TEXT_COLOR)

            comp.setBackground(LIST_SEL_BG if isSelected else THEME_PAPER)
            comp.setOpaque(True)
            return comp

    availList = JList(availModel)
    availList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    availList.setCellRenderer(FriendlyRenderer())
    availList.setSelectionBackground(LIST_SEL_BG)
    availList.setSelectionForeground(LIST_SEL_FG)

    selectedList = JList(selectedModel)
    selectedList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    selectedList.setCellRenderer(FriendlyRenderer())
    selectedList.setSelectionBackground(LIST_SEL_BG)
    selectedList.setSelectionForeground(LIST_SEL_FG)

    # Track which list was last interacted with, so Preview runs the highlighted entry the user expects.
    lastSelectedList = {"lst": None}

    def FireChange():
        sel = [selectedModel.getElementAt(i) for i in range(selectedModel.getSize())]
        try:
            LogInfo("Selection for \"" + TitleText + "\": " + ",".join(sel))
        except:
            pass
        OnChangeCallback(sel)

    def _NotifySelected(lst):
        if OnSelectCallback is None:
            return
        try:
            v = lst.getSelectedValue()
            if v is None:
                return
            OnSelectCallback(str(v))
        except:
            pass

    class SelHook(ListSelectionListener):
        def __init__(self, lst):
            self.lst = lst
        def valueChanged(self, e):
            if e.getValueIsAdjusting():
                return
            # Remember which list the user last clicked.
            lastSelectedList["lst"] = self.lst
            _NotifySelected(self.lst)

    # Drive description box from either list
    try:
        availList.addListSelectionListener(SelHook(availList))
        selectedList.addListSelectionListener(SelHook(selectedList))
    except:
        pass

    btnAdd = JButton("Add >>")
    btnRemove = JButton("<< Remove")

    def AddAction(e):
        idx = availList.getSelectedIndices()
        if idx is None or len(idx) == 0:
            return
        items = [availModel.getElementAt(i) for i in idx]
        existing = [selectedModel.getElementAt(i) for i in range(selectedModel.size())]
        for it in items:
            if it not in existing:
                selectedModel.addElement(it)
        for i in sorted(idx, reverse=True):
            availModel.remove(i)
        FireChange()

    def RemoveAction(e):
        idx = selectedList.getSelectedIndices()
        if idx is None or len(idx) == 0:
            return
        items = [selectedModel.getElementAt(i) for i in idx]
        for i in sorted(idx, reverse=True):
            selectedModel.remove(i)
        existing = [availModel.getElementAt(i) for i in range(availModel.size())]
        merged = existing + items

        # Sort by friendly display name (case-insensitive)
        def _SortKey(n):
            try:
                k = str(n)
            except:
                k = n
            try:
                return str(NameMap.get(k, k)).lower()
            except:
                try:
                    return str(k).lower()
                except:
                    return ""
        merged.sort(key=_SortKey)

        availModel.removeAllElements()
        for it in merged:
            availModel.addElement(it)
        FireChange()

    btnAdd.addActionListener(lambda e: AddAction(e))
    btnRemove.addActionListener(lambda e: RemoveAction(e))

    # Optional Preview button
    btnPreview = None
    if OnPreviewCallback is not None:
        btnPreview = JButton("Preview...")

        def PreviewAction(e=None):
            try:
                lst = lastSelectedList.get("lst", None)
                v = None
                if lst is not None:
                    v = lst.getSelectedValue()

                # Fallback: if we don't know which list was last used, pick any selection.
                if v is None:
                    v = availList.getSelectedValue()
                if v is None:
                    v = selectedList.getSelectedValue()
                if v is None:
                    return

                OnPreviewCallback(str(v).strip())
            except Exception as ex:
                LogError("Preview failed: " + str(ex), ex=ex, alsoDialog=True)

        btnPreview.addActionListener(lambda e: PreviewAction(e))

    gbc.gridy = 1
    gbc.weighty = 1.0

    leftScroll = JScrollPane(availList)
    # Wider but not huge; allow vertical growth too
    leftScroll.setPreferredSize(Dimension(360, 200))
    leftScroll.setMinimumSize(Dimension(280, 160))  # prevents overly small pack
    leftScroll.getViewport().setBackground(THEME_PAPER)
    panel.add(leftScroll, gbc)

    btnPanel = Box.createVerticalBox()
    btnPanel.add(btnAdd)
    btnPanel.add(Box.createVerticalStrut(6))
    btnPanel.add(btnRemove)

    # Add Preview button below, with extra spacing so it sits as if there were an additional button between Remove and Preview.
    if btnPreview is not None:
        # Simulate: Remove, (normal gap), [imaginary button], (normal gap), Preview
        btnPanel.add(Box.createVerticalStrut(6))
        try:
            ph = btnRemove.getPreferredSize().height
            if ph is None or int(ph) <= 0:
                ph = 26
            btnPanel.add(Box.createVerticalStrut(int(ph)))
        except:
            btnPanel.add(Box.createVerticalStrut(26))
        btnPanel.add(Box.createVerticalStrut(6))
        btnPanel.add(btnPreview)

    gbc.gridx = 1
    gbc.weightx = 0.0
    gbc.fill = GridBagConstraints.NONE
    panel.add(btnPanel, gbc)

    gbc.gridx = 2
    gbc.weightx = 1.0
    gbc.fill = GridBagConstraints.BOTH

    rightScroll = JScrollPane(selectedList)
    rightScroll.setPreferredSize(Dimension(360, 200))
    rightScroll.setMinimumSize(Dimension(280, 160))
    rightScroll.getViewport().setBackground(THEME_PAPER)
    panel.add(rightScroll, gbc)

    return panel

# ------------------------------- Main frame ----------------------------
IMPublicDisplayList ="PUBLICDISPLAYLIST"
IMSignallerDisplayList = "SIGNALLERDISPLAYLIST"


# ------------------- Display script discovery (profile:jython/*.py) -------------------
# Scan all .py files in the profile's jython directory. Match <<>> comments.

_PID_TAG_RE  = re.compile(r"<<\s*PID-DISP-NAME\s*:\s*(.*?)\s*>>")
_SIG_TAG_RE  = re.compile(r"<<\s*SIG-DISP-NAME\s*:\s*(.*?)\s*>>")
_DESC_TAG_RE = re.compile(r"<<\s*DESCRIPTION\s*:\s*(.*?)\s*>>")

# Detect user setting description lines, e.g.:
#   # <<SETTING DESCRIPTION BOOLEAN: Debranded>>
_SETTING_DESC_RE = re.compile(r"\<\<\s*SETTING\s+DESCRIPTION\s+([A-Za-z]+)\s*:\s*(.*?)\s*\>\>")

# Optional: enum values line (future use), e.g.:
#   # <<SETTING ENUM VALUES Debranded: On|Off|Classic>>
# If not present, ENUM will degrade to a plain text field until values are defined.
_SETTING_ENUMVALS_RE = re.compile(r"\<\<\s*SETTING\s+ENUM\s+VALUES\s+([A-Za-z0-9 _\-]+)\s*:\s*(.*?)\s*\>\>")

def _UserSettingMemoryName(label):
    # "Debranded" -> "TAS_USER_SETTING_DEBRANDED"
    try:
        s = str(label).strip()
    except:
        s = ""
    import re as _re
    key = _re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key

def _ScanSettingsForScript(fullPath):
    """
    Returns a list of dicts: [{"type": "...", "label": "...", "memory": "...", "enumValues": [...]}, ...]
    Looks only at the first ~64KB like the display tag scanner.
    """
    out = []
    text = _ReadDisplayScriptText(fullPath)
    if not text:
        return out

    # Collect optional ENUM values by label (future-proof)
    enumValsByLabel = {}
    for ln in text.split("\n"):
        m2 = _SETTING_ENUMVALS_RE.search(ln)
        if m2:
            lbl = (m2.group(1) or "").strip()
            raw = (m2.group(2) or "").strip()          
            import re as _re
            vals = [v.strip() for v in _re.split(r"[|,;]", raw) if v.strip() != ""]
            enumValsByLabel[lbl] = vals

    for ln in text.split("\n"):
        m = _SETTING_DESC_RE.search(ln)
        if not m:
            continue
        stype = (m.group(1) or "").strip().upper()
        label = (m.group(2) or "").strip()
        mem = _UserSettingMemoryName(label)
        entry = {"type": stype, "label": label, "memory": mem, "enumValues": enumValsByLabel.get(label, [])}
        out.append(entry)
    return out

def ScanDisplayOptions():
    """
    Returns: settingsMap = { fileName.py : [ {type,label,memory,enumValues}, ... ], ... }
    Scans the profile:jython folder for settings descriptors.
    """
    settingsMap = {}
    try:
        jdir = FileUtil.getExternalFilename("profile:jython")
    except:
        jdir = None
    if not jdir or not os.path.isdir(jdir):
        return settingsMap

    try:
        for fn in os.listdir(jdir):
            if not fn.lower().endswith(".py"):
                continue
            fullPath = os.path.join(jdir, fn)
            if not os.path.isfile(fullPath):
                continue
            opts = _ScanSettingsForScript(fullPath)
            if opts:
                settingsMap[fn] = opts
    except Exception as ex:
        LogWarn("Options scan failed: " + str(ex), alsoDialog=False)
    return settingsMap


def _ReadDisplayScriptText(fullPath):
    # Read a limited amount for speed; tags are expected in comments near the top.
    try:
        with open(fullPath, "r") as f:
            raw = f.read(65536)
            return raw.replace("\r\n", "\n").replace("\r", "\n")
    except:
        try:
            with open(fullPath, "rb") as f:
                raw = f.read(65536)
            try:
                return raw.decode("utf-8", "ignore").replace("\r\n", "\n").replace("\r", "\n")
            except:
                return ""
        except:
            return ""

def _ScanOneDisplayScript(fullPath):
    pidName = None
    sigName = None
    desc = None
    text = _ReadDisplayScriptText(fullPath)
    if not text:
        return (None, None, None)

    for ln in text.split("\n"):
        if pidName is None:
            m = _PID_TAG_RE.search(ln)
            if m:
                pidName = (m.group(1) or "").strip()
        if sigName is None:
            m = _SIG_TAG_RE.search(ln)
            if m:
                sigName = (m.group(1) or "").strip()
        if desc is None:
            m = _DESC_TAG_RE.search(ln)
            if m:
                desc = (m.group(1) or "").strip()

        if (pidName is not None) and (sigName is not None) and (desc is not None):
            break

    if pidName == "":
        pidName = None
    if sigName == "":
        sigName = None
    if desc == "":
        desc = None

    return (pidName, sigName, desc)

def ScanDisplayScripts():
    # Returns: (pidFiles, sigFiles, pidNames, sigNames, descriptions)
    pidFiles = []
    sigFiles = []
    pidNames = {}
    sigNames = {}
    descMap = {}

    try:
        jdir = FileUtil.getExternalFilename("profile:jython")
    except:
        jdir = None

    if not jdir or not os.path.isdir(jdir):
        return (pidFiles, sigFiles, pidNames, sigNames, descMap)

    try:
        for fn in os.listdir(jdir):
            if not fn.lower().endswith(".py"):
                continue
            fullPath = os.path.join(jdir, fn)
            if not os.path.isfile(fullPath):
                continue

            pidName, sigName, desc = _ScanOneDisplayScript(fullPath)

            if desc is not None:
                descMap[fn] = desc

            if pidName is not None:
                pidFiles.append(fn)
                pidNames[fn] = pidName

            if sigName is not None:
                sigFiles.append(fn)
                sigNames[fn] = sigName
    except Exception as ex:
        LogWarn("Display script scan failed: " + str(ex), alsoDialog=False)

    # Sort by display name, case-insensitive
    pidFiles.sort(key=lambda f: (pidNames.get(f, f) or f).lower())
    sigFiles.sort(key=lambda f: (sigNames.get(f, f) or f).lower())

    return (pidFiles, sigFiles, pidNames, sigNames, descMap)

class TASSetupFrame(jmri.util.JmriJFrame):
    def __init__(self):
        # Base frame setup
        jmri.util.JmriJFrame.__init__(self, "Timetable Automation System setup")
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
        self.setSize(780, 890)
           
        # Prevent the frame from ever packing smaller than the baseline.
        try:
            self.setMinimumSize(Dimension(780, 890))
        except:
            pass

        # --- CRITICAL: capture initial states BEFORE building tabs/UI ---
        # These are used by BuildGeneralTab()/BuildDayNightTab() to set initial checkbox states.
        # Also used later to determine whether we must prompt for a restart on close.
        self.InitialTimeActions = IsTimeActionsEnabled()   # CheckWhenTimeChanges.py at Start-Up
        self.InitialDayNight   = IsDayNightEnabled()       # DayNight.py at Start-Up
        self.InitialWeather    = IsWeatherEnabled()        # WeatherGenerator.py at Start-Up

        # Track current (user intent during this session); start equal to initial
        self.CurrentTimeActions = self.InitialTimeActions
        self.CurrentDayNight    = self.InitialDayNight
        self.CurrentWeather     = self.InitialWeather        
        
        # Hardware orientation sensing (LastReportedDirection.py) at Start-Up
        self.InitialDirectionSensing = _IsScriptEnabled("LastReportedDirection.py")
        self.CurrentDirectionSensing = self.InitialDirectionSensing
        
        # TAS menu on Start-Up (TimetableAutomation.py)
        self.InitialTASMenu = _IsScriptEnabled("TimetableAutomation.py")
        self.CurrentTASMenu = self.InitialTASMenu

        # Wizard sync: allow UI to refresh if a setup wizard changes preferences while this window is open.
        self.SuppressWizardSync = False
        self.WizardSyncTimer = None

        # --- Build tabs AFTER initial/current state is ready ---
        tabs = JTabbedPane()
        ApplyTheme(tabs)
        tabs.addTab("General setup", self.BuildGeneralTab())
        tabs.addTab("Timetable", self.BuildTimetableTab())
        tabs.addTab("Workings", self.BuildWorkingsTab())
        tabs.addTab("Timing points", self.BuildTimingPointsTab())
        tabs.addTab("Orientation", self.BuildOrientationTab())
        tabs.addTab("Display configuration", self.BuildDisplayTab())
        tabs.addTab("Day/night cycle", self.BuildDayNightTab())
        tabs.addTab("Interface", self.BuildInterfaceTab())

        # Finalize
        self.getContentPane().add(tabs, BorderLayout.CENTER)
        self.PackAndCenter()
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)  # 32px icon size
        except Exception as ex:
            print("[TASSetup] Failed to set setup window icon: " + str(ex))

        self.setVisible(True)

        # Post-show: prompt to run the wizard when no valid timetable is configured
        try:
            def _DoStartupTimetableCheck():
                try:
                    self.CheckTimetableOnStartup()
                except:
                    pass
            SwingUtilities.invokeLater(RunnableAdapter(_DoStartupTimetableCheck))
        except:
            pass

        try:
            self.StartWizardSyncTimer()
        except:
            pass

        # Ensure the timer stops when this window is closed.
        try:
            class _WizardSyncWindowListener(java.awt.event.WindowAdapter):
                def windowClosing(innerSelf, e):
                    try:
                        if getattr(self, "WizardSyncTimer", None) is not None:
                            self.WizardSyncTimer.stop()
                            self.WizardSyncTimer = None
                    except:
                        pass
                def windowClosed(innerSelf, e):
                    try:
                        if getattr(self, "WizardSyncTimer", None) is not None:
                            self.WizardSyncTimer.stop()
                            self.WizardSyncTimer = None
                    except:
                        pass
            self.addWindowListener(_WizardSyncWindowListener())
        except:
            pass
        # Ensure initial font is applied across all controls
        try:
            _ApplyFontRecursive(self.getContentPane(), THEME_FONT_FAMILY)
        except:
            pass
        LogInfo("Setup window opened.")
 
    def CheckTimetableOnStartup(self):
        # Show a one-time prompt if no valid timetable is configured
        try:
            if getattr(self, "_StartupChecked", False):
                return
            self._StartupChecked = True
        except:
            pass

        try:
            ok, msg, _ = _ValidateTimetable()
        except:
            ok = True
            msg = ""

        if ok:
            return

        reason = ("Reason: " + str(msg)) if (msg is not None and str(msg).strip() != "") else "No timetable configured."
        prompt = ("The Timetable Automation System is not yet configured.\n\n"
                  + reason
                  + "\n\nRun the Setup wizard now?")

        try:
            choice = JOptionPane.showConfirmDialog(
                self, prompt, "Run Setup wizard?",
                JOptionPane.OK_CANCEL_OPTION, JOptionPane.QUESTION_MESSAGE
            )
        except:
            choice = JOptionPane.CANCEL_OPTION

        if choice == JOptionPane.OK_OPTION:
            if not RunSetupWizard(onClosed=lambda: self.OnWizardClosedRefreshSetupUi()):
                LogWarn("Could not run the Setup wizard.", alsoDialog=True)
    
    def PackAndCenter(self):
        self.pack()
        try: self.setLocationRelativeTo(None)
        except: pass

    # ------------------------------ General ----------------------------
    
    def RefreshFonts(self):
        # Apply THEME_FONT_FAMILY to all tabs and headings
        try:
            for comp in self.getContentPane().getComponents():
                ApplyTheme(comp)
                for sub in comp.getComponents():
                    ApplyTheme(sub)
        except:
            pass
    
    def BuildGeneralTab(self):
        panel = MakePaperPanel()
        panel.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10,10,10,10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 0.0
        gbc.weighty = 0.0

        # Top-centered Setup wizard
        gbc.gridx = 0; gbc.gridy = 0; gbc.gridwidth = 3
               
        header = Box.createHorizontalBox()
        header.add(Box.createHorizontalGlue())
        wizardBtn = JButton("Setup wizard...")
        # Make the button bigger with matching bigger text
        try:
            wizardBtn.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 18))
        except:
            pass
        try:
            size = wizardBtn.getPreferredSize()
            wizardBtn.setPreferredSize(Dimension(size.width + 40, int(size.height * 2)))
        except:
            pass

        # Check if TASWiz.py exists in profile:jython
        wizExists = ScriptExists("TASWiz.py")
        wizardBtn.setVisible(wizExists)
        wizardBtn.setEnabled(wizExists)

        # If enabled, make the button double height
        if wizExists:
            # Get current preferred size and double the height
            size = wizardBtn.getPreferredSize()
            wizardBtn.setPreferredSize(Dimension(size.width, size.height * 2))

        def DoWizard(e=None):
            try:
                path = ProfileJythonFilePath("TASWiz.py")
                if not os.path.isfile(path):
                    LogWarn("TASWiz.py not found at: " + path, alsoDialog=True)
                    return
                RunSetupWizard(onClosed=(lambda: self.OnWizardClosedRefreshSetupUi()))
            except Exception as ex:
                LogError("Setup wizard failed: " + str(ex), ex=ex, alsoDialog=True)

        if wizExists:
            wizardBtn.addActionListener(lambda e: DoWizard())

        header.add(wizardBtn)
        header.add(Box.createHorizontalGlue())
        # Add bottom padding under the header row so the next controls sit lower,
        # placing the button roughly mid-gap visually.
        try:
            ph = wizardBtn.getPreferredSize().height
            header.setBorder(BorderFactory.createEmptyBorder(12, 0, int(ph * 0.75), 0))
        except:
            try:
                header.setBorder(BorderFactory.createEmptyBorder(12, 0, 28, 0))
            except:
                pass

        panel.add(header, gbc)

        # (A) Enable time-based actions (requires restart) - controls CheckWhenTimeChanges.py at Start-Up
        gbc.gridwidth = 3
        gbc.gridx = 0; gbc.gridy = 1
        timeRow = Box.createHorizontalBox()
        self.ChkTimeActions = JCheckBox("Enable time-based actions (requires restart)")
        self.ChkTimeActions.setOpaque(False)
        self.ChkTimeActions.setSelected(self.InitialTimeActions)
        # (A0) Show TAS menu on Start-Up (requires restart) - controls TimetableAutomation.py at Start-Up
        gbc.gridwidth = 3
        gbc.gridx = 0; gbc.gridy = 1
        tasMenuRow = Box.createHorizontalBox()
        self.ChkTASMenu = JCheckBox("Show the Timetable Automation System menu on startup")
        self.ChkTASMenu.setOpaque(False)
        self.ChkTASMenu.setSelected(self.InitialTASMenu)

        def OnTASMenu(e=None):
            want = self.ChkTASMenu.isSelected()
            ok = _EnsureScriptEnabled("TimetableAutomation.py", want)
            actual = _IsScriptEnabled("TimetableAutomation.py")
            self.CurrentTASMenu = actual
            self.ChkTASMenu.setSelected(actual)
            if not ok:
                LogWarn("Could not change Start-Up for TimetableAutomation.py", alsoDialog=True)

        self.ChkTASMenu.addActionListener(OnTASMenu)
        tasMenuRow.add(self.ChkTASMenu)
        panel.add(tasMenuRow, gbc)

        # Error label for missing TAS menu script
        gbc.gridy += 1
        self.LblTASMenuError = JLabel("")
        ApplyTheme(self.LblTASMenuError)
        panel.add(self.LblTASMenuError, gbc)

        missingTAS = []
        if not ScriptExists("TimetableAutomation.py"):
            missingTAS.append("TimetableAutomation.py")

        if missingTAS:
            self.ChkTASMenu.setSelected(False)
            self.ChkTASMenu.setEnabled(False)
            msgTAS = "<html>" + "<br/>".join(["Missing script: " + m for m in missingTAS]) + "</html>"
            self.LblTASMenuError.setText(msgTAS)

        # Add a spacer so "Enable time-based actions" moves down cleanly, but nothing else shifts
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)
        def OnTimeActions(e=None):
            want = self.ChkTimeActions.isSelected()

            # Enable/disable all scripts under the single master toggle
            ok = _EnsureScriptEnabled("CheckWhenTimeChanges.py", want) and _EnsureScriptEnabled("TimeWarpChecker.py", want) and _EnsureScriptEnabled("DayTracker.py", want)
            
            # Reflect actual combined state and track it for the restart prompt
            actual = IsTimeActionsEnabled()
            self.CurrentTimeActions = actual
            self.ChkTimeActions.setSelected(actual)

            if not (ok):
                LogWarn("Could not change Start-Up for one or more time-based action scripts.", alsoDialog=True)

        self.ChkTimeActions.addActionListener(OnTimeActions)
        timeRow.add(self.ChkTimeActions)
        panel.add(timeRow, gbc)
        
        # Error label for missing scripts
        gbc.gridy += 1
        self.LblTimeActionsError = JLabel("")
        ApplyTheme(self.LblTimeActionsError)
        panel.add(self.LblTimeActionsError, gbc)

        # Check existence of both scripts
        missing = []
        if not ScriptExists("CheckWhenTimeChanges.py"): missing.append("CheckWhenTimeChanges.py")
        if not ScriptExists("DayTracker.py"): missing.append("DayTracker.py")
        if not ScriptExists("TimeWarpChecker.py"): missing.append("TimeWarpChecker.py")
        if missing:
            self.ChkTimeActions.setSelected(False)
            self.ChkTimeActions.setEnabled(False)
            msg = "<html>" + "<br/>".join(["Missing script: " + m for m in missing]) + "</html>"
            self.LblTimeActionsError.setText(msg)

        # Add extra vertical space before next checkbox
        gbc.gridy += 1
        spacer = JLabel(" ")  # blank spacer for padding
        panel.add(spacer, gbc)

        # Now increment again for the second checkbox row
        gbc.gridy += 1

        # (B) "Run trains automatically" row (checkbox + status label) - NOW uses IMTASAutoWorking memory only
        gbc.gridwidth = 3
        gbc.gridx = 0
        gbc.gridy += 1  # move down below the TAS menu section
        # Add twice as much vertical space below the time-based actions error label
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)  # spacer row 1
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)  # spacer row 2

        # Now place the second checkbox on the next row
        gbc.gridy += 1
        runRow = Box.createHorizontalBox()
        self.ChkRunAuto = JCheckBox("Run trains automatically from timetable")
        self.ChkRunAuto.setOpaque(False)

        # Disable second checkbox whenever the first is disabled
        if not self.ChkTimeActions.isEnabled():
            self.ChkRunAuto.setEnabled(False)

        self.LblRunAutoStatus = JLabel("")  # concise, wrapped status (HTML)
        runRow.add(self.ChkRunAuto)
        runRow.add(Box.createHorizontalStrut(12))
        runRow.add(self.LblRunAutoStatus)
        panel.add(runRow, gbc)
        
        # Disable second checkbox if first is disabled
        if not self.ChkTimeActions.isEnabled():
            self.ChkRunAuto.setEnabled(False)

        # NOTE: Removed separate "Requires restart to take effect." label - restart is for time-based actions only

        # Current timetable heading + widgets
        gbc.gridwidth = 1
        gbc.gridx = 0
        gbc.gridy += 1  # place heading just after the second checkbox row
        panel.add(MakeHeading("Current timetable"), gbc)

        self.TxtCurrentTimetable = JTextField(28)
        self.TxtCurrentTimetable.setToolTipText("Select the timetable used for this layout")
        self.TxtCurrentTimetable.setText(TBL.SafeGetOrCreateMemoryValue(IMCurrentTimetable, ""))

        def CommitText():
            name = StripCsvExt(self.TxtCurrentTimetable.getText().strip())
            TBL.SafeSetMemoryValue(IMCurrentTimetable, name)
            self.UpdateRunAutoControls()
            # No Start-Up change for auto-run now; validations still inform status
        self.TxtCurrentTimetable.addActionListener(lambda e: CommitText())
        class CommitOnFocusLost(FocusAdapter):
            def focusLost(self, e): CommitText()
        self.TxtCurrentTimetable.addFocusListener(CommitOnFocusLost())

        btnBrowse = JButton("Browse...")
        btnBrowse.setToolTipText("Select the timetable used for this layout")
        def DoBrowse(e):
            try:
                dirFile = GetTimetableDirFile()
                chooser = RestrictedCsvChooser(dirFile)
                memName = StripCsvExt(self.TxtCurrentTimetable.getText().strip())
                if memName != "":
                    pre = File(dirFile, memName + ".csv")
                    chooser.setSelectedFile(pre)
                result = chooser.showOpenDialog(self)
                if result == JFileChooser.APPROVE_OPTION:
                    sel = chooser.getSelectedFile()
                    bare = StripCsvExt(sel.getName())
                    self.TxtCurrentTimetable.setText(bare)
                    CommitText()
            except Exception as ex:
                LogError("Browse failed: " + str(ex), ex=ex, alsoDialog=True)
        btnBrowse.addActionListener(lambda e: DoBrowse(e))
        
        gbc.gridx = 1; gbc.weightx = 1.0
        panel.add(self.TxtCurrentTimetable, gbc)
        gbc.gridx = 2; gbc.weightx = 0.0
        panel.add(btnBrowse, gbc)

        # Wire up RunAuto checkbox logic (memory-based)
        def OnRunAuto(e=None):
            want = self.ChkRunAuto.isSelected()
            # Track memory for auto-working; create if first time set to true
            SetMemoryBool(IMTASAutoWorking, want)
            self.UpdateRunAutoControls()
        self.ChkRunAuto.addActionListener(OnRunAuto)
        self.UpdateRunAutoControls()

        # --- Place "Allow delays / Allow cancellations" BELOW the Run Auto row ---
        gbc.gridx = 0
        gbc.gridwidth = 3
        gbc.fill = GridBagConstraints.NONE
        gbc.gridy += 1  # move to the next row under "Run trains automatically from timetable"

        boxPanel = Box.createHorizontalBox()
        chkDelays = JCheckBox("Allow delays")
        chkDelays.setOpaque(False)
        chkDelays.setSelected(GetMemoryBool(IMAllowDelays, False))
        chkDelays.addActionListener(lambda e: SetMemoryBool(IMAllowDelays, chkDelays.isSelected()))
        chkCancellations = JCheckBox("Allow cancellations")
        chkCancellations.setOpaque(False)
        chkCancellations.setSelected(GetMemoryBool(IMAllowCANCELLATIONS, False))
        chkCancellations.addActionListener(lambda e: SetMemoryBool(IMAllowCANCELLATIONS, chkCancellations.isSelected()))
        boxPanel.add(chkDelays); boxPanel.add(Box.createHorizontalStrut(18))
        boxPanel.add(chkCancellations)
        panel.add(boxPanel, gbc)
        
        # -- Reset registers row: two buttons with confirmations --
        gbc.gridy += 1
        gbc.gridwidth = 3
        gbc.fill = GridBagConstraints.NONE
        resetRow = Box.createHorizontalBox()

        btnResetDisruption = JButton("Reset disruption data")
        btnResetTiming = JButton("Reset timing data")

        def DoResetDisruption(e=None):
            try:
                msg = ("This will permanently clear all recorded delays and cancellations.\n"
                       "This action cannot be undone.\n\nProceed?")
                choice = JOptionPane.showConfirmDialog(
                    self, msg, "Confirm reset (disruption data)",
                    JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:
                    # DisruptionRegister: synchronized Hashtable + save()
                    import DisruptionRegister as DR
                    try:
                        DR.register.clear()
                        DR.save()
                        # Also re-seed disruption generator: IMDISRUPTIONSEEDBASE = current time (ms)
                        try:
                            from java.lang import System as _JSystem
                            TBL.SafeSetMemoryValue("DISRUPTIONSEEDBASE", str(_JSystem.currentTimeMillis()))
                        except Exception:
                            import time as _pyTime
                            TBL.SafeSetMemoryValue("DISRUPTIONSEEDBASE", str(int(_pyTime.time() * 1000)))
                        LogInfo("[TAS] Disruption register cleared.", alsoDialog=True, title="Done")
                    except Exception as ex:
                        LogError("Failed to clear disruption register: " + str(ex), ex=ex, alsoDialog=True)
            except Exception as exOuter:
                LogError("Reset disruption action failed: " + str(exOuter), ex=exOuter, alsoDialog=True)

        def DoResetTiming(e=None):
            try:
                msg = ("This will permanently clear all timing point records (timings at every TP).\n"
                       "Blocks definitions remain as-is; only timing tuples are removed when entries are deleted.\n"
                       "This action cannot be undone.\n\nProceed?")
                choice = JOptionPane.showConfirmDialog(
                    self, msg, "Confirm reset (timing data)",
                    JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:
                    import TimingRegister as TR
                    try:
                        # Remove every timing point entry using lock-safe helpers
                        tps = TR.listTimingPoints() or []
                        for tp in tps:
                            try:
                                TR.deleteTimingPoint(tp)
                            except Exception as exDel:
                                print("[TASSetup] WARN: Could not delete timing point {}: {}".format(tp, exDel))
                        TR.save()
                        LogInfo("[TAS] Timing register cleared.", alsoDialog=True, title="Done")
                    except Exception as ex:
                        LogError("Failed to clear timing register: " + str(ex), ex=ex, alsoDialog=True)
            except Exception as exOuter:
                LogError("Reset timing action failed: " + str(exOuter), ex=exOuter, alsoDialog=True)

        btnResetDisruption.addActionListener(lambda e: DoResetDisruption(e))
        btnResetTiming.addActionListener(lambda e: DoResetTiming(e))

        resetRow.add(btnResetDisruption)
        resetRow.add(Box.createHorizontalStrut(12))
        resetRow.add(btnResetTiming)

        panel.add(resetRow, gbc)

        # --- Enqueued workings status + reset button ---
        import enqueuedWorkings as EW

        # Status label showing current count
        gbc.gridy += 1
        self.LblEnqueued = JLabel("Enqueued workings: %d" % EW.countWorkings())
        ApplyTheme(self.LblEnqueued)
        panel.add(self.LblEnqueued, gbc)  
        # Grey-out rule: disable the reset button when there are no enqueued workings
        currentCount = EW.countWorkings()

        # Reset button      
        gbc.gridy += 1
        btnResetEnqueued = JButton("Reset enqueued workings")
        # Set initial enabled state: only enabled when there is something to clear
        btnResetEnqueued.setEnabled(currentCount > 0)

        def DoResetEnqueued(e=None):
            try:
                msg = (
                    "This will permanently clear all enqueued workings.\n"
                    "These are the workings that could not run at their scheduled times.\n"
                    "This action cannot be undone.\n\nProceed?"
                )
                choice = JOptionPane.showConfirmDialog(
                    self,
                    msg,
                    "Confirm reset (enqueued workings)",
                    JOptionPane.OK_CANCEL_OPTION,
                    JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:                  
                    EW.ClearWorkings()
                    # Update label + button enabled state immediately
                    newCount = EW.countWorkings()
                    self.LblEnqueued.setText("Enqueued workings: %d" % newCount)
                    btnResetEnqueued.setEnabled(newCount > 0)
                    self.LblEnqueued.setText("Enqueued workings: %d" % EW.countWorkings())
            except Exception as ex:
                LogError("Failed to clear enqueued workings: " + str(ex), ex=ex, alsoDialog=True)

        btnResetEnqueued.addActionListener(lambda e: DoResetEnqueued())
        panel.add(btnResetEnqueued, gbc)
        
        return panel

        # Wire up RunAuto checkbox logic (memory-based)
        def OnRunAuto(e=None):
            want = self.ChkRunAuto.isSelected()
            # Track memory for auto-working; create if first time set to true
            SetMemoryBool(IMTASAutoWorking, want)
            self.UpdateRunAutoControls()
        self.ChkRunAuto.addActionListener(OnRunAuto)
        self.UpdateRunAutoControls()

        return panel

    def UpdateRunAutoControls(self):
        # 1) Read current memory state
        isEnabled = GetMemoryBool(IMTASAutoWorking, False)

        # 2) Run validations (unchanged) for informative status only
        ttOK, ttMsg, hdr = _ValidateTimetable()
        wsOK, wsMsg = _CheckWorkingScripts()

        # 3) Concise, wrapped status: general explanation + first issue only
        statusHtml = ""
        if not ttOK:
            statusHtml = "<html>Cannot enable automatic running: timetable is not valid.<br/>First issue: %s There may be more issues.</html>" % ttMsg
        elif not wsOK:
            statusHtml = "<html>Cannot enable automatic running: required working scripts are missing.<br/>First issue: %s There may be more issues.</html>" % wsMsg
        else:
            statusHtml = ""
        self.LblRunAutoStatus.setText(statusHtml)

        # 4) Checkbox mirrors memory
        self.ChkRunAuto.setSelected(isEnabled)

        # 5) Grey-out rule with master toggle guard:
        # If the master time-based actions checkbox is disabled (missing scripts),
        # always disable auto-working; otherwise apply the normal validation rule.
        masterEnabled = self.ChkTimeActions.isEnabled()
        if not masterEnabled:
            self.ChkRunAuto.setEnabled(False)
        else:
            # If currently disabled and validations cannot be met -> disable (grey out).
            # If currently enabled -> allow interaction (you may want to turn it off).
            canEnable = ttOK and wsOK
            self.ChkRunAuto.setEnabled(isEnabled or canEnable)

    # ------------------------ Display configuration --------------------
    def BuildDisplayTab(self):
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(8,8,8,8) 
        # Ensure every row (lists, options, description) fills horizontally
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0        
    
        pubSel = [s for s in TBL.SafeGetOrCreateMemoryValue(IMPublicDisplayList, "").split(",")
                  if s.strip() not in ["", "..."]]
        sigSel = [s for s in TBL.SafeGetOrCreateMemoryValue(IMSignallerDisplayList, "").split(",")
                  if s.strip() not in ["", "..."]]

        def SavePublic(selection):
            TBL.SafeSetMemoryValue(IMPublicDisplayList, ",".join(selection))

        def SaveSignaller(selection):
            TBL.SafeSetMemoryValue(IMSignallerDisplayList, ",".join(selection))

        # Discover scripts from profile: jython
        pidFiles, sigFiles, pidNames, sigNames, descMap = ScanDisplayScripts()
             
        # Discover per-file configurable options
        settingsMap = ScanDisplayOptions()

        # Options area (shared; appears above description)
        optionsPanel = JPanel()
        optionsPanel.setOpaque(False)
        optionsPanel.setLayout(GridBagLayout())
        opg = GridBagConstraints()
        opg.insets = Insets(2,2,2,2)
        opg.fill = GridBagConstraints.HORIZONTAL
        opg.gridx = 0
        opg.gridy = 0
        opg.weightx = 1.0

        # Heading (kept hidden when no options)
        lblOptsHeading = MakeHeading("Options")
        optionsPanel.add(lblOptsHeading, opg)

        # Container for controls (replaced per selection)
        opg.gridy = 1
        optsInner = JPanel()
        optsInner.setOpaque(False)
        optsInner.setLayout(GridBagLayout())
        optionsPanel.add(optsInner, opg)

        def _ClearOptions():
            try:
                optsInner.removeAll()
                optsInner.revalidate()
                optsInner.repaint()
            except:
                pass

        # Display options must NOT seed values. TASSetup does not know defaults.
        # If the memory does not exist yet, disable the control and explain why.
        _NEED_RUN_HINT = "Run the selected display once to create this option, then reopen TASSetup to change it."

        def _FindExistingMemoryBeanBySuffix(memSuffix):
            # memSuffix is the suffix used by TASBeanLookup (e.g. "TAS_USER_SETTING_STRIP_COLUMNS").
            # We must NOT create anything here.
            try:
                mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
            except:
                mm = None
            if mm is None:
                return None

            # Try as-given (in case caller passed a full system name).
            try:
                if hasattr(mm, "getBySystemName"):
                    m = mm.getBySystemName(str(memSuffix))
                else:
                    m = mm.getMemory(str(memSuffix))
                if m is not None:
                    return m
            except:
                pass

            # Try common Internal Memory prefixes used by TASBeanLookup (IM/I2M/I3M...).
            prefixes = ["IM","I2M","I3M","I4M","I5M","I6M","I7M","I8M","I9M"]
            for p in prefixes:
                sysName = p + str(memSuffix)
                try:
                    if hasattr(mm, "getBySystemName"):
                        m = mm.getBySystemName(sysName)
                    else:
                        m = mm.getMemory(sysName)
                except:
                    m = None
                if m is not None:
                    return m

            return None

        def _DisableWithRunHint(*components):
            for c in components:
                try:
                    if c is not None:
                        c.setEnabled(False)
                except:
                    pass
                try:
                    if c is not None:
                        c.setToolTipText(_NEED_RUN_HINT)
                except:
                    pass

        def _ToolTip(*components):
            for c in components:
                try:
                    if c is not None:
                        c.setToolTipText(_NEED_RUN_HINT)
                except:
                    pass

        def _ParseBoolValue(raw, defaultVal=False):
            try:
                t = ("" if raw is None else str(raw)).strip().lower()
                if t in ["1", "true", "yes", "y", "on", "enabled"]:
                    return True
                if t in ["0", "false", "no", "n", "off", "disabled"]:
                    return False
            except:
                pass
            return bool(defaultVal)

        def _AddBooleanRow(labelText, memName, rowIdx):
            bean = _FindExistingMemoryBeanBySuffix(memName)

            row = Box.createHorizontalBox()
            chk = JCheckBox(labelText)
            chk.setOpaque(False)

            if bean is None:
                chk.setSelected(False)
                _DisableWithRunHint(chk)
            else:
                try:
                    chk.setSelected(_ParseBoolValue(bean.getValue(), False))
                except:
                    chk.setSelected(False)

                def _apply(e=None):
                    try:
                        bean.setValue("true" if chk.isSelected() else "false")
                    except:
                        try:
                            TBL.SafeSetMemoryValue(memName, "true" if chk.isSelected() else "false")
                        except:
                            pass

                chk.addActionListener(lambda e: _apply())

            row.add(chk)
            g = GridBagConstraints()
            g.insets = Insets(2,2,2,2)
            g.gridx = 0
            g.gridy = int(rowIdx)
            g.fill = GridBagConstraints.HORIZONTAL
            g.weightx = 1.0
            optsInner.add(row, g)

        def _AddStringRow(labelText, memName, rowIdx):
            bean = _FindExistingMemoryBeanBySuffix(memName)

            row = Box.createHorizontalBox()
            lbl = JLabel(labelText + ":")
            txt = JTextField(20)

            if bean is None:
                txt.setText("")
                _DisableWithRunHint(lbl, txt)
            else:
                try:
                    v = bean.getValue()
                    txt.setText("" if v is None else str(v))
                except:
                    txt.setText("")

                def _commit():
                    try:
                        bean.setValue(txt.getText().strip())
                    except:
                        try:
                            TBL.SafeSetMemoryValue(memName, txt.getText().strip())
                        except:
                            pass

                txt.addActionListener(lambda e: _commit())
                class _Lost(FocusAdapter):
                    def focusLost(self, e): _commit()
                txt.addFocusListener(_Lost())

            _ToolTip(lbl, txt)
            row.add(lbl); row.add(Box.createHorizontalStrut(6)); row.add(txt)
            g = GridBagConstraints(); g.insets = Insets(2,2,2,2)
            g.gridx=0; g.gridy=int(rowIdx)
            g.fill=GridBagConstraints.HORIZONTAL; g.weightx=1.0
            optsInner.add(row, g)

        def _AddNumberRow(labelText, memName, rowIdx):
            bean = _FindExistingMemoryBeanBySuffix(memName)

            curVal = 0
            if bean is not None:
                try:
                    raw = bean.getValue()
                    s = ("" if raw is None else str(raw)).strip()
                    if s != "":
                        curVal = int(float(s))
                except:
                    curVal = 0

            model = SpinnerNumberModel(int(curVal), 0, 2147483647, 1)
            spn = JSpinner(model)

            try:
                spn.setEditor(JSpinner.NumberEditor(spn, "#"))
            except:
                pass

            row = Box.createHorizontalBox()
            lbl = JLabel(labelText + ":")

            if bean is None:
                _DisableWithRunHint(lbl, spn)
            else:
                def _commit():
                    try:
                        v = spn.getValue()
                        n = int(v)
                        try:
                            bean.setValue(str(n))
                        except:
                            TBL.SafeSetMemoryValue(memName, str(n))
                    except:
                        pass

                class _CL(ChangeListener):
                    def stateChanged(self, e):
                        _commit()

                try:
                    spn.addChangeListener(_CL())
                except:
                    pass

            _ToolTip(lbl, spn)
            row.add(lbl)
            row.add(Box.createHorizontalStrut(6))

            try:
                ph = spn.getPreferredSize().height
                spn.setPreferredSize(Dimension(80, ph))
                spn.setMinimumSize(Dimension(80, ph))
                spn.setMaximumSize(Dimension(100, ph))
            except:
                pass

            row.add(spn)
            row.add(Box.createHorizontalGlue())

            g = GridBagConstraints()
            g.insets = Insets(2,2,2,2)
            g.gridx = 0
            g.gridy = int(rowIdx)
            g.fill = GridBagConstraints.HORIZONTAL
            g.weightx = 1.0
            optsInner.add(row, g)

        def _AddColorRow(labelText, memName, rowIdx):
            bean = _FindExistingMemoryBeanBySuffix(memName)

            row = Box.createHorizontalBox()
            lbl = JLabel(labelText + ":")
            swatch = JPanel()
            swatch.setOpaque(True)
            swatch.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))
            sw, sh = 80, 22
            swatch.setPreferredSize(Dimension(sw, sh))

            # Show existing value if present; otherwise show a neutral preview only (do not seed).
            if bean is not None:
                try:
                    memRgb = bean.getValue()
                except:
                    memRgb = None
                current = _RgbStrToColorOrDefault(memRgb, Color(240,238,220))
                swatch.setBackground(current)
            else:
                swatch.setBackground(Color(240,238,220))
                _DisableWithRunHint(lbl, swatch)

            btnReset = JButton("Reset")

            if bean is None:
                _DisableWithRunHint(btnReset)
            else:
                class _Click(MouseAdapter):
                    def mouseClicked(self, e):
                        try:
                            initial = swatch.getBackground()
                            chosen = JColorChooser.showDialog(None, "Choose colour", initial)
                            if chosen is not None:
                                swatch.setBackground(chosen)
                                try:
                                    bean.setValue(_ColorToRgbStr(chosen))
                                except:
                                    TBL.SafeSetMemoryValue(memName, _ColorToRgbStr(chosen))
                        except Exception as ex:
                            LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

                swatch.addMouseListener(_Click())

                def _doReset(e=None):
                    try:
                        defaultColor = _RgbStrToColorOrDefault(GetDefaultBackgroundRGB(), Color(240,238,220))
                        swatch.setBackground(defaultColor)
                        try:
                            bean.setValue(_ColorToRgbStr(defaultColor))
                        except:
                            TBL.SafeSetMemoryValue(memName, _ColorToRgbStr(defaultColor))
                    except Exception as ex:
                        LogWarn("Reset failed: " + str(ex), alsoDialog=True)

                btnReset.addActionListener(lambda e: _doReset())

            _ToolTip(lbl, swatch, btnReset)
            row.add(lbl); row.add(Box.createHorizontalStrut(6)); row.add(swatch); row.add(Box.createHorizontalStrut(6)); row.add(btnReset)
            g = GridBagConstraints(); g.insets = Insets(2,2,2,2)
            g.gridx=0; g.gridy=int(rowIdx)
            g.fill=GridBagConstraints.HORIZONTAL; g.weightx=1.0
            optsInner.add(row, g)

        def _AddEnumRow(labelText, memName, values, rowIdx):
            bean = _FindExistingMemoryBeanBySuffix(memName)

            if isinstance(values, list) and len(values) > 0:
                row = Box.createHorizontalBox()
                lbl = JLabel(labelText + ":")
                cmb = JComboBox(values)

                if bean is None:
                    try:
                        cmb.setSelectedItem(values[0])
                    except:
                        pass
                    _DisableWithRunHint(lbl, cmb)
                else:
                    current = None
                    try:
                        current = bean.getValue()
                    except:
                        current = None
                    try:
                        if current in values:
                            cmb.setSelectedItem(current)
                        else:
                            cmb.setSelectedItem(values[0])
                    except:
                        pass

                    def _apply(e=None):
                        try:
                            val = str(cmb.getSelectedItem())
                            try:
                                bean.setValue(val)
                            except:
                                TBL.SafeSetMemoryValue(memName, val)
                        except:
                            pass

                    cmb.addActionListener(lambda e: _apply())

                _ToolTip(lbl, cmb)
                row.add(lbl); row.add(Box.createHorizontalStrut(6)); row.add(cmb)
                g = GridBagConstraints(); g.insets = Insets(2,2,2,2)
                g.gridx=0; g.gridy=int(rowIdx)
                g.fill=GridBagConstraints.HORIZONTAL; g.weightx=1.0
                optsInner.add(row, g)
            else:
                _AddStringRow(labelText, memName, rowIdx)


        def ShowOptionsForFile(fname):
            """
            Rebuild the options controls for the currently selected display script.
            Hidden when there are no settings for this script.
            """
            _ClearOptions()
            opts = settingsMap.get(fname, [])
            hasOpts = isinstance(opts, list) and len(opts) > 0

            try:
                lblOptsHeading.setVisible(hasOpts)
            except:
                pass
            try:
                optionsPanel.setVisible(hasOpts)
            except:
                pass
            
            # Also toggle the scroller itself
            try:
                optionsScroll.setVisible(hasOpts)
            except:
                pass

            if not hasOpts:
                return

            # Build rows
            r = 0
            for o in opts:
                stype = (o.get("type","") or "").upper()
                label = o.get("label","") or ""
                mem = o.get("memory","") or _UserSettingMemoryName(label)
                if stype == "BOOLEAN":
                    _AddBooleanRow(label, mem, r)
                elif stype == "STRING":
                    _AddStringRow(label, mem, r)
                elif stype == "NUMBER":
                    _AddNumberRow(label, mem, r)
                elif stype == "COLOR":
                    _AddColorRow(label, mem, r)
                elif stype == "ENUM":
                    _AddEnumRow(label, mem, o.get("enumValues", []), r)
                else:
                    # Unknown -> treat as STRING to avoid breaking
                    _AddStringRow(label, mem, r)
                r += 1

        # Fit options into the scroller without stealing space from the list rows
        try:
            optH = int(optionsPanel.getPreferredSize().height)
            # Clamp visible height to 200..360px; larger content scrolls
            visH = max(200, min(360, optH))
            optionsScroll.setPreferredSize(Dimension(660, visH))
            optionsScroll.revalidate(); optionsScroll.repaint()
            root.revalidate(); root.repaint()
        except:
            pass
      
        # Description area (shared between both panels)
        from javax.swing import JTextArea
        descArea = JTextArea(4, 50)
        ApplyTheme(descArea)
        descArea.setLineWrap(True)
        descArea.setWrapStyleWord(True)
        descArea.setEditable(False)
        descArea.setBackground(THEME_PAPER)
        descArea.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(Color(180,170,150), 1),
            BorderFactory.createEmptyBorder(6,6,6,6)
        ))
     
        def ShowDescriptionForFile(fname):
            try:
                # Update description text
                txt = descMap.get(fname, "")
                if txt is None:
                    txt = ""
                descArea.setText(str(txt))
                try:
                    descArea.setCaretPosition(0)
                except:
                    pass
                # ALSO update the options pane for this selection
                try:
                    ShowOptionsForFile(fname)
                except:
                    pass
            except:
                pass

        def PreviewDisplayScript(fname):
            try:
                fn = ("" if fname is None else str(fname)).strip()
                if fn == "":
                    return
                path = ProfileJythonFilePath(fn)
                if not os.path.isfile(path):
                    LogWarn("Script not found: " + str(path), alsoDialog=True)
                    return

                # Run in a clean global namespace, but set __file__/__name__ for scripts that rely on them.
                g = {"__file__": path, "__name__": "__main__"}
                execfile(path, g)

            except Exception as ex:
                LogError("Failed to run preview for: " + str(fname) + " :: " + str(ex), ex=ex, alsoDialog=True)
        
        # Row 0: Public (PID) displays
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.weighty = 0.45
        pubPanel = MakeDualListPanel(
         "Public information displays",
         pidFiles, pidNames, descMap,
         pubSel, SavePublic,
         OnSelectCallback=ShowDescriptionForFile,
         OnPreviewCallback=PreviewDisplayScript
        )
        root.add(pubPanel, gbc)

        # Keep the public list pane readable even when options grow
        try:
            pubPanel.setMinimumSize(Dimension(520, 260))
        except:
            pass

        # Row 1: Signallers' displays
        gbc.gridx = 0
        gbc.gridy = 1
        gbc.weighty = 0.45
        sigPanel = MakeDualListPanel(
         "Signallers' displays",
         sigFiles, sigNames, descMap,
         sigSel, SaveSignaller,
         OnSelectCallback=ShowDescriptionForFile,
         OnPreviewCallback=PreviewDisplayScript
)
        root.add(sigPanel, gbc)
             
        # Keep the signallers' list pane readable even when options grow
        try:
            sigPanel.setMinimumSize(Dimension(520, 260))
        except:
            pass

        # Row 2: Description box at bottom
        descPanel = JPanel()
        descPanel.setOpaque(False)
        descPanel.setLayout(GridBagLayout())
        dg = GridBagConstraints()
        dg.insets = Insets(2,2,2,2)
        dg.fill = GridBagConstraints.BOTH
        dg.weightx = 1.0

        dg.gridx = 0
        dg.gridy = 0
        dg.weighty = 0.0
        descPanel.add(MakeHeading("Description"), dg)

        dg.gridy = 1
        dg.weighty = 1.0
        descScroll = JScrollPane(descArea)
        descScroll.getViewport().setBackground(THEME_PAPER)
        descScroll.setPreferredSize(Dimension(660, 110))
        descScroll.setMinimumSize(Dimension(520, 110))
        descPanel.add(descScroll, dg)
             
        # Keep the description area from collapsing when options grow
        try:
            descPanel.setMinimumSize(Dimension(520, 150))
        except:
            pass
         
        # Row 2: Options panel (scrollable) to prevent it from stealing all vertical space
        from javax.swing import ScrollPaneConstants
        optionsScroll = JScrollPane(optionsPanel)
        optionsScroll.setOpaque(False)
        try: optionsScroll.getViewport().setBackground(THEME_PAPER)
        except: pass
        try: optionsScroll.setBorder(BorderFactory.createEmptyBorder(0,0,0,0))
        except: pass
        optionsScroll.setHorizontalScrollBarPolicy(ScrollPaneConstants.HORIZONTAL_SCROLLBAR_NEVER)
        optionsScroll.setVerticalScrollBarPolicy(ScrollPaneConstants.VERTICAL_SCROLLBAR_AS_NEEDED)
        # Baseline visible height; content beyond this scrolls
        optionsScroll.setPreferredSize(Dimension(660, 260))
        optionsScroll.setMinimumSize(Dimension(520, 200))
        # Place the options scroller in its own row (row 2)
        gbc.gridx = 0
        gbc.gridy = 2
        gbc.weighty = 0.0
        gbc.fill = GridBagConstraints.BOTH
        root.add(optionsScroll, gbc)

        # Row 3: Description box (moved down one row)
        gbc.gridy = 3
        gbc.weighty = 0.10

        root.add(descPanel, gbc)

        return root
        gbc.fill = GridBagConstraints.BOTH
        
     # --------------------------- Interface -----------------------
    def BuildInterfaceTab(self):
        # Interface tab for TimetableAutomation front-page UI settings
        # ASCII-only, modular, memory-backed, thread-safe.

        root = MakePaperPanel()
        root.setLayout(GridBagLayout())

        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        root.add(MakeHeading("TimetableAutomation UI settings"), gbc)
        
        def ApplyFont(e=None):
            try:
                sel = str(cmbFont.getSelectedItem())
                if sel and len(sel.strip()) > 0:
                    TBL.SafeSetMemoryValue("TAS_FONT_FAMILY", sel.strip())
                    # Update theme and refresh UI
                    global THEME_FONT_FAMILY
                    THEME_FONT_FAMILY = sel.strip()
                    self.RefreshFonts()
            except:
                pass
 
        
        # -------------------- (A) Typeface (system fonts) --------------------
        gbc.gridy += 1
        rowFont = Box.createHorizontalBox()
        lblFont = JLabel("Typeface (font family):")
        # Collect available font family names from Java AWT
        try:
            families = list(GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames())
            families.sort(key=lambda s: s.lower())
        except:
            families = [GetDefaultFontFamily()]
        cmbFont = JComboBox(families)
        currentFont = TBL.SafeGetOrCreateMemoryValue("TAS_FONT_FAMILY", GetDefaultFontFamily())
        # Choose current if present; else fall back to default
        try:
            if currentFont in families:
                cmbFont.setSelectedItem(currentFont)
            else:
                cmbFont.setSelectedItem(GetDefaultFontFamily())
        except:
            pass
        def ApplyFont(e=None):
            try:
                sel = str(cmbFont.getSelectedItem())
                if sel and len(sel.strip()) > 0:
                    TBL.SafeSetMemoryValue("TAS_FONT_FAMILY", sel.strip())
                    # Update the theme font and refresh everything
                    global THEME_FONT_FAMILY
                    THEME_FONT_FAMILY = sel.strip()
                    # Re-apply fonts recursively to the entire content pane
                    cp = self.getContentPane()
                    if cp is not None:
                        _ApplyFontRecursive(cp, THEME_FONT_FAMILY)
                        # Ensure tab headers and title bar revalidate/repaint
                        try:
                            cp.revalidate(); cp.repaint()
                        except:
                            pass
            except:
                pass
        cmbFont.addActionListener(lambda e: ApplyFont(e))
        rowFont.add(lblFont); rowFont.add(Box.createHorizontalStrut(8)); rowFont.add(cmbFont)
        root.add(rowFont, gbc)

        # (A2) Font check: show missing font count and provide a button to open the font checker.
        gbc.gridy += 1
        rowFontsCheck = Box.createHorizontalBox()
        btnFontsCheck = JButton("Check for missing fonts...")
        self.LblFontsMissing = JLabel("Missing fonts: (checking...)")
        try:
            self.LblFontsMissing.setOpaque(False)
        except:
            pass
        rowFontsCheck.add(btnFontsCheck)
        rowFontsCheck.add(Box.createHorizontalStrut(12))
        rowFontsCheck.add(self.LblFontsMissing)
        root.add(rowFontsCheck, gbc)

        FONT_CHECK_SCRIPT = "TASFontCheck.py"

        def _LoadFontCheckModule():
            try:
                import imp
                pth = ProfileJythonFilePath(FONT_CHECK_SCRIPT)
                return imp.load_source("TASFontCheck_i", pth)
            except:
                return None

        def _UpdateFontsMissingLabel():
            def _Worker():
                cnt = 0
                try:
                    mod = _LoadFontCheckModule()
                    if mod is not None:
                        if hasattr(mod, "CountMissingFonts"):
                            cnt = int(mod.CountMissingFonts(False))
                        elif hasattr(mod, "GetMissingFontsCount"):
                            cnt = int(mod.GetMissingFontsCount(False))
                        elif hasattr(mod, "RunFontCheck"):
                            cnt = int(mod.RunFontCheck(True, None))
                except:
                    cnt = 0
                def _Apply():
                    try:
                        self.LblFontsMissing.setText("Missing fonts: %d" % int(cnt))
                    except:
                        pass
                try:
                    SwingUtilities.invokeLater(RunnableAdapter(_Apply))
                except:
                    try:
                        _Apply()
                    except:
                        pass
            try:
                java.lang.Thread(RunnableAdapter(_Worker), "TASFontCheckCount").start()
            except:
                try:
                    _Worker()
                except:
                    pass

        def DoFontsCheck(e=None):
            try:
                mod = _LoadFontCheckModule()
                if mod is not None:
                    try:
                        mod.RunFontCheck(False, self)
                    except:
                        try:
                            mod.RunFontCheckDialog(self)
                        except:
                            try:
                                mod.FontsFrame(self)
                            except:
                                pass
                else:
                    pth = ProfileJythonFilePath(FONT_CHECK_SCRIPT)
                    if os.path.isfile(pth):
                        execfile(pth, {"__name__": "__main__"})
                    else:
                        LogWarn("Font check script not found: " + str(pth), alsoDialog=True)
            except Exception as ex:
                LogError("Font check failed: " + str(ex), ex=ex, alsoDialog=True)
            _UpdateFontsMissingLabel()

        btnFontsCheck.addActionListener(lambda e: DoFontsCheck(e))
        _UpdateFontsMissingLabel()

        # -------------------- (B) Background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg = Box.createHorizontalBox()
        lblBg = JLabel("Background colour:")

        # Swatch panel (robust against LAF quirks)
        swatch = JPanel()
        swatch.setOpaque(True)
        swatch.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size: BoxLayout honors min/max for JPanel
        sw, sh = 100, 36
        swatch.setPreferredSize(Dimension(sw, sh))
        swatch.setMinimumSize(Dimension(sw, sh))
        swatch.setMaximumSize(Dimension(sw, sh))

        # Initial colour from memory (fallback to TimetableAutomation default cover colour 240,238,220)
        memRgb = TBL.SafeGetOrCreateMemoryValue("TASCOVERCOLOUR", GetDefaultBackgroundRGB())
        currentColor = _RgbStrToColorOrDefault(memRgb, Color(240,238,220))
        swatch.setBackground(currentColor)

        class SwatchClick(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch.getBackground()
                    # Parent None avoids inner-class 'self' confusion in Jython
                    chosen = JColorChooser.showDialog(None, "Choose background colour", initial)
                    if chosen is not None:
                        swatch.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASCOVERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch.addMouseListener(SwatchClick())

        # Reset button: revert to TimetableAutomation default cover colour
        btnReset = JButton("Reset")
        def DoReset(e=None):
            try:
                defaultColor = _RgbStrToColorOrDefault(GetDefaultBackgroundRGB(), Color(240,238,220))
                swatch.setBackground(defaultColor)
                TBL.SafeSetMemoryValue("TASCOVERCOLOUR", _ColorToRgbStr(defaultColor))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)
        btnReset.addActionListener(lambda e: DoReset(e))

        rowBg.add(lblBg)
        rowBg.add(Box.createHorizontalStrut(8))
        rowBg.add(swatch)
        rowBg.add(Box.createHorizontalStrut(8))
        rowBg.add(btnReset)
        root.add(rowBg, gbc)


        # (B1) Main menu ink colour (cover text/lines)
        gbc.gridy += 1
        rowCoverInk = Box.createHorizontalBox()
        lblCoverInk = JLabel('Main menu ink colour:')
        # Swatch panel
        swatchCoverInk = JPanel()
        swatchCoverInk.setOpaque(True)
        swatchCoverInk.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))
        swi2, shi2 = 100, 36
        swatchCoverInk.setPreferredSize(Dimension(swi2, shi2))
        swatchCoverInk.setMinimumSize(Dimension(swi2, shi2))
        swatchCoverInk.setMaximumSize(Dimension(swi2, shi2))
        # Initial colour from memory (default = black 0,0,0)
        memRgbCoverInk = TBL.SafeGetOrCreateMemoryValue('TASCOVERINKCOLOUR', '0,0,0')
        currentCoverInk = _RgbStrToColorOrDefault(memRgbCoverInk, Color(0,0,0))
        swatchCoverInk.setBackground(currentCoverInk)
        class SwatchCoverInkClick(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatchCoverInk.getBackground()
                    chosen = JColorChooser.showDialog(None, 'Choose main menu ink colour', initial)
                    if chosen is not None:
                        swatchCoverInk.setBackground(chosen)
                        TBL.SafeSetMemoryValue('TASCOVERINKCOLOUR', _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn('Colour chooser failed: ' + str(ex), alsoDialog=True)
        swatchCoverInk.addMouseListener(SwatchCoverInkClick())
        btnResetCoverInk = JButton('Reset')
        def DoResetCoverInk(e=None):
            try:
                defaultCoverInk = Color(0,0,0)
                swatchCoverInk.setBackground(defaultCoverInk)
                TBL.SafeSetMemoryValue('TASCOVERINKCOLOUR', _ColorToRgbStr(defaultCoverInk))
            except Exception as ex:
                LogWarn('Reset failed: ' + str(ex), alsoDialog=True)
        btnResetCoverInk.addActionListener(lambda e: DoResetCoverInk(e))
        rowCoverInk.add(lblCoverInk)
        rowCoverInk.add(Box.createHorizontalStrut(8))
        rowCoverInk.add(swatchCoverInk)
        rowCoverInk.add(Box.createHorizontalStrut(8))
        rowCoverInk.add(btnResetCoverInk)
        root.add(rowCoverInk, gbc)
        
        # -------------------- (B2) Inner panel background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg2 = Box.createHorizontalBox()
        lblBg2 = JLabel("Inner background colour:")

        # Swatch panel (robust against LAF quirks)
        swatch2 = JPanel()
        swatch2.setOpaque(True)
        swatch2.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size: BoxLayout honors min/max for JPanel
        sw2, sh2 = 100, 36
        swatch2.setPreferredSize(Dimension(sw2, sh2))
        swatch2.setMinimumSize(Dimension(sw2, sh2))
        swatch2.setMaximumSize(Dimension(sw2, sh2))

        # Initial colour from memory (fallback to TimetableAutomation inner default 220,235,220)
        memRgb2 = TBL.SafeGetOrCreateMemoryValue("TASINNERCOLOUR", "220,235,220")
        currentColor2 = _RgbStrToColorOrDefault(memRgb2, Color(220,235,220))
        swatch2.setBackground(currentColor2)

        class Swatch2Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch2.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose inner background colour", initial)
                    if chosen is not None:
                        swatch2.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASINNERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch2.addMouseListener(Swatch2Click())

        # Reset button: revert to TimetableAutomation inner default colour
        btnReset2 = JButton("Reset")
        def DoReset2(e=None):
            try:
                defaultColor2 = Color(220,235,220)
                swatch2.setBackground(defaultColor2)
                TBL.SafeSetMemoryValue("TASINNERCOLOUR", _ColorToRgbStr(defaultColor2))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset2.addActionListener(lambda e: DoReset2(e))

        rowBg2.add(lblBg2)
        rowBg2.add(Box.createHorizontalStrut(8))
        rowBg2.add(swatch2)
        rowBg2.add(Box.createHorizontalStrut(8))
        rowBg2.add(btnReset2)
        root.add(rowBg2, gbc)
        
        # (B2.5) Ink colour (text/lines/boxes/button outlines) - JColorChooser
        gbc.gridy += 1
        rowInk = Box.createHorizontalBox()
        lblInk = JLabel("Ink colour (text/lines/boxes/button outlines):")
        # Swatch panel
        swatchInk = JPanel()
        swatchInk.setOpaque(True)
        swatchInk.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))
        # Fixed size like other swatches
        swi, shi = 100, 36
        swatchInk.setPreferredSize(Dimension(swi, shi))
        swatchInk.setMinimumSize(Dimension(swi, shi))
        swatchInk.setMaximumSize(Dimension(swi, shi))
        # Initial colour from memory (default = black 0,0,0)
        memRgbInk = TBL.SafeGetOrCreateMemoryValue("TASINKCOLOUR", "0,0,0")
        currentInk = _RgbStrToColorOrDefault(memRgbInk, Color(0,0,0))
        swatchInk.setBackground(currentInk)

        class SwatchInkClick(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatchInk.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose ink colour", initial)
                    if chosen is not None:
                        swatchInk.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASINKCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatchInk.addMouseListener(SwatchInkClick())

        # Reset button -> default black
        btnResetInk = JButton("Reset")
        def DoResetInk(e=None):
            try:
                defaultInk = Color(0,0,0)
                swatchInk.setBackground(defaultInk)
                TBL.SafeSetMemoryValue("TASINKCOLOUR", _ColorToRgbStr(defaultInk))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)
        btnResetInk.addActionListener(lambda e: DoResetInk(e))

        rowInk.add(lblInk)
        rowInk.add(Box.createHorizontalStrut(8))
        rowInk.add(swatchInk)
        rowInk.add(Box.createHorizontalStrut(8))
        rowInk.add(btnResetInk)
        root.add(rowInk, gbc)

        # -------------------- (B3) Paper background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg3 = Box.createHorizontalBox()
        lblBg3 = JLabel("Setup & WTT paper colour:")

        # Swatch panel
        swatch3 = JPanel()
        swatch3.setOpaque(True)
        swatch3.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw3, sh3 = 100, 36
        swatch3.setPreferredSize(Dimension(sw3, sh3))
        swatch3.setMinimumSize(Dimension(sw3, sh3))
        swatch3.setMaximumSize(Dimension(sw3, sh3))

        # Initial colour from memory (default = WTTDisplay.py paper 249,246,238)
        memRgb3 = TBL.SafeGetOrCreateMemoryValue("TASPAPERCOLOUR", "249,246,238")
        currentColor3 = _RgbStrToColorOrDefault(memRgb3, Color(249,246,238))
        swatch3.setBackground(currentColor3)

        class Swatch3Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch3.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose paper colour", initial)
                    if chosen is not None:
                        swatch3.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASPAPERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch3.addMouseListener(Swatch3Click())

        # Reset button -> default 249,246,238
        btnReset3 = JButton("Reset")
        def DoReset3(e=None):
            try:
                defaultColor3 = Color(249,246,238)
                swatch3.setBackground(defaultColor3)
                TBL.SafeSetMemoryValue("TASPAPERCOLOUR", _ColorToRgbStr(defaultColor3))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset3.addActionListener(lambda e: DoReset3(e))

        rowBg3.add(lblBg3)
        rowBg3.add(Box.createHorizontalStrut(8))
        rowBg3.add(swatch3)
        rowBg3.add(Box.createHorizontalStrut(8))
        rowBg3.add(btnReset3)
        root.add(rowBg3, gbc)
        
        # -------------------- (B4) WTT darker band colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg4 = Box.createHorizontalBox()
        lblBg4 = JLabel("WTT darker band colour:")

        # Swatch panel
        swatch4 = JPanel()
        swatch4.setOpaque(True)
        swatch4.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw4, sh4 = 100, 36
        swatch4.setPreferredSize(Dimension(sw4, sh4))
        swatch4.setMinimumSize(Dimension(sw4, sh4))
        swatch4.setMaximumSize(Dimension(sw4, sh4))

        # Initial colour from memory (default = legacy dark band 245,242,235)
        memRgb4 = TBL.SafeGetOrCreateMemoryValue("TASWTTBANDDARK", "245,242,235")
        currentColor4 = _RgbStrToColorOrDefault(memRgb4, Color(245,242,235))
        swatch4.setBackground(currentColor4)

        class Swatch4Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch4.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose WTT darker band colour", initial)
                    if chosen is not None:
                        swatch4.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASWTTBANDDARK", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch4.addMouseListener(Swatch4Click())

        # Reset button -> default 245,242,235
        btnReset4 = JButton("Reset")
        def DoReset4(e=None):
            try:
                defaultColor4 = Color(245,242,235)
                swatch4.setBackground(defaultColor4)
                TBL.SafeSetMemoryValue("TASWTTBANDDARK", _ColorToRgbStr(defaultColor4))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset4.addActionListener(lambda e: DoReset4(e))

        rowBg4.add(lblBg4)
        rowBg4.add(Box.createHorizontalStrut(8))
        rowBg4.add(swatch4)
        rowBg4.add(Box.createHorizontalStrut(8))
        rowBg4.add(btnReset4)
        root.add(rowBg4, gbc)
        
        # -------------------- ((B5) WTT lighter band colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg5 = Box.createHorizontalBox()
        lblBg5 = JLabel("WTT lighter band colour:")

        # Swatch panel
        swatch5 = JPanel()
        swatch5.setOpaque(True)
        swatch5.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw5, sh5 = 100, 36
        swatch5.setPreferredSize(Dimension(sw5, sh5))
        swatch5.setMinimumSize(Dimension(sw5, sh5))
        swatch5.setMaximumSize(Dimension(sw5, sh5))

        # Initial colour from memory (default = legacy light band 255,253,247)
        memRgb5 = TBL.SafeGetOrCreateMemoryValue("TASWTTBANDLIGHT", "255,253,247")
        currentColor5 = _RgbStrToColorOrDefault(memRgb5, Color(255,253,247))
        swatch5.setBackground(currentColor5)

        class Swatch5Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch5.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose WTT lighter band colour", initial)
                    if chosen is not None:
                        swatch5.setBackground(chosen)
                        TBL.SafeSetMemoryValue("TASWTTBANDLIGHT", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch5.addMouseListener(Swatch5Click())

        # Reset button -> default 255,253,247
        btnReset5 = JButton("Reset")
        def DoReset5(e=None):
            try:
                defaultColor5 = Color(255,253,247)
                swatch5.setBackground(defaultColor5)
                TBL.SafeSetMemoryValue("TASWTTBANDLIGHT", _ColorToRgbStr(defaultColor5))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset5.addActionListener(lambda e: DoReset5(e))

        rowBg5.add(lblBg5)
        rowBg5.add(Box.createHorizontalStrut(8))
        rowBg5.add(swatch5)
        rowBg5.add(Box.createHorizontalStrut(8))
        rowBg5.add(btnReset5)
        root.add(rowBg5, gbc)
        
        
        # -------------------- (C) Cover header text: IMRAILWAYCO / IMREGION / IMSECTION --------------------
        # IMRAILWAYCO
        gbc.gridy += 1
        rowRail = Box.createHorizontalBox()
        lblRail = JLabel("Railway company:")
        txtRail = JTextField(24)
        txtRail.setText(TBL.SafeGetMemoryValue("RAILWAYCO", "BRITISH RAILWAYS"))
        def CommitRail():
            TBL.SafeSetMemoryValue("RAILWAYCO", txtRail.getText().strip())
        txtRail.addActionListener(lambda e: CommitRail())
        class RailLost(FocusAdapter):
            def focusLost(self, e): CommitRail()
        txtRail.addFocusListener(RailLost())
        rowRail.add(lblRail); rowRail.add(Box.createHorizontalStrut(8)); rowRail.add(txtRail)
        root.add(rowRail, gbc)

        # IMREGION
        gbc.gridy += 1
        rowRegion = Box.createHorizontalBox()
        lblRegion = JLabel("Region:")
        txtRegion = JTextField(24)
        txtRegion.setText(TBL.SafeGetOrCreateMemoryValue("REGION", "LONDON MIDLAND REGION"))
        def CommitRegion():
            TBL.SafeSetMemoryValue("REGION", txtRegion.getText().strip())
        txtRegion.addActionListener(lambda e: CommitRegion())
        class RegionLost(FocusAdapter):
            def focusLost(self, e): CommitRegion()
        txtRegion.addFocusListener(RegionLost())
        rowRegion.add(lblRegion); rowRegion.add(Box.createHorizontalStrut(8)); rowRegion.add(txtRegion)
        root.add(rowRegion, gbc)

        # IMSECTION
        gbc.gridy += 1
        rowSection = Box.createHorizontalBox()
        lblSection = JLabel("Section:")
        txtSection = JTextField(24)
        txtSection.setText(TBL.SafeGetOrCreateMemoryValue("SECTION", "SECTION B"))
        def CommitSection():
            TBL.SafeSetMemoryValue("SECTION", txtSection.getText().strip())
        txtSection.addActionListener(lambda e: CommitSection())
        class SectionLost(FocusAdapter):
            def focusLost(self, e): CommitSection()
        txtSection.addFocusListener(SectionLost())
        rowSection.add(lblSection); rowSection.add(Box.createHorizontalStrut(8)); rowSection.add(txtSection)
        root.add(rowSection, gbc)

        # -------------------- (D) Spacer for future interface controls --------------------
        gbc.gridy += 1
        spacer = JLabel("")
        ApplyTheme(spacer)
        root.add(spacer, gbc)

        return root

    def BuildTimetableTab(self):
        """
        Timetable (WTTDisplay) parameter configuration.
        Controls chosen per field:
          - PAGE_MODE        : JComboBox (drop-down of known modes)
          - TIME_24H         : JCheckBox (boolean)
          - TIME_SEPARATOR   : JTextField (single character; limited to length 1)
          - ECS_LABEL        : JTextField (single line)
          - _ECS_DEST_MATCH  : JTextArea (multi-line; one token per line)
          - DIRECTION_SPLIT  : JCheckBox (boolean)
        """
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        root.add(MakeHeading("Working Timetable (WTT) display options"), gbc)

        # (1) PAGE_MODE - drop-down (matches WTTDisplay recognized modes)
        gbc.gridy += 1
        rowMode = Box.createHorizontalBox()
        lblMode = JLabel("Page mode:")
        ApplyTheme(lblMode)
        modes = ["WEEKDAYS_SAT_SUN", "SEVEN_DAYS", "MONSAT_PLUS_SUN", "ALL_WEEK"]
        friendlyModes = {
            "WEEKDAYS_SAT_SUN": "Weekdays, Saturdays, Sundays",
            "SEVEN_DAYS": "Each day of the week individually",
            "MONSAT_PLUS_SUN": "Weekdays (including Saturdays), Sundays",
            "ALL_WEEK": "All week in one view"
            }
        
        # Combo box with friendly names
        cmbMode = JComboBox(list(friendlyModes.values()))
        ApplyTheme(cmbMode)

        # Load current internal code and select corresponding friendly name
        currentModeCode = TBL.SafeGetOrCreateMemoryValue(IMWTT_PageMode, "WEEKDAYS_SAT_SUN")
        currentFriendly = friendlyModes.get(currentModeCode, friendlyModes["WEEKDAYS_SAT_SUN"])
        cmbMode.setSelectedItem(currentFriendly)

        # Commit logic: map friendly name back to internal code
        def ApplyPageMode(e=None):
            try:
                selFriendly = str(cmbMode.getSelectedItem()).strip()
                for code, friendly in friendlyModes.items():
                    if friendly == selFriendly:
                        TBL.SafeSetMemoryValue(IMWTT_PageMode, code)
                        break
            except:
                pass

        cmbMode.addActionListener(lambda e: ApplyPageMode(e))

        rowMode.add(lblMode)
        rowMode.add(Box.createHorizontalStrut(8))
        rowMode.add(cmbMode)
        root.add(rowMode, gbc)

        cmbMode.addActionListener(lambda e: ApplyPageMode(e))
        rowMode.add(lblMode); rowMode.add(Box.createHorizontalStrut(8)); rowMode.add(cmbMode)
        root.add(rowMode, gbc)

        # (2) TIME_24H - checkbox
        gbc.gridy += 1
        row24 = Box.createHorizontalBox()
        chk24 = JCheckBox("Use 24-hour time")
        chk24.setOpaque(False)
        chk24.setSelected(GetMemoryBool(IMWTT_Time24, True))
        def ApplyTime24(e=None):
            SetMemoryBool(IMWTT_Time24, chk24.isSelected())
        chk24.addActionListener(ApplyTime24)
        row24.add(chk24)
        root.add(row24, gbc)

        # (3) TIME_SEPARATOR - single-character text field
        gbc.gridy += 1
        rowSep = Box.createHorizontalBox()
        lblSep = JLabel("Time separator (single character):")
        ApplyTheme(lblSep)
        txtSep = JTextField(2)
        sepVal = TBL.SafeGetOrCreateMemoryValue(IMWTT_TimeSeparator, " ")
        if sepVal is None or len(sepVal.strip()) == 0: sepVal = " "
        txtSep.setText(sepVal[:1])
        def ApplySep():
            s = txtSep.getText().strip()
            if len(s) == 0: s = " "
            TBL.SafeSetMemoryValue(IMWTT_TimeSeparator, s[:1])
        txtSep.addActionListener(lambda e: ApplySep())
        class SepLost(FocusAdapter):
            def focusLost(self, e): ApplySep()
        txtSep.addFocusListener(SepLost())
        rowSep.add(lblSep); rowSep.add(Box.createHorizontalStrut(8)); rowSep.add(txtSep)
        root.add(rowSep, gbc)

        # (4) TP name dot leaders - checkbox
        gbc.gridy += 1
        rowDots = Box.createHorizontalBox()
        chkDots = JCheckBox("Show dot leaders after timing point names")
        chkDots.setOpaque(False)
        chkDots.setSelected(GetMemoryBool(IMWTT_TpNameDotLeaders, False))
        def ApplyTpDots(e=None):
            SetMemoryBool(IMWTT_TpNameDotLeaders, chkDots.isSelected())
        chkDots.addActionListener(ApplyTpDots)
        rowDots.add(chkDots)
        root.add(rowDots, gbc)

        # (4) ECS_LABEL - single-line text field
        gbc.gridy += 1
        rowEcsLabel = Box.createHorizontalBox()
        lblEcs = JLabel("ECS label (text):")
        ApplyTheme(lblEcs)
        txtEcs = JTextField(12)
        txtEcs.setText(TBL.SafeGetOrCreateMemoryValue(IMWTT_EcsLabel, "ECS"))
        def ApplyEcsLabel():
            TBL.SafeSetMemoryValue(IMWTT_EcsLabel, txtEcs.getText().strip())
        txtEcs.addActionListener(lambda e: ApplyEcsLabel())
        class EcsLost(FocusAdapter):
            def focusLost(self, e): ApplyEcsLabel()
        txtEcs.addFocusListener(EcsLost())
        rowEcsLabel.add(lblEcs); rowEcsLabel.add(Box.createHorizontalStrut(8)); rowEcsLabel.add(txtEcs)
        root.add(rowEcsLabel, gbc)
        # (4b) Timing load label (display text and optional alternative timetable column header)
        gbc.gridy += 1
        rowTlLabel = Box.createHorizontalBox()
        lblTlLabel = JLabel("Timing load label (and optional column header):")
        ApplyTheme(lblTlLabel)
        txtTlLabel = JTextField(16)
        txtTlLabel.setText(TBL.SafeGetOrCreateMemoryValue(IMWTT_TimingLoadLabel, "Timing load"))
        def ApplyTlLabel():
            s = (txtTlLabel.getText() or "").strip()
            # Blank means use the default 'Timing load'
            TBL.SafeSetMemoryValue(IMWTT_TimingLoadLabel, s)
        txtTlLabel.addActionListener(lambda e: ApplyTlLabel())
        class TlLabelLost(FocusAdapter):
            def focusLost(self, e): ApplyTlLabel()
        txtTlLabel.addFocusListener(TlLabelLost())
        rowTlLabel.add(lblTlLabel); rowTlLabel.add(Box.createHorizontalStrut(8)); rowTlLabel.add(txtTlLabel)
        root.add(rowTlLabel, gbc)
        gbc.gridy += 1
        root.add(MakeWrappedLabel("If your timetable CSV uses this exact text as a column header, it will be used instead of 'Timing load'.", widthPx=560, lineHeight=1.20, bold=False), gbc)
        # (4c) Reporting number row label (WTT display only; does not affect the timetable CSV)
        gbc.gridy += 1
        rowRepLabel = Box.createHorizontalBox()
        lblRepLabel = JLabel("Reporting number row label:")
        ApplyTheme(lblRepLabel)
        txtRepLabel = JTextField(16)
        txtRepLabel.setText(TBL.SafeGetOrCreateMemoryValue(IMWTT_RepNoLabel, "Rep. no."))
        def ApplyRepLabel():
            s = (txtRepLabel.getText() or "").strip()
            # Blank means use the default 'Rep. no.'
            TBL.SafeSetMemoryValue(IMWTT_RepNoLabel, s)
        txtRepLabel.addActionListener(lambda e: ApplyRepLabel())
        class RepLabelLost(FocusAdapter):
            def focusLost(self, e): ApplyRepLabel()
        txtRepLabel.addFocusListener(RepLabelLost())
        rowRepLabel.add(lblRepLabel); rowRepLabel.add(Box.createHorizontalStrut(8)); rowRepLabel.add(txtRepLabel)
        root.add(rowRepLabel, gbc)

        # (5) _ECS_DEST_MATCH - multi-line tokens (one per line). Stored lowercased, comma-separated.
        gbc.gridy += 1
        rowEcsMatch = Box.createHorizontalBox()
        lblMatch = JLabel("ECS destination synonyms (one per line):")
        ApplyTheme(lblMatch)
        from javax.swing import JTextArea
        txtArea = JTextArea(4, 24)
        ApplyTheme(txtArea)
        txtArea.setLineWrap(True); txtArea.setWrapStyleWord(True)
        rawMatch = TBL.SafeGetOrCreateMemoryValue(IMWTT_EcsMatch, "empty to depot,empty,ety.,ecs")
        preload = [t.strip() for t in rawMatch.split(",") if len(t.strip()) > 0]
        txtArea.setText("\n".join(preload))
        def ApplyEcsMatch():
            lines = txtArea.getText().split("\n")
            tokens = []
            for ln in lines:
                t = (ln or "").strip().lower()
                if len(t) > 0: tokens.append(t)
            TBL.SafeSetMemoryValue(IMWTT_EcsMatch, ",".join(tokens))
        class MatchLost(FocusAdapter):
            def focusLost(self, e): ApplyEcsMatch()
        txtArea.addFocusListener(MatchLost())
        sp = JScrollPane(txtArea)
        rowEcsMatch.add(lblMatch); rowEcsMatch.add(Box.createHorizontalStrut(8)); rowEcsMatch.add(sp)
        root.add(rowEcsMatch, gbc)

        # (6) DIRECTION_SPLIT - checkbox
        gbc.gridy += 1
        rowDir = Box.createHorizontalBox()
        chkDir = JCheckBox("Split pages by direction (e.g., DOWN / UP)")
        chkDir.setOpaque(False)
        chkDir.setSelected(GetMemoryBool(IMWTT_DirectionSplit, True))
        def ApplyDir(e=None):
            SetMemoryBool(IMWTT_DirectionSplit, chkDir.isSelected())
        chkDir.addActionListener(ApplyDir)
        rowDir.add(chkDir)
        root.add(rowDir, gbc)
                
        # (7) Origin/Destination header orientation - checkbox
        gbc.gridy += 1
        rowOdHdr = Box.createHorizontalBox()
        chkOdVertical = JCheckBox("Vertical headers")
        chkOdVertical.setOpaque(False)
        # Default is horizontal (false); reflect current memory setting
        chkOdVertical.setSelected(GetMemoryBool(IMWTT_OdHeaderVertical, False))
        def ApplyOdVertical(e=None):
            SetMemoryBool(IMWTT_OdHeaderVertical, chkOdVertical.isSelected())
        chkOdVertical.addActionListener(ApplyOdVertical)
        rowOdHdr.add(chkOdVertical)
        root.add(rowOdHdr, gbc)

        # Final spacer
        gbc.gridy += 1
        spacer = JLabel("")
        ApplyTheme(spacer)
        root.add(spacer, gbc)

        # Apply chosen font to the entire tab
        try:
            _ApplyFontRecursive(root, THEME_FONT_FAMILY)
        except:
            pass
        return root
    
    # --- Workings tab: list extracted workings, check for script, edit/save/revert ---   
    class WorkingItem(object):
        # Lightweight record: RN + Direction + RowIndex + ScriptPath + HasScript + ValidScript
        def __init__(self, rn, direction, rowIndex, scriptPath, hasScript, validScript, timeText=""):
            self.RN = rn
            self.Direction = direction
            self.RowIndex = rowIndex
            self.ScriptPath = scriptPath
            self.HasScript = hasScript
            self.ValidScript = validScript
            self.IsExtra = False
            self.Time = timeText
        def Label(self):
            # Example: "2G56 (Trigger) - row 42 [12:34]"
            timePart = (" [" + self.Time + "]") if self.Time else ""
            return "%s (%s) - row %d%s" % (self.RN, self.Direction, int(self.RowIndex), timePart)

    def BuildWorkingsTab(self):
        # Workings tab UI is provided by a shared module so TASSetup and TASWiz use identical logic.
        mod = None
        try:
            import imp
            pth = ProfileJythonFilePath("TASWorkingsUi.py")
            if pth and os.path.isfile(pth):
                mod = imp.load_source("TASWorkingsUi_i", pth)
        except Exception as ex:
            LogWarn("Could not load shared Workings UI: " + str(ex), alsoDialog=False)
            mod = None
        if mod is None or not hasattr(mod, "BuildWorkingsPanel"):
            p = MakePaperPanel()
            try:
                p.setLayout(GridBagLayout())
            except:
                pass
            gbc = GridBagConstraints(); gbc.insets = Insets(10,10,10,10); gbc.gridx=0; gbc.gridy=0
            try:
                p.add(MakeHeading("Workings"), gbc)
            except:
                pass
            gbc.gridy = 1
            try:
                p.add(MakeWrappedLabel("Shared Workings UI module not found: TASWorkingsUi.py", widthPx=560, lineHeight=1.25, bold=False), gbc)
            except:
                pass
            return p
        def _GetTT():
            return _TimetableFilePath()
        try:
            panel, controller = mod.BuildWorkingsPanel(self, _GetTT, ProfileJythonFilePath, ApplyTheme, MakePaperPanel, MakeHeading, MakeWrappedLabel, THEME_PAPER, THEME_FONT_FAMILY, THEME_TEXT_COLOR, LIST_SEL_BG, LIST_SEL_FG, LogInfo, LogWarn, LogError)
            self.WorkingsUiController = controller
            return panel
        except Exception as ex:
            LogError("Failed to build Workings UI: " + str(ex), ex=ex, alsoDialog=True)
            return MakePaperPanel()
    def BuildTimingPointsTab(self):
        # "Timing points" tab - dual list: left = virtual TPs from timetable,
        # right = physical TPs (blocks assigned via TimingRegister).
        import TimingRegister as TR
        from jmri import InstanceManager
        from jmri import BlockManager

        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # --- Helpers ---
        def _CurrentTimetablePath():
            try:
                name = TBL.SafeGetOrCreateMemoryValue(IMCurrentTimetable, "").strip()
                if name == "":
                    return None
                prof = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
                return os.path.join(prof, "timetable", name + ".csv")
            except Exception:
                return None

        def _ExtractVirtualTPNamesFromTimetable():
            path = _CurrentTimetablePath()
            out = set()
            if not (path and os.path.exists(path)):
                return []
            try:
                with open(path, "r") as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    headers = reader.fieldnames or []   
                    # Match "TPArr <name>" or "TPDep <name>" (case-insensitive), tolerate extra spaces
                    pat = re.compile(r'^TP(\d*)(Arr|Dep)\s+(.+)$', re.IGNORECASE)
                    for h in headers:
                        if not h:
                            continue
                        m = pat.match(str(h).strip())
                        if m:
                            nm = (m.group(3) or "").strip()
                            if nm != "":
                                out.add(nm)
            except Exception as ex:
                LogWarn("Could not read timetable header for timing points: " + str(ex), alsoDialog=False)
            return sorted(list(out), key=lambda s: s.lower())

        def _ListPhysicalTPs():
            names = []
            try:
                for tp in TR.listTimingPoints() or []:
                    try:
                        blocks = TR.getBlocks(tp)
                        if isinstance(blocks, list) and len(blocks) > 0:
                            names.append(tp)
                    except Exception:
                        pass
            except Exception as ex:
                LogWarn("Could not list physical timing points: " + str(ex), alsoDialog=False)
            return sorted(names, key=lambda s: s.lower())

        def _AllBlocks():
            items = []
            try:
                bm = InstanceManager.getDefault(BlockManager)
                if bm is None:
                    return items
                try:
                    beans = bm.getNamedBeanSet()
                    seq = beans.toArray() if hasattr(beans, "toArray") else list(beans)
                except Exception:
                    seq = []
                for b in seq:
                    try:
                        sys = str(b.getSystemName())
                    except Exception:
                        sys = None
                    if not sys:
                        continue
                    try:
                        usr = b.getUserName()
                        lbl = (str(usr).strip() + " (" + sys + ")") if usr else sys
                    except Exception:
                        lbl = sys
                    items.append((sys, lbl))
            except Exception as ex:
                LogWarn("Could not enumerate blocks: " + str(ex), alsoDialog=False)
            items.sort(key=lambda t: t[1].lower())
            return items

        # --- List models & views ---
        virtModel = DefaultListModel()
        physModel = DefaultListModel()     
        
        def RefreshLists():
            # Refresh both list models, ensuring the virtual list excludes any TP
            # that is present in the physical list (case-insensitive).
            try:
                vnames = _ExtractVirtualTPNamesFromTimetable()
            except Exception:
                vnames = []
            try:
                pnames = _ListPhysicalTPs()
            except Exception:
                pnames = []

            # Case-insensitive physical set for filtering
            psetLower = set([str(p).strip().lower() for p in (pnames or [])])

            # Left list (virtual): show only names not already physical
            try:
                virtModel.removeAllElements()
                for nm in vnames:
                    if str(nm).strip().lower() not in psetLower:
                        virtModel.addElement(nm)
            except Exception:
                pass

            # Right list (physical): unchanged
            try:
                physModel.removeAllElements()
                for nm in pnames:
                    physModel.addElement(nm)
            except Exception:
                pass

            # Build a case-insensitive set of physical names for filtering
            psetLower = set([str(p).strip().lower() for p in (pnames or [])])

            # --- Left list (virtual): vnames minus pnames (case-insensitive)


        virtList = JList(virtModel)
        virtList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        virtScroll = JScrollPane(virtList)
        virtScroll.setPreferredSize(Dimension(300, 240))

        physList = JList(physModel)
        physList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        physScroll = JScrollPane(physList)
        physScroll.setPreferredSize(Dimension(300, 240))
             
        # Two separate header labels for proper column alignment
        lblLeft = JLabel("Virtual timing points (from current timetable)")
        lblRight = JLabel("Physical timing points (blocks assigned in register)")
        ApplyTheme(lblLeft)
        ApplyTheme(lblRight)

        # Left header in column 0, row 0
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.WEST
        root.add(lblLeft, gbc)

        # Right header in column 1, row 0
        gbc.gridx = 1
        gbc.gridy = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.WEST
        root.add(lblRight, gbc)
       
        # Reset constraints for the scroll panes (row 1)
        gbc.gridy += 1
        gbc.gridx = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.CENTER  # ensure list panes aren't stuck to WEST from header
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        root.add(virtScroll, gbc)

        # Right list in column 1
        gbc.gridx = 1
        root.add(physScroll, gbc)


        # --- Block picker dialog ---
        def ShowBlockPicker(tpName, preselectedSysNames):
            dlg = JDialog(self, "Assign blocks to '" + str(tpName) + "'", True)
            dlg.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)  # make sure closing X disposes the dialog
            dlg.setSize(480, 420)
            dlg.setLayout(BorderLayout())

            items = _AllBlocks()  # [(sysName, label), ...]
            blocksModel = DefaultListModel()
            for _, label in items:
                blocksModel.addElement(label)

            lstBlocks = JList(blocksModel)
            lstBlocks.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
            try:
                idxs = []
                preSet = set([str(x).strip() for x in (preselectedSysNames or [])])
                for i, (sys, _) in enumerate(items):
                    if sys in preSet:
                        idxs.append(i)
                if idxs:
                    lstBlocks.setSelectedIndices([j for j in idxs])
            except Exception:
                pass

            dlg.add(JScrollPane(lstBlocks), BorderLayout.CENTER)

            btnPanel = Box.createHorizontalBox()
            btnAssign = JButton("Assign")
            btnCancel = JButton("Cancel")
            btnPanel.add(btnAssign)
            btnPanel.add(Box.createHorizontalStrut(12))
            btnPanel.add(btnCancel)
            dlg.add(btnPanel, BorderLayout.SOUTH)
            ApplyTheme(lstBlocks); ApplyTheme(btnPanel); ApplyTheme(btnAssign); ApplyTheme(btnCancel)

            def DoAssign(e=None):
                try:
                    selIdx = lstBlocks.getSelectedIndices() or []
                    chosen = []
                    for k in selIdx:
                        try:
                            sysName = items[int(k)][0]
                            chosen.append(sysName)
                        except Exception:
                            pass
                    TR.assignBlocks(tpName, chosen)
                    TR.save()
                    RefreshLists()
                    dlg.dispose()
                except Exception as ex:
                    LogError("Failed to assign blocks: " + str(ex), ex=ex, alsoDialog=True)

            btnAssign.addActionListener(lambda e: DoAssign())
            btnCancel.addActionListener(lambda e: dlg.dispose())
            dlg.setLocationRelativeTo(self)
            dlg.setVisible(True)

        # --- Buttons row ---
        gbc.gridx = 0; gbc.gridy += 1; gbc.weightx = 1.0; gbc.weighty = 0.0; gbc.fill = GridBagConstraints.NONE
        leftBtns = Box.createHorizontalBox()
        btnAssignBlocks = JButton("Assign blocks")
        leftBtns.add(btnAssignBlocks)
        root.add(leftBtns, gbc)

        gbc.gridx = 1
        rightBtns = Box.createHorizontalBox()
        btnEditBlocks = JButton("Edit blocks")
        btnDeleteBlocks = JButton("Delete all blocks")
        rightBtns.add(btnEditBlocks)
        rightBtns.add(Box.createHorizontalStrut(12))
        rightBtns.add(btnDeleteBlocks)
        root.add(rightBtns, gbc)
        ApplyTheme(btnAssignBlocks); ApplyTheme(btnEditBlocks); ApplyTheme(btnDeleteBlocks)

        def DoAssignBlocks(e=None):
            tp = virtList.getSelectedValue()
            if tp is None:
                LogWarn("Select a virtual timing point first.", alsoDialog=True)
                return
            pre = TR.getBlocks(str(tp)) or []
            ShowBlockPicker(str(tp), pre)

        def DoEditBlocks(e=None):
            tp = physList.getSelectedValue()
            if tp is None:
                LogWarn("Select a physical timing point first.", alsoDialog=True)
                return
            pre = TR.getBlocks(str(tp)) or []
            ShowBlockPicker(str(tp), pre)

        def DoDeleteBlocks(e=None):
            tp = physList.getSelectedValue()
            if tp is None:
                LogWarn("Select a physical timing point first.", alsoDialog=True)
                return
            msg = ("This will delete all block assignments stored for timing point '{}'.\n"
                   "The timing point itself is kept; only its physical bindings are removed.\n"
                   "This action cannot be undone.\n\nProceed?").format(str(tp))
            choice = JOptionPane.showConfirmDialog(
                self, msg, "Confirm delete (blocks)", JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
            )
            if choice != JOptionPane.OK_OPTION:
                return
            try:
                TR.clearBlocks(str(tp))
                TR.save()
                RefreshLists()
                LogInfo("[TAS] Cleared blocks for timing point '" + str(tp) + "'.", alsoDialog=True, title="Done")
            except Exception as ex:
                LogError("Failed to clear blocks: " + str(ex), ex=ex, alsoDialog=True)

        btnAssignBlocks.addActionListener(lambda e: DoAssignBlocks())
        btnEditBlocks.addActionListener(lambda e: DoEditBlocks())
        btnDeleteBlocks.addActionListener(lambda e: DoDeleteBlocks())

        RefreshLists()
        return root
    
    def BuildOrientationTab(self):
        import OrientationRegister as OR       
        from jmri import InstanceManager
        from jmri.jmrit.roster import Roster  
        
        # Color renderer needs access to the two direction registers used by the hardware UI
        try:
            import NormalDirectionRegister as NDR
        except Exception:
            NDR = None
        try:
            import LastReportedDirection as LRD
        except Exception:
            LRD = None
      
        panel = MakePaperPanel()
        panel.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(8, 8, 8, 8)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        panel.add(
            MakeWrappedLabel(
                "All of the Train Info files that define what happens when we run a working "
                "assume that a train is in a particular orientation. "
                "If a train is in the opposite orientation on the layout, it will go the wrong way. "
                "To correct that, here are two lists of all the roster entries on the layout: those that are "
                "facing in the normal orientation and those that are facing in the inverse orientation. "
                "Trains in the normal list will run in the correct direction if they are in normal orientation, "
                "and trains on the inverted list will run in the correct direction if they are in inverse orientation. "
                "Either assign trains to the normal and inverted lists manually using the controls below, or, if "
                "you have the appropraite hardware, configure hardware orientation sensing below.",
                widthPx=560,    # tweak to taste; matches your tab width
                lineHeight=1.25 # tighter than default; adjust 1.2-1.3 as desired
            ),
            gbc
)
        # Hardware orientation sensing controls
        # Row 1: checkbox
        rowSenseTop = Box.createHorizontalBox()
        self.ChkDirSense = JCheckBox("Enable hardware orientation sensing*")
        self.ChkDirSense.setOpaque(False)

        initialEnabled = _IsScriptEnabled("LastReportedDirection.py")
        self.ChkDirSense.setSelected(initialEnabled)

        def OnDirSense(e=None):
            want = self.ChkDirSense.isSelected()
            ok = _EnsureScriptEnabled("LastReportedDirection.py", want)
            actual = _IsScriptEnabled("LastReportedDirection.py")
            self.ChkDirSense.setSelected(actual)
            try:
                self.BtnDirSenseConfig.setEnabled(actual)
            except Exception:
                pass
            self.CurrentDirectionSensing = actual
            if not ok:
                LogWarn("Could not change Start-Up for LastReportedDirection.py", alsoDialog=True)

        self.ChkDirSense.addActionListener(OnDirSense)
        rowSenseTop.add(self.ChkDirSense)

        # Row 2: note
        self.LblDirSenseNote = MakeWrappedLabel(
            "*Requires compatible hardware. See under Help for details.",
            widthPx=560, lineHeight=1.20, bold=False
        )

        # Row 3: button
        rowSenseCfg = Box.createHorizontalBox()
        self.BtnDirSenseConfig = JButton("Configure hardware orientation sensing...")
        self.BtnDirSenseConfig.setEnabled(initialEnabled)

        def DoDirSenseConfig(e=None):
            try:
                path = ProfileJythonFilePath("HardwareDirectionConfig.py")
                if os.path.isfile(path):
                    RunSetupWizard(onClosed=(lambda: self.OnWizardClosedRefreshSetupUi()))
                else:
                    JOptionPane.showMessageDialog(
                        panel,
                        "No configuration script found.\nCreate: profile:jython/HardwareDirectionConfig.py",
                        "Configuration",
                        JOptionPane.INFORMATION_MESSAGE
                    )
            except Exception as ex:
                LogError("Hardware orientation sensing configuration failed: " + str(ex),
                         ex=ex, alsoDialog=True)

        self.BtnDirSenseConfig.addActionListener(lambda e: DoDirSenseConfig())
        rowSenseCfg.add(self.BtnDirSenseConfig)

        # Stack the three rows tightly in a single subpanel
        dirSensePanel = JPanel()
        dirSensePanel.setOpaque(False)
        dirSensePanel.setLayout(GridBagLayout())

        dg = GridBagConstraints()
        dg.insets = Insets(0, 0, 0, 0)
        dg.gridx = 0
        dg.gridy = 0
        dg.fill = GridBagConstraints.HORIZONTAL
        dg.weightx = 1.0
        dg.weighty = 0.0
        dirSensePanel.add(rowSenseTop, dg)

        dg.gridy = 1
        dirSensePanel.add(self.LblDirSenseNote, dg)

        dg.gridy = 2
        dirSensePanel.add(rowSenseCfg, dg)

        # Add the subpanel as one compact block
        gbc.gridy += 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weighty = 0.0
        panel.add(dirSensePanel, gbc)

        # Error label for missing orientation-sensing script
        gbc.gridy += 1
        self.LblDirSenseError = JLabel("")
        ApplyTheme(self.LblDirSenseError)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weighty = 0.0
        panel.add(self.LblDirSenseError, gbc)

        # If missing, disable controls and show an error
        if not ScriptExists("LastReportedDirection.py"):
            try:
                self.ChkDirSense.setSelected(False)
                self.ChkDirSense.setEnabled(False)
                self.BtnDirSenseConfig.setEnabled(False)
                self.LblDirSenseError.setText("Missing script: LastReportedDirection.py")
            except Exception:
                pass


        # Two lists: left = normal direction (not inverted), right = inverted direction (in register)
        gbc.gridy += 1
        leftModel = DefaultListModel()
        rightModel = DefaultListModel()

        # Load roster and split into left/right
        try:
            import jmri.jmrit.roster as JR
            roster = JR.Roster.getDefault()
            allIDs = []
            if roster is not None:
                entries = roster.matchingList(None, None, None, None, None, None, None)
                for re in entries.toArray():
                    allIDs.append(re.getId())
            invertedSet = set(OR.GetOrientationRegisterCopy())
            for rid in allIDs:
                if rid in invertedSet:
                    rightModel.addElement(rid)
                else:
                    leftModel.addElement(rid)
        except Exception as ex:
            LogWarn("Roster unavailable or failed: " + str(ex), alsoDialog=True)

        # Lists
        leftList = JList(leftModel)
        rightList = JList(rightModel)
        leftList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        rightList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)      
        
        # Apply same text colors as HardwareDirectionConfig:
        #   - cyan: in LastReportedDirection only
        #   - dark blue: in both NormalDirectionRegister and LastReportedDirection
        #   - dark purple: in NormalDirectionRegister only      
        from javax.swing import DefaultListCellRenderer

        class OrientationColorRenderer(DefaultListCellRenderer):
            def __init__(self):
                DefaultListCellRenderer.__init__(self)

                # Helper: normalize roster IDs
                def _Norm(s):
                    try:
                        return str(s).strip().lower()
                    except:
                        return ""

                # Snapshot normal register keys (case-insensitive)
                try:
                    self.normalKeys = set([_Norm(k) for k in (NDR.GetCopy().keys() if NDR else [])])
                except Exception:
                    self.normalKeys = set()

                # Build roster address index: lower(rid) -> addr, addr -> [display RIDs]
                self.ridLowerToAddr = {}
                self.addrToRidList = {}
                try:
                    roster = jmri.jmrit.roster.Roster.getDefault()
                    if roster is not None:
                        entries = roster.matchingList(None, None, None, None, None, None, None)
                        seq = entries.toArray() if hasattr(entries, "toArray") else list(entries)
                        for re in seq:
                            try:
                                rid = str(re.getId())
                                addr = str(re.getDccAddress()) if hasattr(re, "getDccAddress") else ""
                                if addr is None or addr.strip() == "":
                                    addr = ""
                                lrid = _Norm(rid)
                                if lrid != "":
                                    self.ridLowerToAddr[lrid] = addr
                                    lst = self.addrToRidList.get(addr, [])
                                    lst.append(rid)
                                    self.addrToRidList[addr] = lst
                            except Exception:
                                pass
                except Exception:
                    pass

                # Expand last-reported set to include ALL roster IDs that share the same DCC address
                self.lastKeys = set()
                try:
                    lm = getattr(LRD, "lastReportedDirection", {})
                    for k in (lm.keys() if lm else []):
                        lk = _Norm(k)
                        if lk == "":
                            continue
                        addr = self.ridLowerToAddr.get(lk, None)
                        if addr is None:
                            # Address unknown: include the original key only
                            self.lastKeys.add(lk)
                            continue
                        siblings = self.addrToRidList.get(addr, []) or []
                        for rid in siblings:
                            self.lastKeys.add(_Norm(rid))
                except Exception:
                    # Fallback to raw keys if anything goes wrong
                    try:
                        lm = getattr(LRD, "lastReportedDirection", {})
                        for k in (lm.keys() if lm else []):
                            self.lastKeys.add(_Norm(k))
                    except Exception:
                        pass

                # Palette (match HardwareDirectionConfig)
                self.cyan = Color(0, 200, 200)
                self.darkBlue = Color(0, 51, 102)
                self.darkPurple = Color(76, 0, 153)

            def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
                comp = DefaultListCellRenderer.getListCellRendererComponent(
                    self, lst, value, index, isSelected, cellHasFocus
                )
                try:
                    rid = str(value)
                    lower = rid.strip().lower()
                    inNormal = lower in self.normalKeys
                    inLast = lower in self.lastKeys

                    if inLast and not inNormal:
                        fg = self.cyan          # last-only -> cyan
                    elif inNormal and inLast:
                        fg = self.darkBlue      # both -> dark blue
                    elif inNormal and not inLast:
                        fg = self.darkPurple    # normal-only -> dark purple
                    else:
                        fg = comp.getForeground()

                    comp.setForeground(fg)

                    # Keep TASSetup theme: paper selection/background and font
                    try:
                        comp.setBackground(LIST_SEL_BG if isSelected else THEME_PAPER)
                        comp.setOpaque(True)
                    except Exception:
                        pass
                    try:
                        comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
                    except Exception:
                        pass
                except Exception:
                    pass
                return comp

        # Use the colored renderer for both lists
        try:
            _renderer = OrientationColorRenderer()
            leftList.setCellRenderer(_renderer)
            rightList.setCellRenderer(_renderer)
        except Exception:
            pass


        # Move buttons (ASCII-only)
        btnMoveRight = JButton(">>")
        btnMoveLeft  = JButton("<<")
              
        # Attach listeners for buttons
        btnMoveRight.addActionListener(lambda e: DoMoveRight())
        btnMoveLeft.addActionListener(lambda e: DoMoveLeft())
        
        
        # Refresh button: rebuild both lists from current registers
        btnRefresh = JButton("Refresh")
        def DoRefresh(e=None):
            try:
                # Reload roster and orientation register
                import OrientationRegister as ORlocal
                from jmri.jmrit.roster import Roster
                roster = Roster.getDefault()
                allIDs = []
                if roster is not None:
                    entries = roster.matchingList(None, None, None, None, None, None, None)
                    seq = entries.toArray() if hasattr(entries, "toArray") else list(entries)
                    for re in seq:
                        try:
                            allIDs.append(str(re.getId()))
                        except Exception:
                            pass

                invertedSet = set(ORlocal.GetOrientationRegisterCopy() if hasattr(ORlocal, "GetOrientationRegisterCopy") else [])

                # Clear models
                leftModel.removeAllElements()
                rightModel.removeAllElements()

                # Repopulate
                for rid in allIDs:
                    if rid in invertedSet:
                        rightModel.addElement(rid)
                    else:
                        leftModel.addElement(rid)

                # Reapply color renderer
                try:
                    _renderer2 = OrientationColorRenderer()
                    leftList.setCellRenderer(_renderer2)
                    rightList.setCellRenderer(_renderer2)
                    leftList.repaint()
                    rightList.repaint()
                except Exception:
                    pass

                LogInfo("[TASSetup] Orientation lists refreshed.")
            except Exception as ex:
                LogError("Failed to refresh orientation lists: " + str(ex), ex=ex, alsoDialog=True)

        btnRefresh.addActionListener(lambda e: DoRefresh())


        def DoMoveRight(e=None):
            idx = leftList.getSelectedIndex()
            if idx < 0: return
            rid = leftModel.getElementAt(idx)
            try:
                leftModel.remove(idx)
                rightModel.addElement(rid)
                OR.AddTrain(rid)
                OR.save()
                LogInfo("[TASSetup] Orientation: added " + str(rid))
            except Exception as ex:
                LogError("Failed to add to orientation register: " + str(ex), ex=ex, alsoDialog=True)

        def DoMoveLeft(e=None):
            idx = rightList.getSelectedIndex()
            if idx < 0: return
            rid = rightModel.getElementAt(idx)
            try:
                rightModel.remove(idx)
                leftModel.addElement(rid)
                OR.RemoveTrain(rid)
                OR.save()
                LogInfo("[TASSetup] Orientation: removed " + str(rid))
            except Exception as ex:
                LogError("Failed to remove from orientation register: " + str(ex), ex=ex, alsoDialog=True)

        # Layout with headings and equal-width columns (matching Display configuration pattern)      

        # Header row: align "Normal" (left) and "Inverted" (right) over the two lists
        gbc.gridy += 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.weighty = 0.0

        headerPanel = JPanel(GridLayout(1, 3, 12, 0))  # match the listsPanel grid (3 columns)
        lblNormal = JLabel("Normal")
        lblInverted = JLabel("Inverted")
        ApplyTheme(lblNormal)
        ApplyTheme(lblInverted)

        # Left column: "Normal"
        headerPanel.add(lblNormal)
        # Middle column: keep empty to align over the move buttons
        headerPanel.add(Box.createVerticalBox())
        # Right column: "Inverted"
        headerPanel.add(lblInverted)

        panel.add(headerPanel, gbc)     
        
        # Row: lists with equal widths and buttons in the middle
        gbc.gridy += 1
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH

        # Create a sub-panel with GridLayout to enforce equal column widths
        listsPanel = JPanel(GridLayout(1, 3, 12, 0))  # 3 columns, 12px horizontal gap

        # Left list
        leftScroll = JScrollPane(leftList)
        leftScroll.getViewport().setBackground(THEME_PAPER)
        listsPanel.add(leftScroll)

        # Buttons in the middle
        btnPanel = Box.createVerticalBox()
        btnPanel.add(btnMoveRight)
        btnPanel.add(Box.createVerticalStrut(6))
        btnPanel.add(btnMoveLeft)
        listsPanel.add(btnPanel)       
        btnPanel.add(Box.createVerticalStrut(12))  # extra space before refresh
        btnPanel.add(btnRefresh)

        # Right list
        rightScroll = JScrollPane(rightList)
        rightScroll.getViewport().setBackground(THEME_PAPER)
        listsPanel.add(rightScroll)

        # Add the sub-panel to the main panel
        panel.add(listsPanel, gbc)



        return panel


    # --------------------------- Day/night cycle -----------------------
    def BuildDayNightTab(self):
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10,10,10,10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0

        # (1) Day/Night enable - authoritative from Start-Up; clicking mutates Start-Up
        gbc.gridy = 0
        row1 = Box.createHorizontalBox()
        chkDN = JCheckBox("Enable day/night cycle (requires restart)")
        chkDN.setOpaque(False)
        chkDN.setSelected(IsDayNightEnabled())
        self.ChkDayNight = chkDN
        def OnDN(e=None):
            try:
                if getattr(self, "SuppressWizardSync", False):
                    return
            except:
                pass
            want = chkDN.isSelected()
            ok = _EnsureScriptEnabled("DayNight.py", want)
            chkDN.setSelected(IsDayNightEnabled())
            self.CurrentDayNight = IsDayNightEnabled()
            if not ok:
                LogWarn("Could not change Start-Up for DayNight.py", alsoDialog=True)
        chkDN.addActionListener(OnDN)
        row1.add(chkDN)
        root.add(row1, gbc)
        
        gbc.gridy += 1
        self.LblDayNightError = JLabel("")
        ApplyTheme(self.LblDayNightError)
        root.add(self.LblDayNightError, gbc)

        if not ScriptExists("DayNight.py"):
            chkDN.setSelected(False)
            chkDN.setEnabled(False)
            self.LblDayNightError.setText("Missing script: DayNight.py")

        # (2) Warm/cool addresses (used by DayNight.py)
        gbc.gridy = 1
        root.add(MakeHeading("Lighting DCC addresses"), gbc)
        gbc.gridy = 2
        addrRow = Box.createHorizontalBox()
        lblWarm = JLabel("Warm (low colour temperature):")
        txtWarm = JTextField(8); txtWarm.setText(TBL.SafeGetOrCreateMemoryValue(IMLowThrottleAddr, "990"))
        lblCool = JLabel(" Cool (high colour temperature):")
        txtCool = JTextField(8); txtCool.setText(TBL.SafeGetOrCreateMemoryValue(IMHighThrottleAddr, "991"))
        self.TxtWarmAddr = txtWarm
        self.TxtCoolAddr = txtCool
        def CommitAddrWarm():
            s = txtWarm.getText().strip()
            try: n=int(float(s)); TBL.SafeSetMemoryValue(IMLowThrottleAddr, str(n))
            except: LogWarn("Warm address invalid: " + s, alsoDialog=True)
        def CommitAddrCool():
            s = txtCool.getText().strip()
            try: n=int(float(s)); TBL.SafeSetMemoryValue(IMHighThrottleAddr, str(n))
            except: LogWarn("Cool address invalid: " + s, alsoDialog=True)
        class WarmLost(FocusAdapter):
            def focusLost(self, e): CommitAddrWarm()
        class CoolLost(FocusAdapter):
            def focusLost(self, e): CommitAddrCool()
        txtWarm.addActionListener(lambda e: CommitAddrWarm()); txtWarm.addFocusListener(WarmLost())
        txtCool.addActionListener(lambda e: CommitAddrCool()); txtCool.addFocusListener(CoolLost())
        addrRow.add(lblWarm); addrRow.add(Box.createHorizontalStrut(6)); addrRow.add(txtWarm)
        addrRow.add(lblCool); addrRow.add(Box.createHorizontalStrut(6)); addrRow.add(txtCool)
        root.add(addrRow, gbc)

        # (3) Weather generator enable - from Start-Up; clicking mutates Start-Up
        gbc.gridy = 3
        row3 = Box.createHorizontalBox()
        chkWX = JCheckBox("Use weather generator (requires restart)")
        chkWX.setOpaque(False)
        chkWX.setSelected(IsWeatherEnabled())
        self.ChkWeatherGenerator = chkWX
        def OnWX(e=None):
            try:
                if getattr(self, "SuppressWizardSync", False):
                    return
            except:
                pass
            want = chkWX.isSelected()
            ok = _EnsureScriptEnabled("WeatherGenerator.py", want)
            chkWX.setSelected(IsWeatherEnabled())
            self.CurrentWeather = IsWeatherEnabled()
            if not ok:
                LogWarn("Could not change Start-Up for WeatherGenerator.py", alsoDialog=True)
            RefreshWXEnableState()
        chkWX.addActionListener(OnWX)
        row3.add(chkWX)
        root.add(row3, gbc)
        
        gbc.gridy += 1
        self.LblWeatherError = JLabel("")
        ApplyTheme(self.LblWeatherError)
        root.add(self.LblWeatherError, gbc)

        if not ScriptExists("WeatherGenerator.py"):
            chkWX.setSelected(False)
            chkWX.setEnabled(False)
            self.LblWeatherError.setText("Missing script: WeatherGenerator.py")

        # (4) Climate preset
        gbc.gridy = 4
        row4 = Box.createHorizontalBox()
        lblClimate = JLabel("Climate preset:")
        climateNames = self.LoadClimateNames()
        cmbClimate = JComboBox(climateNames)
        self.CmbClimate = cmbClimate
        currentClimate = TBL.SafeGetOrCreateMemoryValue(IMWxClimate, "SouthWales_EarlySep")
        cmbClimate.setSelectedItem(currentClimate if currentClimate in climateNames else "SouthWales_EarlySep")
        def ApplyClimate():
            val = str(cmbClimate.getSelectedItem())
            TBL.SafeSetMemoryValue(IMWxClimate, val)
        cmbClimate.addActionListener(lambda e: ApplyClimate())
        row4.add(lblClimate); row4.add(Box.createHorizontalStrut(8)); row4.add(cmbClimate)
        root.add(row4, gbc)
     
        # (4b) Daylight hours preset
        gbc.gridy += 1
        row4b = Box.createHorizontalBox()
        lblDaylight = JLabel("Daylight hours preset:")
        daylightNames = self.LoadDayNightNames()
        cmbDaylight = JComboBox(daylightNames)
        currentDaylight = TBL.SafeGetOrCreateMemoryValue(IMDayNightPreset, "Maesteg_Sep2017")
        cmbDaylight.setSelectedItem(currentDaylight if currentDaylight in daylightNames else "Maesteg_Sep2017")
        def ApplyDaylight():
            val = str(cmbDaylight.getSelectedItem())
            TBL.SafeSetMemoryValue(IMDayNightPreset, val)
        cmbDaylight.addActionListener(lambda e: ApplyDaylight())
        row4b.add(lblDaylight); row4b.add(Box.createHorizontalStrut(8)); row4b.add(cmbDaylight)
        root.add(row4b, gbc)
        
        # (5) Cloud cover (%) and Minimum night glow (0.0-1.0) side by side
        gbc.gridy += 1
        rowCloudGlow = Box.createHorizontalBox()

        # Cloud cover control
        lblCloud = JLabel("Cloud cover (%):")
        txtCloud = JTextField(3)
        txtCloud.setText(str(TBL.SafeGetOrCreateMemoryValue(IMWxCloudPct, "0")))
        self.TxtCloudPct = txtCloud
        def ApplyCloud():
            s = txtCloud.getText().strip()
            try:
                n = int(float(s))
                n = max(0, min(100, n))
                TBL.SafeSetMemoryValue(IMWxCloudPct, str(n))
            except:
                LogWarn("Cloud cover must be 0..100", alsoDialog=True)
        class CloudLost(FocusAdapter):
            def focusLost(self, e): ApplyCloud()
        txtCloud.addActionListener(lambda e: ApplyCloud())
        txtCloud.addFocusListener(CloudLost())

        # Minimum night glow control
        lblGlow = JLabel("Minimum night glow (0.0-1.0):")
        txtGlow = JTextField(4)
        txtGlow.setText(TBL.SafeGetOrCreateMemoryValue("MINNIGHTGLOW", "0.02"))
        def CommitGlow():
            s = txtGlow.getText().strip()
            try:
                v = float(s)
                if v < 0.0: v = 0.0
                if v > 1.0: v = 1.0
                TBL.SafeSetMemoryValue("MINNIGHTGLOW", str(v))
            except:
                LogWarn("Night glow must be a number between 0.0 and 1.0", alsoDialog=True)
        class GlowLost(FocusAdapter):
            def focusLost(self, e): CommitGlow()
        txtGlow.addActionListener(lambda e: CommitGlow())
        txtGlow.addFocusListener(GlowLost())

        # Add both controls to the same row
        rowCloudGlow.add(lblCloud)
        rowCloudGlow.add(Box.createHorizontalStrut(6))
        rowCloudGlow.add(txtCloud)
        rowCloudGlow.add(Box.createHorizontalStrut(24))  # spacing between groups
        rowCloudGlow.add(lblGlow)
        rowCloudGlow.add(Box.createHorizontalStrut(6))
        rowCloudGlow.add(txtGlow)

        root.add(rowCloudGlow, gbc)
 
        def ApplyCloud():
            s = txtCloud.getText().strip()
            try:
                n = int(float(s)); n = max(0, min(100, n))
                TBL.SafeSetMemoryValue(IMWxCloudPct, str(n))
            except:
                LogWarn("Cloud cover must be 0..100", alsoDialog=True)
        class CloudLost(FocusAdapter):
            def focusLost(self, e): ApplyCloud()
        txtCloud.addActionListener(lambda e: ApplyCloud()); txtCloud.addFocusListener(CloudLost())

        def RefreshWXEnableState():
            enabled = IsWeatherEnabled()
            cmbClimate.setEnabled(enabled)
            txtCloud.setEnabled(not enabled)
        RefreshWXEnableState()
        
        # --- Time-warp blackout (placed above Weather forecast UI)
        gbc.gridy += 1
        root.add(MakeHeading("Time-warp blackout"), gbc)

        # Row A: checkbox + threshold minutes
        gbc.gridy += 1
        warpRow = Box.createHorizontalBox()

        # Create checkbox FIRST
        chkBlackout = JCheckBox("Enable blackout when time warp exceeds")
        chkBlackout.setOpaque(False)

        # Read current memory values
        secsVal = TBL.SafeGetOrCreateMemoryValue(IMTimeWarpBlackoutSeconds, "2").strip()
        minsVal = TBL.SafeGetOrCreateMemoryValue(IMTimeWarpThresholdMinutes, "5").strip()

        # Determine initial enabled state from seconds (0 => disabled)
        try:
            initialSecs = float(secsVal) if secsVal != "" else 0.0
        except:
            initialSecs = 2.0
        chkBlackout.setSelected(initialSecs > 0.0)

        # Threshold minutes field
        txtWarpMins = JTextField(3)
        try:
            txtWarpMins.setText(str(max(0, int(float(minsVal)))))
        except:
            txtWarpMins.setText("5")

        # Commit logic for threshold
        def CommitWarpMins():
            s = txtWarpMins.getText().strip()
            try:
                n = max(0, int(float(s)))
                TBL.SafeSetMemoryValue(IMTimeWarpThresholdMinutes, str(n))
            except:
                pass

        txtWarpMins.addActionListener(lambda e: CommitWarpMins())
        class WarpMinsLost(FocusAdapter):
            def focusLost(self, e): CommitWarpMins()
        txtWarpMins.addFocusListener(WarpMinsLost())

        # Add components to row
        warpRow.add(chkBlackout)
        warpRow.add(Box.createHorizontalStrut(6))
        warpRow.add(txtWarpMins)
        warpRow.add(Box.createHorizontalStrut(6))
        warpRow.add(JLabel("minutes"))
        root.add(warpRow, gbc)

        # Row B: blackout seconds
        gbc.gridy += 1
        secsRow = Box.createHorizontalBox()
        lblSecs = JLabel("Blackout duration (seconds):")
        txtBlackoutSecs = JTextField(4)
        try:
            txtBlackoutSecs.setText(str(max(0.0, float(secsVal))))
        except:
            txtBlackoutSecs.setText("2")

        def CommitBlackoutSecs():
            s = txtBlackoutSecs.getText().strip()
            try:
                v = max(0.0, float(s))
                TBL.SafeSetMemoryValue(IMTimeWarpBlackoutSeconds, ("%s" % v))
            except:
                pass

        txtBlackoutSecs.addActionListener(lambda e: CommitBlackoutSecs())
        class BlackoutSecsLost(FocusAdapter):
            def focusLost(self, e): CommitBlackoutSecs()
        txtBlackoutSecs.addFocusListener(BlackoutSecsLost())

        # Toggle logic
        def ApplyBlackoutToggle():
            try:
                if chkBlackout.isSelected():
                    txtBlackoutSecs.setEnabled(True)
                    try:
                        v = float(txtBlackoutSecs.getText().strip())
                        if v == 0.0:
                            txtBlackoutSecs.setText("2")
                    except:
                        txtBlackoutSecs.setText("2")
                    CommitBlackoutSecs()
                else:
                    txtBlackoutSecs.setEnabled(False)
                    TBL.SafeSetMemoryValue(IMTimeWarpBlackoutSeconds, "0")
            except:
                pass

        txtBlackoutSecs.setEnabled(chkBlackout.isSelected())
        ApplyBlackoutToggle()
        chkBlackout.addActionListener(lambda e: ApplyBlackoutToggle())

        secsRow.add(lblSecs)
        secsRow.add(Box.createHorizontalStrut(8))
        secsRow.add(txtBlackoutSecs)
        root.add(secsRow, gbc)

        
        # Enable/disable the newspaper title controls depending on UI choice
        def RefreshPaperTitleEnable():
            # rbApp / rbNewsO / rbNewsM are in scope here
            useNewspaper = (rbNewsO.isSelected() or rbNewsM.isSelected())
            try:
                txtPaper.setEnabled(useNewspaper)
            except:
                pass
            try:
                lblPaper.setEnabled(useNewspaper)
            except:
                pass
            try:
                lblExplain.setEnabled(useNewspaper)
            except:
                pass

        # (6) Weather forecast UI (radio buttons)      
        gbc.gridy += 1
        root.add(MakeHeading("Weather forecast UI"), gbc)
        gbc.gridy += 1
        uiRow = Box.createHorizontalBox()
        rbApp = JRadioButton("Mobile app"); rbApp.setOpaque(False)
        rbNewsO = JRadioButton("Newspaper (Old)"); rbNewsO.setOpaque(False)
        rbNewsM = JRadioButton("Newspaper (Modern)"); rbNewsM.setOpaque(False)
        self.RbWxApp = rbApp
        self.RbWxNewsOld = rbNewsO
        self.RbWxNewsModern = rbNewsM
        group = ButtonGroup(); group.add(rbApp); group.add(rbNewsO); group.add(rbNewsM)
        uiChoice = TBL.SafeGetOrCreateMemoryValue(IMWxUiChoice, "Newspaper").strip()
        style = TBL.SafeGetOrCreateMemoryValue(IMWxNewsStyle, "Old").strip()
        if uiChoice.lower() == "app":
            rbApp.setSelected(True)
        else:
            if style.lower() == "modern": rbNewsM.setSelected(True)
            else: rbNewsO.setSelected(True)
        def ApplyUi():
            if rbApp.isSelected():
                TBL.SafeSetMemoryValue(IMWxUiChoice, "App")
            elif rbNewsO.isSelected():
                TBL.SafeSetMemoryValue(IMWxUiChoice, "Newspaper")
                TBL.SafeSetMemoryValue(IMWxNewsStyle, "Old")
            else:
                TBL.SafeSetMemoryValue(IMWxUiChoice, "Newspaper")
                TBL.SafeSetMemoryValue(IMWxNewsStyle, "Modern")
            # ALSO: update enable/disable for the Newspaper title controls
            RefreshPaperTitleEnable()
            RefreshAdsControlEnable()
        rbApp.addActionListener(lambda e: ApplyUi())
        rbNewsO.addActionListener(lambda e: ApplyUi())
        rbNewsM.addActionListener(lambda e: ApplyUi())
        uiRow.add(rbApp); uiRow.add(Box.createHorizontalStrut(16)); uiRow.add(rbNewsO)
        uiRow.add(Box.createHorizontalStrut(12)); uiRow.add(rbNewsM)
        root.add(uiRow, gbc)       
        
        # (7) Newspaper title (used by WeatherForecastUINewspaper)
        gbc.gridy += 1
        rowPaper = Box.createHorizontalBox()
        lblPaper = JLabel("Newspaper title:")
        ApplyTheme(lblPaper)

        txtPaper = JTextField(28)
        self.TxtPaperName = txtPaper
        self.LblPaperName = lblPaper
        # Default template uses the active profile name token
        initPaper = TBL.SafeGetOrCreateMemoryValue("WX_NEWS_PAPERNAME", "The {PROFILE} Echo")
        txtPaper.setText(initPaper)

        def CommitPaper():
            s = txtPaper.getText().strip()
            if len(s) == 0:
                s = "The {PROFILE} Echo"
            TBL.SafeSetMemoryValue("WX_NEWS_PAPERNAME", s)

        txtPaper.addActionListener(lambda e: CommitPaper())
        class PaperLost(FocusAdapter):
            def focusLost(self, e): CommitPaper()
        txtPaper.addFocusListener(PaperLost())

        rowPaper.add(lblPaper); rowPaper.add(Box.createHorizontalStrut(8)); rowPaper.add(txtPaper)
        root.add(rowPaper, gbc)
        # Set enabled/disabled state at creation time
        RefreshPaperTitleEnable()

        # Explanatory text about tokens
        gbc.gridy += 1
        lblExplain = JLabel("<html>"
            "Use <b>{PROFILE}</b> anywhere in the text to insert the active profile name.<br/>"
            "Example: <i>The {PROFILE} Echo</i>"
            "</html>")
        ApplyTheme(lblExplain)
        self.LblPaperExplain = lblExplain
        root.add(lblExplain, gbc)
        
        # (8) Forecast reliability (%)
        gbc.gridy += 1
        rowAcc = Box.createHorizontalBox()
        lblAcc = JLabel("Forecast reliability (%):")
        ApplyTheme(lblAcc)

        txtAcc = JTextField(4)
        # Default = 80; clamp 0..100 when committing
        initAcc = TBL.SafeGetOrCreateMemoryValue("WX_FORECAST_ACCURACY", "80")
        txtAcc.setText(initAcc)

        self.TxtForecastAccuracy = txtAcc
        def CommitAcc():
            s = txtAcc.getText().strip()
            try:
                n = int(float(s))
                n = max(0, min(100, n))
                TBL.SafeSetMemoryValue("WX_FORECAST_ACCURACY", str(n))
            except:
                # keep prior value if invalid; optional: show warning
                pass

        txtAcc.addActionListener(lambda e: CommitAcc())
        class AccLost(FocusAdapter):
            def focusLost(self, e): CommitAcc()
        txtAcc.addFocusListener(AccLost())

        rowAcc.add(lblAcc); rowAcc.add(Box.createHorizontalStrut(8)); rowAcc.add(txtAcc)
        root.add(rowAcc, gbc)
        
        # (9) Show spoof mobile ads (App only)
        gbc.gridy += 1
        rowAds = Box.createHorizontalBox()
        lblAds = JLabel("Show spoof mobile ads:")
        ApplyTheme(lblAds)

        chkSpoofAds = JCheckBox("")
        chkSpoofAds.setOpaque(False)
        chkSpoofAds.setSelected(GetMemoryBool("SPOOFADSENABLED", True))
        self.ChkSpoofAds = chkSpoofAds
        self.LblSpoofAds = lblAds

        def OnSpoofAds(e=None):
            try:
                if getattr(self, "SuppressWizardSync", False):
                    return
            except:
                pass
            SetMemoryBool("SPOOFADSENABLED", chkSpoofAds.isSelected())

        chkSpoofAds.addActionListener(OnSpoofAds)

        rowAds.add(lblAds); rowAds.add(Box.createHorizontalStrut(8)); rowAds.add(chkSpoofAds)
        root.add(rowAds, gbc)

        # Helper: enable the checkbox only when Mobile app UI is selected
        def RefreshAdsControlEnable():
            try:
                chkSpoofAds.setEnabled(rbApp.isSelected())
                lblAds.setEnabled(True)   # label stays visible; checkbox greys out when app is not selected
            except:
                pass

        # Initial enable/disable at creation time
        RefreshAdsControlEnable()

        return root


    # ---- Helper: read climate names from profile:jython/config/climate.csv ----

    # ---------------- Wizard UI auto-refresh (for running the wizard from this window) ----------------
    def RefreshDayNightTabFromWizardChanges(self):
        # Update the Day/night cycle tab controls from current memories/startup state.
        try:
            if not hasattr(self, "ChkDayNight"):
                return
        except:
            return
        try:
            self.SuppressWizardSync = True
        except:
            pass
        try:
            try:
                self.ChkDayNight.setSelected(bool(IsDayNightEnabled()))
            except:
                pass
            try:
                if hasattr(self, "ChkWeatherGenerator"):
                    self.ChkWeatherGenerator.setSelected(bool(IsWeatherEnabled()))
            except:
                pass
            try:
                if hasattr(self, "TxtWarmAddr"):
                    self.TxtWarmAddr.setText(str(TBL.SafeGetOrCreateMemoryValue("LOWCTTHROTTLEADDR", "990")).strip())
                if hasattr(self, "TxtCoolAddr"):
                    self.TxtCoolAddr.setText(str(TBL.SafeGetOrCreateMemoryValue("HIGHCTTHROTTLEADDR", "991")).strip())
            except:
                pass
            try:
                if hasattr(self, "TxtForecastAccuracy"):
                    self.TxtForecastAccuracy.setText(str(TBL.SafeGetOrCreateMemoryValue("WX_FORECAST_ACCURACY", "80")).strip())
            except:
                pass
            try:
                uiChoice = str(TBL.SafeGetOrCreateMemoryValue("WX_UI", "Newspaper")).strip()
            except:
                uiChoice = "Newspaper"
            try:
                style = str(TBL.SafeGetOrCreateMemoryValue("WX_NEWS_STYLE", "Old")).strip()
            except:
                style = "Old"
            try:
                if hasattr(self, "RbWxApp") and hasattr(self, "RbWxNewsOld") and hasattr(self, "RbWxNewsModern"):
                    if uiChoice.lower() == "app":
                        self.RbWxApp.setSelected(True)
                    else:
                        if style.lower() == "modern":
                            self.RbWxNewsModern.setSelected(True)
                        else:
                            self.RbWxNewsOld.setSelected(True)
            except:
                pass
            try:
                useNewspaper = True
                try:
                    useNewspaper = hasattr(self, "RbWxApp") and (not self.RbWxApp.isSelected())
                except:
                    useNewspaper = True
                if hasattr(self, "TxtPaperName"):
                    self.TxtPaperName.setEnabled(bool(useNewspaper))
                if hasattr(self, "LblPaperName"):
                    self.LblPaperName.setEnabled(bool(useNewspaper))
                if hasattr(self, "LblPaperExplain"):
                    self.LblPaperExplain.setEnabled(bool(useNewspaper))
            except:
                pass
            try:
                if hasattr(self, "ChkSpoofAds") and hasattr(self, "RbWxApp"):
                    self.ChkSpoofAds.setEnabled(bool(self.RbWxApp.isSelected()))
            except:
                pass
        finally:
            try:
                self.SuppressWizardSync = False
            except:
                pass

    def RefreshThemeFromMemories(self):
        # Refresh theme globals and apply to existing components after TASWiz changes.
        try:
            global THEME_FONT_FAMILY
            global THEME_PAPER
        except:
            pass
        oldPaper = None
        try:
            oldPaper = THEME_PAPER
        except:
            oldPaper = None
        try:
            THEME_FONT_FAMILY = str(TBL.SafeGetOrCreateMemoryValue('TAS_FONT_FAMILY', 'Gill Sans MT')).strip()
        except:
            THEME_FONT_FAMILY = 'Gill Sans MT'
        try:
            rgb = TBL.SafeGetOrCreateMemoryValue('TASPAPERCOLOUR', '249,246,238')
            THEME_PAPER = _RgbStrToColorOrDefault(rgb, Color(249, 246, 238))
        except:
            try:
                THEME_PAPER = Color(249, 246, 238)
            except:
                pass
        # Re-apply fonts recursively to all controls.
        try:
            cp = self.getContentPane()
            if cp is not None:
                _ApplyFontRecursive(cp, THEME_FONT_FAMILY)
        except:
            pass
        # Update PaperPanel background/texture and any components using the old paper background.
        try:
            from java.awt import Container
            def _Walk(comp):
                try:
                    if comp is None:
                        return
                except:
                    return
                try:
                    if hasattr(comp, 'texture') and hasattr(comp, '_makeTexture'):
                        try:
                            comp.setBackground(THEME_PAPER)
                        except:
                            pass
                        try:
                            comp.texture = comp._makeTexture()
                        except:
                            pass
                    else:
                        try:
                            if oldPaper is not None and comp.getBackground() == oldPaper:
                                comp.setBackground(THEME_PAPER)
                        except:
                            pass
                except:
                    pass
                try:
                    if isinstance(comp, Container):
                        for ch in comp.getComponents():
                            _Walk(ch)
                except:
                    pass
            _Walk(self.getContentPane())
        except:
            pass
        try:
            self.revalidate()
            self.repaint()
        except:
            pass

    def RefreshGeneralTabFromWizard(self):
        # Refresh General-tab controls that the wizard may have changed.
        try:
            if hasattr(self, 'ChkTASMenu') and self.ChkTASMenu is not None:
                actual = bool(_IsScriptEnabled('TimetableAutomation.py'))
                self.CurrentTASMenu = actual
                self.ChkTASMenu.setSelected(actual)
        except:
            pass
        try:
            if hasattr(self, 'ChkTimeActions') and self.ChkTimeActions is not None:
                actual = bool(IsTimeActionsEnabled())
                self.CurrentTimeActions = actual
                self.ChkTimeActions.setSelected(actual)
        except:
            pass
        try:
            if hasattr(self, 'TxtCurrentTimetable') and self.TxtCurrentTimetable is not None:
                val = str(TBL.SafeGetOrCreateMemoryValue(IMCurrentTimetable, '')).strip()
                self.TxtCurrentTimetable.setText(val)
        except:
            pass

    def OnWizardClosedRefreshSetupUi(self):
        # Called by TASWiz via callback when the wizard closes (Finish/Cancel/window close).
        def _Do():
            try:
                self.RefreshThemeFromMemories()
            except:
                pass
            try:
                self.RefreshGeneralTabFromWizard()
            except:
                pass
            try:
                self.RefreshFromWizardChanges()
            except:
                pass
        try:
            SwingUtilities.invokeLater(RunnableAdapter(_Do))
        except:
            try:
                _Do()
            except:
                pass

    def RefreshFromWizardChanges(self):
        try:
            self.RefreshDayNightTabFromWizardChanges()
        except:
            pass
        try:
            if hasattr(self, "UpdateRunAutoControls"):
                self.UpdateRunAutoControls()
        except:
            pass

    def StartWizardSyncTimer(self):
        try:
            if getattr(self, "WizardSyncTimer", None) is not None:
                return
        except:
            pass
        try:
            self.WizardSyncTimer = Timer(750, lambda e: self.RefreshFromWizardChanges())
            self.WizardSyncTimer.setRepeats(True)
            self.WizardSyncTimer.start()
        except:
            pass

    def LoadClimateNames(self):
        names = ["SouthWales_EarlySep"]
        try:
            path = FileUtil.getExternalFilename("profile:jython/config/climate.csv")
            import java.io as jio
            f = jio.File(path)
            if not f.exists() or not f.isFile(): return names
            fis = jio.FileInputStream(f)
            isr = java.io.InputStreamReader(fis, "US-ASCII")
            br = java.io.BufferedReader(isr)
            header = br.readLine()
            idx = -1
            if header:
                cols = header.split("\t")
                for i,c in enumerate(cols):
                    if c.strip().lower() == "name": idx = i; break
            line = br.readLine()
            seen = set(names)
            while line is not None:
                parts = line.split("\t")
                if idx >= 0 and idx < len(parts):
                    val = parts[idx].strip()
                    if val and val not in seen:
                        names.append(val); seen.add(val)
                line = br.readLine()
            br.close(); isr.close(); fis.close()
        except Exception as ex:
            LogWarn("Could not read climate presets: " + str(ex))
        return names

    # ---- Helper: read day/night preset names from profile:jython/config/daynight.csv ----
    def LoadDayNightNames(self):
        names = ["Maesteg_Sep2017"]
        try:
            path = FileUtil.getExternalFilename("profile:jython/config/daynight.csv")
            import java.io as jio
            f = jio.File(path)
            if not f.exists() or not f.isFile(): return names
            fis = jio.FileInputStream(f)
            isr = java.io.InputStreamReader(fis, "US-ASCII")
            br = java.io.BufferedReader(isr)
            header = br.readLine()
            idx = -1
            if header:
                cols = header.split("\t")
                for i,c in enumerate(cols):
                    if c.strip().lower() == "name": idx = i; break
            line = br.readLine()
            seen = set(names)
            while line is not None:
                parts = line.split("\t")
                if idx >= 0 and idx < len(parts):
                    val = parts[idx].strip()
                    if val and val not in seen:
                        names.append(val); seen.add(val)
                line = br.readLine()
            br.close(); isr.close(); fis.close()
        except Exception as ex:
            LogWarn("Could not read day/night presets: " + str(ex))
        return names


        # --------------------- Restart prompt on close ---------------------- 
        def dispose(self):
            # First, guard against unsaved edits in the Workings tab
            try:
                if (hasattr(self, "WorkingsUiController") and self.WorkingsUiController is not None and self.WorkingsUiController.HasUnsavedChanges()):
                    choice = JOptionPane.showConfirmDialog(
                        self,
                        "You have unsaved changes in a working script.\nDiscard changes and close the setup window?",
                        "Unsaved changes",
                        JOptionPane.OK_CANCEL_OPTION,
                        JOptionPane.WARNING_MESSAGE
                    )
                    if choice != JOptionPane.OK_OPTION:
                        return  # abort closing; user wants to keep editing
            except Exception:
                pass

            # Then apply your existing restart-needed prompt logic           
            changed = (self.InitialTimeActions != self.CurrentTimeActions or
                       self.InitialDayNight != self.CurrentDayNight or
                       self.InitialWeather != self.CurrentWeather or
                       self.InitialDirectionSensing != self.CurrentDirectionSensing)
            if changed:
                try:
                    JOptionPane.showMessageDialog(
                        self,
                        "Some changes require a restart to take effect.\nPlease close and restart JMRI manually.",
                        "Restart Required",
                        JOptionPane.INFORMATION_MESSAGE
                    )
                except Exception as ex:
                    LogWarn("Please restart JMRI manually to apply changes.", alsoDialog=False)
        
        # Actively dispose any owned child dialogs (e.g., Block Picker) so nothing lingers
        try:
            for w in self.getOwnedWindows():
                try:
                    if w is not None and w.isDisplayable():
                        w.dispose()
                except:
                    pass
        except:
            pass

        jmri.util.JmriJFrame.dispose(self)

# -------------------------------- Entry --------------------------------
class RunnableAdapter(Runnable):
    def __init__(self, func): self.func = func
    def run(self): self.func()

def ShowTASSetup():
    def Run():
        try: TASSetupFrame()
        except Exception as ex:
            LogError("Error opening Timetable Automation System setup: " + str(ex), ex=ex, alsoDialog=True)
    if SwingUtilities.isEventDispatchThread():
        Run()
    else:
        SwingUtilities.invokeLater(RunnableAdapter(Run))

ShowTASSetup()