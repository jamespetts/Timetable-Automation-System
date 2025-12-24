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
# This needs to be a STARTUP SCRIPT
#
# Provides a 2010s-style mobile app UI for the weather forecast.
# PURPOSE: UI frontend ONLY - reads future weather data published by WeatherGenerator.py
# (schema WG2: IMWX_FC_POINTS etc.). Also shows sunrise/sunset for the current day.
# Input memories:
# - IMCURRENTTIME (for simulated time)
# - IMDAYOFWEEK
# - IMCLOUDCOVERPCT (NOW, as published by WeatherGenerator)
# - IMWX_SCHEMA, IMWX_FC_STEP_MIN, IMWX_FC_LENGTH, IMWX_FC_ISSUE_ABSMIN, IMWX_FC_POINTS, IMWX_UPDATED_ABSMIN
# - (optional) IMWX_FC_ISSUES, IMWX_FC_<issueAbsMin>
# - Spoof ad / rotation (optional):
#   IMSPOOFADSENABLED (1/0), IMAD_ROTATE_SEC (int), IMAD_MODE ('seq'|'rand'), IMAD_COUNT (int),
#   IMAD{i}_BRAND, IMAD{i}_L1, IMAD{i}_L2, IMAD{i}_CTA for i = 1..IMAD_COUNT
#
# Start style preserved at bottom:
# ui = WeatherForecastUI(); ui.setName('Weather forecast UI'); ui.start()
import jmri, java, csv
from java.awt import Color, Font, BasicStroke, RenderingHints, Dimension, GridLayout
from java.awt.geom import RoundRectangle2D
from javax.swing import JPanel, JLabel, BoxLayout, BorderFactory, Timer, JButton
from javax.swing.border import EmptyBorder
import TASBeanLookup as TBL
from java.awt.event import WindowAdapter
from javax.swing import WindowConstants

# ------------------------------ UI Configuration ------------------------------
REALTIME_REFRESH_MS = 4000
CARD_CORNER = 16
# Bluer theme (portrait)
PANEL_BG = Color(224,235,247) # window background
CARD_BG = Color(236,243,252)  # card background
TEXT_PRIMARY = Color(15,22,35)
TEXT_SECONDARY = Color(70,84,104)
ACCENT = Color(35,105,225)
ACCENT_LIGHT = Color(197,214,245)
TAB_BG = Color(219,229,247)
# Grid layout (portrait): 4 rows x 6 columns = 24 hours/page
GRID_ROWS = 4
GRID_COLS = 6
# Icon colors
SUN_YELLOW = Color(255,190,0)
MOON_GRAY = Color(210,210,220)
CLOUD_GRAY = Color(150,155,165)

# Sunrise/Sunset CSV (reuse your other scripts' location)
try:
    DAYNIGHT_CSV_PATH = jmri.util.FileUtil.getExternalFilename("profile:jython/config/daynight.csv")
except Exception:
    DAYNIGHT_CSV_PATH = "jython/config/daynight.csv"

# (Removed hard-coded DAYNIGHT_PRESET; use Memory instead)

# ------------------------------ Memory bindings ------------------------------
mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)

# Use TASBeanLookup to handle prefix and creation
def mem(suffix, default=None):
    return TBL.ProvideMemoryBySuffix(suffix, default)

CLOCK_MEM = mem("CURRENTTIME")
DOW_MEM = mem("DAYOFWEEK")
CLOUD_NOW = mem("CLOUDCOVERPCT", 0)

# WG2 publication from WeatherGenerator
FC_SCHEMA = mem("WX_SCHEMA", 'WG2')
FC_STEP = mem("WX_FC_STEP_MIN", 60)
FC_LEN = mem("WX_FC_LENGTH", 48)
FC_ISSUE = mem("WX_FC_ISSUE_ABSMIN", 0)
FC_POINTS = mem("WX_FC_POINTS", '')
FC_UPDATED = mem("WX_UPDATED_ABSMIN", 0)

# NEW: day/night preset name from memory (matches newspaper script behavior)
DAYNIGHT_PRESET_MEM = mem("DAYNIGHT_PRESET", None)

# Spoof ad controls (optional)
ADS_ENABLED_MEM = mem("SPOOFADSENABLED", True)
AD_ROTATE_SEC = mem("AD_ROTATE_SEC", 15) # seconds
AD_MODE_MEM = mem("AD_MODE", 'seq')      # 'seq' or 'rand'
AD_COUNT_MEM = mem("AD_COUNT", 0)        # 0 -> use defaults

# ------------------------------ Sunrise/Sunset helpers ------------------------------
FALLBACK_SUN = {
    'Monday':    {'civil_dawn': 303, 'sunrise': 401, 'sunset': 1200, 'civil_dusk': 1298},
    'Tuesday':   {'civil_dawn': 305, 'sunrise': 402, 'sunset': 1198, 'civil_dusk': 1296},
    'Wednesday': {'civil_dawn': 306, 'sunrise': 404, 'sunset': 1196, 'civil_dusk': 1294},
    'Thursday':  {'civil_dawn': 308, 'sunrise': 406, 'sunset': 1194, 'civil_dusk': 1292},
    'Friday':    {'civil_dawn': 310, 'sunrise': 407, 'sunset': 1192, 'civil_dusk': 1290},
    'Saturday':  {'civil_dawn': 312, 'sunrise': 409, 'sunset': 1191, 'civil_dusk': 1287},
    'Sunday':    {'civil_dawn': 314, 'sunrise': 410, 'sunset': 1189, 'civil_dusk': 1285}
}
DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

def _parse_time_to_minutes(s, default_m):
    try:
        if s is None: return int(default_m)
        s = str(s).strip()
        if s.isdigit(): return int(s) % (24*60)
        parts = s.split(':')
        if len(parts) >= 2:
            h = int(parts[0]); m = int(parts[1])
            return ((h % 24) * 60 + (m % 60))
        return int(default_m)
    except Exception:
        return int(default_m)

def _load_daynight_from_tsv(path, preset_name, fallback):
    out = dict(fallback)
    try:
        f = open(path, 'r')
        try:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row.get('name') != preset_name: continue
                day = row.get('day')
                if day not in DAYS: continue
                out[day] = {
                    'civil_dawn': _parse_time_to_minutes(row.get('civil_dawn'), fallback[day]['civil_dawn']),
                    'sunrise':    _parse_time_to_minutes(row.get('sunrise'),    fallback[day]['sunrise']),
                    'sunset':     _parse_time_to_minutes(row.get('sunset'),     fallback[day]['sunset']),
                    'civil_dusk': _parse_time_to_minutes(row.get('civil_dusk'), fallback[day]['civil_dusk']),
                }
        finally:
            f.close()
    except Exception as e:
        print('DayNight CSV load failed in UI: {}'.format(e))
    return out

def _fmt_hhmm(mins_of_day):
    hh = int((mins_of_day % 1440) // 60)
    mm = int(mins_of_day % 60)
    return ("%02d:%02d" % (hh, mm))

def _dow_idx(name):
    try: return DAYS.index(str(name))
    except Exception: return 0

def _dow_name_from_abs_minute(abs_min):
    idx = int((abs_min // 1440) % 7)
    return DAYS[idx]

# NEW: fetch active preset from memory (fallback if missing)
def _active_preset_name():
    try:
        v = DAYNIGHT_PRESET_MEM.getValue()
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    except Exception:
        pass
    return 'Maesteg_Sep2017'

# ------------------------------ spacing helpers (no Box.) ------------------------------
def gapV(h):
    p = JPanel(); p.setOpaque(False)
    p.setPreferredSize(Dimension(1, h))
    p.setMinimumSize(Dimension(1, h))
    p.setMaximumSize(Dimension(32767, h))
    return p

def gapH(w):
    p = JPanel(); p.setOpaque(False)
    p.setPreferredSize(Dimension(w, 1))
    p.setMinimumSize(Dimension(w, 1))
    p.setMaximumSize(Dimension(w, 1))
    return p

# ------------------------------ UI components ------------------------------
class Card(JPanel):
    def __init__(self, pad=12):
        JPanel.__init__(self)
        self.setOpaque(False)
        self.setBorder(EmptyBorder(pad, pad, pad, pad))
    def paintComponent(self, g):
        super(Card, self).paintComponent(g)
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth(); h = self.getHeight()
            rr = RoundRectangle2D.Float(4, 4, w-8, h-8, CARD_CORNER, CARD_CORNER)
            g2.setColor(CARD_BG); g2.fill(rr)
            g2.setColor(Color(205,218,240)); g2.setStroke(BasicStroke(1.0)); g2.draw(rr)
        finally:
            g2.dispose()

# -- Weather icon primitives --
def _draw_sun(g2, cx, cy, r_outer):
    g2.setColor(SUN_YELLOW)
    r = r_outer * 0.55
    g2.fillOval(int(cx - r), int(cy - r), int(2*r), int(2*r))
    g2.setStroke(BasicStroke(2.0))
    for k in range(8):
        ang = (3.14159/4.0)*k
        x1 = cx + int((r + 2) * java.lang.Math.cos(ang))
        y1 = cy + int((r + 2) * java.lang.Math.sin(ang))
        x2 = cx + int((r + 8) * java.lang.Math.cos(ang))
        y2 = cy + int((r + 8) * java.lang.Math.sin(ang))
        g2.drawLine(x1,y1,x2,y2)

def _draw_cloud(g2, cx, cy, w, h):
    g2.setColor(CLOUD_GRAY)
    g2.fillOval(int(cx - 0.5*w), int(cy - 0.35*h), int(0.6*w), int(0.6*h))
    g2.fillOval(int(cx - 0.1*w), int(cy - 0.45*h), int(0.7*w), int(0.7*h))
    g2.fillOval(int(cx - 0.3*w), int(cy - 0.15*h), int(0.9*w), int(0.6*h))

def _draw_moon_crescent(g2, cx, cy, r_outer, bgColor):
    g2.setColor(MOON_GRAY)
    g2.fillOval(int(cx - r_outer), int(cy - r_outer), int(2*r_outer), int(2*r_outer))
    g2.setColor(bgColor)
    g2.fillOval(int(cx - r_outer*0.65), int(cy - r_outer), int(2*r_outer), int(2*r_outer))

def _draw_partly_day(g2, cx, cy, r):
    _draw_sun(g2, cx - int(r*0.3), cy - int(r*0.2), r)
    _draw_cloud(g2, cx + int(r*0.05), cy + int(r*0.2), int(r*1.4), int(r*0.9))

def _draw_partly_night(g2, cx, cy, r, bgColor):
    _draw_moon_crescent(g2, cx - int(r*0.25), cy - int(r*0.1), int(r*0.6), bgColor)
    _draw_cloud(g2, cx + int(r*0.05), cy + int(r*0.2), int(r*1.4), int(r*0.9))

class BigIconPanel(JPanel):
    """Large vector icon for the 'Now' bar."""
    def __init__(self, get_absmin_callable, get_pct_callable, get_suntimes_callable):
        JPanel.__init__(self); self.setOpaque(False)
        self._get_abs = get_absmin_callable
        self._get_pct = get_pct_callable
        self._get_sun = get_suntimes_callable
        self.setPreferredSize(Dimension(150, 120)) # larger than hourly icons
    def paintComponent(self, g):
        super(BigIconPanel, self).paintComponent(g)
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth(); h = self.getHeight()
            cx = int(w*0.55); cy = int(h*0.58); r = int(min(w,h)*0.42)
            absmin = self._get_abs()
            try: pct = int(self._get_pct() or 0)
            except Exception: pct = 0
            sr, ss = self._get_sun(absmin)
            mod = absmin % 1440
            is_day = (mod >= sr) and (mod <= ss)
            if is_day:
                if pct <= 10: _draw_sun(g2, cx, cy, r)
                elif pct <= 75: _draw_partly_day(g2, cx, cy, r)
                else: _draw_cloud(g2, cx, cy+2, int(2.0*r), int(1.35*r))
            else:
                if pct <= 10: _draw_moon_crescent(g2, cx, cy, int(0.85*r), CARD_BG)
                elif pct <= 85: _draw_partly_night(g2, cx, cy, r, CARD_BG)
                else: _draw_cloud(g2, cx, cy+2, int(2.0*r), int(1.35*r))
        finally:
            g2.dispose()

class MiniIconPanel(JPanel):
    def __init__(self):
        JPanel.__init__(self); self.setOpaque(False)
        self.absmin = 0; self.pct = 0; self.sunrise = 360; self.sunset = 1080
        self.setPreferredSize(Dimension(34, 26))
    def setData(self, absmin, pct, sunrise, sunset):
        self.absmin = int(absmin); self.pct = int(pct)
        self.sunrise = int(sunrise); self.sunset = int(sunset)
        self.repaint()
    def paintComponent(self, g):
        super(MiniIconPanel, self).paintComponent(g)
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth(); h = self.getHeight()
            cx = int(w*0.55); cy = int(h*0.60); r = int(min(w,h)*0.45)
            mod = self.absmin % 1440
            is_day = (mod >= self.sunrise) and (mod <= self.sunset)
            p = self.pct
            if is_day:
                if p <= 10: _draw_sun(g2, cx, cy, r)
                elif p <= 75: _draw_partly_day(g2, cx, cy, r)
                else: _draw_cloud(g2, cx, cy+1, int(1.4*r), int(0.9*r))
            else:
                if p <= 10: _draw_moon_crescent(g2, cx, cy, int(0.8*r), CARD_BG)
                elif p <= 85: _draw_partly_night(g2, cx, cy, r, CARD_BG)
                else: _draw_cloud(g2, cx, cy+1, int(1.4*r), int(0.9*r))
        finally:
            g2.dispose()

def _wrap_desc(desc):
    """Return HTML two-line centered text to avoid clipping."""
    if desc == "Mostly cloudy":
        return "<html><center>Mostly<br>cloudy</center></html>"
    if desc == "Partly cloudy night":
        return "<html><center>Partly cloudy<br>night</center></html>"
    if desc == "Mostly cloudy night":
        return "<html><center>Mostly cloudy<br>night</center></html>"
    if desc == "Mostly clear":
        return "<html><center>Mostly<br>clear</center></html>"
    return "<html><center>%s</center></html>" % desc

# --- Blue CTA button: always renders a pill in ACCENT blue ---
class BlueCtaButton(JButton):
    def __init__(self, text):
        JButton.__init__(self, text)
        self.setOpaque(False)
        self.setContentAreaFilled(False)
        self.setBorderPainted(False)
        self.setFocusPainted(False)
        self.setFocusable(False)
        self.setForeground(Color(255,255,255))  # white text
        self.setFont(Font("SansSerif", Font.BOLD, 13))
        # start with a roomy size; we will adjust at paint time
        self.setPreferredSize(Dimension(180, 32))
        self.setMinimumSize(Dimension(160, 32))
        self.setMaximumSize(Dimension(280, 32))

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth(); h = self.getHeight()
            r = h  # full pill
            # Pressed state slightly darker
            isPressed = self.getModel().isPressed()
            base = ACCENT if not isPressed else Color(
                max(0, ACCENT.getRed() - 15),
                max(0, ACCENT.getGreen() - 15),
                max(0, ACCENT.getBlue() - 15)
            )
            g2.setColor(base)
            g2.fillRoundRect(0, 0, w, h, r, r)
            # subtle outline
            g2.setColor(ACCENT_LIGHT)
            g2.setStroke(BasicStroke(1.0))
            g2.drawRoundRect(0, 0, w-1, h-1, r, r)
        finally:
            g2.dispose()
        # draw the label text centered
        super(BlueCtaButton, self).paintComponent(g)

class HourCell(Card):
    def __init__(self):
        Card.__init__(self, 6)
        self.setLayout(BoxLayout(self, BoxLayout.Y_AXIS))
        self.t = JLabel("--"); self.t.setForeground(TEXT_PRIMARY); self.t.setFont(Font("SansSerif", Font.BOLD, 13))
        self.ico = MiniIconPanel()
        self.d = JLabel(" "); self.d.setForeground(TEXT_PRIMARY); self.d.setFont(Font("SansSerif", Font.BOLD, 12))
        self.add(self.t); self.add(gapV(3)); self.add(self.ico); self.add(gapV(3)); self.add(self.d)    

    def setData(self, absmin, hhmm, pct, sunrise, sunset):
        self.t.setText(hhmm)
        self.ico.setData(absmin, pct, sunrise, sunset)
        p = int(pct); mod = absmin % 1440; is_day = (mod >= sunrise) and (mod <= sunset)
        if p <= 5: desc = "Clear" if is_day else "Clear night"
        elif p <= 25: desc = "Mostly clear" if is_day else "Partly cloudy night"
        elif p <= 50: desc = "Partly cloudy"
        elif p <= 75: desc = "Mostly cloudy"
        else: desc = "Overcast"
        self.d.setText(_wrap_desc(desc))

class AdBanner(Card):
    def __init__(self):
        Card.__init__(self, 10)
        self.setLayout(BoxLayout(self, BoxLayout.X_AXIS))
        self.badge = JLabel("Sponsored"); self.badge.setForeground(Color(120,120,130)); self.badge.setFont(Font("SansSerif", Font.PLAIN, 11))
        self.brand = JLabel(""); self.brand.setForeground(ACCENT); self.brand.setFont(Font("SansSerif", Font.BOLD, 14))
        self.l1 = JLabel(""); self.l1.setForeground(TEXT_PRIMARY); self.l1.setFont(Font("SansSerif", Font.BOLD, 16))
        self.l2 = JLabel(""); self.l2.setForeground(TEXT_SECONDARY); self.l2.setFont(Font("SansSerif", Font.PLAIN, 13))
        from javax.swing import JButton
        self.cta = BlueCtaButton(" ")
        self.cta.setBorder(BorderFactory.createEmptyBorder(6,12,6,12))  # inner padding
        self._onUpgrade = None  # optional callback supplied by parent UI
        
        # Attach a single, persistent listener once; never rewire.
        # This avoids stacked listeners and multiple successive dialogs.
        def _OnCta(e):
            try:
                self._HandleCtaClick()
            except:
                pass
        self.cta.addActionListener(_OnCta)

        # Build the left text block and add it before the CTA button
        left = JPanel(); left.setOpaque(False); left.setLayout(BoxLayout(left, BoxLayout.Y_AXIS))
        left.add(self.badge); left.add(gapV(2)); left.add(self.brand); left.add(gapV(3)); left.add(self.l1); left.add(self.l2)

        self.add(left); self.add(gapH(12)); self.add(self.cta)
          
    def _HandleCtaClick(self):
        # Decide at click time based on current label text; run exactly one action.
        try:
            br = str(self.brand.getText() or "").strip().lower()
            txt = str(self.cta.getText() or "").strip().lower()
        except:
            br = ""; txt = ""

        # 1) Upgrade path (brand "Weather" or CTA mentions upgrade/pro)
        try:
            if self._onUpgrade and (
                br == "weather" or
                (("upgrade" in txt) and ("pro" in txt))
            ):
                self._onUpgrade()
                return
        except:
            pass

        # 2) Spice Inveiglers path (brand match only)
        try:
            if br == "spice inveiglers":
                from jmri.util import FileUtil
                import os
                execfile(os.path.join(FileUtil.getScriptsPath(), 'SecretScriptDoNotRun.py'), globals())
                return
        except:
            pass

        # 3) Default spoof payment-declined dialog for all other ads
        try:
            from javax.swing import JOptionPane
            JOptionPane.showMessageDialog(
                None,
                "Payment declined.\nPlease contact your bank.",
                "Payment Error",
                JOptionPane.INFORMATION_MESSAGE
            )
        except:
            pass
    

    def setAd(self, brand, l1, l2, cta):
        # Text-only refresh; listener is persistent and decides at click time.
        self.brand.setText(str(brand or ""))
        self.l1.setText(str(l1 or ""))
        self.l2.setText(str(l2 or ""))
        self.cta.setText(str(cta or ""))

    def setUpgradeCallback(self, fn):
        self._onUpgrade = fn

class PillButton(JButton):
    """Minimal pill-style button for 2010s mobile look."""
    def __init__(self, text):
        JButton.__init__(self, text)
        self._isSelected = False # avoid JavaBean 'selected' collision
        self.setOpaque(False)
        self.setContentAreaFilled(False)
        self.setBorderPainted(False)
        self.setFocusPainted(False)
        self.setFont(Font("SansSerif", Font.BOLD, 12))
        self.setForeground(Color(20,45,90))
        self.setPreferredSize(Dimension(120, 36))
    def setSelected(self, sel):
        try:
            super(PillButton, self).setSelected(bool(sel))
        except Exception:
            pass
        self._isSelected = bool(sel)
        self.repaint()
    def paintComponent(self, g):
        # Use base Graphics for font metrics before creating g2
        fm = g.getFontMetrics(self.getFont())
        text = self.getText() or ""
        textW = fm.stringWidth(text)
        padX  = 28     # left+right padding total
        minW, maxW = 160, 280
        wantW = max(minW, min(maxW, textW + padX))

        # Tell BoxLayout about the width we need
        h = max(28, self.getPreferredSize().height)
        self.setPreferredSize(Dimension(wantW, h))
        self.setMaximumSize(Dimension(maxW, h))
        
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth(); h = self.getHeight()
            r = h # full pill
            g2.setColor(ACCENT if self._isSelected else TAB_BG)
            g2.fillRoundRect(0, 0, w, h, r, r)
            g2.setColor(ACCENT_LIGHT if self._isSelected else Color(200,210,230))
            g2.setStroke(BasicStroke(1.0))
            g2.drawRoundRect(0, 0, w-1, h-1, r, r)
        finally:
            g2.dispose()
        super(PillButton, self).paintComponent(g)

class NowBar(Card):
    """Now row with big vector icon and Sunrise/Sunset on the same line."""
    def __init__(self, get_absmin, get_nowpct, get_sun_today):
        Card.__init__(self, 10)
        self.setLayout(BoxLayout(self, BoxLayout.X_AXIS))
        left = JPanel(); left.setOpaque(False); left.setLayout(BoxLayout(left, BoxLayout.Y_AXIS))
        self.title = JLabel("Now"); self.title.setForeground(TEXT_SECONDARY); self.title.setFont(Font("SansSerif", Font.PLAIN, 12))
        self.label = JLabel("--"); self.label.setForeground(TEXT_PRIMARY); self.label.setFont(Font("SansSerif", Font.BOLD, 20))
        self.sub = JLabel(" "); self.sub.setForeground(TEXT_SECONDARY); self.sub.setFont(Font("SansSerif", Font.PLAIN, 12))
        left.add(self.title); left.add(gapV(4)); left.add(self.label); left.add(self.sub)
        self.add(left); self.add(gapH(10))
        self.icon = BigIconPanel(get_absmin, get_nowpct, get_sun_today)
        self.add(self.icon); self.add(gapH(12))
        right = JPanel(); right.setOpaque(False); right.setLayout(BoxLayout(right, BoxLayout.Y_AXIS))
        self.sun = JLabel("Sunrise --:-- \n Sunset --:--"); self.sun.setForeground(TEXT_PRIMARY); self.sun.setFont(Font("SansSerif", Font.PLAIN, 13))
        right.add(self.sun)
        self.add(right)
        self._get_absmin = get_absmin
        self._get_nowpct = get_nowpct
        self._get_sun_today = get_sun_today
    def refresh(self):
        abs_now = self._get_absmin()
        try: now_pct = int(self._get_nowpct() or 0)
        except Exception: now_pct = 0
        sr, ss = self._get_sun_today(abs_now)
        is_day = (abs_now % 1440 >= sr) and (abs_now % 1440 <= ss)
        def label_for(p):
            if p <= 5: return "Clear" if is_day else "Clear night"
            if p <= 25: return "Mostly clear" if is_day else "Partly cloudy night"
            if p <= 50: return "Partly cloudy"
            if p <= 75: return "Mostly cloudy"
            return "Overcast"
        self.label.setText(label_for(now_pct))
        self.sub.setText("%s %s" % (_dow_name_from_abs_minute(abs_now), _fmt_hhmm(abs_now % 1440)))
        self.sun.setText("Sunrise %s \n Sunset %s" % (_fmt_hhmm(sr), _fmt_hhmm(ss)))
        self.icon.repaint()

# ------------------------------ Main Automaton ------------------------------
class WeatherForecastUI(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        self.timebase = jmri.InstanceManager.getDefault(jmri.Timebase)
        # MINIMAL CHANGE: load sunrise/sunset table using preset name from Memory
        self.sunTimes = _load_daynight_from_tsv(DAYNIGHT_CSV_PATH, _active_preset_name(), FALLBACK_SUN)

        self.page = 0 # 0=Today, 1=Tomorrow, 2=Day+2

        # --- Ad rotation state ---
        self.adList = [] # list of dicts: {'brand','l1','l2','cta'}
        self.adIndex = -1
        self.adLastMode = None
        self.adLastRotateMs = None
        self.adTimer = None
        self.rand = java.util.Random(123456789) # deterministic random

        self.frame = jmri.util.JmriJFrame("Weather")
        cp = self.frame.getContentPane()
        cp.setBackground(PANEL_BG)
        cp.setLayout(BoxLayout(cp, BoxLayout.Y_AXIS))

        self.hdr = JLabel("Weather"); self.hdr.setForeground(TEXT_PRIMARY); self.hdr.setFont(Font("SansSerif", Font.BOLD, 20))
        self.hdr.setBorder(EmptyBorder(10,12,2,12)); cp.add(self.hdr)
        self.meta = JLabel("Issued -- --:--"); self.meta.setForeground(TEXT_SECONDARY); self.meta.setFont(Font("SansSerif", Font.PLAIN, 12))
        self.meta.setBorder(EmptyBorder(0,12,6,12)); cp.add(self.meta)

        # Now row
        self.nowBar = NowBar(lambda: self._abs_min_now(),
                             lambda: CLOUD_NOW.getValue(),
                             self._sunrise_sunset_for_abs)
        cp.add(self.nowBar); cp.add(gapV(8))

        # Page tabs (pill buttons)
        tabCard = Card(8)
        tabCard.setLayout(BoxLayout(tabCard, BoxLayout.X_AXIS))
        self.btnToday = PillButton("Today")
        self.btnTomorrow = PillButton("Tomorrow")
        self.btnDay2 = PillButton("Day +2") # text updated dynamically
        self.btnToday.setSelected(True) # initial visual state
        for b in (self.btnToday, self.btnTomorrow, self.btnDay2):
            tabCard.add(b); tabCard.add(gapH(8))
        cp.add(tabCard); cp.add(gapV(6))

        # 24-hour grid (portrait 4x6)
        self.gridCard = Card(8)
        self.gridCard.setLayout(GridLayout(GRID_ROWS, GRID_COLS, 6, 6))
        self.hourCells = [HourCell() for _ in range(GRID_ROWS * GRID_COLS)]
        for c in self.hourCells: self.gridCard.add(c)
        cp.add(self.gridCard); cp.add(gapV(6))

        # Spoof ad (rotating)
        self.ad = AdBanner(); cp.add(self.ad); cp.add(gapV(6))
        
        # Clicking the "Upgrade to Weather Pro" ad CTA disables ads and switches to PRO mode
        def _enableProMode():
            try:
                ADS_ENABLED_MEM.setValue(False)  # turn off spoof ads
            except:
                pass
            # Apply immediately
            self._apply_ad_visibility_and_timer()
            self._applyProTitle()

        self.ad.setUpgradeCallback(_enableProMode)
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[WeatherForecastUIApp] Failed to set weather UI window icon: " + str(ex))
      
        self.frame.setSize(540, 960) # phone-like portrait
        self.frame.setLocationByPlatform(True)
        self.frame.setVisible(True)
            
        # Ensure the frame is actually disposed by Swing, not just hidden
        self.frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)

        # Close handler: stop timers and halt the automaton
        class _WXClose(WindowAdapter):
            def windowClosing(this, e):
                try:
                    self._cleanup()
                finally:
                    # Halt the AbstractAutomaton thread now
                    self.stop()
            def windowClosed(this, e):
                # Safety net if the window is disposed programmatically
                try:
                    self._cleanup()
                finally:
                    self.stop()

        self.frame.addWindowListener(_WXClose())
        
        # Wire tabs
        self.btnToday.addActionListener(lambda e: self._setPage(0))
        self.btnTomorrow.addActionListener(lambda e: self._setPage(1))
        self.btnDay2.addActionListener(lambda e: self._setPage(2))

        # Periodic refresh
        self.timer = Timer(REALTIME_REFRESH_MS, self._onTick); self.timer.start()

        # Initialize ads and start rotation if enabled
        self._reload_ads_from_mem()
        self._apply_ad_visibility_and_timer()
        self._applyProTitle()
            
    def _cleanup(self):
        # Idempotent shutdown: stop timers and detach listeners
        try:
            self._Log("Cleanup starting")
        except:
            pass
        try:
            if getattr(self, 'timer', None) is not None:
                try:
                    self.timer.stop()
                except:
                    pass
                self.timer = None
        except:
            pass
        try:
            if getattr(self, 'adTimer', None) is not None:
                try:
                    self.adTimer.stop()
                except:
                    pass
                self.adTimer = None
        except:
            pass
        # Remove action listeners to avoid lingering references
        try:
            for b in (self.btnToday, self.btnTomorrow, self.btnDay2):
                try:
                    for l in b.getActionListeners():
                        b.removeActionListener(l)
                except:
                    pass
            try:
                for l in self.ad.cta.getActionListeners():
                    self.ad.cta.removeActionListener(l)
            except:
                pass
        except:
            pass
        # Hide frame (dispose is driven by the window system)
        try:
            self.frame.setVisible(False)
        except:
            pass
        try:
            self._Log("Cleanup done")
        except:
            pass

    # ------------------------------ Helpers ------------------------------
    def _minutes_of_day(self):
        t = self.timebase.getTime()
        fmt = java.text.SimpleDateFormat('HH:mm')
        hh, mm = fmt.format(t).split(':')
        return int(hh)*60 + int(mm)
        
    def _RunOnEdt(self, fn):
        # Ensure Swing UI changes (incl. CTA handler rewiring) happen on the EDT.
        try:
            from javax.swing import SwingUtilities
            if SwingUtilities.isEventDispatchThread():
                try:
                    fn()
                except:
                    pass
            else:
                SwingUtilities.invokeLater(fn)
        except:
            # Never crash the UI if SwingUtilities import fails.
            try:
                fn()
            except:
                pass
        
    # --- DIAGNOSTIC: simple logger with HH:MM from Timebase ---    
    def _Log(self, msg):
        return # Remove this line to re-enable logging
        try:
            t = self._minutes_of_day()
            print("[WX-ADS %s] %s" % (_fmt_hhmm(t), str(msg)))
        except:
            print("[WX-ADS] %s" % str(msg))

    def _abs_min_now(self):
        return _dow_idx(DOW_MEM.getValue()) * 1440 + self._minutes_of_day()

    def _read_points(self):
        try:
            s = str(FC_POINTS.getValue() or '').strip()
            if s == '': return []
            out = []
            for tok in s.split(','):
                tok = tok.strip()
                if tok == '' or ':' not in tok: continue
                a, b = tok.split(':', 1)
                out.append((int(a), int(b)))
            return out
        except Exception as e:
            print("UI parse error (FC_POINTS): {}".format(e))
            return []

    def _sunrise_sunset_for_abs(self, absmin):
        dayname = _dow_name_from_abs_minute(absmin)
        st = self.sunTimes.get(dayname, FALLBACK_SUN[dayname])
        return st['sunrise'], st['sunset']

    def _setPage(self, p):
        self.page = max(0, min(2, int(p)))
        self._onTick(None)

    def _nearest_value_at(self, t_abs, pts, step_min):
        if not pts: return (0, False)
        first = pts[0][0]; last = pts[-1][0]
        if t_abs < first - step_min: return (0, False)
        if t_abs > last + step_min: return (0, False)
        best_i = 0; best_d = 1<<30
        for i,(tt,_) in enumerate(pts):
            d = abs(tt - t_abs)
            if d < best_d: best_d = d; best_i = i
        if best_d > int(step_min * 1.5):
            return (0, False)
        return (pts[best_i][1], True)

    def _page_midnight_abs(self, base_abs_now, page):
        today_midnight = base_abs_now - (base_abs_now % 1440)
        return today_midnight + page * 1440

    # ------------------------------ Ad rotation helpers ------------------------------
    def _read_int(self, m, d):
        try: return int(m.getValue() or d)
        except Exception: return d
    
    def _read_enabled(self, m, defaultEnabled):
    # Accept both 1/0 and common boolean words
        try:
            v = m.getValue()
            if v is None:
                return 1 if defaultEnabled else 0
            s = str(v).strip().lower()
            if s in ('1','true','yes','y','on','enabled'):
                return 1
            if s in ('0','false','no','n','off','disabled'):
                return 0
            # If a numeric string was stored, try parsing
            try:
                return 1 if int(s) != 0 else 0
            except:
                return 1 if defaultEnabled else 0
        except:
            return 1 if defaultEnabled else 0
        
    def _read_str(self, m, d):
        try:
            v = m.getValue()
            return d if v is None else str(v)
        except Exception:
            return d

    def _reload_ads_from_mem(self):
        """Rebuild self.adList from IMAD_* memories, or defaults if none."""
        count = self._read_int(AD_COUNT_MEM, 0)
        ads = []
        if count > 0:
            for i in range(1, count+1):             
                b = self._read_str(mem('AD%d_BRAND' % i, 'Brand %d' % i), 'Brand %d' % i)
                l1 = self._read_str(mem('AD%d_L1' % i, 'Headline %d' % i), 'Headline %d' % i)
                l2 = self._read_str(mem('AD%d_L2' % i, 'Subline %d' % i), 'Subline %d' % i)
                cta = self._read_str(mem('AD%d_CTA' % i, 'Learn more'), 'Learn more')
                ads.append({'brand':b,'l1':l1,'l2':l2,'cta':cta})
        else:
            # Defaults (rotate if user hasn't configured anything)
            ads = [
                {'brand':'Spice Inveiglers', 'l1':'Mobile gaming action joy extreme!', 'l2':'New, innovative gameplay', 'cta':'Play now!'},
                {'brand':'RailNet Ultra', 'l1':'Upgrade your railway to 5G steam!', 'l2':'Quantum buffers. Extra coupling.', 'cta':'Install now'},
                {'brand':"Billy's Replacement Bluetooth Speakers",   'l1':'Loud in the cloud',           'l2':'Subscribe to turn the volume up to 11!',       'cta':'Order now'},
                {'brand':'Acme RailCloud','l1':'Your signals, in the cloud',       'l2':'Low latency, high whimsy.',       'cta':'Try free'},
                # Special upgrade ad - allows upgrading to Weather PRO to remove ads
                {'brand':'Weather',        'l1':'Go ad-free',                       'l2':'Unlock more space',               'cta':'Upgrade to Weather Pro'}
            ]
        self.adList = ads
        if self.adIndex >= len(self.adList):
            self.adIndex = -1  # force restart at next rotation tick
        # --- DIAGNOSTIC ---
        try:
            self._Log("ReloadAds count=%d adIndex=%d enabledMem=%r modeMem=%r rotateSecMem=%r" % (
                len(self.adList),
                int(self.adIndex),
                ADS_ENABLED_MEM.getValue(),
                AD_MODE_MEM.getValue(),
                AD_ROTATE_SEC.getValue()
            ))
            if len(self.adList) > 0:
                a0 = self.adList[0]
                self._Log("FirstAd brand='%s' l1='%s' l2='%s' cta='%s'" % (a0.get('brand',''), a0.get('l1',''), a0.get('l2',''), a0.get('cta','')))
        except:
            pass

    def _applyProTitle(self):
        enabled = self._read_enabled(ADS_ENABLED_MEM, True)
        title = "Weather PRO" if enabled != 1 else "Weather"
        try:
            self.frame.setTitle(title)
        except:
            pass
        try:
            self.hdr.setText(title)
        except:
            pass
    
    def _apply_ad_visibility_and_timer(self):
        """Show/hide banner and (re)configure rotation timer from Memories."""
        enabled = self._read_enabled(ADS_ENABLED_MEM, True)
        self.ad.setVisible(enabled == 1 and len(self.adList) > 0)

        rotate_ms = max(3000, self._read_int(AD_ROTATE_SEC, 15) * 1000)
        mode = self._read_str(AD_MODE_MEM, 'seq').lower()

        # (Re)start timer if needed or if settings changed
        createdTimer = False
        if self.adTimer is None:
            self.adTimer = Timer(rotate_ms, self._onAdTick)
            self.adTimer.start()
            createdTimer = True
        else:
            if rotate_ms != self.adLastRotateMs:
                self.adTimer.setDelay(rotate_ms)
                self.adTimer.setInitialDelay(rotate_ms)
            if enabled == 1 and len(self.adList) > 0:
                if not self.adTimer.isRunning():
                    self.adTimer.start()
            else:
                if self.adTimer.isRunning():
                    self.adTimer.stop()

        # Keep last-applied settings
        self.adLastRotateMs = rotate_ms
        self.adLastMode = mode

        # --- DIAGNOSTIC ---
        try:
            isRun = (self.adTimer is not None and self.adTimer.isRunning())
            self._Log("ApplyAds enabled=%d vis=%s rotateMs=%d mode=%s timerCreated=%s timerRunning=%s adIndex=%d adCount=%d" % (
                int(enabled),
                str(self.ad.isVisible()),
                int(rotate_ms),
                mode,
                str(createdTimer),
                str(isRun),
                int(self.adIndex),
                len(self.adList)
            ))
        except:
            pass

        # Push first ad immediately via a helper (prevents any class-scope NameError)
        self._PushFirstAdIfNeeded(enabled)
    
    def _PushFirstAdIfNeeded(self, enabled):
        # Only run when ads are enabled and there's at least one ad.
        try:
            if enabled == 1 and len(self.adList) > 0:
                if self.adIndex < 0:
                    self._Log("ApplyAds pushing first ad now")
                    # IMPORTANT: marshal to EDT to avoid race with Swing Timer.
                    self._RunOnEdt(lambda: self._advance_ad(first=True))
        except:
            # Diagnostics must never crash the UI
            pass
    
    def _advance_ad(self, first=False):
        """Advance ad index according to mode and push to banner on the EDT."""
        if len(self.adList) == 0:
            try: self._Log("AdvanceAd skipped: adList empty")
            except: pass
            return
        mode = self._read_str(AD_MODE_MEM, 'seq').lower()
        prev = self.adIndex
        if first:
            self.adIndex = 0
        else:
            if mode == 'rand':
                if len(self.adList) == 1:
                    self.adIndex = 0
                else:
                    n = self.adIndex
                    while n == self.adIndex:
                        n = int(self.rand.nextInt(len(self.adList)))
                    self.adIndex = n
            else:
                self.adIndex = (self.adIndex + 1) % len(self.adList)

        ad = self.adList[self.adIndex]

        try:
            self._Log("AdvanceAd first=%s prev=%d next=%d mode=%s brand='%s' cta='%s'" % (
                str(first), int(prev), int(self.adIndex), mode, ad.get('brand',''), ad.get('cta','')
            ))
        except:
            pass

        # Push to the Swing UI strictly on the EDT
        def push():
            try:
                self.ad.setAd(ad.get('brand',''), ad.get('l1',''), ad.get('l2',''), ad.get('cta',''))
                self.ad.revalidate(); self.ad.repaint()
            except:
                pass

        self._RunOnEdt(push)

    def _onAdTick(self, ev):
        enabled = self._read_enabled(ADS_ENABLED_MEM, True)
        try:
            self._Log("AdTick enabled=%d adIndex=%d adCount=%d timerRunning=%s" % (
                int(enabled),
                int(self.adIndex),
                len(self.adList),
                str(self.adTimer is not None and self.adTimer.isRunning())
            ))
        except:
            pass
        if enabled != 1 or len(self.adList) == 0:
            return
        self._advance_ad(first=False)

    # ------------------------------ Render ------------------------------
    def _onTick(self, ev):
        # Issuance (user-facing)
        try:
            issue = int(FC_ISSUE.getValue() or 0)
            self.meta.setText("Issued %s %s" % (_dow_name_from_abs_minute(issue), _fmt_hhmm(issue % 1440)))
        except Exception:
            self.meta.setText("Issued -- --:--")

        # Update Now bar (large icon)
        self.nowBar.refresh()

        # Update tab labels and selection styles
        day2_name = _dow_name_from_abs_minute(self._abs_min_now() + 2*1440)
        self.btnDay2.setText(day2_name)
        for i,b in enumerate((self.btnToday, self.btnTomorrow, self.btnDay2)):
            b.setSelected(i == self.page)

        # Read forecast and render current page
        pts = self._read_points()
        try: step = int(FC_STEP.getValue() or 60)
        except Exception: step = 60

        base_abs = self._abs_min_now()
        start_abs = self._page_midnight_abs(base_abs, self.page)
        sr_page, ss_page = self._sunrise_sunset_for_abs(start_abs)

        # Fill up to 24 cells; hide any without data
        shown = 0
        for hour in range(24):
            t = start_abs + hour * 60
            pct, ok = self._nearest_value_at(t, pts, step)
            if ok and shown < len(self.hourCells):
                cell = self.hourCells[shown]
                cell.setData(t, _fmt_hhmm(t % 1440), pct, sr_page, ss_page)
                cell.setVisible(True)
                shown += 1
        for i in range(shown, len(self.hourCells)):
            self.hourCells[i].setVisible(False)

        # --- Ads: reload if config changed and ensure timer/visibility correct ---
        self._reload_ads_from_mem()
        self._apply_ad_visibility_and_timer()
        self._applyProTitle()

    def handle(self):
        # Wake on time/DOW/forecast update and ad controls
        self.waitChange([
            CLOCK_MEM, DOW_MEM, FC_POINTS, FC_ISSUE, FC_UPDATED, CLOUD_NOW,
            ADS_ENABLED_MEM, AD_ROTATE_SEC, AD_MODE_MEM, AD_COUNT_MEM
            # Note: individual IMAD{i}_* are polled inside _reload_ads_from_mem()
        ])
        self._onTick(None)
        return True

# Start
ui = WeatherForecastUI()
ui.setName('Weather forecast UI')
ui.start()