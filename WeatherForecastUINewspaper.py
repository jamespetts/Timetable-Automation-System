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
import jmri, java, csv, random
from java.awt import Color, Font, BasicStroke, RenderingHints, Dimension, GridLayout, BorderLayout
from java.awt.geom import Area, Ellipse2D, RoundRectangle2D
from javax.swing import JPanel, JLabel, BoxLayout, BorderFactory, JTextArea, JEditorPane, JScrollPane, ScrollPaneConstants
from javax.swing.border import EmptyBorder
import TASBeanLookup as TBL

# ------------------------------ SIZING & STYLES ------------------------------
PAGE_H_MARGIN = 8  # left/right padding
COL_GAP = 8        # gap between day columns (modern)
ROW_GAP = 4        # gap between rows
ICON_W = 66        # icon column width (modern)
WRAP_W_OLD_AD  = 220  # wrap width inside right-side old advert (px)
WRAP_W_OLD_COL = 230  # wrap width in each old-style text column (px)
OLD_COL_GAP    = 10   # horizontal gap between old columns
AD_SIDEBAR_W   = WRAP_W_OLD_AD + 50  # reserve space to align header over columns
MIN_H_MODERN = 680
MAX_W_OLD    = 900
OLD_HEIGHT_CAP = 440

# Modern (white)
MOD_BG   = Color(255,255,255)
MOD_TEXT = Color(20,20,20)
MOD_SUBTEXT = Color(75,80,90)
MOD_RULE = Color(130,135,145)

# Old (newsprint)
OLD_BG    = Color(246,244,235)
OLD_TEXT  = Color(24,24,24)
OLD_SUBTEXT = Color(70,70,70)
OLD_RULE  = Color(0,0,0)  # CHANGED: true black rules

# Modern icon ink
INK = Color(25,25,25)
INK_LINE = Color(70,70,80)

# Half-day bounds
AM_START, AM_END = 6*60, 12*60
PM_START, PM_END = 12*60, 24*60

# ------------------------------ MEMORIES ------------------------------
mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)

# Use TASBeanLookup to ensure beans exist and values are seeded
def mem(suffix, default=None):
    return TBL.ProvideMemoryBySuffix(suffix, default)

CLOCK_MEM = mem("CURRENTTIME")
DOW_MEM = mem("DAYOFWEEK")

# WG2 forecast
FC_STEP = mem("WX_FC_STEP_MIN", 60)
FC_POINTS = mem("WX_FC_POINTS", '')


# Newspaper options (snapshot at launch)
NEWS_STYLE = mem("WX_NEWS_STYLE", 'modern') # 'modern' | 'old'
NEWS_DAYS = mem("WX_NEWS_DAYS", 3)        # 2..3
PAPERNAME_MEM = mem("WX_NEWS_PAPERNAME")

# Day/night preset
DAYNIGHT_PRESET_MEM = mem("DAYNIGHT_PRESET")

# Spoof ads
ADS_ENABLED = mem("SPOOFADSENABLED", 1)
AD_COUNT = mem("AD_COUNT", 0)

# ------------------------------ SUN TIMES ------------------------------
def _active_preset_name():
    try:
        v = DAYNIGHT_PRESET_MEM.getValue()
        if v is not None:
            s = str(v).strip()
            if s: return s
    except Exception:
        pass
    return 'Maesteg_Sep2017'

def _sun_csv_path():
    try:
        return jmri.util.FileUtil.getExternalFilename("profile:jython/config/daynight.csv")
    except Exception:
        return "jython/config/daynight.csv"

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
        p = s.split(':')
        if len(p) >= 2: return (int(p[0])%24)*60 + (int(p[1])%60)
        return int(default_m)
    except Exception:
        return int(default_m)

def _load_daynight_from_tsv(path, preset_name, fallback):
    out = dict(fallback)
    try:
        f = open(path, 'r')
        try:
            rdr = csv.DictReader(f, delimiter='\t')
            for row in rdr:
                if row.get('name') != preset_name: continue
                d = row.get('day')
                if d not in DAYS: continue
                out[d] = {
                    'civil_dawn': _parse_time_to_minutes(row.get('civil_dawn'), fallback[d]['civil_dawn']),
                    'sunrise':    _parse_time_to_minutes(row.get('sunrise'),    fallback[d]['sunrise']),
                    'sunset':     _parse_time_to_minutes(row.get('sunset'),     fallback[d]['sunset']),
                    'civil_dusk': _parse_time_to_minutes(row.get('civil_dusk'), fallback[d]['civil_dusk']),
                }
        finally:
            f.close()
    except Exception as e:
        print('DayNight CSV load failed in newspaper UI: {}'.format(e))
    return out

def _dow_idx(name):
    try: return DAYS.index(str(name))
    except Exception: return 0

def _dow_name_from_abs_minute(abs_min):
    return DAYS[int((abs_min // 1440) % 7)]

def _fmt_hhmm(mins_of_day):
    hh = int((mins_of_day % 1440) // 60)
    mm = int(mins_of_day % 60)
    return "%02d:%02d" % (hh, mm)
# ------------------------------ HELPERS ------------------------------
def _abs_now(timebase, dow_mem):
    t = timebase.getTime()
    fmt = java.text.SimpleDateFormat('HH:mm'); hh, mm = fmt.format(t).split(':')
    return _dow_idx(dow_mem.getValue()) * 1440 + int(hh)*60 + int(mm)

def _page_midnight_abs(base_abs, day_offset):
    return base_abs - (base_abs % 1440) + day_offset * 1440

def _read_points_once():
    try:
        s = str(FC_POINTS.getValue() or '').strip()
        if s == '': return []
        out = []
        for tok in s.split(','):
            tok = tok.strip()
            if ':' not in tok: continue
            a, b = tok.split(':', 1)
            out.append((int(a), int(b)))
        return out
    except Exception as e:
        print("Newspaper UI parse error (FC_POINTS): {}".format(e))
        return []

def _avg_block(pts, start_abs, end_abs, step_min, sun_lookup):
    if not pts: return (0, 0.0, 0)
    total = 0; n = 0; day_hits = 0
    t = start_abs; step = max(1, int(step_min))
    while t < end_abs:
        best = None; bestd = 1<<30
        for (tt, v) in pts:
            d = abs(tt - t)
            if d < bestd: bestd = d; best = (tt, v)
        if best is None or bestd > int(step * 1.5):
            t += step; continue
        v = int(best[1]); total += v; n += 1
        sr, ss = sun_lookup(t); mod = t % 1440
        if (mod >= sr) and (mod <= ss): day_hits += 1
        t += step
    if n == 0: return (0, 0.0, 0)
    return (int(round(float(total)/n)), float(day_hits)/n, n)

def _headline(avg_pct, daylike):
    p = int(avg_pct)
    if not daylike:
        if p <= 5:  return "Clear night"
        if p <= 25: return "Mostly clear night"
        if p <= 50: return "Partly cloudy night"
        if p <= 75: return "Mostly cloudy night"
        return "Overcast night"
    else:
        if p <= 5:  return "Clear"
        if p <= 25: return "Mostly clear"
        if p <= 50: return "Partly cloudy"
        if p <= 75: return "Mostly cloudy"
        return "Overcast"

def _strap_modern(avg_pct, daylike):
    if not daylike:
        if avg_pct <= 25: return "Good visibility"
        if avg_pct <= 50: return "Broken cloud"
        if avg_pct <= 75: return "Extensive cloud"
        return "Thick cloud"
    else:
        if avg_pct <= 25: return "Bright spells"
        if avg_pct <= 50: return "Sunny intervals"
        if avg_pct <= 75: return "Limited brightness"
        return "Dull conditions"

# ------------------------------ text utilities ------------------------------
def _ascii_only(s):
    try:
        u = unicode(s)
    except Exception:
        u = str(s)
    repl = {
        u'\u2018': "'", u'\u2019': "'",
        u'\u201C': '"', u'\u201D': '"',
        u'\u2013': '-', u'\u2014': '-',
        u'\u00A0': ' ', u'\u00B7': '.',
        u'\u00E9': 'e', u'\u00E0': 'a', u'\u00F6': 'o'
    }
    u = ''.join(repl.get(ch, ch) for ch in u)
    return ''.join(ch for ch in u if ord(ch) < 128)

def _html_escape(s):
    t = str(s)
    # (kept as in your file)
    return (t.replace("&","&")
             .replace("<","<")
             .replace(">"," >")
             .replace("'", "&#39;"))

def _apply_fixed_html_width(ep, width_px):
    ep.setSize(Dimension(int(width_px), 10000))
    ps = ep.getPreferredSize()
    ep.setPreferredSize(Dimension(int(width_px), ps.height))

# ------------------------------ glue helpers ------------------------------
def _gapV(h):
    p = JPanel(); p.setOpaque(False)
    p.setPreferredSize(Dimension(1, h)); p.setMinimumSize(Dimension(1, h)); p.setMaximumSize(Dimension(32767, h))
    return p

def glueH():
    p = JPanel(); p.setOpaque(False)
    p.setPreferredSize(Dimension(1, 1)); p.setMinimumSize(Dimension(1, 1)); p.setMaximumSize(Dimension(32767, 1))
    return p

# ------------------------------ Masthead ------------------------------
def _build_suntimes_panel(style_old, sunRiseStr, sunSetStr):
 # Build a small sunrise/sunset line to appear below the last forecast.
 if sunRiseStr is None or sunSetStr is None: return None
 p = JPanel(); p.setOpaque(False)
 p.setLayout(BoxLayout(p, BoxLayout.Y_AXIS))
 rule_col = OLD_RULE if style_old else MOD_RULE
 txt_col = OLD_SUBTEXT if style_old else MOD_SUBTEXT
 p.add(RuleLine(rule_col, 1))
 p.add(_gapV(2))
 row = JPanel(); row.setOpaque(False)
 row.setLayout(BoxLayout(row, BoxLayout.X_AXIS))
 label = JLabel("Sunrise " + str(sunRiseStr) + "   Sunset " + str(sunSetStr))
 label.setForeground(txt_col)
 label.setFont(Font("Serif" if style_old else "SansSerif", Font.PLAIN, 12))
 row.add(glueH()); row.add(label); row.add(glueH())
 p.add(row)
 return p

def _build_suntimes_box(style_old, sunRiseStr, sunSetStr):
    # Compact sunrise/sunset block to sit inside a forecast column (ASCII only).
    if sunRiseStr is None or sunSetStr is None: return None
    p = JPanel(); p.setOpaque(False)
    rule_col = OLD_RULE if style_old else MOD_RULE
    txt_col = OLD_TEXT if style_old else MOD_TEXT
    sub_col = OLD_SUBTEXT if style_old else MOD_SUBTEXT
    p.setBorder(BorderFactory.createCompoundBorder(
        BorderFactory.createLineBorder(rule_col, 1),
        EmptyBorder(6,8,6,8)
    ))
    p.setLayout(BoxLayout(p, BoxLayout.Y_AXIS))
    h = JLabel("SUN")
    h.setForeground(sub_col)
    h.setFont(Font("Serif" if style_old else "SansSerif", Font.BOLD, 10))
    h.setAlignmentX(0.5)
    p.add(h)
    p.add(_gapV(2))
    l1 = JLabel("Sunrise " + str(sunRiseStr))
    l1.setForeground(txt_col)
    l1.setFont(Font("Serif" if style_old else "SansSerif", Font.BOLD, 12))
    l1.setAlignmentX(0.5)
    p.add(l1)
    p.add(_gapV(1))
    l2 = JLabel("Sunset  " + str(sunSetStr))
    l2.setForeground(txt_col)
    l2.setFont(Font("Serif" if style_old else "SansSerif", Font.BOLD, 12))
    l2.setAlignmentX(0.5)
    p.add(l2)
    return p

class RuleLine(JPanel):
    def __init__(self, color, pixels=2):
        JPanel.__init__(self); self.setOpaque(False)
        self._c = color; self._h = int(pixels)
        self.setPreferredSize(Dimension(1, self._h))
        self.setMinimumSize(Dimension(1, self._h))
        self.setMaximumSize(Dimension(32767, self._h))
    def paintComponent(self, g):
        super(RuleLine, self).paintComponent(g)
        g.setColor(self._c); g.fillRect(0, 0, self.getWidth(), self._h)

class Masthead(JPanel):
    def __init__(self, style_old, paper, pub_label, include_title=True):
        JPanel.__init__(self); self.setOpaque(False)
        self.setLayout(BoxLayout(self, BoxLayout.Y_AXIS))
        self.setBorder(EmptyBorder(4, PAGE_H_MARGIN, 2, PAGE_H_MARGIN))
        if style_old:
            small = Font("Serif", Font.BOLD, 12); titleF = Font("Serif", Font.BOLD, 30)
            tcol = OLD_SUBTEXT; text = OLD_TEXT; rule = OLD_RULE
        else:
            small = Font("SansSerif", Font.BOLD, 12); titleF = Font("SansSerif", Font.BOLD, 24)
            tcol = MOD_SUBTEXT; text = MOD_TEXT; rule = MOD_RULE
        top = JPanel(); top.setOpaque(False); top.setLayout(BoxLayout(top, BoxLayout.X_AXIS))
        left = JLabel(paper); left.setForeground(tcol); left.setFont(small); left.setForeground(tcol); left.setFont(small)
        right = JLabel(pub_label); right.setForeground(tcol); right.setFont(small)
        top.add(left); top.add(glueH()); top.add(right)
        self.add(top); self.add(RuleLine(rule, 2)); self.add(_gapV(4))
        if include_title:
            title = JLabel("Weather forecast"); title.setForeground(text); title.setFont(titleF); title.setAlignmentX(0.5)
            self.add(title); self.add(_gapV(4))

# ------------------------------ Modern icon canvas ------------------------------
class IconCanvas(JPanel):
    def __init__(self):
        JPanel.__init__(self); self.setOpaque(False)
        self.setPreferredSize(Dimension(ICON_W, 60))
        self.setMinimumSize(Dimension(ICON_W, 60))
        self.setMaximumSize(Dimension(ICON_W, 60))
        self.kind = None
    def setKind(self, k): self.kind = k; self.repaint()
    def paintComponent(self, g):
        super(IconCanvas, self).paintComponent(g)
        if self.kind is None: return
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            _draw_icon_modern(g2, self.kind, 6, 6, 46)
        finally:
            g2.dispose()

def _draw_icon_modern(g2, kind, x, y, size):
    cx = x + size//2; cy = y + size//2; r = int(size*0.36)
    g2.setStroke(BasicStroke(2.4))
    if kind == 'sun':
        g2.setColor(INK); g2.fillOval(cx-r, cy-r, 2*r, 2*r)
        ray = int(r*0.48)
        for k in range(8):
            ang = (3.14159/4.0)*k
            x1 = cx + int((r+1)  * java.lang.Math.cos(ang))
            y1 = cy + int((r+1)  * java.lang.Math.sin(ang))
            x2 = cx + int((r+ray)* java.lang.Math.cos(ang))
            y2 = cy + int((r+ray)* java.lang.Math.sin(ang))
            g2.drawLine(x1,y1,x2,y2)
    elif kind == 'cloud':
        _puffy_cloud(g2, cx, cy, size)
    elif kind == 'sun+cloud':
        _draw_icon_modern(g2, 'sun', x-5, y-7, size); _puffy_cloud(g2, cx+9, cy+7, int(size*0.94))
    elif kind == 'moon':
        R = r+1
        g2.setColor(INK); g2.fillOval(cx-R, cy-R, 2*R, 2*R)
        g2.setColor(Color(255,255,255))
        g2.fillOval(cx-int(R*0.56), cy-R, int(2.18*R), 2*R)
    elif kind == 'moon+cloud':
        _draw_icon_modern(g2, 'moon', x-5, y-5, size); _puffy_cloud(g2, cx+9, cy+7, int(size*0.94))

def _puffy_cloud(g2, cx, cy, size):
    e1 = Ellipse2D.Float(cx - int(0.52*size), cy - int(0.30*size), int(0.58*size), int(0.58*size))
    e2 = Ellipse2D.Float(cx - int(0.12*size), cy - int(0.38*size), int(0.62*size), int(0.62*size))
    e3 = Ellipse2D.Float(cx + int(0.30*size), cy - int(0.22*size), int(0.46*size), int(0.46*size))
    base = RoundRectangle2D.Float(cx - int(0.62*size), cy - int(0.02*size), int(1.24*size), int(0.52*size), 16, 16)
    area = Area(e1); area.add(Area(e2)); area.add(Area(e3)); area.add(Area(base))
    g2.setColor(Color(255,255,255)); g2.fill(area)
    g2.setColor(INK_LINE); g2.setStroke(BasicStroke(2.0)); g2.draw(area)

# ------------------------------ DAY PANELS ------------------------------
class ModernHalfRow(JPanel):
    def __init__(self, label_text):
        JPanel.__init__(self); self.setOpaque(False)
        self.setLayout(BoxLayout(self, BoxLayout.X_AXIS))
        self.setBorder(EmptyBorder(4,4,4,4))
        self.icon = IconCanvas()
        text = JPanel(); text.setOpaque(False); text.setLayout(BoxLayout(text, BoxLayout.Y_AXIS))
        self.t = JLabel(label_text); self.t.setForeground(MOD_SUBTEXT); self.t.setFont(Font("SansSerif", Font.BOLD, 12))
        self.h = JLabel("--"); self.h.setForeground(MOD_TEXT); self.h.setFont(Font("SansSerif", Font.BOLD, 15))
        self.s = JLabel(" "); self.s.setForeground(MOD_SUBTEXT); self.s.setFont(Font("SansSerif", Font.PLAIN, 12))
        text.add(self.t); text.add(_gapV(1)); text.add(self.h); text.add(_gapV(1)); text.add(self.s)
        self.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createLineBorder(MOD_RULE,1), EmptyBorder(4,4,4,4)))
        self.add(self.icon)
        self.add(_gapV(0))
        self.add(JPanel()); self.getComponent(2).setOpaque(False); self.getComponent(2).setPreferredSize(Dimension(8,1))
        self.add(text)
    def setContent(self, have, avg, daylike, head, strap):
        self.setVisible(have)
        if not have: return
        if daylike:
            kind = 'sun' if avg <= 10 else ('sun+cloud' if avg <= 75 else 'cloud')
        else:
            kind = 'moon' if avg <= 10 else ('moon+cloud' if avg <= 85 else 'cloud')
        self.icon.setKind(kind); self.h.setText(str(head)); self.s.setText(str(strap))

class OldFlowLine(JPanel):
    """Single wrappable line: <b>Prefix:</b> body (HTML in a JEditorPane)."""
    def __init__(self, wrap_px):
        JPanel.__init__(self); self.setOpaque(False)
        self._wrap = int(wrap_px)
        self.setLayout(BorderLayout())
        self.setBorder(EmptyBorder(1,0,1,0))
        self.ep = JEditorPane()
        self.ep.setContentType("text/html")
        self.ep.setEditable(False)
        self.ep.setOpaque(False)
        self.add(self.ep, BorderLayout.CENTER)
    def setParts(self, prefix, body):
        html = "<html><div style='font-family: serif; font-size: 12px; color: rgb(24,24,24);'><b>%s</b> %s</div></html>" % (
            _html_escape(prefix), _html_escape(body)
        )
        self.ep.setText(html)
        _apply_fixed_html_width(self.ep, self._wrap)
        try:
            ps = self.ep.getPreferredSize()
            # Prevent BoxLayout from stretching lines vertically; keep gaps realistic.
            self.ep.setMinimumSize(ps)
            self.ep.setPreferredSize(ps)
            self.ep.setMaximumSize(ps)
            self.setMinimumSize(ps)
            self.setPreferredSize(ps)
            self.setMaximumSize(ps)
        except Exception:
            pass

# ------------------------------ ADS ------------------------------
def _get_str(name, default):
    try:
        m = mem(name, default)
        v = m.getValue() if m is not None else None
        return default if v is None else _ascii_only(v)
    except Exception:
        return default

def _ads_from_memory(old_style):
    """Return candidate ads (list of tuples). If memories define ads, use them; else use era-appropriate defaults."""
    try: enabled = int(ADS_ENABLED.getValue() or 1)
    except Exception: enabled = 1
    if enabled != 1: return []
    try: count = int(AD_COUNT.getValue() or 0)
    except Exception: count = 0
    if count > 0:
        ads = []
        for i in range(1, count+1):
            b  = _get_str('AD%d_BRAND' % i, 'Brand %d' % i)
            l1 = _get_str('AD%d_L1' % i, 'Headline %d' % i)
            l2 = _get_str('AD%d_L2' % i, 'Subline %d' % i)
            cta= _get_str('AD%d_CTA' % i, 'Enquire within')
            ads.append((_ascii_only(b), _ascii_only(l1), _ascii_only(l2), _ascii_only(cta)))
        return ads
    # Expanded ASCII-only defaults (old era) ~12 items
    if old_style:
        return [
            ('Great Western Refreshments', 'Tea of notable strength', 'Favoured by travellers and staff alike.', 'Apply by post for prices'),
            ('Maesteg Coal and Iron', 'Engines properly supplied', 'Quality fuel for dependable service.', 'Enquiries to the office'),
            ('Jones and Sons Outfitters', 'Clothing for the railwayman', 'Durable boots and coats at fair rates.', 'Catalogues on request'),
            ('Bristol Brassworks', 'Fittings and couplings', 'Reliable stock for workshops and depots.', 'Write for a price list'),
            ('Harringtons Patent Oils', 'For smooth running', 'Engines preserved from undue wear.', 'Agents nationwide'),
            ('Western Union Carriage Works', 'Repairs undertaken', 'Prompt attention - fair charges.', 'Estimates furnished'),
            ('Carter and Pike Provisions', 'Provisions for staff messes', 'Good value. Sound quality.', 'Terms on application'),
            ('Albion Lamp Company', 'Lanterns and wicks', 'Bright light for yard and shed.', 'Order by post'),
            ('Swan Ink and Copy', 'For offices and clerks', 'Clean, durable ink.', 'Boxes kept in stock'),
            ('Pembroke Rope and Canvas', 'Ropes, tarpaulins, sheets', 'Strong and weather fast.', 'Send measurements'),
            ('Midland Timber Merchants', 'Wagons and staging', 'Well seasoned and straight.', 'Yard open daily'),
            ('Gower Quarry Stone', 'Setts and sleepers packed', 'Hard wearing and true.', 'Rates on enquiry'),
        ]
    # Expanded ASCII-only defaults (modern era) ~12 items
    else:
        return [
            ('RailNet Ultra', 'Reliable signalling for busy routes', 'Trusted by operators nationwide', 'Call 0800 000 000'),
            ("Billy's Replacement Speakers", 'Turning it up to 11 since 1911', 'Only the best interior gubbins', 'Order today'),
            ('Acme RailCloud', 'Fleet control made simple', 'Fast. Secure. Affordable.', 'Visit acme.example'),
            ('SignalSure', 'Next gen interlocking', 'Fail safe by design', 'Book a demo'),
            ('LocoWash Pro', 'Keep the fleet spotless', 'Low water. High shine.', 'Service plans available'),
            ('Waybeam IoT', 'Trackside sensors at scale', 'Data you can depend on', 'Contact sales'),
            ('RailShield', 'Lineside cabinets', 'Rugged and secure', 'Request a brochure'),
            ('AxleGuard', 'Condition monitoring', 'Detect faults early', 'Free trial available'),
            ('DepotMate', 'Crew rostering software', 'Simple. Powerful.', 'Start now'),
            ('GreenVolt Power', 'Battery systems for yards', 'Quiet and clean', 'Ask for a quote'),
            ('ClearSignal', 'Training and certification', 'Build skills fast', 'Enroll today'),
            ('TrackBond', 'High strength adhesives', 'For fast repairs', 'Order online'),
        ]

def _small_old_ads():
    """Dedicated pool for compact old-style adverts (shorter lines; ASCII only)."""
    return [
        ('Rivet and Bolt Co', 'Fastenings supplied', 'Strong stock. Fair rates.', 'Post orders'),
        ('Harper Oil and Grease', 'For bearings and slides', 'Clean running assured.', 'Agents wanted'),
        ('Beacon Lamps', 'Yard and shed lanterns', 'Bright light. Long burning.', 'Write for lists'),
        ('Crown Canvas', 'Tarpaulins and sheets', 'Well made. Weather fast.', 'Send sizes'),
        ('Willm. Loud & Sons', 'Replacement gramophone horns', 'Made from finest materials', 'Order by post'),
        ('Foundry Tools Ltd', 'Hammers and chisels', 'Forged and tempered.', 'Price by letter'),
        ('Steam Gasket Works', 'Joints and packings', 'Tight seals, low cost.', 'Order today'),
        ('Ironmongers Supply', 'Nails, screws, fittings', 'Prompt dispatch.', 'Catalogue free'),
        ('Railway Tailor', 'Coats and boots', 'Hard wearing kit.', 'Measurements by post'),
        ('Coastal Quarries', 'Ballast and stone', 'Well screened.', 'Rates on enquiry'),
        ('Western Saddlery', 'Harness and leather', 'Stout and serviceable.', 'List sent'),
        ('Midland Brush Co', 'Yard brooms', 'Tough fibres.', 'Boxes in stock'),
    ]

# ------------------------------ OLD strapline with per-edition randomness & uniqueness ------------------------------
_EDITION_RNG = None
_ED_USED_LINES = None

def _bank_day(p):
    t = "today"
    if p <= 7:  return ["Clear and bright; excellent visibility " + t + ".",
                        "Fine and sunny " + t + "; cloud slight.",
                        "Sunny throughout " + t + "; air clear.",
                        "Bright and clear for much of " + t + ".",
                        "Good sunshine " + t + "; cloud minimal."]
    if p <= 18: return ["Plenty of sunshine " + t + "; only small amounts of cloud.",
                        "Bright for much of " + t + "; cloud slight at times.",
                        "Sunny most of " + t + "; pleasant conditions.",
                        "Long sunny spells " + t + "; light cloud passing.",
                        "Largely sunny; a little cloud " + t + "."]
    if p <= 28: return ["Bright intervals " + t + "; conditions widely pleasant.",
                        "Sunny spells " + t + "; brief cloud at times.",
                        "Good brightness for many; cloud increasing late " + t + ".",
                        "Sunshine and cloud in turn " + t + ".",
                        "Sunny periods for most; cloud more later."]
    if p <= 45: return ["Sunny intervals with passing cloud " + t + ".",
                        "Bright spells at times; cloud otherwise variable " + t + ".",
                        "Occasional sunshine " + t + "; cloud more general later.",
                        "Mixed skies " + t + "; sunshine now and then.",
                        "Intervals of brightness amid variable cloud " + t + "."]
    if p <= 60: return ["Rather cloudy " + t + "; limited brightness.",
                        "Cloud increasing; only brief bright intervals " + t + ".",
                        "Mostly cloudy " + t + "; a few short sunny spells.",
                        "Cloudy spells for much of " + t + "; odd gleam.",
                        "Bright breaks few and far between " + t + "."]
    if p <= 75: return ["Much cloud " + t + "; only rare gleams of sunshine.",
                        "Dull for long periods " + t + "; scant brightness.",
                        "Extensive cloud " + t + "; only occasional breaks.",
                        "Cloud thick for much of " + t + "; limited bright spells.",
                        "Grey conditions " + t + "; brightness scarce."]
    if p <= 88: return ["Overcast for much of " + t + "; little change expected.",
                        "Grey and dull " + t + "; only isolated thinner patches.",
                        "Cloud thick and widespread " + t + "; brightness scarce.",
                        "Uniform grey skies " + t + "; breaks unlikely.",
                        "Widespread cloud " + t + "; few if any sunny spells."]
    return ["Overcast throughout " + t + "; little alteration looked for.",
            "Uniform grey conditions " + t + "; no appreciable brightness.",
            "Dull and overcast " + t + "; little or no change.",
            "Cloud unbroken " + t + "; brightness not expected.",
            "Solid overcast " + t + "; no improvement likely."]

def _bank_night(p):
    t = "tonight"
    if p <= 10: return ["Fair and clear " + t + "; visibility generally good.",
                        "Clear spells " + t + "; stars apparent at times.",
                        "Mostly clear " + t + "; air fresh.",
                        "Clear sky " + t + " for many places.",
                        "Largely clear " + t + "; good visibility."]
    if p <= 25: return ["Broken cloud " + t + "; occasional clear slots.",
                        "Cloud in parts " + t + "; intervals of clearer sky.",
                        "Variable cloud " + t + "; some clear periods.",
                        "Cloud patchy " + t + "; clearer gaps at times.",
                        "Cloud broken at times " + t + "; some stars seen."]
    if p <= 50: return ["Patchy cloud " + t + "; clearer intervals at times.",
                        "Variable cloud through the hours of darkness.",
                        "Cloud changing " + t + "; some breaks possible.",
                        "Cloud varying " + t + "; occasional clearer spells.",
                        "Large patches of cloud " + t + "; odd break."]
    if p <= 75: return ["Cloud rather extensive " + t + ".",
                        "Large amounts of cloud " + t + "; few stars seen.",
                        "Considerable cloud " + t + "; only brief clearer spells.",
                        "Cloud widespread " + t + "; clearer slots uncommon.",
                        "Much cloud " + t + "; only rare gaps."]
    return ["Overcast " + t + "; little alteration expected.",
            "Thick cloud " + t + "; no significant breaks.",
            "Cloud solid " + t + "; little change likely.",
            "Skies overcast " + t + "; no clearance expected.",
            "Cloud persistent " + t + "; breaks not expected."]

def _strap_old(avg_pct, daylike):
    """
    Keep the original call signature, but:
    - Use per-edition RNG for non-determinism,
    - Enforce uniqueness within the current edition (no duplicate lines),
    - ASCII only.
    """
    global _EDITION_RNG, _ED_USED_LINES
    if _EDITION_RNG is None:
        _EDITION_RNG = random.Random(int(java.lang.System.currentTimeMillis() & 0x7FFFFFFF))
    if _ED_USED_LINES is None:
        _ED_USED_LINES = set()
    p = int(avg_pct)
    bank = _bank_day(p) if daylike else _bank_night(p)
    bank = list(bank)
    _EDITION_RNG.shuffle(bank)
    for cand in bank:
        if cand not in _ED_USED_LINES:
            _ED_USED_LINES.add(cand)
            return cand
    # Rare fallback: mutate one to make it unique
    base = bank[0]
    qualifiers = [
        " Conditions similar elsewhere.",
        " Little change expected across the district.",
        " Only slight variation by locality.",
        " A few brief changes possible.",
        " Widely so.",
    ]
    nudges = [
        " Later improvement uncertain.",
        " Any clearance short-lived.",
        " Trend uncertain.",
        " Only minor change later.",
    ]
    out = base.rstrip('.') + "." + qualifiers[_EDITION_RNG.randrange(len(qualifiers))]
    if out in _ED_USED_LINES:
        out = out + nudges[_EDITION_RNG.randrange(len(nudges))]
    _ED_USED_LINES.add(out)
    return out

# ------------------------------ AD FOOTER STRAP (old big ad) ------------------------------
def _old_ad_footer_strap():
    """
    Build a short, era-appropriate strap for the big old advert footer.
    CHANGED: avoid literal '\u00b7' sequence; use ASCII hyphen as separator.
    """
    rng = _EDITION_RNG if _EDITION_RNG else random.Random(int(java.lang.System.currentTimeMillis() & 0x7FFFFFFF))
    est_pool = [
        "Established 1909", "Est. 1909", "Since 1909", "Founded 1909"
    ]
    scope_pool = [
        "Agents nationwide", "Branches in principal towns", "Enquiries invited",
        "Prices on application", "Catalogues posted", "Trade supplied"
    ]
    # ASCII-only separator to avoid stray \u00b7 text
    return rng.choice(est_pool) + " - " + rng.choice(scope_pool)

# ------------------------------ AD PANELS ------------------------------
class ModernAd(JPanel):
    """Centred lines; font sizes tuned to fill; used in a 2-column footer."""
    def __init__(self, ad_tuple):
        JPanel.__init__(self); self.setOpaque(False)
        b, l1, l2, cta = ad_tuple
        self.setLayout(GridLayout(0,1,0,2))
        self.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createLineBorder(MOD_RULE,2), EmptyBorder(10,12,10,12)))
        def L(txt, size, bold):
            style = Font.BOLD if bold else Font.PLAIN
            lbl = JLabel(_ascii_only(txt))
            lbl.setForeground(MOD_TEXT)
            lbl.setFont(Font("SansSerif", style, int(size)))
            lbl.setHorizontalAlignment(JLabel.CENTER)
            return lbl
        adv = JLabel("Advertisement")
        adv.setForeground(MOD_SUBTEXT)
        adv.setFont(Font("SansSerif", Font.BOLD, 11))
        adv.setHorizontalAlignment(JLabel.CENTER)
        self.add(adv)
        self.add(L(b, 18, True))
        self.add(L(l1, 16, True))
        self.add(L(l2, 14, False))
        self.add(L(cta, 14, True))

class OldAd(JPanel):
    """
    Right-side OLD advert (double rule).
    - All text centre-aligned (HTML).
    - Two separator rules (above body and above footer).
    - Always shows a footer strap.
    - Fixed wrap width.

    Note: The advert is intended to fit the forecast column height. If the
    rendered advert is taller, it will be vertically clipped by the caller
    (preferred/max height set externally).
    """
    def __init__(self, ad_tuple):
        JPanel.__init__(self); self.setOpaque(False)
        b,l1,l2,cta = tuple(_ascii_only(x) for x in ad_tuple)

        # Border (single rule) with padding
        self.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(OLD_RULE, 2),
            EmptyBorder(8, 10, 8, 10)
        ))
        self.setLayout(BorderLayout())

        hr_col = "rgb(0,0,0)"
        strap = _old_ad_footer_strap()

        def sep_div(mtop=6, mbot=6):
            mt = int(mtop); mb = int(mbot)
            return (
                "<div style='margin:{mt}px 0 {mb}px 0; border-top:1px solid {hr}; height:0;'></div>"
            ).format(mt=mt, mb=mb, hr=hr_col)

        html = (
            "<html><div style='font-family: serif; color: rgb(24,24,24); text-align:center; line-height:1.28;'>"
            "<div style='font-size: 17px; font-weight:bold; margin-top: 2px;'>{brand}</div>"
            "<div style='font-size: 17px; font-weight:bold; margin-top: 3px;'>{l1}</div>"
            "{rule1}"
            "<div style='font-size: 13px; margin-top: 12px;'>{l2}</div>"
            "<div style='font-size: 13px; font-weight:bold; margin-top: 10px;'>{cta}</div>"
                        "<div style='font-size: 12px; color: rgb(60,60,60); margin-top: 12px;'>{strap}</div>"
            "</div></html>"
        ).format(
            brand=_html_escape(b.upper()),
            l1=_html_escape(l1),
            l2=_html_escape(l2) if (l2 and l2.strip()) else " ",
            cta=_html_escape(cta) if (cta and cta.strip()) else " ",
            rule1=sep_div(6, 6),
            rule2="",
            strap=_html_escape(strap)
        )

        self.ep = JEditorPane()
        self.ep.setContentType("text/html")
        self.ep.setEditable(False)
        self.ep.setOpaque(False)
        self.ep.setText(html)

        # Constrain width for wrapping
        _apply_fixed_html_width(self.ep, WRAP_W_OLD_AD)
        try:
            ps = self.ep.getPreferredSize()
            self.ep.setMinimumSize(ps)
            self.ep.setPreferredSize(ps)
            self.ep.setMaximumSize(ps)
        except Exception:
            pass

        self.add(self.ep, BorderLayout.CENTER)

        # Width hint (height is set by caller)
        self.setPreferredSize(Dimension(WRAP_W_OLD_AD + 50, 10))
        self.setMaximumSize(Dimension(WRAP_W_OLD_AD + 80, 100000))
class SmallOldAd(JPanel):
    """Compact, era-style advert to drop inside a column (fills missing space neatly)."""
    def __init__(self, ad_tuple):
        JPanel.__init__(self); self.setOpaque(False)
        b,l1,l2,cta = tuple(_ascii_only(x) for x in ad_tuple)
        self.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(OLD_RULE,1),
            EmptyBorder(6,8,6,8)
        ))
        self.setLayout(BorderLayout())
        self.ep = JEditorPane()
        self.ep.setContentType("text/html"); self.ep.setEditable(False); self.ep.setOpaque(False)
        html = (
            "<html><div style='font-family: serif; font-size: 12px; color: rgb(24,24,24); text-align:center; line-height:1.28;'>"
            "<div style='font-weight:bold; margin-top: 0px;'>{b}</div>"
            "<div style='font-weight:bold; margin-top: 6px;'>{l1}</div>"
            "<div style='margin-top: 8px;'>{l2}</div>"
            "<div style='margin-top: 8px;'>{cta}</div>"
            "</div></html>"
        ).format(b=_html_escape(b), l1=_html_escape(l1), l2=_html_escape(l2), cta=_html_escape(cta))
        self.ep.setText(html)
        _apply_fixed_html_width(self.ep, WRAP_W_OLD_COL)
        self.add(self.ep, BorderLayout.CENTER)

# ------------------------------ MAIN AUTOMATON ------------------------------
class WeatherForecastNewspaper(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        self.timebase = jmri.InstanceManager.getDefault(jmri.Timebase)
        self.sunTimes = _load_daynight_from_tsv(_sun_csv_path(), _active_preset_name(), FALLBACK_SUN)

        # Snapshot style/days
        try: style = str(NEWS_STYLE.getValue() or 'modern').lower()
        except Exception: style = 'modern'
        old_style = (style == 'old')
        oldBigAd = None
        oldLeftPanel = None
        try:
            d = int(NEWS_DAYS.getValue() or 3); d = 2 if d < 2 else (3 if d > 3 else d)
        except Exception:
            d = 3
        requested_days = d

        # Publication stamp
        abs_now = _abs_now(self.timebase, DOW_MEM)
        pub_day = _dow_name_from_abs_minute(abs_now)
        pub_half = "AM" if (abs_now % 1440) < 12*60 else "PM"
        sunRiseStr = None
        sunSetStr = None
        try:
            stPub = self.sunTimes.get(pub_day, FALLBACK_SUN[pub_day])
            sunRiseStr = _fmt_hhmm(stPub['sunrise'])
            sunSetStr = _fmt_hhmm(stPub['sunset'])
        except Exception:
            pass
        pub_label = "%s %s" % (pub_day, pub_half)

        # Forecast snapshot
        pts = _read_points_once()
        try: step = int(FC_STEP.getValue() or 60)
        except Exception: step = 60

        # Non-deterministic edition RNG + uniqueness set (with console banner)
        global _EDITION_RNG, _ED_USED_LINES
        seed = int(java.lang.System.currentTimeMillis() & 0x7FFFFFFF)
        _EDITION_RNG = random.Random(seed)
        _ED_USED_LINES = set()
        print("Newspaper OLD variant engine ACTIVE; seed={}".format(seed))

        # Decide which days have content
        decisions = []
        for day_offset in range(requested_days):
            day0 = _page_midnight_abs(abs_now, day_offset)
            def sun_lookup(t_abs):
                dname = _dow_name_from_abs_minute(t_abs); st = self.sunTimes.get(dname, FALLBACK_SUN[dname])
                return st['sunrise'], st['sunset']
            s_am, e_am = day0 + AM_START, day0 + AM_END
            avg_am, dayfrac_am, n_am = _avg_block(pts, s_am, e_am, step, sun_lookup)
            s_pm, e_pm = day0 + PM_START, day0 + PM_END
            avg_pm, dayfrac_pm, n_pm = _avg_block(pts, s_pm, e_pm, step, sun_lookup)
            have_any = (n_am > 0) or (n_pm > 0)
            if have_any:
                decisions.append(('content', (day0, avg_am, dayfrac_am, n_am, avg_pm, dayfrac_pm, n_pm)))
            else:
                decisions.append(('skip', None))

        # Window title is the newspaper name
        title = self._paper_title()
        self.frame = jmri.util.JmriJFrame(title)
        cp = self.frame.getContentPane()
        cp.setBackground(OLD_BG if old_style else MOD_BG)
        cp.setLayout(BoxLayout(cp, BoxLayout.Y_AXIS))

        if old_style:
            # Masthead (title centered over columns via spacer)
            cp.add(Masthead(True, title, pub_label, include_title=False))

            # ===== OLD BODY: header centered over columns + two text columns + (EAST) large ad =====
            body = JPanel(); body.setOpaque(False); body.setLayout(BorderLayout())

            leftPanel = JPanel(); leftPanel.setOpaque(False); leftPanel.setLayout(BorderLayout())
            oldLeftPanel = leftPanel
            body.add(leftPanel, BorderLayout.CENTER)

            # Header row centered over columns, with fixed spacer at EAST equal to advert width
            hdr = JPanel(); hdr.setOpaque(False); hdr.setLayout(BorderLayout())
            title = JLabel("Weather forecast")
            title.setForeground(OLD_TEXT); title.setFont(Font("Serif", Font.BOLD, 30))
            title.setHorizontalAlignment(JLabel.CENTER)
            hdr.add(title, BorderLayout.CENTER)
            hdr.setBorder(EmptyBorder(0, PAGE_H_MARGIN, 0, PAGE_H_MARGIN))
            leftPanel.add(hdr, BorderLayout.NORTH)

            # Build sequential half-day lines; day names UPPERCASE
            items = []
            for kind, payload in decisions:
                if kind != 'content': continue
                (day0, avg_am, dayfrac_am, n_am, avg_pm, dayfrac_pm, n_pm) = payload
                dayname_up = _dow_name_from_abs_minute(day0).upper()
                if n_am > 0:
                    items.append( (dayname_up, "%s morning:" % dayname_up, _strap_old(avg_am, dayfrac_am >= 0.5)) )
                if n_pm > 0:
                    items.append( (dayname_up, "%s afternoon & evening:" % dayname_up, _strap_old(avg_pm, dayfrac_pm >= 0.5)) )

            # Rotate so current half-day is first
            today_up = _dow_name_from_abs_minute(abs_now).upper()
            current_is_am = (abs_now % 1440) < AM_END
            want_prefix = ("%s morning:" if current_is_am else "%s afternoon & evening:") % today_up
            start_idx = 0
            for i,(_,pfx,_) in enumerate(items):
                if pfx.startswith(want_prefix):
                    start_idx = i; break
            ordered = items[start_idx:] + items[:start_idx]

            # Split into columns
            left_n = min(3, len(ordered))
            left_list = ordered[:left_n]
            right_list = ordered[left_n:]
            col_count = 2 if len(right_list) > 0 else 1

            cols = JPanel(); cols.setOpaque(False)
            cols.setBorder(EmptyBorder(2, PAGE_H_MARGIN, 2, PAGE_H_MARGIN))
            cols.setLayout(GridLayout(1, col_count, OLD_COL_GAP, 0))

            def make_col(col_items):
                c = JPanel(); c.setOpaque(False); c.setLayout(BoxLayout(c, BoxLayout.Y_AXIS))
                prev_day = None
                for idx, (day_up, pfx, bodytxt) in enumerate(col_items):
                    if prev_day is not None and day_up != prev_day:
                        c.add(_gapV(2)); c.add(RuleLine(OLD_RULE, 1)); c.add(_gapV(2))
                    line = OldFlowLine(WRAP_W_OLD_COL); line.setParts(pfx, bodytxt)
                    c.add(line)
                    if idx < len(col_items)-1:
                        c.add(_gapV(ROW_GAP))
                    prev_day = day_up
                return c

            left_col = make_col(left_list)
            cols.add(left_col)

            if col_count == 2:
                right_col = make_col(right_list)
                # If right shorter than left, add one compact ad to balance visually
                if len(right_list) < len(left_list):
                    pool = _small_old_ads()
                    if len(pool) > 0:
                        small_ad = _EDITION_RNG.choice(pool)
                        if len(right_list) > 0:
                            right_col.add(_gapV(ROW_GAP))
                        right_col.add(SmallOldAd(small_ad))

                        # Place sunrise/sunset in the empty space under the left forecast column (opposite the small advert).
                        sunBox = _build_suntimes_box(True, sunRiseStr, sunSetStr)
                        if sunBox is not None:
                            try:
                                left_col.add(_gapV(ROW_GAP))
                                left_col.add(sunBox)
                            except Exception:
                                pass
                cols.add(right_col)
            leftPanel.add(cols, BorderLayout.CENTER)

            # EAST: Large advert
            ad_list = _ads_from_memory(True)
            if len(ad_list) > 0:
                big_ad = OldAd(_EDITION_RNG.choice(ad_list))
                oldBigAd = big_ad
            body.add(big_ad, BorderLayout.EAST)

            cp.add(body)

        else:
            # ===== MODERN =====
            cp.add(Masthead(False, title, pub_label, include_title=True))
            actual_cols = max(1, sum(1 for k,_ in decisions if k != 'skip'))
            row = JPanel(); row.setOpaque(False)
            row.setBorder(EmptyBorder(2, PAGE_H_MARGIN, 2, PAGE_H_MARGIN))
            row.setLayout(GridLayout(1, actual_cols, COL_GAP, 0))
            for kind, payload in decisions:
                if kind == 'skip': continue
                (day0, avg_am, dayfrac_am, n_am, avg_pm, dayfrac_pm, n_pm) = payload
                dayname = _dow_name_from_abs_minute(day0)
                col = JPanel(); col.setOpaque(False); col.setLayout(BoxLayout(col, BoxLayout.Y_AXIS))
                d = JLabel(dayname); d.setForeground(MOD_TEXT); d.setFont(Font("SansSerif", Font.BOLD, 16))
                col.add(d); col.add(_gapV(ROW_GAP))
                m = ModernHalfRow("Morning")
                p = ModernHalfRow("Afternoon & evening")
                if n_am > 0:
                    head_am = _headline(avg_am, dayfrac_am >= 0.5); strap_am = _strap_modern(avg_am, dayfrac_am >= 0.5)
                    m.setContent(True, avg_am, (dayfrac_am >= 0.5), head_am, strap_am)
                    col.add(m); col.add(_gapV(ROW_GAP))
                if n_pm > 0:
                    head_pm = _headline(avg_pm, dayfrac_pm >= 0.5); strap_pm = _strap_modern(avg_pm, dayfrac_pm >= 0.5)
                    p.setContent(True, avg_pm, (dayfrac_pm >= 0.5), head_pm, strap_pm)
                    col.add(p)
                row.add(col)
            cp.add(row)
            stPanel = _build_suntimes_panel(False, sunRiseStr, sunSetStr)
            if stPanel is not None:
                cp.add(stPanel)

            # Footer ads
            adsM = _ads_from_memory(False)
            if len(adsM) > 0:
                cp.add(_gapV(4))
                footer = JPanel(); footer.setOpaque(False)
                footer.setBorder(EmptyBorder(2, PAGE_H_MARGIN, 8, PAGE_H_MARGIN))
                footer.setLayout(GridLayout(1, 2, COL_GAP, 0))
                picks = random.sample(adsM, 2) if len(adsM) >= 2 else [adsM[0], adsM[0]]
                footer.add(ModernAd(picks[0])); footer.add(ModernAd(picks[1]))
                cp.add(footer)

        # Pack and adjust window sizes
        self.frame.pack()  
        
        # Post-pack: constrain old advert height to left panel height to avoid forcing window taller.
        if old_style and (oldBigAd is not None) and (oldLeftPanel is not None):
            try:
                hLp = oldLeftPanel.getPreferredSize().height
                if hLp is not None and int(hLp) > 0:
                    wAd = int(WRAP_W_OLD_AD + 50)
                    dim = Dimension(wAd, int(hLp))
                    oldBigAd.setMinimumSize(dim)
                    oldBigAd.setPreferredSize(dim)
                    oldBigAd.setMaximumSize(dim)
                    self.frame.pack()
            except Exception:
                pass
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[WeatherForecastUIApp] Failed to set weather UI window icon: " + str(ex))
        
        if old_style:
            w = self.frame.getWidth(); h = self.frame.getHeight()
            if w > MAX_W_OLD:
                self.frame.setSize(MAX_W_OLD, h); w = MAX_W_OLD
            if h > OLD_HEIGHT_CAP:
                self.frame.setSize(w, OLD_HEIGHT_CAP)
        else:
            w = self.frame.getWidth(); h = self.frame.getHeight()
            if h < MIN_H_MODERN:
                self.frame.setSize(w, MIN_H_MODERN)

        self.frame.setLocationByPlatform(True)
        self.frame.setVisible(True)
        
        # ---- CLEANUP ON WINDOW CLOSE ----
        # Ensure proper disposal and clear module/global state so repeat opens are fresh.
        try:
            from javax.swing import WindowConstants
            self.frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        except Exception:
            pass

        # Lightweight component detacher to hasten GC; ASCII and Jython-safe.
        def _DetachAll(p):
            # Remove listeners we added (none dynamic here), clear editors, and remove children.
            try:
                p.setVisible(False)
            except Exception:
                pass
            try:
                # Clear large editors' content to drop Document references.
                if isinstance(p, JEditorPane):
                    p.setEditorKit(None)
                    p.setText("")
            except Exception:
                pass
            try:
                # Recurse and remove all children from containers.
                if hasattr(p, "getComponentCount"):
                    for i in range(p.getComponentCount() - 1, -1, -1):
                        c = p.getComponent(i)
                        _DetachAll(c)
                        try:
                            p.remove(i)
                        except Exception:
                            pass
            except Exception:
                pass

        from java.awt.event import WindowAdapter
        from javax.swing import SwingUtilities
        from java.lang import Runnable

        # Hold a reference to the outer automaton for use inside the listener.
        outer = self

        class _CleanupOnClose(WindowAdapter):
            def windowClosing(self, ev):
                # 1) Clear module-level edition state.
                try:
                    global _EDITION_RNG, _ED_USED_LINES
                    _EDITION_RNG = None
                    if _ED_USED_LINES is not None:
                        _ED_USED_LINES.clear()
                    _ED_USED_LINES = None
                except Exception:
                    pass
                # 2) Detach UI components and drop references.
                try:
                    cp = outer.frame.getContentPane()
                    _DetachAll(cp)
                except Exception:
                    pass
                # 3) Drop strong refs held by this automaton instance.
                try:
                    outer.sunTimes = None
                    outer.timebase = None
                except Exception:
                    pass
                # 4) Ensure dispose runs on the EDT.
                try:
                    class _DoDispose(Runnable):
                        def run(self):
                            try:
                                ev.getWindow().dispose()
                            except Exception:
                                pass
                    SwingUtilities.invokeLater(_DoDispose())
                except Exception:
                    # Last resort: direct dispose (should already be on EDT)
                    try:
                        ev.getWindow().dispose()
                    except Exception:
                        pass
        try:
            self.frame.addWindowListener(_CleanupOnClose())
        except Exception:
            pass


        # Lightweight component detacher to hasten GC; ASCII and Jython-safe.
        def _DetachAll(p):
            # Remove listeners we added (none dynamic here), clear icons, and remove children.
            try:
                p.setVisible(False)
            except Exception:
                pass
            try:
                # Clear large editors' content to drop Document references.
                if isinstance(p, JEditorPane):
                    p.setEditorKit(None)
                    p.setText("")
            except Exception:
                pass
            try:
                # Recurse and remove all children from containers.
                if hasattr(p, "getComponentCount"):
                    for i in range(p.getComponentCount() - 1, -1, -1):
                        c = p.getComponent(i)
                        _DetachAll(c)
                        try:
                            p.remove(i)
                        except Exception:
                            pass
            except Exception:
                pass

        from java.awt.event import WindowAdapter
        from java.lang import Runnable

        class _CleanupOnClose(WindowAdapter):
            def windowClosing(self, ev):
                # 1) Clear module-level edition state.
                try:
                    global _EDITION_RNG, _ED_USED_LINES
                    _EDITION_RNG = None
                    if _ED_USED_LINES is not None:
                        _ED_USED_LINES.clear()
                    _ED_USED_LINES = None
                except Exception:
                    pass
                # 2) Detach UI components and drop references.
                try:
                    cp = self.frame.getContentPane()
                    _DetachAll(cp)
                    # Remove the content pane; JmriJFrame will dispose afterwards.
                except Exception:
                    pass
                # 3) Drop strong refs held by this automaton instance.
                try:
                    self.sunTimes = None
                    self.timebase = None
                except Exception:
                    pass
                # 4) Ensure dispose runs on the EDT.
                try:
                    from javax.swing import SwingUtilities
                    class _DoDispose(Runnable):
                        def run(self):
                            try:
                                selfOuter = ev.getWindow()
                                selfOuter.dispose()
                            except Exception:
                                pass
                    SwingUtilities.invokeLater(_DoDispose())
                except Exception:
                    # Last resort: direct dispose (should already be on EDT)
                    try:
                        ev.getWindow().dispose()
                    except Exception:
                        pass

        try:
            self.frame.addWindowListener(_CleanupOnClose())
        except Exception:
            pass

        # ---- CLEANUP ON WINDOW CLOSE ----

    def _profile_name(self):
        """Return the active profile name (fallback 'Layout')."""
        try:
            p = jmri.util.FileUtil.getProfilePath()
            if p is not None:
                s = str(p).replace('\\','/').rstrip('/')
                if '/' in s:
                    nm = s.split('/')[-1].strip()
                    if nm:
                        return nm
        except Exception:
            pass
        return "Layout"

    def _paper_title(self):
        """
        Resolve the newspaper title from memory IMWX_NEWS_PAPERNAME.
        Supports tokens:
          - {PROFILE}       (recommended)
          - {PROFILE_NAME}  (alias)
        Default template: "The {PROFILE} Echo".
        """
        try:
            v = PAPERNAME_MEM.getValue()
            templ = ("" if v is None else str(v).strip())
        except Exception:
            templ = ""

        if len(templ) == 0:
            templ = "The {PROFILE} Echo"

        prof = self._profile_name()
        # Replace supported tokens (case-sensitive by design; documented in TASSetup)
        title = templ.replace("{PROFILE}", prof).replace("{PROFILE_NAME}", prof)

        # Safety: avoid empty after replacement
        if len(title.strip()) == 0:
            title = "The %s Echo" % prof

        return title

    def handle(self):
        return False  # static edition

# Start
ui = WeatherForecastNewspaper()
ui.setName('Weather forecast (newspaper)')
ui.start()