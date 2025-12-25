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
# Text composition remains configurable:
#   FBP_TEXT_MODE = "CALLING_ONLY" or "DEST_THEN_CALLING"
#   FBP_CALLING_SEPARATOR, FBP_DEST_CALL_JOINER, FBP_UPPERCASE_ALL
#
# <<PID-DISP-NAME: Platform fingerboard>>
# <<DESCRIPTION: A wooden board with the destination and calling pattern of the next train painted on it>>

# ----------------------------------------------------------------
# User-configurable settings discovered by TASSetup:
# Text composition
# <<SETTING DESCRIPTION ENUM: Text layout>>
# <<SETTING ENUM VALUES Text layout: Calling pattern only | Destination then calling pattern>>
# <<SETTING DESCRIPTION STRING: Separator between calling points>>
# <<SETTING DESCRIPTION STRING: Joiner between destination and calling text>>
# <<SETTING DESCRIPTION BOOLEAN: Use uppercase letters>>
# Behaviour
# <<SETTING DESCRIPTION NUMBER: Due window (minutes)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide clocks when empty>>
# <<SETTING DESCRIPTION STRING: Extra ECS keywords>>
# <<SETTING DESCRIPTION STRING: Departure timing point(s)>>
# Colours (RGB r,g,b)
# <<SETTING DESCRIPTION COLOR: Text colour>>
# <<SETTING DESCRIPTION COLOR: Board fill colour>>
# <<SETTING DESCRIPTION COLOR: Board edge colour>>
# <<SETTING DESCRIPTION COLOR: Clock face colour>>
# <<SETTING DESCRIPTION COLOR: Clock hands colour>>
# <<SETTING DESCRIPTION COLOR: Label fill colour>>
# <<SETTING DESCRIPTION COLOR: Label edge colour>>
# <<SETTING DESCRIPTION COLOR: Background colour>>
# Geometry / layout (numbers)
# <<SETTING DESCRIPTION NUMBER: Clock diameter (px)>>
# <<SETTING DESCRIPTION NUMBER: Label box max width (px)>>
# <<SETTING DESCRIPTION NUMBER: Text maximum size (pt)>>
# <<SETTING DESCRIPTION NUMBER: Text minimum size (pt)>>

# ----------------------------------------------------------------

# Friendly label -> legacy key
# Text layout                  -> TEXT_MODE
# Separator between calling... -> CALLING_SEPARATOR
# Joiner between destination...-> DEST_CALL_JOINER
# Use uppercase letters        -> UPPERCASE_ALL
# Due window (minutes)         -> WITHIN_MINUTES
# Hide clocks when empty       -> HIDE_CLOCKS_WHEN_EMPTY
# Extra ECS keywords           -> EXTRA_ECS_TERMS
# Departure timing point(s)    -> DEPARTURE_TP
# Text colour                  -> TEXT_COLOR
# Board fill colour            -> BOARD_FILL_COLOR
# Board edge colour            -> BOARD_EDGE_COLOR
# Clock face colour            -> CLOCK_FACE_COLOR
# Clock hands colour           -> CLOCK_HAND_COLOR
# Label fill colour            -> LABEL_FILL_COLOR
# Label edge colour            -> LABEL_EDGE_COLOR
# Background colour            -> BACKGROUND_COLOR
# Clock diameter (px)          -> CLOCK_DIAMETER
# Label box max width (px)     -> LABEL_BOX_MAX_W
# Text maximum size (pt)       -> LINE_FONT_MAX
# Text minimum size (pt)       -> LINE_FONT_MIN

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
from javax.swing import Timer
import jmri
from jmri import InstanceManager
import os
import csv as FBP_csv
import java.text.SimpleDateFormat as SimpleDateFormat
from java.awt.geom import Area, RoundRectangle2D, Ellipse2D
import TimingRegister as TR  # read-only tuples (reportingNumber, direction, time, day)
import TASBeanLookup as TBL
import PlatformAllocationRegister as PAR  # allocation takes precedence over timetable/overrides

# -------------------- TYPEFACE & COLOURS --------------------
def FBP_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

# Primary face (board & labels)
FBP_TYPEFACE_PRIMARY  = FBP_PickFamily(["Gill Sans MT", "Gill Sans", "SansSerif"])
# Numerals face (Roman around the dial)
FBP_TYPEFACE_NUMERALS = FBP_PickFamily(["Serif", "Times New Roman", "DejaVu Serif", "Serif"])

# -------------------- TEXT COMPOSITION --------------------
FBP_TEXT_MODE          = "CALLING_ONLY"   # "CALLING_ONLY" or "DEST_THEN_CALLING"
FBP_CALLING_SEPARATOR  = " - "
FBP_DEST_CALL_JOINER   = " "
FBP_UPPERCASE_ALL      = True

# -------------------- COLOURS --------------------
FBP_BG_COLOR      = Color(20, 20, 30)
FBP_POST_COLOR    = Color(96, 70, 38)
FBP_POST_SHADE    = Color(68, 48, 26)
FBP_BOARD_FILL    = Color(252, 252, 252)
FBP_BOARD_EDGE    = Color(35, 35, 35)
FBP_TEXT_COLOR    = Color(0, 0, 0)
FBP_CLOCK_FACE    = Color(250, 250, 250)
FBP_CLOCK_EDGE    = Color(35, 35, 35)
FBP_CLOCK_TICK    = Color(65, 65, 65)
FBP_CLOCK_HAND    = Color(20, 20, 20)
FBP_LABEL_BOX_FILL= Color(255, 255, 255)
FBP_LABEL_BOX_EDGE= Color(20, 20, 20)

# -------------------- GEOMETRY / LAYOUT --------------------
FBP_MARGIN            = 10
FBP_POST_W            = 36
FBP_POST_RADIUS       = 14
FBP_BOARD_H           = 120
FBP_BOARD_LEFT_GAP    = -1   # slight overlap onto post
FBP_BOARD_TOP         = 14
FBP_CAP_RADIUS        = FBP_BOARD_H // 2
FBP_OUTLINE_STROKE    = BasicStroke(3.0)
FBP_LEFT_PAD          = 14
FBP_RIGHT_PAD         = 18
FBP_CLOCK_D           = 120
FBP_CLOCK_PAIR_GAP    = 30
FBP_CLOCK_BLOCK_TOP_G = 18

# ARR/DEP label boxes beside clocks
FBP_LABEL_BOX_MAX_W   = 180
FBP_LABEL_BOX_H       = 40
FBP_LABEL_BOX_PAD_TXT = 6
FBP_LABEL_BOX_INSET   = 4
FBP_LABEL_FONT_MAX    = 28
FBP_LABEL_FONT_MIN    = 12

# Board text sizing
FBP_LINE_FONT_MAX     = 42
FBP_LINE_FONT_MIN     = 18

# ------------------------- JMRI MEMORIES / TIMETABLE -------------------------
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
FBP_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
FBP_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
FBP_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
FBP_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Optional: departure TP list, ECS keywords, due-window, hide-clocks toggle
FBP_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
FBP_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")
FBP_WithInMinMem = TBL.ProvideMemoryBySuffix("PID_FINGERBOARD_WITHIN_MINUTES", "10")
FBP_HideClocksEmptyMem = TBL.ProvideMemoryBySuffix("PID_FINGERBOARD_HIDE_CLOCKS_WHEN_EMPTY", "false")

FBP_DefaultWithinMinutes = 10

# Optional authoritative fast clock for "now"
FBP_Timebase      = InstanceManager.getDefault(jmri.Timebase)

# -------------------- USER SETTINGS (via TASSetup) --------------------
# Memory beans discovered by TASSetup from the <<SETTING ...>> tags.
# We use ProvideMemoryBySuffix so the IM/I2M/I3M prefix is agnostic.
FBP_TextModeMem     = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_TEXT_MODE", "")
FBP_CallSepMem      = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_CALLING_SEPARATOR", "")
FBP_DestJoinMem     = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_DEST_CALL_JOINER", "")
FBP_UppercaseMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_UPPERCASE_ALL", "")

FBP_WithinMinMem2   = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_WITHIN_MINUTES", "")
FBP_HideClocksMem2  = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_HIDE_CLOCKS_WHEN_EMPTY", "")
FBP_ExtraEcsMem2    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_EXTRA_ECS_TERMS", "")
FBP_DepartTpMem2    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_DEPARTURE_TP", "")

# Colour memories (rgb string "r,g,b")
FBP_TextColorMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_TEXT_COLOR", "")
FBP_BoardFillMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_BOARD_FILL_COLOR", "")
FBP_BoardEdgeMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_BOARD_EDGE_COLOR", "")
FBP_ClockFaceMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_CLOCK_FACE_COLOR", "")
FBP_ClockHandMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_CLOCK_HAND_COLOR", "")
FBP_LabelFillMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_LABEL_FILL_COLOR", "")
FBP_LabelEdgeMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_LABEL_EDGE_COLOR", "")
FBP_BackgroundMem   = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_BACKGROUND_COLOR", "")

# Geometry memories (numbers)
FBP_ClockDiamMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_CLOCK_DIAMETER", "")
FBP_LabelMaxWMem    = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_LABEL_BOX_MAX_W", "")
FBP_LineFontMaxMem  = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_LINE_FONT_MAX", "")
FBP_LineFontMinMem  = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_LINE_FONT_MIN", "")

# Basic parsers for settings
def FBP_ReadStr(memBean, defaultVal):
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip()
        return s if s != "" else defaultVal
    except:
        return defaultVal

def FBP_ReadBool(memBean, defaultVal):
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip().lower()
        if s in ("1","true","yes","y","on","t"):   return True
        if s in ("0","false","no","n","off","f"): return False
        return defaultVal
    except:
        return defaultVal

def FBP_ReadInt(memBean, defaultVal):
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip()
        return int(float(s)) if s != "" else defaultVal
    except:
        return defaultVal

def FBP_ParseColor(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3: return defaultColor
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return Color(r,g,b)
    except:
        return defaultColor

def FBP_ReadColor(memBean, defaultColor):
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip()
        return FBP_ParseColor(s, defaultColor) if s != "" else defaultColor
    except:
        return defaultColor
          

# --- Derive TAS user-setting memory suffix from a friendly label (same rule TASSetup uses) ---
def FBP_MemSuffixFromLabel(label):
    try:
        s = str(label).strip()
    except:
        s = ""
    import re
    key = re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key

# --- Obtain both new (friendly) and legacy (old ALLCAPS) beans for a setting ---
def FBP_GetDualSettingBeans(friendlyLabel, legacyKey):
    try:
        newBean = TBL.ProvideMemoryBySuffix(FBP_MemSuffixFromLabel(friendlyLabel), "")
    except:
        newBean = None
    try:
        legacyBean = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_" + legacyKey, "")
    except:
        legacyBean = None
    return newBean, legacyBean

# --- Dual readers: prefer the friendly bean if it has a value; else fall back to legacy ---
def FBP_ReadStrDual(newBean, legacyBean, defaultVal):
    try:
        v = newBean.getValue() if newBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s != "":
            return s
    except:
        pass
    try:
        v2 = legacyBean.getValue() if legacyBean is not None else None
        s2 = ("" if v2 is None else str(v2)).strip()
        if s2 != "":
            return s2
    except:
        pass
    return defaultVal

def FBP_ReadBoolDual(newBean, legacyBean, defaultVal):
    def to_bool(x, d):
        t = ("" if x is None else str(x)).strip().lower()
        if t in ("1","true","yes","y","on","t"): return True
        if t in ("0","false","no","n","off","f"): return False
        return d
    try:
        v = newBean.getValue() if newBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s != "":
            return to_bool(s, defaultVal)
    except:
        pass
    try:
        v2 = legacyBean.getValue() if legacyBean is not None else None
        s2 = ("" if v2 is None else str(v2)).strip()
        if s2 != "":
            return to_bool(s2, defaultVal)
    except:
        pass
    return defaultVal

def FBP_ReadIntDual(newBean, legacyBean, defaultVal):
    try:
        v = newBean.getValue() if newBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s != "":
            return int(float(s))
    except:
        pass
    try:
        v2 = legacyBean.getValue() if legacyBean is not None else None
        s2 = ("" if v2 is None else str(v2)).strip()
        if s2 != "":
            return int(float(s2))
    except:
        pass
    return defaultVal

def FBP_ReadColorDual(newBean, legacyBean, defaultColor):
    try:
        v = newBean.getValue() if newBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s != "":
            return FBP_ParseColor(s, defaultColor)
    except:
        pass
    try:
        v2 = legacyBean.getValue() if legacyBean is not None else None
        s2 = ("" if v2 is None else str(v2)).strip()
        if s2 != "":
            return FBP_ParseColor(s2, defaultColor)
    except:
        pass
    return defaultColor


# --- Helpers to seed initial colour memories with sensible fingerboard defaults ---
def _FBP_ColorToRgbStr(c):
    try:
        return "%d,%d,%d" % (c.getRed(), c.getGreen(), c.getBlue())
    except:
        return "0,0,0"

def FBP_SeedColorIfPlaceholder(memBean, defaultColor):
    """
    If the colour memory is blank or equals a generic beige placeholder,
    write the fingerboard's sensible default into the memory (so TASSetup
    shows it), and return that default. Otherwise, return the user's colour.
    """
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s == "":
            # Blank -> seed with default
            if memBean is not None:
                memBean.setValue(_FBP_ColorToRgbStr(defaultColor))
            return defaultColor
        # Known placeholders used by TASSetup/WTTDisplay; treat as "unset"
        placeholders = ["240,238,220", "249,246,238"]
        if s in placeholders:
            if memBean is not None:
                memBean.setValue(_FBP_ColorToRgbStr(defaultColor))
            return defaultColor
        # Real user choice
        return FBP_ParseColor(s, defaultColor)
    except:
        return defaultColor
        
def FBP_WriteColorSeed(newBean, legacyBean, colorObj):
    """
    Prefer writing to the 'friendly' bean (newBean). If that bean doesn't exist,
    write to the legacy bean. Only seed when the current value is blank.
    """
    try:
        rgb = _FBP_ColorToRgbStr(colorObj)

        # Try friendly first
        if newBean is not None:
            cur = newBean.getValue()
            if cur is None:
                newBean.setValue(rgb)
                return

        # Fall back to legacy
        if legacyBean is not None:
            cur2 = legacyBean.getValue()
            if cur2 is None:
                legacyBean.setValue(rgb)
    except:
        pass

# Dual beans: (new friendly, legacy) for each setting
FBP_TextLayout_New,      FBP_TextMode_Leg = FBP_GetDualSettingBeans("Text layout",                  "TEXT_MODE")
FBP_CallSep_New,         FBP_CallSep_Leg  = FBP_GetDualSettingBeans("Separator between calling points", "CALLING_SEPARATOR")
FBP_DestJoin_New,        FBP_DestJoin_Leg = FBP_GetDualSettingBeans("Joiner between destination and calling text", "DEST_CALL_JOINER")
FBP_Uppercase_New,       FBP_Uppercase_Leg= FBP_GetDualSettingBeans("Use uppercase letters",         "UPPERCASE_ALL")

FBP_Within_New,          FBP_Within_Leg   = FBP_GetDualSettingBeans("Due window (minutes)",          "WITHIN_MINUTES")
FBP_HideClocks_New,      FBP_HideClocks_Leg=FBP_GetDualSettingBeans("Hide clocks when empty",        "HIDE_CLOCKS_WHEN_EMPTY")
FBP_ExtraEcs_New,        FBP_ExtraEcs_Leg = FBP_GetDualSettingBeans("Extra ECS keywords",            "EXTRA_ECS_TERMS")
FBP_DepartTp_New,        FBP_DepartTp_Leg = FBP_GetDualSettingBeans("Departure timing point(s)",     "DEPARTURE_TP")

FBP_TextColor_New,       FBP_TextColor_Leg= FBP_GetDualSettingBeans("Text colour",                   "TEXT_COLOR")
FBP_BoardFill_New,       FBP_BoardFill_Leg= FBP_GetDualSettingBeans("Board fill colour",             "BOARD_FILL_COLOR")
FBP_BoardEdge_New,       FBP_BoardEdge_Leg= FBP_GetDualSettingBeans("Board edge colour",             "BOARD_EDGE_COLOR")
FBP_ClockFace_New,       FBP_ClockFace_Leg= FBP_GetDualSettingBeans("Clock face colour",             "CLOCK_FACE_COLOR")
FBP_ClockHand_New,       FBP_ClockHand_Leg= FBP_GetDualSettingBeans("Clock hands colour",            "CLOCK_HAND_COLOR")
FBP_LabelFill_New,       FBP_LabelFill_Leg= FBP_GetDualSettingBeans("Label fill colour",             "LABEL_FILL_COLOR")
FBP_LabelEdge_New,       FBP_LabelEdge_Leg= FBP_GetDualSettingBeans("Label edge colour",             "LABEL_EDGE_COLOR")
FBP_Background_New,      FBP_Background_Leg=FBP_GetDualSettingBeans("Background colour",             "BACKGROUND_COLOR")

FBP_ClockDiam_New,       FBP_ClockDiam_Leg= FBP_GetDualSettingBeans("Clock diameter (px)",           "CLOCK_DIAMETER")
FBP_LabelMaxW_New,       FBP_LabelMaxW_Leg= FBP_GetDualSettingBeans("Label box max width (px)",      "LABEL_BOX_MAX_W")
FBP_LineFontMax_New,     FBP_LineFontMax_Leg=FBP_GetDualSettingBeans("Text maximum size (pt)",       "LINE_FONT_MAX")
FBP_LineFontMin_New,     FBP_LineFontMin_Leg=FBP_GetDualSettingBeans("Text minimum size (pt)",       "LINE_FONT_MIN")

# -------------------- APPLY USER SETTINGS (after helpers are defined) --------------------

# Text composition
tmp_mode = FBP_ReadStrDual(FBP_TextLayout_New, FBP_TextMode_Leg, FBP_TEXT_MODE).upper()
if tmp_mode in ("CALLING_ONLY", "DEST_THEN_CALLING"):
    FBP_TEXT_MODE = tmp_mode
FBP_CALLING_SEPARATOR = FBP_ReadStrDual(FBP_CallSep_New,  FBP_CallSep_Leg,  FBP_CALLING_SEPARATOR)
FBP_DEST_CALL_JOINER  = FBP_ReadStrDual(FBP_DestJoin_New, FBP_DestJoin_Leg, FBP_DEST_CALL_JOINER)

# Colours
FBP_TEXT_COLOR     = FBP_ReadColorDual(FBP_TextColor_New,  FBP_TextColor_Leg,  FBP_TEXT_COLOR)
FBP_BOARD_FILL     = FBP_ReadColorDual(FBP_BoardFill_New,  FBP_BoardFill_Leg,  FBP_BOARD_FILL)
FBP_BOARD_EDGE     = FBP_ReadColorDual(FBP_BoardEdge_New,  FBP_BoardEdge_Leg,  FBP_BOARD_EDGE)
FBP_CLOCK_FACE     = FBP_ReadColorDual(FBP_ClockFace_New,  FBP_ClockFace_Leg,  FBP_CLOCK_FACE)
FBP_CLOCK_HAND     = FBP_ReadColorDual(FBP_ClockHand_New,  FBP_ClockHand_Leg,  FBP_CLOCK_HAND)
FBP_LABEL_BOX_FILL = FBP_ReadColorDual(FBP_LabelFill_New,  FBP_LabelFill_Leg,  FBP_LABEL_BOX_FILL)
FBP_LABEL_BOX_EDGE = FBP_ReadColorDual(FBP_LabelEdge_New,  FBP_LabelEdge_Leg,  FBP_LABEL_BOX_EDGE)
FBP_BG_COLOR       = FBP_ReadColorDual(FBP_Background_New, FBP_Background_Leg, FBP_BG_COLOR)

# Seed friendly/legacy memories with the script's defaults when blank or beige
FBP_WriteColorSeed(FBP_TextColor_New,  FBP_TextColor_Leg,  FBP_TEXT_COLOR)
FBP_WriteColorSeed(FBP_BoardFill_New,  FBP_BoardFill_Leg,  FBP_BOARD_FILL)
FBP_WriteColorSeed(FBP_BoardEdge_New,  FBP_BoardEdge_Leg,  FBP_BOARD_EDGE)
FBP_WriteColorSeed(FBP_ClockFace_New,  FBP_ClockFace_Leg,  FBP_CLOCK_FACE)
FBP_WriteColorSeed(FBP_ClockHand_New,  FBP_ClockHand_Leg,  FBP_CLOCK_HAND)
FBP_WriteColorSeed(FBP_LabelFill_New,  FBP_LabelFill_Leg,  FBP_LABEL_BOX_FILL)
FBP_WriteColorSeed(FBP_LabelEdge_New,  FBP_LabelEdge_Leg,  FBP_LABEL_BOX_EDGE)
FBP_WriteColorSeed(FBP_Background_New, FBP_Background_Leg, FBP_BG_COLOR)

# Booleans
FBP_UPPERCASE_ALL  = FBP_ReadBoolDual(FBP_Uppercase_New, FBP_Uppercase_Leg, FBP_UPPERCASE_ALL)

# Numbers / clamps
try:
    FBP_CLOCK_D = max(100, FBP_ReadIntDual(FBP_ClockDiam_New,  FBP_ClockDiam_Leg,  FBP_CLOCK_D))   # min raised to avoid starburst
except: pass
try:
    FBP_LABEL_BOX_MAX_W = max(60, FBP_ReadIntDual(FBP_LabelMaxW_New, FBP_LabelMaxW_Leg, FBP_LABEL_BOX_MAX_W))
except: pass
try:
    fmax = max(12, FBP_ReadIntDual(FBP_LineFontMax_New, FBP_LineFontMax_Leg, FBP_LINE_FONT_MAX))
    fmin = max(22, FBP_ReadIntDual(FBP_LineFontMin_New, FBP_LineFontMin_Leg, FBP_LINE_FONT_MIN))  # legibility baseline
    if fmin > fmax:
        fmin, fmax = fmax, fmin
    FBP_LINE_FONT_MAX = fmax
    FBP_LINE_FONT_MIN = fmin
except: pass

# Behaviour memories used elsewhere:
# Due window minutes / hide clocks when empty / extra ECS / departure TP - use dual readers
FBP_WithinMinutes_Value   = FBP_ReadIntDual(FBP_Within_New,     FBP_Within_Leg,   FBP_DefaultWithinMinutes)
FBP_HideClocksWhenEmpty_Value = FBP_ReadBoolDual(FBP_HideClocks_New, FBP_HideClocks_Leg, False)
FBP_ExtraEcs_Value        = FBP_ReadStrDual(FBP_ExtraEcs_New,   FBP_ExtraEcs_Leg, "")
FBP_DepartTp_Value        = FBP_ReadStrDual(FBP_DepartTp_New,   FBP_DepartTp_Leg, "")

# -------------------- END APPLY USER SETTINGS --------------------

def FBP_ReadUserColor(memBean, defaultColor):
    """
    Read a user-setting colour. If the memory is blank or equals one of the
    global beige placeholders that TASSetup seeds by default, ignore it and
    keep the script's own defaultColor. This restores sensible first-run defaults.
    """
    try:
        v = memBean.getValue() if memBean is not None else None
        s = ("" if v is None else str(v)).strip()
        if s == "":
            return defaultColor
        c = FBP_ParseColor(s, defaultColor)
        # Treat common seeded placeholders as "unset"
        placeholder1 = Color(240, 238, 220)  # Cover colour used by TASSetup
        placeholder2 = Color(249, 246, 238)  # Paper colour used by WTTDisplay/TASSetup
        if ((c.getRed()   == placeholder1.getRed() and c.getGreen() == placeholder1.getGreen() and c.getBlue() == placeholder1.getBlue()) or
            (c.getRed()   == placeholder2.getRed() and c.getGreen() == placeholder2.getGreen() and c.getBlue() == placeholder2.getBlue())):
            return defaultColor
        return c
    except:
        return defaultColor


# -------------------- TIME HELPERS --------------------
FBP_TimeParser24 = SimpleDateFormat("H:mm")
FBP_TimeParser12 = SimpleDateFormat("h:mm a")
FBP_FmtHHmm = SimpleDateFormat("HH:mm")

def FBP_ParseMinutes(s):
    for p in [FBP_TimeParser12, FBP_TimeParser24]:
        try:
            d = p.parse(s); return d.getHours()*60 + d.getMinutes()
        except:
            pass
    return None

def FBP_NormTime(s):
    for p in [FBP_TimeParser12, FBP_TimeParser24]:
        try:
            d = p.parse(s); return FBP_FmtHHmm.format(d)
        except:
            pass
    return None

def FBP_ReadWithinMinutes():
    try:       
        v = None
        try:
            v = FBP_WithInMinMem.getValue() if FBP_WithInMinMem is not None else None
        except: pass
        # Prefer TASSetup value when present
        try:
            v2 = FBP_WithinMinMem2.getValue() if FBP_WithinMinMem2 is not None else None
            s2 = ("" if v2 is None else str(v2)).strip()
            if s2 != "": v = v2
        except: pass
        if v is None: return FBP_DefaultWithinMinutes
        s = str(v).strip()
        if not s: return FBP_DefaultWithinMinutes
        x = int(s)
        if x < 0: return FBP_DefaultWithinMinutes
        return x
    except:
        return FBP_DefaultWithinMinutes

def FBP_ReadHideClocksWhenEmpty():  
    # Prefer TASSetup toggle when present
    try:
        v2 = FBP_HideClocksMem2.getValue() if FBP_HideClocksMem2 is not None else None
        s2 = ("" if v2 is None else str(v2)).strip().lower()
        if s2 in ("true","yes","1","on","y","t"): return True
        if s2 in ("false","no","0","off","n","f"): return False
    except: 
        try:
            v = FBP_HideClocksEmptyMem.getValue() if FBP_HideClocksEmptyMem is not None else None
            if v is None: return False
            s = str(v).strip().lower()
            return s in ("true","yes","1","on","y","t")
        except:
            return False

# -------------------- CSV ACCESS --------------------
def FBP_TimetablePath():
    name = FBP_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")

def FBP_CsvRows():
    path = FBP_TimetablePath()
    if not os.path.exists(path): return []
    try:
        with open(path, "r") as f:
            rdr = FBP_csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []

def FBP_PlatformField(row):
    return (row.get("Plat","") or row.get("Platform","") or "").strip()

def FBP_ParseOverrides(s):
    out = {}
    if not s: return out
    for part in s.replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        k, v = part.split("=",1)
        out[k.strip()] = v.strip()
    return out

def FBP_GetOverride(rn):
    try:
        return FBP_ParseOverrides(FBP_OverridesMem.getValue()).get(rn)
    except:
        return None

# -------------------- DEPARTURE-LOGGING SUPPORT --------------------
def FBP_ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def FBP_DepartureTPList():
    # Merge legacy PID_DEPARTURE_TP and TAS_USER_SETTING_DEPARTURE_TP.
    # If nothing configured, default to the active profile name (one TP).
    names = []

    # Legacy memory (semicolon or comma separated)
    try:
        raw = FBP_DepartTPMem.getValue() if FBP_DepartTPMem is not None else None
        if raw:
            for p in str(raw).replace(",", ";").split(";"):
                t = (p or "").strip()
                if t and t not in names:
                    names.append(t)
    except:
        pass

    # If still empty, fall back to active profile name
    if not names:
        base = FBP_ActiveProfileBaseTPName()
        if base:
            names = [base]

    # TASSetup user setting (semicolon or comma separated) - overrides/augments
    try:
        raw2 = FBP_DepartTpMem2.getValue() if FBP_DepartTpMem2 is not None else None
        if raw2:
            for p in str(raw2).replace(",", ";").split(";"):
                t = (p or "").strip()
                if t and t not in names:
                    names.append(t)
    except:
        pass

    return names

def FBP_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = FBP_DepartureTPList()
    if not tps:
        return False
    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except:
            entries = []
        for rec in entries:
            try:
                rn = rec[0]; tstr = rec[2]; d = rec[3]
            except:
                continue
            if str(rn) != str(reportingNumber): continue
            if str(d)  != str(dayName):        continue
            mm = FBP_ParseMinutes(tstr)
            if mm is None: continue
            if mm <= int(nowMinutes):
                return True
    return False

# -------------------- ECS FILTER (KEYWORDS ONLY) --------------------
FBP_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]

def FBP_ReadExtraEcsTerms():
    # Merge legacy PID_ECS_FILTER_TERMS and TAS_USER_SETTING_EXTRA_ECS_TERMS
    out = []
    # Legacy terms
    try:
        raw = FBP_EcsFilterMem.getValue() if FBP_EcsFilterMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                t = p.strip()
                if t:
                    out.append(t.upper())
    except:
        pass
    # TASSetup terms
    try:
        raw2 = FBP_ExtraEcsMem2.getValue() if FBP_ExtraEcsMem2 is not None else None
        if raw2:
            parts2 = str(raw2).replace(",", ";").split(";")
            for p in parts2:
                t = p.strip()
                if t:
                    out.append(t.upper())
    except:
        pass
    return out

def FBP_IsEcsWorking(row):
    dest = ((row.get("Destination","") or "")).strip().upper()
    call = ((row.get("Calling pattern","") or "")).strip().upper()
    terms = set([t.upper() for t in FBP_DefaultEcsTerms])
    for extra in FBP_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " | " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

# -------------------- NEXT TRAIN FOR A PLATFORM --------------------
def FBP_PickNextTrainForPlatform(platform):
    rows = FBP_CsvRows()

    # "Now" minutes: prefer fast clock, else IMCURRENTTIME
    if FBP_Timebase is not None:
        ft = FBP_Timebase.getTime()
        curMin = ft.getHours()*60 + ft.getMinutes()
    else:
        curStr = FBP_TimeMem.getValue() or ""
        curMin = FBP_ParseMinutes(curStr)
    if curMin is None: return None

    curDay = FBP_DayMem.getValue() or ""
    within = FBP_ReadWithinMinutes()
    cands = []

    for row in rows:
        dep = (row.get("Dep","") or "").strip()
        if not dep:
            continue
        if ((row.get(curDay,"") or "").strip().lower() != "true"):
            continue

        # Platform precedence: allocation register > overrides > timetable
        rn = (row.get("Reporting number","") or "").strip()
        alloc = PAR.getPlatform(rn)
        if alloc is not None and str(alloc).strip():
            plat = str(alloc).strip()
        else:
            plat = FBP_GetOverride(rn) or FBP_PlatformField(row)
        if str(plat) != str(platform):
            continue

        # ECS filter (keywords only)
        if FBP_IsEcsWorking(row):
            continue

        depMin = FBP_ParseMinutes(dep)
        if depMin is None:
            continue

        # Skip past departures
        if depMin < curMin:
            continue

        # Clear-on-departure (skip if already logged as departed)
        if FBP_HasDepartedAtConfiguredTP(rn, curDay, curMin):
            continue

        # Due within X minutes (wrap-safe)
        delta = (depMin - curMin) % (24*60)
        if not (delta == 0 or (0 <= delta <= within)):
            continue

        arr     = (row.get("Arr","") or "").strip()
        calling = (row.get("Calling pattern","") or "").strip()
        dest    = (row.get("Destination","") or "").strip()

        cands.append({
            "rn": rn,
            "arr": FBP_NormTime(arr),
            "dep": FBP_NormTime(dep),
            "calling": calling,
            "dest": dest
        })

    if not cands: return None
    cands.sort(key=lambda t: FBP_ParseMinutes(t["dep"]))
    return cands[0]

# -------------------- DRAWING PANEL --------------------
class FBP_FingerBoardPanel(swing.JPanel):
    def __init__(self, platform):
        super(FBP_FingerBoardPanel, self).__init__()
        self.setOpaque(True); self.setBackground(FBP_BG_COLOR)
        self.platform = str(platform)
        self.model = None   # None => no board to paint (as if not hoisted)
        self.setLayout(None)
        self.setPreferredSize(self.computePreferred())
        # repaint timer
        def _doRepaint(e):
            self.repaint()
        self.repaintTimer = Timer(800, _doRepaint)
        self.repaintTimer.start()
        
        
    # --- cleanup helpers: stop the repaint timer when panel goes away ---
    def stopRepaintTimer(self):
        try:
            if hasattr(self, "repaintTimer") and self.repaintTimer is not None:
                self.repaintTimer.stop()
                self.repaintTimer = None
        except:
            pass

    def removeNotify(self):
        # Called when the component is removed from a container
        try:
            self.stopRepaintTimer()
        finally:
            super(FBP_FingerBoardPanel, self).removeNotify()


    def computePreferred(self):
        boardW = 980
        clocksH = FBP_CLOCK_D + FBP_CLOCK_BLOCK_TOP_G + FBP_MARGIN
        height = FBP_MARGIN + max(FBP_BOARD_TOP + FBP_BOARD_H, FBP_CLOCK_D) + clocksH + FBP_MARGIN
        width  = FBP_MARGIN + FBP_POST_W + FBP_BOARD_LEFT_GAP + boardW + FBP_MARGIN
        return Dimension(width, height)

    def setModel(self, m):
        self.model = m; self.repaint()

    # helpers (fit and wrap)
    def fit_font_to_box(self, g2, family, text, maxW, maxH, maxSize, minSize, bold=True):
        style = Font.BOLD if bold else Font.PLAIN
        best = minSize
        for size in range(minSize, maxSize+1):
            f = Font(family, style, size)
            fm = g2.getFontMetrics(f)
            if fm.stringWidth(text) <= maxW and (fm.getAscent()+fm.getDescent()) <= maxH:
                best = size
            else:
                break
        return Font(family, style, best)

    def wrap_text_to_fit(self, g2, family, maxW, maxH, maxSize, minSize, text):
        paragraphs = (text or "").split("\n")
        def wrap_with_font(font):
            fm = g2.getFontMetrics(font)
            perH = fm.getAscent() + fm.getDescent()
            all_lines = []
            for para in paragraphs:
                words = [w for w in para.split() if w]
                if not words:
                    all_lines.append("")
                    continue
                cur = ""
                for w in words:
                    t = (cur + " " + w).strip()
                    if fm.stringWidth(t) <= maxW or not cur:
                        cur = t
                    else:
                        all_lines.append(cur)
                        cur = w
                if cur:
                    all_lines.append(cur)
            neededH = len(all_lines) * perH
            return all_lines, neededH, perH
        for size in range(maxSize, minSize-1, -1):
            f = Font(family, Font.BOLD, size)
            lines, neededH, perH = wrap_with_font(f)
            if neededH <= maxH:
                return f, lines
        f = Font(family, Font.BOLD, minSize)
        lines, neededH, perH = wrap_with_font(f)
        maxLines = max(1, maxH // perH)
        return f, lines[:maxLines]

    def compose_board_text(self):
        if not self.model: return ""
        items = [s.strip() for s in (self.model.get("calling") or "").split(",") if s.strip()]
        calling_text = FBP_CALLING_SEPARATOR.join(items)
        dest_text = (self.model.get("dest") or "").strip()
        if FBP_UPPERCASE_ALL:
            calling_text = calling_text.upper()
            dest_text = dest_text.upper()
        mode = (FBP_TEXT_MODE or "").upper()
        if mode == "DEST_THEN_CALLING":
            if dest_text and calling_text:
                return dest_text + "\n" + calling_text
            elif dest_text:
                return dest_text
            else:
                return calling_text
        return calling_text

    # clock drawing
    def draw_hand_arrow(self, g2, x1, y1, x2, y2, head_len=8):
        g2.drawLine(x1, y1, x2, y2)
        import math
        ang = math.atan2(y2-y1, x2-x1)
        left  = (int(x2 - head_len*math.cos(ang) + (head_len/2)*math.sin(ang)),
                 int(y2 - head_len*math.sin(ang) - (head_len/2)*math.cos(ang)))
        right = (int(x2 - head_len*math.cos(ang) - (head_len/2)*math.sin(ang)),
                 int(y2 - head_len*math.sin(ang) + (head_len/2)*math.cos(ang)))
        poly = awt.Polygon()
        poly.addPoint(x2, y2); poly.addPoint(left[0], left[1]); poly.addPoint(right[0], right[1])
        g2.fillPolygon(poly)

    def draw_roman_clock(self, g2, cx, cy, d, label, timeText, label_side):
        r = d//2
        g2.setColor(FBP_CLOCK_FACE); g2.fillOval(cx - r, cy - r, d, d)
        g2.setColor(FBP_CLOCK_EDGE); g2.setStroke(BasicStroke(3.0)); g2.drawOval(cx - r, cy - r, d, d)
        romans = ["XII","I","II","III","IV","V","VI","VII","VIII","IX","X","XI"]
        inner = r - 26
        maxArcW = int(2*3.14159*(inner)/12 * 0.85)
        size = 16
        while size > 10:
            ftest = Font(FBP_TYPEFACE_NUMERALS, Font.BOLD, size)
            w = max([g2.getFontMetrics(ftest).stringWidth(s) for s in romans])
            if w <= maxArcW: break
            size -= 1
        g2.setFont(Font(FBP_TYPEFACE_NUMERALS, Font.BOLD, size))
        fm = g2.getFontMetrics()
        import math
        for i in range(12):
            a = math.radians(i*30)
            rx = int(cx + inner*math.sin(a))
            ry = int(cy - inner*math.cos(a))
            s = romans[i]
            g2.setColor(FBP_CLOCK_EDGE)
            g2.drawString(s, rx - g2.getFontMetrics().stringWidth(s)//2, ry + fm.getAscent()//2 - 2)
        for i in range(60):
            a = math.radians(i*6)
            if i % 5 == 0:
                x1 = int(cx + (r-12)*math.sin(a)); y1 = int(cy - (r-12)*math.cos(a))
                x2 = int(cx + (r-6)*math.sin(a));  y2 = int(cy - (r-6)*math.cos(a))
                g2.setColor(FBP_CLOCK_TICK); g2.setStroke(BasicStroke(2.2))
                g2.drawLine(x1,y1,x2,y2)
            else:
                x = int(cx + (r-8)*math.sin(a)); y = int(cy - (r-8)*math.cos(a))
                g2.setColor(Color(150,150,150)); g2.fillOval(x-1,y-1,2,2)
        if timeText:
            try:
                t = FBP_TimeParser24.parse(timeText)
                h = t.getHours() % 12
                m = t.getMinutes()
                min_a = __import__("math").radians(m*6.0)
                hr_a  = __import__("math").radians(h*30.0 + m*0.5)
                g2.setColor(FBP_CLOCK_HAND)
                g2.setStroke(BasicStroke(3.0))
                mx = int(cx + (r-20)*__import__("math").sin(min_a))
                my = int(cy - (r-20)*__import__("math").cos(min_a))
                self.draw_hand_arrow(g2, cx, cy, mx, my, head_len=7)
                g2.setStroke(BasicStroke(4.8))
                hx = int(cx + (r-34)*__import__("math").sin(hr_a))
                hy = int(cy - (r-34)*__import__("math").cos(hr_a))
                self.draw_hand_arrow(g2, cx, cy, hx, hy, head_len=8)
                g2.fillOval(cx-3, cy-3, 6, 6)
            except:
                pass
        # label box
        boxH = FBP_LABEL_BOX_H
        if label_side == "left":
            maxW = (cx - r) - (FBP_MARGIN + FBP_POST_W) - 2*FBP_LABEL_BOX_PAD_TXT
            boxW = min(FBP_LABEL_BOX_MAX_W, max(60, maxW))
            bx = (FBP_MARGIN + FBP_POST_W) + FBP_LABEL_BOX_PAD_TXT
            by = cy - boxH//2
        else:
            maxW = (self.getWidth() - FBP_MARGIN) - (cx + r) - 2*FBP_LABEL_BOX_PAD_TXT
            boxW = min(FBP_LABEL_BOX_MAX_W, max(60, maxW))
            bx = self.getWidth() - FBP_MARGIN - FBP_LABEL_BOX_PAD_TXT - boxW
            by = cy - boxH//2
        g2.setColor(FBP_LABEL_BOX_FILL); g2.fillRoundRect(bx, by, boxW, boxH, 8,8)
        g2.setColor(FBP_LABEL_BOX_EDGE); g2.setStroke(BasicStroke(2.0))
        inset = FBP_LABEL_BOX_INSET
        g2.drawRoundRect(bx+inset, by+inset, boxW-2*inset, boxH-2*inset, 6,6)
        label_txt = label.upper()
        f = self.fit_font_to_box(g2, FBP_TYPEFACE_PRIMARY, label_txt,
                                 boxW-2*FBP_LABEL_BOX_PAD_TXT, boxH-2*FBP_LABEL_BOX_PAD_TXT,
                                 FBP_LABEL_FONT_MAX, FBP_LABEL_FONT_MIN, bold=True)
        g2.setFont(f); g2.setColor(FBP_TEXT_COLOR)
        fmL = g2.getFontMetrics()
        tx = bx + (boxW - fmL.stringWidth(label_txt))//2
        ty = by + (boxH + fmL.getAscent() - fmL.getDescent())//2
        g2.drawString(label_txt, tx, ty)

    def paintComponent(self, g):
        super(FBP_FingerBoardPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()

        # Post (always present)
        postX = FBP_MARGIN; postY = FBP_MARGIN; postH = H - 2*FBP_MARGIN
        g2.setPaint(GradientPaint(postX, postY, FBP_POST_COLOR, postX+FBP_POST_W, postY, FBP_POST_SHADE))
        g2.fillRoundRect(postX, postY, FBP_POST_W, postH, FBP_POST_RADIUS, FBP_POST_RADIUS)

        # Board/clock layout refs
        boardX = postX + FBP_POST_W + FBP_BOARD_LEFT_GAP
        boardY = FBP_MARGIN + FBP_BOARD_TOP
        boardW = W - boardX - FBP_MARGIN

        # Draw plank + text only if a model exists
        if self.model is not None:
            rectW  = max(100, boardW - FBP_CAP_RADIUS)
            plank  = Area(RoundRectangle2D.Float(boardX, boardY, rectW, FBP_BOARD_H, 6, 6))
            cap    = Area(Ellipse2D.Float(boardX + rectW - FBP_CAP_RADIUS, boardY, 2*FBP_CAP_RADIUS, FBP_BOARD_H))
            plank.add(cap)
            g2.setColor(FBP_BOARD_FILL); g2.fill(plank)
            g2.setColor(FBP_BOARD_EDGE); g2.setStroke(FBP_OUTLINE_STROKE); g2.draw(plank)
            textL = boardX + FBP_LEFT_PAD
            textR = boardX + boardW - FBP_RIGHT_PAD
            textW = max(50, textR - textL)
            textT = boardY + 10
            textH = FBP_BOARD_H - 20
            board_text = self.compose_board_text()
            f, lines = self.wrap_text_to_fit(g2, FBP_TYPEFACE_PRIMARY, textW, textH,
                                             FBP_LINE_FONT_MAX, FBP_LINE_FONT_MIN, board_text)
            g2.setColor(FBP_TEXT_COLOR); g2.setFont(f)
            fm = g2.getFontMetrics()
            y = textT + fm.getAscent()
            for ln in lines:
                g2.drawString(ln, textL, y)
                y += (fm.getAscent()+fm.getDescent())

        # Clocks + labels (optionally hidden when empty)
        hideClocksWhenEmpty = FBP_ReadHideClocksWhenEmpty()
        clocksW = 2*FBP_CLOCK_D + FBP_CLOCK_PAIR_GAP
        cx1 = boardX + (boardW - clocksW)//2 + FBP_CLOCK_D//2
        cx2 = cx1 + FBP_CLOCK_D + FBP_CLOCK_PAIR_GAP
        cy  = boardY + FBP_BOARD_H + FBP_CLOCK_BLOCK_TOP_G + FBP_CLOCK_D//2

        if (self.model is None) and hideClocksWhenEmpty:
            # When empty and toggle is on: draw no clocks at all
            return

        arrTxt = self.model["arr"] if (self.model and self.model["arr"]) else None
        depTxt = self.model["dep"] if (self.model and self.model["dep"]) else None
        self.draw_roman_clock(g2, cx1, cy, FBP_CLOCK_D, "ARR", arrTxt, label_side="left")
        self.draw_roman_clock(g2, cx2, cy, FBP_CLOCK_D, "DEP", depTxt, label_side="right")

# -------------------- WINDOW PER PLATFORM --------------------
class FBP_FingerBoardWindow(object):
    def __init__(self, platform):
        self.platform = str(platform)
        self.panel = FBP_FingerBoardPanel(self.platform)
        preferred = self.panel.getPreferredSize()
        self.frame = swing.JFrame("Finger board - Platform " + self.platform)
        cp = self.frame.getContentPane()
        cp.setLayout(None); cp.setBackground(FBP_BG_COLOR)
        cp.setPreferredSize(preferred)
        self.panel.setBounds(0,0, preferred.width, preferred.height)
        cp.add(self.panel)
        self.frame.pack()     
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTFingerboard] Failed to set PID window icon: " + str(ex))
       
        self.frame.setResizable(False)
        self.frame.setVisible(True)     
        
        # Ensure closing the window disposes it and triggers cleanup
        self.frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)

        # Correct import for WindowAdapter (java.awt.event, not javax.swing.event)
        from java.awt.event import WindowAdapter

        class CloseListener(WindowAdapter):
            def __init__(self, owner):
                self.owner = owner
            def windowClosed(self, e):
                try:
                    self.owner.onWindowClosed()
                except:
                    pass
            def windowClosing(self, e):
                try:
                    self.owner.onWindowClosed()
                except:
                    pass

        self.frame.addWindowListener(CloseListener(self))

        # listeners
        FBP_TimeMem.addPropertyChangeListener(self.refresh)
        FBP_DayMem.addPropertyChangeListener(self.refresh)
        if FBP_TimetableMem is not None: FBP_TimetableMem.addPropertyChangeListener(self.refresh)
        if FBP_OverridesMem is not None: FBP_OverridesMem.addPropertyChangeListener(self.refresh)
        if FBP_DepartTPMem is not None: FBP_DepartTPMem.addPropertyChangeListener(self.refresh)
        if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.addPropertyChangeListener(self.refresh)
        if FBP_WithInMinMem is not None: FBP_WithInMinMem.addPropertyChangeListener(self.refresh)
        if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.addPropertyChangeListener(self.refresh)
           
        # --- Listen to TASSetup user-setting memories as well ---       
        for m in [
            FBP_TextModeMem, FBP_CallSepMem, FBP_DestJoinMem, FBP_UppercaseMem,
            FBP_WithinMinMem2, FBP_HideClocksMem2, FBP_ExtraEcsMem2, FBP_DepartTpMem2,
            FBP_TextColorMem, FBP_BoardFillMem, FBP_BoardEdgeMem, FBP_ClockFaceMem,
            FBP_ClockHandMem, FBP_LabelFillMem, FBP_LabelEdgeMem, FBP_BackgroundMem,
            FBP_ClockDiamMem, FBP_LabelMaxWMem, FBP_LineFontMaxMem, FBP_LineFontMinMem,
        ]:
            try:
                if m is not None:
                    m.addPropertyChangeListener(self.refresh)
            except:
                pass

        # Also refresh immediately on platform allocation register events
        try:
            PAR.addPlatformListener(self.refresh)
        except Exception as ex:
            try:
                print("[PIDFingerboard] Failed to add platform allocation listener:", ex)
            except:
                pass

        self.refresh()

    def refresh(self, e=None):
        m = FBP_PickNextTrainForPlatform(self.platform)
        self.panel.setModel(m)

    def cleanup(self):   
        # Stop the repaint timer even when cleanup is called programmatically
        try:
            self.panel.stopRepaintTimer()
        except:
            pass
        try: 
            FBP_TimeMem.removePropertyChangeListener(self.refresh)
        except: pass
        try: 
            FBP_DayMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_TimetableMem is not None: FBP_TimetableMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_OverridesMem is not None: FBP_OverridesMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_DepartTPMem is not None: FBP_DepartTPMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_WithInMinMem is not None: FBP_WithInMinMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.removePropertyChangeListener(self.refresh)
        except: pass       
        # --- remove TASSetup user-setting listeners ---
        for m in [
            FBP_TextModeMem, FBP_CallSepMem, FBP_DestJoinMem, FBP_UppercaseMem,
            FBP_WithinMinMem2, FBP_HideClocksMem2, FBP_ExtraEcsMem2, FBP_DepartTpMem2,
            FBP_TextColorMem, FBP_BoardFillMem, FBP_BoardEdgeMem, FBP_ClockFaceMem,
            FBP_ClockHandMem, FBP_LabelFillMem, FBP_LabelEdgeMem, FBP_BackgroundMem,
            FBP_ClockDiamMem, FBP_LabelMaxWMem, FBP_LineFontMaxMem, FBP_LineFontMinMem
        ]:
            try:
                if m is not None:
                    m.removePropertyChangeListener(self.refresh)
            except:
                pass
        # Remove platform allocation listener
        try:
            PAR.removePlatformListener(self.refresh)
        except:
            pass
     
    def onWindowClosed(self):
        # Called by the window listener for both 'closing' and 'closed' events
        try:
            self.panel.stopRepaintTimer()
        except:
            pass
        self.cleanup()
        # Remove from manager to allow GC and prevent stale references
        try:
            if 'FBP_Manager' in globals() and FBP_Manager is not None:
                try:
                    FBP_Manager.handleWindowClosed(self.platform)
                except:
                    pass
        except:
            pass

# -------------------- MANAGER - windows per platform --------------------
def FBP_DetectPlatforms():
    plats = set()
    for r in FBP_CsvRows():
        p = FBP_PlatformField(r)
        if p: plats.add(str(p))
    return sorted(plats, key=lambda x:(x.isdigit(), int(x) if x.isdigit() else x))

class FBP_PlatformFingerBoards(object):
    def __init__(self):
        self.windows = {}
        if FBP_TimetableMem is not None: FBP_TimetableMem.addPropertyChangeListener(self.rebuild)
        if FBP_OverridesMem is not None: FBP_OverridesMem.addPropertyChangeListener(self.refresh_all)
        if FBP_DepartTPMem is not None:  FBP_DepartTPMem.addPropertyChangeListener(self.refresh_all)
        if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.addPropertyChangeListener(self.refresh_all)
        if FBP_WithInMinMem is not None: FBP_WithInMinMem.addPropertyChangeListener(self.refresh_all)
        if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.addPropertyChangeListener(self.refresh_all)
        
        # Also refresh all boards on any TASSetup option update
        for m in [
            FBP_TextModeMem, FBP_CallSepMem, FBP_DestJoinMem, FBP_UppercaseMem,
            FBP_WithinMinMem2, FBP_HideClocksMem2, FBP_ExtraEcsMem2, FBP_DepartTpMem2,
            FBP_TextColorMem, FBP_BoardFillMem, FBP_BoardEdgeMem, FBP_ClockFaceMem,
            FBP_ClockHandMem, FBP_LabelFillMem, FBP_LabelEdgeMem, FBP_BackgroundMem,
            FBP_ClockDiamMem, FBP_LabelMaxWMem, FBP_LineFontMaxMem, FBP_LineFontMinMem
        ]:
            try:
                if m is not None:
                    m.addPropertyChangeListener(self.refresh_all)
            except:
                pass

        self.build()

    def build(self):
        plats = FBP_DetectPlatforms()
        for p in plats:
            if p not in self.windows:
                self.windows[p] = FBP_FingerBoardWindow(p)
        for p in [x for x in list(self.windows.keys()) if x not in plats]:
            try:
                self.windows[p].cleanup(); self.windows[p].frame.dispose()
            except:
                pass
            del self.windows[p]
        # cascade
        x0,y0,dx,dy = 40,40, 22,22
        for i,p in enumerate(self.windows.keys()):
            self.windows[p].frame.setLocation(x0 + dx*i, y0 + dy*i)

    def rebuild(self, e=None):
        self.build(); self.refresh_all()

    def refresh_all(self, e=None):
        for w in self.windows.values():
            w.refresh()
               
    def handleWindowClosed(self, platform):
        # Remove the window entry when its frame has been closed
        try:
            key = str(platform)
            w = self.windows.get(key)
            if w is not None:
                try:
                    w.cleanup()  # idempotent
                except:
                    pass
                del self.windows[key]
        except:
            pass

# -------------------- RUN --------------------
FBP_Manager = FBP_PlatformFingerBoards()