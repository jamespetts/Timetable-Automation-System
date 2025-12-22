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
# - All globals, classes, helpers prefixed with NSECLK_ to avoid shadowing
# - Exact visual/behavioural parity with your original (fonts, sizes, layout)
#
# <<PID-DISP-NAME: Network SouthEast clock>>
# <<DESCRIPTION: The mechanical/digital clocks installed by Network SouthEast in the 1980s>>

import javax.swing as swing
import java.awt as awt
import java.util as java_util
import jmri
from java.awt import GraphicsEnvironment, RenderingHints, Font
from java.io import File, FileInputStream
import os

# ----------------------- CONFIG -----------------------
# Either leave as None and place "digital-7 (mono).ttf" next to this script,
# or set an absolute path here:
NSECLK_Digital7TtfOverride = None  # e.g., r"C:\Users\James\Downloads\digital-7 (mono).ttf"

# Candidate locations (searched if override is None and not in script folder)
NSECLK_CandidateTtfPaths = [
    r"C:\Windows\Fonts\digital-7 (mono).ttf",
    r"C:\Windows\Fonts\DIGITAL-7 (MONO).TTF",
    r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\digital-7 (mono).ttf",
    r"/Library/Fonts/digital-7 (mono).ttf",
    r"/usr/share/fonts/truetype/digital-7 (mono).ttf",
    r"/usr/local/share/fonts/digital-7 (mono).ttf",
]

# ----------------------- COLORS -----------------------
NSECLK_RedFrame   = awt.Color(200, 0, 0)
NSECLK_BlackPanel = awt.Color(0, 0, 0)
NSECLK_Yellow     = awt.Color(255, 220, 35)
NSECLK_RedDigits  = awt.Color(220, 30, 30)
NSECLK_GrayStrip  = awt.Color(190, 190, 190)
NSECLK_Blue       = awt.Color(0, 100, 190)
NSECLK_White      = awt.Color(255, 255, 255)
NSECLK_LogoRed    = awt.Color(190, 20, 20)

def NSECLK_Log(msg):
    print("[NSEClock] " + msg)

def NSECLK_Expand(path):
    if path is None:
        return None
    try:
        return os.path.expandvars(os.path.expanduser(path))
    except:
        return path

def NSECLK_FileBesideScript(name):
    try:
        here = os.getcwd()
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    except:
        pass
    return None

def NSECLK_LoadDigital7TTF():
    """
    Return a created Font from the actual TTF if found, else None.
    Prefer direct TTF loading so Java will not substitute another family.
    """
    # 1) Explicit override path
    if NSECLK_Digital7TtfOverride:
        p = NSECLK_Expand(NSECLK_Digital7TtfOverride)
        if p and os.path.exists(p):
            f = File(p)
            try:
                NSECLK_Log("Loading TTF (override): %s" % p)
                fis = FileInputStream(f)
                try:
                    font = Font.createFont(Font.TRUETYPE_FONT, fis)
                    return font
                finally:
                    fis.close()
            except Exception as e:
                NSECLK_Log("Failed to load override TTF: %s" % e)

    # 2) File next to script / working dir
    local = NSECLK_FileBesideScript("digital-7 (mono).ttf")
    if local:
        try:
            NSECLK_Log("Loading TTF (script folder): %s" % local)
            fis = FileInputStream(File(local))
            try:
                return Font.createFont(Font.TRUETYPE_FONT, fis)
            finally:
                fis.close()
        except Exception as e:
            NSECLK_Log("Failed to load TTF from script folder: %s" % e)

    # 3) Known system locations (including per-user Windows Fonts)
    for raw in NSECLK_CandidateTtfPaths:
        p = NSECLK_Expand(raw)
        if p and os.path.exists(p):
            try:
                NSECLK_Log("Loading TTF (candidate): %s" % p)
                fis = FileInputStream(File(p))
                try:
                    return Font.createFont(Font.TRUETYPE_FONT, fis)
                finally:
                    fis.close()
            except Exception as e:
                NSECLK_Log("Failed to load candidate TTF %s: %s" % (p, e))
    return None

def NSECLK_InstalledDigitalFamily():
    try:
        fams = list(GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames())
        lookup = {f.lower(): f for f in fams}
        for nm in ["digital-7 mono", "digital 7 mono", "digital-7", "digital 7"]:
            f = lookup.get(nm)
            if f:
                return f
        for f in fams:
            l = f.lower()
            if ("digital" in l) and ("mono" in l):
                return f
    except Exception as e:
        NSECLK_Log("Font enumeration failed: %s" % e)
    return None

def NSECLK_GetFonts():
    """
    Returns (fontHM, fontSec) already sized (168pt, 84pt) using Digital-7 mono if possible.
    Falls back to Monospaced Bold if not found.
    """
    created = NSECLK_LoadDigital7TTF()
    if created is not None:
        hm = created.deriveFont(awt.Font.PLAIN, float(168.0))
        sec = created.deriveFont(awt.Font.PLAIN, float(84.0))
        NSECLK_Log("Using TTF font: family='%s', name='%s', PS='%s'" %
                   (hm.getFamily(), hm.getFontName(), hm.getPSName()))
        return hm, sec
    fam = NSECLK_InstalledDigitalFamily()
    if fam:
        hm = awt.Font(fam, awt.Font.PLAIN, 168)
        sec = awt.Font(fam, awt.Font.PLAIN, 84)
        NSECLK_Log("Using installed family: %s" % fam)
        return hm, sec
    NSECLK_Log("Digital-7 TTF not found; using Monospaced Bold fallback.")
    return awt.Font("Monospaced", awt.Font.BOLD, 168), awt.Font("Monospaced", awt.Font.BOLD, 84)

# ----------------------- Custom HH:MM component -----------------------
class NSECLK_HMView(swing.JComponent):
    def __init__(self, text="00:00", font=None, fg=NSECLK_Yellow, bg=NSECLK_BlackPanel):
        swing.JComponent.__init__(self)
        self._text = text
        self._font = font if font is not None else awt.Font("Monospaced", awt.Font.BOLD, 168)
        self._fg = fg
        self._bg = bg
        self._pref = awt.Dimension(430, 170)  # exact original size
        self.setOpaque(True)
    def setFont(self, f): self._font = f
    def getFont(self): return self._font
    def setText(self, t):
        if t != self._text:
            self._text = t
            self.repaint()
    def getPreferredSize(self): return self._pref
    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self._bg); g.fillRect(0, 0, self.getWidth(), self.getHeight())
        try:
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass
        text = self._text
        base = self._font
        fm = self.getFontMetrics(base)
        pad = 6
        avail = max(0, self.getWidth() - 2*pad)
        draw = base
        width = fm.stringWidth(text)
        if width > avail and avail > 0:
            scale = float(avail) / float(width)
            new_pt = max(12.0, base.getSize2D() * scale * 0.995)
            draw = base.deriveFont(new_pt)
            fm = self.getFontMetrics(draw)
            width = fm.stringWidth(text)
        x = (self.getWidth() - width) // 2
        y = (self.getHeight() + fm.getAscent() - fm.getDescent()) // 2
        g.setColor(self._fg)
        g.setFont(draw)
        g.drawString(text, x, y)

# ----------------------- Frame & Panels (unchanged sizes) -----------------------
NSECLK_Frame = swing.JFrame("Network SouthEast Clock")
NSECLK_Frame.defaultCloseOperation = swing.JFrame.DISPOSE_ON_CLOSE
NSECLK_Frame.getContentPane().setBackground(NSECLK_RedFrame)
NSECLK_Frame.getContentPane().setLayout(awt.BorderLayout())

NSECLK_OuterPanel = swing.JPanel()
NSECLK_OuterPanel.setBackground(NSECLK_RedFrame)
NSECLK_OuterPanel.setOpaque(True)
NSECLK_OuterPanel.setLayout(awt.BorderLayout())
NSECLK_OuterPanel.setBorder(swing.BorderFactory.createEmptyBorder(4, 6, 4, 6))  # original surround

NSECLK_ClockPanel = swing.JPanel()
NSECLK_ClockPanel.setBackground(NSECLK_BlackPanel)
NSECLK_ClockPanel.setOpaque(True)
NSECLK_ClockPanel.setLayout(awt.FlowLayout(awt.FlowLayout.CENTER, 6, 4))  # original gaps
NSECLK_ClockPanel.setPreferredSize(awt.Dimension(620, 180))
NSECLK_ClockPanel.setBorder(swing.BorderFactory.createLineBorder(NSECLK_BlackPanel, 2))

# Fonts
NSECLK_FontHM, NSECLK_FontSec = NSECLK_GetFonts()

# HH:MM custom painter + seconds label (original sizes)
NSECLK_HmView = NSECLK_HMView(font=NSECLK_FontHM, fg=NSECLK_Yellow, bg=NSECLK_BlackPanel)
NSECLK_LabelSec = swing.JLabel("00", swing.JLabel.CENTER)
NSECLK_LabelSec.setForeground(NSECLK_RedDigits)
NSECLK_LabelSec.setFont(NSECLK_FontSec)
NSECLK_LabelSec.setBackground(NSECLK_BlackPanel)
NSECLK_LabelSec.setOpaque(True)
NSECLK_LabelSec.setPreferredSize(awt.Dimension(110, 170))  # original

NSECLK_ClockPanel.add(NSECLK_HmView)
NSECLK_ClockPanel.add(NSECLK_LabelSec)

# Logo panel (unchanged)
class NSECLK_LogoPanel(swing.JPanel):
    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self.getBackground()); g.fillRect(0, 0, self.getWidth(), self.getHeight())
        w = self.getWidth(); h = self.getHeight()
        if w <= 0 or h <= 0: return
        grayHeight = int(h * 0.55)
        g.setColor(NSECLK_GrayStrip); g.fillRect(0, 0, w, grayHeight)
        blockWidth = min(420, int(w * 0.6)); blockLeft = (w - blockWidth) // 2
        stripeW = 36; num = int(blockWidth / stripeW) + 4; blockBottom = h
        for i in range(-2, num):
            x = blockLeft + i * stripeW
            pts_x = [x, x + stripeW, x + stripeW + stripeW//2, x + stripeW//2]
            pts_y = [blockBottom, blockBottom, int(grayHeight), int(grayHeight)]
            g.setColor(NSECLK_Blue); g.fillPolygon(awt.Polygon(pts_x, pts_y, 4))
            g.setColor(NSECLK_White); g.fillPolygon(awt.Polygon(
                [x + stripeW, x + stripeW*2, x + stripeW*2 + stripeW//2, x + stripeW + stripeW//2], pts_y, 4))
            g.setColor(NSECLK_LogoRed); g.fillPolygon(awt.Polygon(
                [x + stripeW*2, x + stripeW*3, x + stripeW*3 + stripeW//2, x + stripeW*2 + stripeW//2], pts_y, 4))

NSECLK_Logo = NSECLK_LogoPanel()
NSECLK_Logo.setPreferredSize(awt.Dimension(620, 48))
NSECLK_Logo.setBackground(NSECLK_RedFrame)
NSECLK_Logo.setOpaque(True)

# Assemble
NSECLK_Content = swing.JPanel(awt.BorderLayout())
NSECLK_Content.setOpaque(False)
NSECLK_Content.add(NSECLK_ClockPanel, awt.BorderLayout.CENTER)
NSECLK_Content.add(NSECLK_Logo, awt.BorderLayout.SOUTH)

NSECLK_OuterPanel.add(NSECLK_Content, awt.BorderLayout.CENTER)
NSECLK_Frame.getContentPane().add(NSECLK_OuterPanel, awt.BorderLayout.CENTER)
NSECLK_Frame.pack()

# Set window icon using TASIcon utility
try:
    from TASIcon import SetFrameClockIcon
    SetFrameClockIcon(NSECLK_Frame, 32)  # 32px icon size
except Exception as ex:
    NSECLK_Log("Failed to set NSE clock window icon: " + str(ex))

NSECLK_Frame.setLocationRelativeTo(None)
NSECLK_Frame.setVisible(True)

# ----------------------- Time helper (as original) -----------------------
def NSECLK_GetHmsFromTimebase():
    try:
        tb = jmri.InstanceManager.getDefault(jmri.Timebase)
        t = tb.getTime()
        if isinstance(t, java_util.Date):
            cal = java_util.Calendar.getInstance(); cal.setTime(t)
            return (cal.get(java_util.Calendar.HOUR_OF_DAY),
                    cal.get(java_util.Calendar.MINUTE),
                    cal.get(java_util.Calendar.SECOND))
        hh = getattr(t, "hours", None)
        mm = getattr(t, "minutes", None)
        ss = getattr(t, "seconds", None)
        if hh is not None:
            return int(hh), int(mm), int(ss)
        parts = str(t).split(':')
        if len(parts) >= 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
    except:
        pass
    now = java_util.Date(); cal = java_util.Calendar.getInstance(); cal.setTime(now)
    return (cal.get(java_util.Calendar.HOUR_OF_DAY),
            cal.get(java_util.Calendar.MINUTE),
            cal.get(java_util.Calendar.SECOND))

# ----------------------- Update (minute-only for HH:MM) -----------------------
NSECLK_LastHM = [None]

def NSECLK_UpdateClock(event=None):
    hh, mm, ss = NSECLK_GetHmsFromTimebase()
    hm = "%02d:%02d" % (hh, mm)
    if hm != NSECLK_LastHM[0]:
        NSECLK_HmView.setText(hm)
        NSECLK_LastHM[0] = hm
        f = NSECLK_HmView.getFont()
        NSECLK_Log("HM font in use — family: '%s', name: '%s', PS: '%s', size: %spt"
                   % (f.getFamily(), f.getFontName(), f.getPSName(), f.getSize()))
    NSECLK_LabelSec.setText("%02d" % ss)

NSECLK_Timer = swing.Timer(1000, NSECLK_UpdateClock)
NSECLK_Timer.setInitialDelay(0)
NSECLK_Timer.start()
NSECLK_UpdateClock()