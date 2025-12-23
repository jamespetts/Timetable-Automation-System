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

# <<SETTING DESCRIPTION: Debranded>>
TAS_USER_SETTING_Debranded = False  # When True: (1) plain red logo strip; (2) seconds digits use NSECLK_Yellow

# Read persisted value (if any) via TASBeanLookup (prefix-agnostic)
try:
    import TASBeanLookup as TBL
    _val = TBL.SafeGetOrCreateMemoryValue("DISPLAYOPT_NSECLOCK_DEBRANDED", "false")
except Exception:
    pass
    _t = str(_val).strip().lower()


# --------------------- VISUAL ADJUSTMENT PARAMETERS (pixel offsets) ---------------------
# Pixel offsets
# Positive X moves right; positive Y moves down.
NSECLK_SecPaintOffsetX = 8
NSECLK_SecPaintOffsetY = 10
NSECLK_DotOffsetX = 0
NSECLK_DotOffsetY = 10
NSECLK_DotRadius = 4

# Height of the black digit area (ClockPanel will be vertically centered within this).
# Increase this to add equal black padding above and below the digits without changing their layout.
NSECLK_ClockHolderHeight = 175

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
        self._pref = awt.Dimension(470, 140)
        self.setOpaque(True)

    def setFont(self, f):
        self._font = f

    def getFont(self):
        return self._font

    def setText(self, t):
        if t != self._text:
            self._text = t
            self.repaint()

    def getPreferredSize(self):
        return self._pref

    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self._bg)
            g.fillRect(0, 0, self.getWidth(), self.getHeight())

        try:
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING,
                               RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                               RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        text = self._text
        base = self._font
    
        padX = 6
        padY = 2

        availW = max(1, self.getWidth() - 2 * padX)
        availH = max(1, self.getHeight() - 2 * padY)

        fmBase = self.getFontMetrics(base)
        textW = max(1, fmBase.stringWidth(text))
        textH = max(1, fmBase.getAscent() + fmBase.getDescent())

        scaleW = float(availW) / float(textW)
        scaleH = float(availH) / float(textH)
        scale = min(scaleW, scaleH) * 0.98

        newPt = max(12.0, base.getSize2D() * scale)
        draw = base.deriveFont(float(newPt))
     
        # Centre using glyph visual bounds; FontMetrics ascent/descent can mis-center this font visually.
        try:
            frc = g.getFontRenderContext()
            gv = draw.createGlyphVector(frc, text)
            vb = gv.getVisualBounds()

            x = padX + int((availW - vb.getWidth()) / 2.0 - vb.getX())
            y = padY + int((availH - vb.getHeight()) / 2.0 - vb.getY())

            g.setColor(self._fg)
            g.drawGlyphVector(gv, float(x), float(y))
        except:
            fm = self.getFontMetrics(draw)
            drawW = fm.stringWidth(text)
            x = padX + (availW - drawW) // 2
            textBoxH = fm.getAscent() + fm.getDescent()
            y = padY + (availH - textBoxH) // 2 + fm.getAscent()
            g.setColor(self._fg)
            g.setFont(draw)
            g.drawString(text, x, y)


class NSECLK_SecView(swing.JComponent):
    def __init__(self, text="00", font=None, fg=NSECLK_RedDigits, bg=NSECLK_BlackPanel):
        swing.JComponent.__init__(self)
        self._text = text
        self._font = font if font is not None else awt.Font("Monospaced", awt.Font.BOLD, 84)
        self._fg = fg
        self._bg = bg
        self._pref = awt.Dimension(140, 140)
        self.setOpaque(True)

    def setFont(self, f):
        self._font = f

    def getFont(self):
        return self._font

    def setText(self, t):
        if t != self._text:
            self._text = t
            self.repaint()

    def getPreferredSize(self):
        return self._pref

    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self._bg)
            g.fillRect(0, 0, self.getWidth(), self.getHeight())

        try:
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING,
                               RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                               RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        text = self._text
        base = self._font

        # Smaller padding than before so the digits fill the window better
        padX = 6
        padY = 2

        availW = max(1, self.getWidth() - 2 * padX)
        availH = max(1, self.getHeight() - 2 * padY)

        fmBase = self.getFontMetrics(base)
        textW = max(1, fmBase.stringWidth(text))
        textH = max(1, fmBase.getAscent() + fmBase.getDescent())

        scaleW = float(availW) / float(textW)
        scaleH = float(availH) / float(textH)
        scale = min(scaleW, scaleH) * 0.995

        newPt = max(12.0, base.getSize2D() * scale)
        draw = base.deriveFont(float(newPt))

        # Centre using glyph visual bounds; FontMetrics ascent/descent can mis-center this font visually.
        try:
            frc = g.getFontRenderContext()
            gv = draw.createGlyphVector(frc, text)
            vb = gv.getVisualBounds()
         
            x = padX + int((availW - vb.getWidth()) / 2.0 - vb.getX())
            y = padY + int((availH - vb.getHeight()) / 2.0 - vb.getY())

            # Offset seconds to match the real clock positioning.
            x += NSECLK_SecPaintOffsetX
            y += NSECLK_SecPaintOffsetY

            g.setColor(self._fg)
            g.drawGlyphVector(gv, float(x), float(y))
        except:
            fm = self.getFontMetrics(draw)          
            drawW = fm.stringWidth(text)
            x = padX + (availW - drawW) // 2
            textBoxH = fm.getAscent() + fm.getDescent()
            y = padY + (availH - textBoxH) // 2 + fm.getAscent()

            # Offset seconds to match the prototype positioning.
            x += NSECLK_SecPaintOffsetX
            y += NSECLK_SecPaintOffsetY

            g.setColor(self._fg)
            g.setFont(draw)
            g.drawString(text, x, y)


class NSECLK_MinSecDotView(swing.JComponent):
    def __init__(self, fg=NSECLK_Yellow, bg=NSECLK_BlackPanel):
        swing.JComponent.__init__(self)
        self._fg = fg
        self._bg = bg
        self._pref = awt.Dimension(18, 140)
        self.setOpaque(True)

    def getPreferredSize(self):
        return self._pref

    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self._bg)
            g.fillRect(0, 0, self.getWidth(), self.getHeight())

        try:
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        # Draw a single dot with a small offset to match the prototype.
        w = self.getWidth()
        h = self.getHeight()
        r = NSECLK_DotRadius
        cx = (w // 2) + NSECLK_DotOffsetX
        cy = (h // 2) + NSECLK_DotOffsetY
        g.setColor(self._fg)
        g.fillOval(cx - r, cy - r, 2 * r, 2 * r)

# ----------------------- Frame & Panels -----------------------
NSECLK_Frame = swing.JFrame("Clock" if TAS_USER_SETTING_Debranded else "Network SouthEast Clock")
NSECLK_Frame.defaultCloseOperation = swing.JFrame.DISPOSE_ON_CLOSE
NSECLK_Frame.getContentPane().setBackground(NSECLK_RedFrame)
NSECLK_Frame.getContentPane().setLayout(awt.BorderLayout())

NSECLK_OuterPanel = swing.JPanel()
NSECLK_OuterPanel.setBackground(NSECLK_RedFrame)
NSECLK_OuterPanel.setOpaque(True)
NSECLK_OuterPanel.setLayout(awt.BorderLayout())
NSECLK_OuterPanel.setBorder(swing.BorderFactory.createEmptyBorder(22, 32, 14, 32))
NSECLK_ClockPanel = swing.JPanel()
NSECLK_ClockPanel.setBackground(NSECLK_BlackPanel)
NSECLK_ClockPanel.setOpaque(True)
NSECLK_ClockPanel.setLayout(awt.FlowLayout(awt.FlowLayout.CENTER, 6, 0))
NSECLK_ClockPanel.setPreferredSize(awt.Dimension(660, 140))
NSECLK_ClockPanel.setBorder(swing.BorderFactory.createLineBorder(NSECLK_BlackPanel, 2))

# Fonts
NSECLK_FontHM, NSECLK_FontSec = NSECLK_GetFonts()

# HH:MM custom painter + seconds label
NSECLK_HmView = NSECLK_HMView(font=NSECLK_FontHM, fg=NSECLK_Yellow, bg=NSECLK_BlackPanel)
NSECLK_MinSecDot = NSECLK_MinSecDotView(fg=NSECLK_Yellow, bg=NSECLK_BlackPanel)
secColor = NSECLK_Yellow if TAS_USER_SETTING_Debranded else NSECLK_RedDigits
NSECLK_LabelSec = NSECLK_SecView(text="00", font=NSECLK_FontSec, fg=secColor, bg=NSECLK_BlackPanel)
NSECLK_ClockPanel.add(NSECLK_HmView)
NSECLK_ClockPanel.add(NSECLK_MinSecDot)
NSECLK_ClockPanel.add(NSECLK_LabelSec)

# Holder that vertically centers the clock row so changing the overall height adds padding
# instead of pushing the digits to the top.
NSECLK_ClockHolder = swing.JPanel(awt.GridBagLayout())
NSECLK_ClockHolder.setOpaque(True)
NSECLK_ClockHolder.setBackground(NSECLK_BlackPanel)

# Changing NSECLK_ClockHolderHeight will change the digit area height.
NSECLK_ClockHolder.setPreferredSize(awt.Dimension(660, NSECLK_ClockHolderHeight))

NSECLK_Gbc = awt.GridBagConstraints()
NSECLK_Gbc.gridx = 0
NSECLK_Gbc.gridy = 0
NSECLK_Gbc.weightx = 1.0
NSECLK_Gbc.weighty = 1.0
NSECLK_Gbc.anchor = awt.GridBagConstraints.CENTER
NSECLK_Gbc.fill = awt.GridBagConstraints.NONE

NSECLK_ClockHolder.add(NSECLK_ClockPanel, NSECLK_Gbc)

# Logo panel
class NSECLK_LogoPanel(swing.JPanel):
    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self.getBackground())
            g.fillRect(0, 0, self.getWidth(), self.getHeight())

        w = self.getWidth()
        h = self.getHeight()
        if w <= 0 or h <= 0:
            return

        # D1: Draw a single long grey bar with a single stripe wedge on the left.
        # Stripe direction: bottom-left to top-right.
        # Stripe order (left->right): thin white, thick red, thin white, thick blue, thin white.
        # Thin are about 1/4 of thick (wider red/blue).

        # Base bar
        g.setColor(NSECLK_GrayStrip)
        g.fillRect(0, 0, w, h)

        # Subtle top/bottom edging
        g.setColor(awt.Color(150, 150, 150))
        g.fillRect(0, 0, w, 2)

        # Lead-in grey slanted block (behind stripes)
        leadW = int(w * 0.16)
        shift = int(h * 0.55)  # positive shift => bottom-left to top-right
        g.setColor(awt.Color(175, 175, 175))
        g.fillPolygon(awt.Polygon(
            [0, leadW, leadW + shift, shift],
            [h, h, 0, 0],
            4
        ))

        # Stripe sizing
        thinW = max(4, int(h * 0.18))
        thickW = thinW * 4  # widened red/blue

        widths = [thinW, thickW, thinW, thickW, thinW]
        colors = [NSECLK_White, NSECLK_LogoRed, NSECLK_White, NSECLK_Blue, NSECLK_White]

        # Position the stripe wedge near the left
        x = int(w * 0.10)

        for i in range(len(widths)):
            bw = widths[i]
            g.setColor(colors[i])
            g.fillPolygon(awt.Polygon(
                [x, x + bw, x + bw + shift, x + shift],
                [h, h, 0, 0],
                4
            ))
            x += bw

NSECLK_Logo = NSECLK_LogoPanel()
# Logo strip height
NSECLK_Logo.setPreferredSize(awt.Dimension(660, 24))
NSECLK_Logo.setBackground(NSECLK_RedFrame)
NSECLK_Logo.setOpaque(True)

# Plain red logo replacement for debranded mode
class NSECLK_PlainRedPanel(swing.JPanel):
    def paintComponent(self, g):
        if self.isOpaque():
            g.setColor(self.getBackground())
            g.fillRect(0, 0, self.getWidth(), self.getHeight())

NSECLK_PlainLogo = NSECLK_PlainRedPanel()
NSECLK_PlainLogo.setPreferredSize(awt.Dimension(660, 24))
NSECLK_PlainLogo.setBackground(NSECLK_RedFrame)
NSECLK_PlainLogo.setOpaque(True)

# Assemble
# The real clock has the black aperture and grey strip as part of the same internal assembly.
NSECLK_DisplayStack = swing.JPanel(awt.BorderLayout())
NSECLK_DisplayStack.setOpaque(True)
NSECLK_DisplayStack.setBackground(NSECLK_BlackPanel)
NSECLK_DisplayStack.add(NSECLK_ClockHolder, awt.BorderLayout.CENTER)
if TAS_USER_SETTING_Debranded:
    NSECLK_DisplayStack.add(NSECLK_PlainLogo, awt.BorderLayout.SOUTH)
else:
    NSECLK_DisplayStack.add(NSECLK_Logo, awt.BorderLayout.SOUTH)


# Bezel: create a stepped red frame to better match the real clock.
NSECLK_OuterStepBorder = swing.BorderFactory.createMatteBorder(4, 6, 4, 6, awt.Color(80, 0, 0))
NSECLK_InnerStepBorder = swing.BorderFactory.createMatteBorder(2, 3, 2, 3, awt.Color(120, 0, 0))

NSECLK_InsetBorder = swing.BorderFactory.createEmptyBorder(6, 8, 0, 8)
NSECLK_BezelBorder = swing.BorderFactory.createCompoundBorder(
    NSECLK_OuterStepBorder,
    swing.BorderFactory.createCompoundBorder(NSECLK_InnerStepBorder, NSECLK_InsetBorder)
)

NSECLK_AperturePanel = swing.JPanel(awt.BorderLayout())
NSECLK_AperturePanel.setOpaque(True)
NSECLK_AperturePanel.setBackground(NSECLK_RedFrame)
NSECLK_AperturePanel.setBorder(NSECLK_BezelBorder)
NSECLK_AperturePanel.add(NSECLK_DisplayStack, awt.BorderLayout.CENTER)

NSECLK_OuterPanel.add(NSECLK_AperturePanel, awt.BorderLayout.CENTER)

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
    try:
        if NSECLK_Frame is None or not NSECLK_Frame.isDisplayable():
            if NSECLK_Timer is not None and NSECLK_Timer.isRunning():
                NSECLK_Timer.stop()
            return
    except:
        pass
    
    hh, mm, ss = NSECLK_GetHmsFromTimebase()
    hm = "%02d:%02d" % (hh, mm)
    if hm != NSECLK_LastHM[0]:
        NSECLK_HmView.setText(hm)
        NSECLK_LastHM[0] = hm
        f = NSECLK_HmView.getFont()
        NSECLK_Log("HM font in use - family: '%s', name: '%s', PS: '%s', size: %spt"
                   % (f.getFamily(), f.getFontName(), f.getPSName(), f.getSize()))
    NSECLK_LabelSec.setText("%02d" % ss)


import java.awt.event as awt_event

NSECLK_Timer = swing.Timer(1000, NSECLK_UpdateClock)
NSECLK_Timer.setInitialDelay(0)

class NSECLK_CloseHandler(awt_event.WindowAdapter):
    def windowClosing(self, e):
        try:
            if NSECLK_Timer is not None and NSECLK_Timer.isRunning():
                NSECLK_Timer.stop()
        except:
            pass

    def windowClosed(self, e):
        try:
            if NSECLK_Timer is not None and NSECLK_Timer.isRunning():
                NSECLK_Timer.stop()
        except:
            pass

try:
    NSECLK_Frame.addWindowListener(NSECLK_CloseHandler())
except:
    pass

NSECLK_Timer.start()
NSECLK_UpdateClock()
