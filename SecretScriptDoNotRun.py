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

import jmri
import TASPathResolver
import os
import java
from java.awt import Color, Font, BasicStroke, RenderingHints, Dimension, Rectangle, Polygon
from javax.swing import JPanel, Timer, JOptionPane
from java.awt.event import KeyAdapter, KeyEvent, WindowAdapter
from java.util import Random

# ----------------------------------------------------------------------
# Gameplay constants (tweak here)
# ----------------------------------------------------------------------
TITLE_TEXT = "Spice Inveiglers"
FPS_MS = 16
PANEL_W = 640
PANEL_H = 480

PLAYER_W = 48
PLAYER_H = 22
PLAYER_SPEED = 5
SHOT_COOLDOWN_MS = 300
PLAYER_MAX_SHOTS = 3

ALIEN_ROWS = 4
ALIEN_COLS = 8
ALIEN_W = 30
ALIEN_H = 22
ALIEN_H_GAP = 16
ALIEN_V_GAP = 20
ALIEN_START_X = 60
ALIEN_START_Y = 80
ALIEN_BASE_SPEED = 1.2
ALIEN_STEP_DOWN = 14
ALIEN_SHOOT_CHANCE = 0.008

SHOT_W = 3
SHOT_H = 10
SHOT_SPEED = 7
ENEMY_SHOT_W = 4
ENEMY_SHOT_H = 8
ENEMY_SHOT_SPEED = 5

LIVES_START = 3
# Classic extra life: award once when the score reaches this threshold.
EXTRA_LIFE_SCORE = 1500  # one-time bonus life at 1,500 points (arcade)  # [1](http://tips.retrogames.com/gamepage/invaders.html)
PLAYER_HIT_FLASH_MS = 60
LEVEL_SPEED_INCREMENT = 0.15
EXPLOSION_TOTAL_MS = 96 
EXPLOSION_FRAME_MS = 48 
EXPLOSION_PIXEL = 5
MOTHER_W = 56 
MOTHER_H = 18 
MOTHER_Y = 34 
MOTHER_SPEED = 2.2 
MOTHER_SPAWN_CHANCE = 0.0012 
MOTHER_SCORE = 200 
MOTHER_DISABLE_FIRE_MS = 3000
# After aliens regain fire, boost their fire chance for this duration (ms)
ALIEN_FIRE_BOOST_MS = 1350
# Red flash window (ms) before they recover fire
ALIEN_FLASH_RED_WINDOW_MS = 500
SHIELD_COUNT = 4 
SHIELD_PIXEL = 5 
SHIELD_ROWS = 8 
SHIELD_COLS = 14 
SHIELD_Y = PANEL_H - 150 
SHIELD_MARGIN_X = 70 
SHIELD_ERODE_RADIUS_PLAYER = 1
SHIELD_ERODE_RADIUS_ENEMY = 2

# Animation pacing (larger = slower alien wiggle)
ANIM_TICKS_PER_FLIP = 8

# Dynamic speed-up as aliens are destroyed
# EffectiveSpeed = Base * (1 + DeadFraction * (ALIEN_ACCEL_MAX_MULT - 1))
ALIEN_ACCEL_MAX_MULT = 2.2
ALIEN_ACCEL_LEVEL_FACTOR = 0.18
ALIEN_ACCEL_LEVEL_CAP = 3.0

# Per-row alien colors (phase-0 and phase-1 for subtle blink)
ROW_COLORS_PHASE0 = [
    Color(0, 255, 160),
    Color(255, 120, 0),
    Color(120, 200, 255),
    Color(255, 80, 160),
]
ROW_COLORS_PHASE1 = [
    Color(0, 220, 140),
    Color(230, 105, 0),
    Color(100, 180, 240),
    Color(230, 70, 145),
]

# High score table (Top-10), no timestamp
HS_MAX = 10
HS_FILE_NAME = "spice_inveiglers_scores.tsv"
HS_COLORS = [
    Color(0, 255, 160),
    Color(255, 120, 0),
    Color(120, 200, 255),
    Color(255, 80, 160),
    Color(255, 255, 0),
    Color(160, 255, 120),
    Color(255, 160, 80),
    Color(160, 120, 255),
    Color(255, 90, 90),
    Color(90, 255, 255),
]
HS_HEADER_FG = Color(0, 255, 120)
HS_BORDER = Color(140, 140, 160)
HS_COLUMNS_FG = Color(210, 210, 220)

# Classic Space Invaders scoring
ALIEN_SCORE_BY_KIND = {
    "SQUID": 30,   # top row
    "CRAB": 20,    # middle rows
    "OCTO": 10     # bottom row
}
# UFO (mother ship) classic mystery score: 50/100/150/300 (weighted by the original 15-shot loop)
# We keep MOTHER_SCORE constant defined above for compatibility but won't use it for scoring.

# Colors (game)
CLR_BG = Color(16, 16, 20)
CLR_TEXT = Color(240, 240, 240)
CLR_PANEL = Color(24, 24, 30)
CLR_PLAYER = Color(255, 210, 60)
CLR_SHOT = Color(255, 255, 100)
CLR_ENEMY_SHOT = Color(255, 90, 90)
CLR_UI = Color(180, 180, 200)
CLR_MOTHER = Color(255, 60, 60)
CLR_SHIELD = Color(80, 255, 80)

# ----------------------------------------------------------------------
# High score file path (profile-relative, no absolute paths)
# ----------------------------------------------------------------------
def GetHighScorePath():
    # Use TASPathResolver to keep write locations centralized and profile-portable
    try:
        pj = TASPathResolver.GetProfileJythonDir()
    except Exception:
        pj = None
    if pj:
        try:
            d = os.path.join(str(pj), "config")
            try:
                TASPathResolver.EnsureDir(d)
            except Exception:
                pass
            return os.path.join(str(d), HS_FILE_NAME)
        except Exception:
            pass
    # Fallback: local file name (current working directory)
    return HS_FILE_NAME
# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def Rect(x, y, w, h):
    return Rectangle(int(x), int(y), int(w), int(h))

def Intersects(r1, r2):
    return r1.intersects(r2)

# ----------------------------------------------------------------------
# Sprites
# ----------------------------------------------------------------------
def DrawShip(g2, x, y, w, h):
    bx = int(x); by = int(y); bw = int(w); bh = int(h)
    p = Polygon()
    p.addPoint(bx + int(0.10*bw), by + bh)
    p.addPoint(bx + int(0.00*bw), by + int(0.55*bh))
    p.addPoint(bx + int(0.40*bw), by + int(0.30*bh))
    p.addPoint(bx + int(0.60*bw), by + int(0.30*bh))
    p.addPoint(bx + int(1.00*bw), by + int(0.55*bh))
    p.addPoint(bx + int(0.90*bw), by + bh)
    g2.fillPolygon(p)
    tbx = bx + int(0.44*bw); tby = by + int(0.18*bh); tw = int(0.12*bw); th = int(0.20*bh)
    g2.fillRect(tbx, tby, tw, th)
    g2.setColor(CLR_PANEL)
    notchW = int(0.06*bw); notchH = int(0.08*bh)
    g2.fillRect(bx + int(0.47*bw), by + int(0.18*bh), notchW, notchH)


def DrawAlienSprite(g2, x, y, w, h, kind, phase, rowIdx, FlashWhite=False, FlashRed=False):
    ax = int(x); ay = int(y); aw = int(w); ah = int(h)
    baseCol = ROW_COLORS_PHASE0[min(max(0, rowIdx), len(ROW_COLORS_PHASE0)-1)]
    altCol  = ROW_COLORS_PHASE1[min(max(0, rowIdx), len(ROW_COLORS_PHASE1)-1)]
    # Flash effect on the alternate animation phase
    if phase == 1:
        if FlashRed:
            baseCol = Color(255, 60, 60)   # bright red
            altCol  = Color(255, 60, 60)
        elif FlashWhite:
            baseCol = Color(255, 255, 255)
            altCol  = Color(255, 255, 255)
    g2.setColor(baseCol if (phase == 0) else altCol)

    if kind == "SQUID":
        g2.fillRoundRect(ax + int(0.10*aw), ay + int(0.00*ah), int(0.80*aw), int(0.60*ah), 6, 6)
        g2.setColor(Color(20, 20, 20))
        g2.fillRect(ax + int(0.30*aw), ay + int(0.20*ah), int(0.12*aw), int(0.10*ah))
        g2.fillRect(ax + int(0.58*aw), ay + int(0.20*ah), int(0.12*aw), int(0.10*ah))
        g2.setColor(baseCol if (phase == 1) else altCol)
        for i in range(4):
            tx = ax + int((0.20 + 0.16*i)*aw)
            tw = int(0.10*aw)
            th = int(0.30*ah)
            offs = (i % 2) * (3 if phase == 1 else 0)
            g2.fillRect(tx + offs, ay + int(0.55*ah), tw, th)

    elif kind == "CRAB":
        g2.fillRoundRect(ax + int(0.18*aw), ay + int(0.15*ah), int(0.64*aw), int(0.40*ah), 6, 6)
        g2.setColor(baseCol if (phase == 1) else altCol)
        leftClaw = Polygon()
        leftClaw.addPoint(ax + int(0.08*aw), ay + int(0.20*ah))
        leftClaw.addPoint(ax + int(0.18*aw), ay + int(0.25*ah))
        leftClaw.addPoint(ax + int(0.12*aw), ay + int(0.35*ah + (3 if phase == 1 else 0)))
        g2.fillPolygon(leftClaw)
        rightClaw = Polygon()
        rightClaw.addPoint(ax + int(0.92*aw), ay + int(0.20*ah))
        rightClaw.addPoint(ax + int(0.82*aw), ay + int(0.25*ah))
        rightClaw.addPoint(ax + int(0.88*aw), ay + int(0.35*ah + (3 if phase == 1 else 0)))
        g2.fillPolygon(rightClaw)
        g2.setColor(baseCol if (phase == 0) else altCol)
        baseY = ay + int(0.58*ah)
        for i in range(6):
            lx = ax + int((0.18 + 0.12*i)*aw)
            offs = (i % 2) * (3 if phase == 1 else 0)
            g2.fillRect(lx, baseY + offs, int(0.08*aw), int(0.10*ah))

    else:  # OCTO
        g2.fillRoundRect(ax + int(0.16*aw), ay + int(0.06*ah), int(0.68*aw), int(0.50*ah), 8, 8)
        g2.setColor(Color(20, 20, 20))
        g2.fillOval(ax + int(0.32*aw), ay + int(0.22*ah), int(0.10*aw), int(0.12*ah))
        g2.fillOval(ax + int(0.58*aw), ay + int(0.22*ah), int(0.10*aw), int(0.12*ah))
        g2.setColor(baseCol if (phase == 0) else altCol)
        baseY = ay + int(0.56*ah)
        for i in range(5):
            axx = ax + int((0.20 + 0.12*i)*aw)
            wig = (3 if (phase == 1 and i % 2 == 0) else 0)
            g2.fillRect(axx, baseY + wig, int(0.10*aw), int(0.14*ah))

def DrawShot(g2, x, y, w, h, friendly=True):
    if friendly:
        g2.setColor(CLR_SHOT)
        g2.fillRect(int(x), int(y), int(w), int(h))
    else:
        g2.setColor(CLR_ENEMY_SHOT)
        g2.fillOval(int(x), int(y), int(w), int(h))
        g2.setColor(Color(255, 140, 140))
        g2.fillRect(int(x), int(y + h), int(w), 2)
              
def DrawExplosion(g2, x, y, w, h, col, phase):
    cx = int(x + w / 2)
    cy = int(y + h / 2)
    ps = int(EXPLOSION_PIXEL)

    g2.setColor(col)

    # Two simple frames: phase 0 = tighter, phase 1 = wider scatter
    if phase == 0:
        offs = [
           (0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
           (1, 1), (-1, -1), (1, -1), (-1, 1),
        ]
    else:
        offs = [
           (0, 0), (2, 0), (-2, 0), (0, 2), (0, -2),
           (2, 1), (-2, -1), (1, 2), (-1, -2),
        ]

    half = ps / 2
    for (dx, dy) in offs:
        px = cx + dx * ps - half
        py = cy + dy * ps - half
        g2.fillRect(int(px), int(py), ps, ps)    

def DrawMotherShip(g2, x, y, w, h):
    bx = int(x); by = int(y); bw = int(w); bh = int(h)

    # Base body (blocky)
    g2.setColor(CLR_MOTHER)
    g2.fillRect(bx + 6, by + 8, bw - 12, bh - 10)
    g2.fillRect(bx + 14, by + 3, bw - 28, 6)
    g2.fillRect(bx + 2, by + 10, 4, bh - 14)
    g2.fillRect(bx + bw - 6, by + 10, 4, bh - 14)

    # Windows (cut-outs)
    g2.setColor(CLR_PANEL)
    g2.fillRect(bx + 18, by + 10, 6, 4)
    g2.fillRect(bx + 28, by + 10, 6, 4)
    g2.fillRect(bx + 38, by + 10, 6, 4)
       
def DrawShield(g2, shield):
    # shield = {"x":..., "y":..., "grid":[[bool...]], "cols":..., "rows":...}
    px = int(shield.get("x", 0))
    py = int(shield.get("y", 0))
    grid = shield.get("grid", None)
    if grid is None:
        return

    g2.setColor(CLR_SHIELD)
    for ry in range(len(grid)):
        row = grid[ry]
        for cx in range(len(row)):
            if row[cx]:
                g2.fillRect(px + cx * SHIELD_PIXEL, py + ry * SHIELD_PIXEL, SHIELD_PIXEL, SHIELD_PIXEL)

# ----------------------------------------------------------------------
# High score I/O (Top-10, TSV) - strictly ASCII, no timestamp
# ----------------------------------------------------------------------
def LoadHighScores():
    path = GetHighScorePath()
    scores = []
    try:
        if os.path.exists(path):
            f = open(path, "r")
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        nm = parts[0]
                        try: sc = int(parts[1])
                        except: sc = 0
                        try: lv = int(parts[2])
                        except: lv = 1
                        scores.append({"name": nm, "score": sc, "level": lv})
            finally:
                f.close()
    except:
        pass
    scores.sort(key=lambda d: (d.get("score", 0), d.get("level", 0)), reverse=True)
    return scores[:HS_MAX]

def SaveHighScores(scores):
    path = GetHighScorePath()
    try:

        d = os.path.dirname(path)

        if d:

            try:

                TASPathResolver.EnsureDir(d)

            except Exception:

                if not os.path.exists(d):

                    os.makedirs(d)

    except:

        pass
    try:
        f = open(path, "w")
        try:
            for s in scores[:HS_MAX]:
                line = "%s\t%d\t%d\n" % (str(s.get("name","")), int(s.get("score",0)), int(s.get("level",1)))
                f.write(line)
        finally:
            f.close()
    except:
        pass

def AddHighScore(scores, name, score, level):
    scores.append({"name": name, "score": int(score), "level": int(level)})
    scores.sort(key=lambda d: (d.get("score", 0), d.get("level", 0)), reverse=True)
    return scores[:HS_MAX]

def Qualifies(scores, score):
    if len(scores) < HS_MAX:
        return True
    try:
        minSc = min([s.get("score", 0) for s in scores])
    except:
        minSc = 0
    return score > minSc

# ----------------------------------------------------------------------
# GamePanel
# ----------------------------------------------------------------------
class GamePanel(JPanel):
    def __init__(self, closeFn):
        JPanel.__init__(self)
        self.setPreferredSize(Dimension(PANEL_W, PANEL_H))
        self.setDoubleBuffered(True)
        self.CloseFn = closeFn

        self.Rng = Random(123456789)
        self.HighScores = LoadHighScores()
        self.ResetFull()

        self.KeyLeft = False
        self.KeyRight = False
        self.KeyFire = False

        self.Timer = Timer(FPS_MS, self._OnTick)
        self.Timer.setInitialDelay(0)
        self.Timer.start()

        # Fonts (all ASCII names)
        self.FontHud = Font("Monospaced", Font.BOLD, 14)
        self.FontIntroTitle = Font("Monospaced", Font.BOLD, 36)
        self.FontBig = Font("Monospaced", Font.BOLD, 32)
        self.FontScore = Font("Monospaced", Font.BOLD, 16)
        self.FontScoreTitle = Font("Monospaced", Font.BOLD, 28)

    
    def ResetFull(self):
        self.Score = 0
        self.Lives = LIVES_START
        self.Level = 1
        self.GameOver = False
        self.Attract = True
        self.ShowScores = False
        self.PromptedHS = False
        self.BonusLifeAwarded = False  # one-time extra life has not yet been awarded

        self.PlayerX = PANEL_W / 2 - PLAYER_W / 2
        self.PlayerY = PANEL_H - 64
        self.PlayerCooldownMs = 0
        self.PlayerShots = []
        self.EnemyShots = []

        self.PlayerHitFlashMs = 0
        self.Explosions = []

        self.MotherActive = False
        self.MotherX = -MOTHER_W
        self.MotherDir = 1   
        self.AlienFireDisableMs = 0
        self.AlienFireBoostMs = 0
        
        self.ShowGameOver = False

        self.AlienDir = 1
        self.AlienSpeed = ALIEN_BASE_SPEED
        self.AlienStepDownPending = False
        self.TickPhase = 0
        self.AnimTickCount = 0

        self.BuildAliens()
        self.BuildShields()
   
    def MaybeAwardBonusLife(self):
        # Award exactly one extra life once the score reaches EXTRA_LIFE_SCORE.
        # Safe against multiple calls; does nothing once awarded.
        try:
            if not hasattr(self, "BonusLifeAwarded"):
                self.BonusLifeAwarded = False
            if (not self.BonusLifeAwarded) and int(self.Score) >= int(EXTRA_LIFE_SCORE):
                self.Lives += 1
                self.BonusLifeAwarded = True
        except:
            pass
    
    def BuildAliens(self):
        self.Aliens = []
        for r in range(ALIEN_ROWS):
            row = []
            kind = ("SQUID" if r == 0 else ("CRAB" if r in (1, 2) else "OCTO"))
            for c in range(ALIEN_COLS):
                x = ALIEN_START_X + c * (ALIEN_W + ALIEN_H_GAP)
                y = ALIEN_START_Y + r * (ALIEN_H + ALIEN_V_GAP)
                row.append({"x": float(x), "y": float(y), "w": ALIEN_W, "h": ALIEN_H, "alive": True, "kind": kind})
            self.Aliens.append(row)
  
    def BuildShields(self):
        # Build classic-ish bunker shapes as a grid of chunky pixels.
        # Pattern uses 'X' for a filled cell, ' ' for empty.
        pattern = [
            "XXXXXXXXXXXXXX",
            "XXXXXXXXXXXXXX",
            "XXXXXXXXXXXXXX",
            "XXXXXXXXXXXXXX",
            "XXXXXX  XXXXXX",
            "XXXXX    XXXXX",
            "XXXX      XXXX",
            "XXX        XXX",
        ]

        cols = SHIELD_COLS
        rows = SHIELD_ROWS

        # Safety: ensure pattern matches the configured size
        if len(pattern) != rows:
            rows = len(pattern)
        if rows > 0:
            cols = len(pattern[0])

        shieldW = cols * SHIELD_PIXEL
        usableW = PANEL_W - (2 * SHIELD_MARGIN_X)

        if SHIELD_COUNT > 1:
            gap = (usableW - (SHIELD_COUNT * shieldW)) / float(SHIELD_COUNT - 1)
        else:
            gap = 0.0

        self.Shields = []
        for i in range(SHIELD_COUNT):
            sx = SHIELD_MARGIN_X + i * (shieldW + gap)
            sy = SHIELD_Y

            grid = []
            for ry in range(rows):
                line = pattern[ry]
                row = []
                for cx in range(cols):
                    row.append(line[cx] == "X")
                grid.append(row)

            self.Shields.append({"x": float(sx), "y": float(sy), "grid": grid, "cols": cols, "rows": rows})

    def DamageShieldAt(self, hitX, hitY, radiusCells):
        # Erode any shield cells around the impact point.
        # Returns True if any cell was removed.
        if not hasattr(self, "Shields"):
            return False

        removed = False
        r = int(radiusCells)

        for sh in self.Shields:
            sx = float(sh.get("x", 0))
            sy = float(sh.get("y", 0))
            cols = int(sh.get("cols", 0))
            rows = int(sh.get("rows", 0))
            grid = sh.get("grid", None)
            if grid is None:
                continue

            w = cols * SHIELD_PIXEL
            h = rows * SHIELD_PIXEL

            if hitX < sx or hitX >= sx + w or hitY < sy or hitY >= sy + h:
                continue

            # Convert to cell coordinates
            cx = int((hitX - sx) / SHIELD_PIXEL)
            cy = int((hitY - sy) / SHIELD_PIXEL)

            for yy in range(max(0, cy - r), min(rows, cy + r + 1)):
                dy = yy - cy
                for xx in range(max(0, cx - r), min(cols, cx + r + 1)):
                    dx = xx - cx
                    # Cheap circular-ish mask
                    if (dx * dx + dy * dy) <= (r * r + 1):
                        if grid[yy][xx]:
                            grid[yy][xx] = False
                            removed = True

        return removed
  
    def DamageShieldRect(self, rx, ry, rw, rh):
        # Remove any shield cells overlapped by the given rectangle.
        # Returns True if any cell was removed.
        if not hasattr(self, "Shields"):
            return False

        removed = False

        x0 = float(rx)
        y0 = float(ry)
        x1 = float(rx) + float(rw)
        y1 = float(ry) + float(rh)

        for sh in self.Shields:
            sx = float(sh.get("x", 0))
            sy = float(sh.get("y", 0))
            cols = int(sh.get("cols", 0))
            rows = int(sh.get("rows", 0))
            grid = sh.get("grid", None)
            if grid is None:
                continue

            sw = float(cols * SHIELD_PIXEL)
            shh = float(rows * SHIELD_PIXEL)

            ox0 = max(x0, sx)
            oy0 = max(y0, sy)
            ox1 = min(x1, sx + sw)
            oy1 = min(y1, sy + shh)

            if ox0 >= ox1 or oy0 >= oy1:
                continue

            # Convert overlap bounds to cell indices (inclusive)
            c0 = int((ox0 - sx) / float(SHIELD_PIXEL))
            c1 = int((ox1 - sx - 1.0) / float(SHIELD_PIXEL))
            r0 = int((oy0 - sy) / float(SHIELD_PIXEL))
            r1 = int((oy1 - sy - 1.0) / float(SHIELD_PIXEL))

            if c0 < 0:
                c0 = 0
            if r0 < 0:
                r0 = 0
            if c1 >= cols:
                c1 = cols - 1
            if r1 >= rows:
                r1 = rows - 1

            for yy in range(r0, r1 + 1):
                row = grid[yy]
                for xx in range(c0, c1 + 1):
                    if row[xx]:
                        row[xx] = False
                        removed = True

        return removed
     
    def RandomMotherScore(self):
        # Use the classic 15-shot loop's long-run distribution:
        # 100 appears 8/15, 50 appears 4/15, 150 appears 2/15, 300 appears 1/15.
        # We sample with those probabilities to keep it "mystery" but arcade-accurate.
        i = self.Rng.nextInt(15)  # 0..14
        if i == 8:
            return 300
        elif i in (4, 13):
            return 150
        elif i in (1, 2, 7, 12):
            return 50
        else:
            return 100
    
    def SetKeyLeft(self, down):  self.KeyLeft = bool(down)
    def SetKeyRight(self, down): self.KeyRight = bool(down)
    def SetKeyFire(self, down):  self.KeyFire = bool(down)

    def _OnTick(self, ev):
        # Slow alien animation flip
        self.AnimTickCount += 1
        if self.AnimTickCount >= ANIM_TICKS_PER_FLIP:
            self.TickPhase = 1 - self.TickPhase
            self.AnimTickCount = 0

        # Cooldown
        if self.PlayerCooldownMs > 0:
            self.PlayerCooldownMs = max(0, self.PlayerCooldownMs - FPS_MS)
        if self.PlayerHitFlashMs > 0:
            self.PlayerHitFlashMs = max(0, self.PlayerHitFlashMs - FPS_MS)

        # Handle alien fire disable and post-recovery boost
        wasDisabled = (self.AlienFireDisableMs > 0)
        if self.AlienFireDisableMs > 0:
            self.AlienFireDisableMs = max(0, self.AlienFireDisableMs - FPS_MS)
        # When the disable period ends, start the temporary boost
        if wasDisabled and self.AlienFireDisableMs == 0:
            self.AlienFireBoostMs = ALIEN_FIRE_BOOST_MS
        if hasattr(self, "AlienFireBoostMs") and self.AlienFireBoostMs > 0:
            self.AlienFireBoostMs = max(0, self.AlienFireBoostMs - FPS_MS)
                       
        # Update explosions
        for i in range(len(self.Explosions) - 1, -1, -1):
            e = self.Explosions[i]
            e["ms"] = int(e.get("ms", 0)) - FPS_MS
            if e["ms"] <= 0:
                del self.Explosions[i]

        if self.GameOver:
            # Prompt for high score immediately (once), but DO NOT show the table yet.
            if not self.PromptedHS:
                self.PromptHighScoreIfQualified()
                self.PromptedHS = True

            # Enter attract mode with a Game Over banner first.
            self.Attract = True         
            if self.ShowScores:
                self.ShowGameOver = False
            else:
                self.ShowGameOver = True
            self.repaint()
            return

        if self.Attract:
            self.repaint()
            return

        # Movement
        if self.KeyLeft:
            self.PlayerX = max(8, self.PlayerX - PLAYER_SPEED)
        if self.KeyRight:
            self.PlayerX = min(PANEL_W - PLAYER_W - 8, self.PlayerX + PLAYER_SPEED)

        # Firing
        if self.KeyFire and self.PlayerCooldownMs == 0 and len(self.PlayerShots) < PLAYER_MAX_SHOTS:
            sx = self.PlayerX + PLAYER_W / 2 - SHOT_W / 2
            sy = self.PlayerY - SHOT_H
            self.PlayerShots.append(Rect(sx, sy, SHOT_W, SHOT_H))
            self.PlayerCooldownMs = SHOT_COOLDOWN_MS

        # Update player shots
        for i in range(len(self.PlayerShots) - 1, -1, -1):
            r = self.PlayerShots[i]
            r.y -= SHOT_SPEED
            if r.y + r.height < 0:
                del self.PlayerShots[i]

        # Update enemy shots
        for i in range(len(self.EnemyShots) - 1, -1, -1):
            r = self.EnemyShots[i]
            r.y += ENEMY_SHOT_SPEED
            if r.y > PANEL_H:
                del self.EnemyShots[i]
          
        # Collisions: player shots vs shields
        for i in range(len(self.PlayerShots) - 1, -1, -1):
            ps = self.PlayerShots[i]
            hitX = ps.x + ps.width / 2.0
            hitY = ps.y  # top of shot (moving up)          
            if self.DamageShieldAt(hitX, hitY, SHIELD_ERODE_RADIUS_PLAYER):
                del self.PlayerShots[i]
        
        # Collisions: enemy shots vs shields
        for i in range(len(self.EnemyShots) - 1, -1, -1):
            es = self.EnemyShots[i]
            hitX = es.x + es.width / 2.0
            hitY = es.y + es.height  # bottom of shot (moving down)         
            if self.DamageShieldAt(hitX, hitY, SHIELD_ERODE_RADIUS_ENEMY):
                del self.EnemyShots[i]
      
        # Collisions: player shots vs enemy shots (both destroyed)
        for pi in range(len(self.PlayerShots) - 1, -1, -1):
            ps = self.PlayerShots[pi]
            shotHit = False
            for ei in range(len(self.EnemyShots) - 1, -1, -1):
                es = self.EnemyShots[ei]
                if Intersects(ps, es):
                    del self.PlayerShots[pi]
                    del self.EnemyShots[ei]
                    shotHit = True
                    break
            if shotHit:
                continue
      
        # Dynamic speed-up as fewer aliens remain
        totalAliens = ALIEN_ROWS * ALIEN_COLS
        aliveCount = 0
        for row in self.Aliens:
            for a in row:
                if a["alive"]:
                    aliveCount += 1
        deadFraction = 0.0
        if totalAliens > 0:
            deadFraction = float(totalAliens - aliveCount) / float(totalAliens)
        baseSpeed = self.AlienSpeed     
        levelAccel = 1.0 + float(self.Level - 1) * float(ALIEN_ACCEL_LEVEL_FACTOR)
        dynMult = 1.0 + deadFraction * (ALIEN_ACCEL_MAX_MULT - 1.0) * levelAccel
        if dynMult > ALIEN_ACCEL_LEVEL_CAP:
            dynMult = ALIEN_ACCEL_LEVEL_CAP
        effSpeed = baseSpeed * dynMult

        # Move aliens horizontally
        edgeHit = False
        for row in self.Aliens:
            for a in row:
                if not a["alive"]:
                    continue
                a["x"] += self.AlienDir * effSpeed
                if a["x"] < 8 or a["x"] + a["w"] > PANEL_W - 8:
                    edgeHit = True

        if edgeHit:
            self.AlienDir *= -1
            self.AlienStepDownPending = True

        if self.AlienStepDownPending:
            for row in self.Aliens:
                for a in row:
                    if not a["alive"]:
                        continue
                    a["y"] += ALIEN_STEP_DOWN
            self.AlienStepDownPending = False
                               
        # Aliens eat through shields while moving (horizontal and step-down)
        if hasattr(self, "Shields"):
            biteH = SHIELD_PIXEL * 2
            for r in range(ALIEN_ROWS):
                for c in range(ALIEN_COLS):
                    a = self.Aliens[r][c]
                    if not a["alive"]:
                        continue
                    biteY = float(a["y"]) + float(a["h"]) - float(biteH)
                    self.DamageShieldRect(float(a["x"]), biteY, float(a["w"]), float(biteH))
        
        # Mother ship spawn / movement
        if not self.MotherActive:
            if self.Rng.nextFloat() < MOTHER_SPAWN_CHANCE:
                self.MotherActive = True
                self.MotherDir = 1 if self.Rng.nextBoolean() else -1
                if self.MotherDir == 1:
                    self.MotherX = -float(MOTHER_W)
                else:
                    self.MotherX = float(PANEL_W + MOTHER_W)
        else:
            spd = float(MOTHER_SPEED) + 0.03 * float(self.Level - 1)
            self.MotherX += float(self.MotherDir) * spd
            if self.MotherDir == 1 and self.MotherX > float(PANEL_W + MOTHER_W):
                self.MotherActive = False
            elif self.MotherDir == -1 and self.MotherX < -float(MOTHER_W):
                self.MotherActive = False
        
        # Enemy shooting: lowest alive per column
        if self.AlienFireDisableMs == 0:
            for c in range(ALIEN_COLS):
                lowest = None
                for r in range(ALIEN_ROWS - 1, -1, -1):
                    a = self.Aliens[r][c]
                    if a["alive"]:
                        lowest = a
                        break           
                if lowest:
                    # Chance is tripled during the boost window immediately after disable ends
                    chance = ALIEN_SHOOT_CHANCE * (3.0 if (hasattr(self, "AlienFireBoostMs") and self.AlienFireBoostMs > 0) else 1.0)
                    if self.Rng.nextFloat() < chance:
                        sx = lowest["x"] + lowest["w"] / 2 - ENEMY_SHOT_W / 2
                        sy = lowest["y"] + lowest["h"]
                        self.EnemyShots.append(Rect(sx, sy, ENEMY_SHOT_W, ENEMY_SHOT_H))

        # Collisions: player shots vs aliens
        for i in range(len(self.PlayerShots) - 1, -1, -1):
            ps = self.PlayerShots[i]

            # Collisions: player shots vs mother ship
            if self.MotherActive:
                msRect = Rect(self.MotherX, MOTHER_Y, MOTHER_W, MOTHER_H)
                if Intersects(ps, msRect):
                    del self.PlayerShots[i]
                    self.Score += int(self.RandomMotherScore())
                    self.MaybeAwardBonusLife()
                    self.MotherActive = False          
                    self.AlienFireDisableMs = MOTHER_DISABLE_FIRE_MS
                    self.AlienFireBoostMs = 0

                    # Optional: reuse explosion effect for mother ship
                    self.Explosions.append({
                        "x": float(self.MotherX),
                        "y": float(MOTHER_Y),
                        "w": MOTHER_W,
                        "h": MOTHER_H,
                        "ms": int(EXPLOSION_TOTAL_MS),
                        "col": CLR_MOTHER,
                    })
                    continue

            hit = False
            for r in range(ALIEN_ROWS):
                for c in range(ALIEN_COLS):
                    a = self.Aliens[r][c]
                    if not a["alive"]:
                        continue

                    if Intersects(ps, Rect(a["x"], a["y"], a["w"], a["h"])):
                        # Explosion uses the same color the alien is currently drawn with
                        rowCol0 = ROW_COLORS_PHASE0[min(max(0, r), len(ROW_COLORS_PHASE0) - 1)]
                        rowCol1 = ROW_COLORS_PHASE1[min(max(0, r), len(ROW_COLORS_PHASE1) - 1)]
                        expCol = rowCol0 if (self.TickPhase == 0) else rowCol1

                        self.Explosions.append({
                            "x": float(a["x"]),
                            "y": float(a["y"]),
                            "w": a["w"],
                            "h": a["h"],
                            "ms": int(EXPLOSION_TOTAL_MS),
                            "col": expCol,
                        })

                        a["alive"] = False
                        # Classic per-row scoring
                        self.Score += int(ALIEN_SCORE_BY_KIND.get(a.get("kind", "OCTO"), 10))
                        self.MaybeAwardBonusLife()
                        del self.PlayerShots[i]
                        hit = True
                        break
                if hit:
                    break
     
        # Collisions: enemy shots vs player 
        playerRect = Rect(self.PlayerX, self.PlayerY, PLAYER_W, PLAYER_H) 
        if self.PlayerHitFlashMs == 0: 
            for i in range(len(self.EnemyShots) - 1, -1, -1): 
                es = self.EnemyShots[i] 
                if Intersects(es, playerRect): 
                    del self.EnemyShots[i] 
                    self.LoseLife() 
                    break 
        else: 
            # Invulnerable while flashing white: consume overlapping enemy shots without losing lives
            for i in range(len(self.EnemyShots) - 1, -1, -1): 
                es = self.EnemyShots[i] 
                if Intersects(es, playerRect): 
                    del self.EnemyShots[i] 
                    break
        
        # Aliens reach player line
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                a = self.Aliens[r][c]
                if not a["alive"]:
                    continue
                if a["y"] + a["h"] >= self.PlayerY:
                    self.LoseLife()
                    break

        # Wave clear
        allDead = True
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                if self.Aliens[r][c]["alive"]:
                    allDead = False
                    break
            if not allDead:
                break

        if allDead:
            self.Level += 1
            self.AlienSpeed += LEVEL_SPEED_INCREMENT
            self.EnemyShots[:] = []
            self.PlayerShots[:] = []
            self.Explosions[:] = [] 
            self.BuildAliens()
            self.MotherActive = False 
            self.AlienFireDisableMs = 0 

        self.repaint()

    def LoseLife(self):
        self.Lives -= 1
        self.PlayerHitFlashMs = PLAYER_HIT_FLASH_MS

        # Move the whole alien formation up without compressing rows.
        # Work out the highest (smallest y) alive alien; shift all rows up equally,
        # but never allow the formation to go above ALIEN_START_Y.
        minY = None
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                a = self.Aliens[r][c]
                if a["alive"]:
                    if minY is None or a["y"] < minY:
                        minY = a["y"]

        shiftUp = 0.0
        if minY is not None and minY > ALIEN_START_Y:
            shiftUp = min(float(ALIEN_STEP_DOWN), float(minY - ALIEN_START_Y))

        if shiftUp > 0.0:
            for r in range(ALIEN_ROWS):
                for c in range(ALIEN_COLS):
                    a = self.Aliens[r][c]
                    if a["alive"]:
                        a["y"] -= shiftUp

        if self.Lives <= 0:
            self.GameOver = True

    def PromptHighScoreIfQualified(self):
        try:
            if not Qualifies(self.HighScores, self.Score):
                return
            defaultName = "PLAYER"
            nm = JOptionPane.showInputDialog(self, "Enter name for High Scores:", defaultName)
            if nm is None:
                nm = defaultName
            nm = str(nm).strip()
            if nm == "":
                nm = defaultName
            # Easter egg: plain ASCII dialog
            try:
                if "bumface" in nm.lower():
                    JOptionPane.showMessageDialog(self, "Hello, Zoe")
            except:
                pass
            self.HighScores = AddHighScore(self.HighScores, nm, self.Score, self.Level)
            SaveHighScores(self.HighScores)
        except:
            pass

    def paintComponent(self, g):
        super(GamePanel, self).paintComponent(g)
        g2 = g
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        g2.setColor(CLR_BG)
        g2.fillRect(0, 0, self.getWidth(), self.getHeight())

        g2.setColor(CLR_PANEL)
        g2.fillRoundRect(10, 10, self.getWidth() - 20, self.getHeight() - 20, 12, 12)

        g2.setFont(self.FontHud)
        g2.setColor(CLR_UI)    
        
        
        # Score + Level (text)
        hud = "Score: %d   Level: %d" % (self.Score, self.Level)
        g2.drawString(hud, 20, 30)

        # Lives (icons): draw one small ship per remaining life, aligned to the right 
        lifeCount = int(self.Lives)
        if lifeCount > 0:
            iconW = max(12, int(PLAYER_W / 2))
            iconH = max(8,  int(PLAYER_H / 2))
            gap   = 6

            totalW = lifeCount * iconW + (lifeCount - 1) * gap
            startX = int(self.getWidth() - 20 - totalW)
            yTop   = 16

            for i in range(lifeCount):
                x = startX + i * (iconW + gap)
                g2.setColor(CLR_PLAYER)  # DrawShip leaves color as CLR_PANEL; reset per icon
                DrawShip(g2, int(x), int(yTop), int(iconW), int(iconH))

        # Attract mode
        if self.Attract:
            if self.ShowScores:
                self.DrawHighScores(g2)
            elif self.ShowGameOver:
                # Game Over banner that must be cleared with Space
                g2.setFont(self.FontIntroTitle)
                g2.setColor(CLR_TEXT)
                fmTitle = g2.getFontMetrics(self.FontIntroTitle)
                msg = "GAME OVER"
                msgX = int((self.getWidth() - fmTitle.stringWidth(msg)) / 2)
                g2.drawString(msg, msgX, 160)

                g2.setFont(self.FontHud)
                g2.setColor(CLR_UI)
                sub1 = "Press Space to view High Scores"
                sub2 = "Press Esc to quit"
                fmHud = g2.getFontMetrics(self.FontHud)
                s1X = int((self.getWidth() - fmHud.stringWidth(sub1)) / 2)
                s2X = int((self.getWidth() - fmHud.stringWidth(sub2)) / 2)
                g2.drawString(sub1, s1X, 200)
                g2.drawString(sub2, s2X, 226)
                return
            else:
                g2.setFont(self.FontIntroTitle)
                g2.setColor(CLR_TEXT)
                # Center title horizontally
                fmTitle = g2.getFontMetrics(self.FontIntroTitle)
                titleX = int((self.getWidth() - fmTitle.stringWidth(TITLE_TEXT)) / 2)
                g2.drawString(TITLE_TEXT, titleX, 78)
                # --- draw score advance table ABOVE the control instructions ---
                tableBottom = self.DrawScoreAdvanceTable(g2)

                # Prepare instruction strings and metrics
                g2.setFont(self.FontHud)
                g2.setColor(CLR_UI)
                fmHud = g2.getFontMetrics(self.FontHud)
                line1 = "Left/Right = Move, Space = Fire, Esc = Quit"
                line2 = "Press Space to start"
                line3 = "Press H for High Scores"
                x1 = int((self.getWidth() - fmHud.stringWidth(line1)) / 2)
                x2 = int((self.getWidth() - fmHud.stringWidth(line2)) / 2)
                x3 = int((self.getWidth() - fmHud.stringWidth(line3)) / 2)

                # Dynamic vertical placement BELOW the table
                INSTR_MARGIN = 48    # generous gap after the table
                STEP = 26            # vertical step between instruction lines

                # Start where there is no chance to collide with the table
                instrStartY = int(tableBottom + INSTR_MARGIN)

                # Keep instructions inside the panel if fonts are very tall
                bottomMargin = 16
                maxFirstY = self.getHeight() - bottomMargin - (2 * STEP)
                if instrStartY > maxFirstY:
                    instrStartY = maxFirstY

                g2.drawString(line1, x1, instrStartY)
                g2.drawString(line2, x2, instrStartY + STEP)
                g2.drawString(line3, x3, instrStartY + 2 * STEP)

            return
    
         # Player 
        if self.PlayerHitFlashMs > 0: 
            g2.setColor(Color(255, 255, 255)) 
        else: 
            g2.setColor(CLR_PLAYER) 
        DrawShip(g2, int(self.PlayerX), int(self.PlayerY), PLAYER_W, PLAYER_H) 
              
        # Mother ship
        if self.MotherActive:
            DrawMotherShip(g2, int(self.MotherX), int(MOTHER_Y), MOTHER_W, MOTHER_H)

        # Shields
        if hasattr(self, "Shields"):
            for sh in self.Shields:
                DrawShield(g2, sh)
                
        # Aliens (per-row color)
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                a = self.Aliens[r][c]
                if not a["alive"]:
                    continue           
                DrawAlienSprite(
                    g2, int(a["x"]), int(a["y"]), a["w"], a["h"], a["kind"], self.TickPhase, r,
                    (self.AlienFireDisableMs > ALIEN_FLASH_RED_WINDOW_MS),   # flash white only when > 500ms remaining
                    (self.AlienFireDisableMs > 0 and self.AlienFireDisableMs <= ALIEN_FLASH_RED_WINDOW_MS)  # flash red in last 500ms
                )
       
        # Explosions (simple 2-frame chunky pixels)
        for e in self.Explosions:
            ms = int(e.get("ms", 0))
            phase = 0 if ms > EXPLOSION_FRAME_MS else 1
            DrawExplosion(g2, e.get("x", 0), e.get("y", 0), e.get("w", 0), e.get("h", 0), e.get("col", CLR_TEXT), phase)
        
        # Shots
        for ps in self.PlayerShots:
            DrawShot(g2, ps.x, ps.y, ps.width, ps.height, friendly=True)
        for es in self.EnemyShots:
            DrawShot(g2, es.x, es.y, es.width, es.height, friendly=False)
                 
    def DrawScoreAdvanceTable(self, g2):
        # "SCORE ADVANCE TABLE" centered, dynamically spaced (ASCII-only, Python 2.7-safe).
        # Returns the integer Y coordinate of the bottom of the table (for placing instructions below).

        # Vertical placement (above player instructions)
        tableTitleY = 90

        # Strings (ASCII only)
        titleText = ""

        # Points text (classic)
        t1 = "= 30 PTS"    # Squid (top)
        t2 = "= 20 PTS"    # Crab (middle)
        t3 = "= 10 PTS"    # Octopus (bottom)
        t4 = "= ?? PTS"    # UFO (mystery)

        # Names/descriptions
        d1 = "Cinnamon"
        d2 = "Ginger"
        d3 = "Cloves"
        d4 = "Allspice"

        # --- Metrics ---
        g2.setFont(self.FontScore)
        fmScore = g2.getFontMetrics(self.FontScore)
        titleW = fmScore.stringWidth(titleText)
        titleX = int((self.getWidth() - titleW) / 2)

        scoreAscent  = fmScore.getAscent()
        scoreDescent = fmScore.getDescent()
        scoreLineH   = scoreAscent + scoreDescent

        g2.setFont(self.FontHud)
        fmHud = g2.getFontMetrics(self.FontHud)
        hudAscent  = fmHud.getAscent()
        hudDescent = fmHud.getDescent()
        hudLineH   = hudAscent + hudDescent

        # Sprite sizes
        spriteW = 40; spriteH = 28
        saucerW = 56; saucerH = 18

        # Horizontal block: 160 px gap from sprite to text; center (sprite + gap + widest text)
        g2.setFont(self.FontScore)
        maxPtsW  = max(fmScore.stringWidth(t1), fmScore.stringWidth(t2),
                       fmScore.stringWidth(t3), fmScore.stringWidth(t4))
        g2.setFont(self.FontHud)
        maxDescW = max(fmHud.stringWidth(d1), fmHud.stringWidth(d2),
                       fmHud.stringWidth(d3), fmHud.stringWidth(d4))
        maxTextW = max(maxPtsW, maxDescW)

        spriteTextGap = 160
        totalW = spriteTextGap + maxTextW
        blockX = int((self.getWidth() - totalW) / 2)
        sx = blockX
        tx = blockX + spriteTextGap

        # Draw table title
        g2.setFont(self.FontScore)
        g2.setColor(CLR_UI)
        g2.drawString(titleText, titleX, tableTitleY)

        # --- Spacing controls (roomy) ---
        spriteBottomPad = 10           # space between sprite bottom and points baseline
        ptsToDescGap    = 6            # space between points and description
        rowGap          = max(14, hudLineH)  # space after description to next row (>= one HUD line)

        # The first points baseline sits cleanly below title and sprite
        yPts = tableTitleY + 34 + max(scoreLineH, spriteH)

        # >>> Shift text up by exactly one row <<<
        rowShift = hudLineH + rowGap   # amount to move text baselines upward
        # ---------------------------------------------------------------------

        # ---- Row 1: SQUID ----
        spriteTopY = int((yPts - spriteBottomPad) - spriteH)
        DrawAlienSprite(g2, sx, spriteTopY, spriteW, spriteH, "SQUID", 0, 0, False, False)
        # Text baselines moved up one row
        yText = yPts - rowShift
        g2.setFont(self.FontScore); g2.setColor(CLR_UI); g2.drawString(t1, tx, yText)
        g2.setFont(self.FontHud);   g2.setColor(HS_COLUMNS_FG)
        descY = yText + ptsToDescGap + hudAscent
        g2.drawString(d1, tx, descY)
        # Advance yPts (sprite anchor) for next row as before
        yPts = (yPts + (hudAscent + ptsToDescGap + hudDescent + rowGap))

        # ---- Row 2: CRAB ----
        spriteTopY = int((yPts - spriteBottomPad) - spriteH)
        DrawAlienSprite(g2, sx, spriteTopY, spriteW, spriteH, "CRAB", 0, 1, False, False)
        yText = yPts - rowShift
        g2.setFont(self.FontScore); g2.setColor(CLR_UI); g2.drawString(t2, tx, yText)
        g2.setFont(self.FontHud);   g2.setColor(HS_COLUMNS_FG)
        descY = yText + ptsToDescGap + hudAscent
        g2.drawString(d2, tx, descY)
        yPts = (yPts + (hudAscent + ptsToDescGap + hudDescent + rowGap))

        # ---- Row 3: OCTOPUS ----
        spriteTopY = int((yPts - spriteBottomPad) - spriteH)
        DrawAlienSprite(g2, sx, spriteTopY, spriteW, spriteH, "OCTO", 0, 3, False, False)
        yText = yPts - rowShift
        g2.setFont(self.FontScore); g2.setColor(CLR_UI); g2.drawString(t3, tx, yText)
        g2.setFont(self.FontHud);   g2.setColor(HS_COLUMNS_FG)
        descY = yText + ptsToDescGap + hudAscent
        g2.drawString(d3, tx, descY)
        yPts = (yPts + (hudAscent + ptsToDescGap + hudDescent + rowGap))

        # ---- Row 4: UFO ----
        saucerTopY = int((yPts - spriteBottomPad) - saucerH)
        DrawMotherShip(g2, sx, saucerTopY, saucerW, saucerH)
        # DrawMotherShip leaves g2 in CLR_PANEL; set visible colour for text
        yText = yPts - rowShift
        g2.setFont(self.FontScore); g2.setColor(CLR_UI); g2.drawString(t4, tx, yText)
        g2.setFont(self.FontHud);   g2.setColor(HS_COLUMNS_FG)
        descY = yText + ptsToDescGap + hudAscent
        g2.drawString(d4, tx, descY)

        # Return the bottom Y of the table (baseline + descent of the last description line)
        bottomY = descY + hudDescent
            
        return int(bottomY)

    # High scores card (off-black, colored rows, no timestamp)
    def DrawHighScores(self, g2):
        bx = 40; by = 60; bw = self.getWidth() - 80; bh = self.getHeight() - 140

        g2.setColor(CLR_PANEL)
        g2.fillRoundRect(bx, by, bw, bh, 12, 12)
        g2.setColor(HS_BORDER)
        g2.setStroke(BasicStroke(2.0))
        g2.drawRoundRect(bx, by, bw, bh, 12, 12)

        g2.setFont(self.FontScoreTitle)
        g2.setColor(HS_HEADER_FG)
        g2.drawString("HIGH SCORES", bx + 20, by + 40)

        g2.setFont(self.FontScore)
        g2.setColor(HS_COLUMNS_FG)
        g2.drawString("#",     bx + 20,  by + 70)
        g2.drawString("NAME",  bx + 60,  by + 70)
        g2.drawString("SCORE", bx + 320, by + 70)
        g2.drawString("LV",    bx + 430, by + 70)

        y = by + 92
        rowH = 26
        for i in range(min(HS_MAX, len(self.HighScores))):
            s = self.HighScores[i]
            rowClr = HS_COLORS[i % len(HS_COLORS)]

            g2.setColor(rowClr)
            g2.drawRoundRect(bx + 18, y - 18, 24, 20, 6, 6)
            g2.setFont(self.FontHud)
            g2.drawString("%d" % (i+1), bx + 24, y - 4)

            g2.setFont(self.FontScore)
            g2.setColor(rowClr)
            name = str(s.get("name", ""))
            score = int(s.get("score", 0))
            level = int(s.get("level", 1))
            g2.drawString(name,         bx + 60,  y)
            g2.drawString("%d" % score, bx + 320, y)
            g2.drawString("%d" % level, bx + 430, y)
            
            if i < (min(HS_MAX, len(self.HighScores)) - 1):
                g2.setColor(Color(60, 60, 70))
                g2.drawLine(bx + 20, y + 6, bx + bw - 20, y + 6)
            y += rowH

        g2.setFont(self.FontHud)
        g2.setColor(HS_COLUMNS_FG)
        g2.drawString("Press Space to start \n Press H to hide table", bx + 20, by + bh - 1)

    def OnKeyPress(self, code, ctrl=False):
        if code == KeyEvent.VK_LEFT:  self.SetKeyLeft(True)
        elif code == KeyEvent.VK_RIGHT: self.SetKeyRight(True)
        elif code == KeyEvent.VK_H:
            if self.Attract:
                self.ShowScores = not self.ShowScores    
        elif code == KeyEvent.VK_R:
            # CTRL+R resets the high scores when the high-score table is visible in attract mode
            if ctrl and self.Attract and self.ShowScores:
                try:
                    self.HighScores = []
                    SaveHighScores(self.HighScores)
                    try:
                        JOptionPane.showMessageDialog(self, "High scores reset")
                    except:
                        pass
                    self.repaint()
                except:
                    pass            
        elif code == KeyEvent.VK_SPACE:
            if self.GameOver:
                # If the High Scores table is already visible, return to intro/attract instead of starting play.
                if self.ShowScores:
                    # Reset to clean attract state (title + instructions).
                    # ResetFull sets GameOver=False and Attract=True, and clears ShowScores/ShowGameOver.
                    self.ResetFull()
                    # Ensure intro/attract (not play) is shown.
                    self.Attract = True
                    self.ShowScores = False
                    self.ShowGameOver = False
                    self.repaint()
                    return
                # Prompt for high score immediately (once)
                if not self.PromptedHS:
                    self.PromptHighScoreIfQualified()
                    self.PromptedHS = True
                # --- Unconditional view flip (outside the guard) ---
                self.ShowGameOver = False
                self.ShowScores = True
                self.Attract = True
                self.repaint()
                return
            else:
                # Normal behaviour: start game from attract, or fire in-game
                if self.Attract:
                    self.Attract = False
                else:
                    self.SetKeyFire(True)

        elif code == KeyEvent.VK_ESCAPE:
            try:
                self.Timer.stop()
            except:
                pass
            try:
                self.CloseFn()
            except:
                pass

    def OnKeyRelease(self, code):
        if code == KeyEvent.VK_LEFT:  self.SetKeyLeft(False)
        elif code == KeyEvent.VK_RIGHT: self.SetKeyRight(False)
        elif code == KeyEvent.VK_SPACE: self.SetKeyFire(False)

# ----------------------------------------------------------------------
# Window wrapper
# ----------------------------------------------------------------------
class SpiceInveiglersWindow(object):
    def __init__(self):
        self.Frame = jmri.util.JmriJFrame(TITLE_TEXT)
        cp = self.Frame.getContentPane()
        self.Panel = GamePanel(self.Close)
        cp.setBackground(Color(0, 0, 0))
        cp.setLayout(None)
        self.Panel.setBounds(0, 0, PANEL_W, PANEL_H)
        cp.add(self.Panel)
        self.Frame.pack()
        self.Frame.setSize(PANEL_W, PANEL_H)
        self.Frame.setLocationByPlatform(True)
        self.Frame.setFocusable(True)
        self.Frame.setVisible(True)
        self.Frame.requestFocusInWindow()       
        class _Keys(KeyAdapter):      
            def keyPressed(_, e):
                self.Panel.OnKeyPress(e.getKeyCode(), e.isControlDown())
            def keyReleased(_, e): self.Panel.OnKeyRelease(e.getKeyCode())
        self.Frame.addKeyListener(_Keys())     
        outerSelf = self
        class _WinClose(WindowAdapter):
            def windowClosing(_, e):
                try:
                    outerSelf.Close()
                except:
                    pass
        self.Frame.addWindowListener(_WinClose())
  
    def Close(self):
        try:
            self.Panel.Timer.stop()
        except:
            pass
        try:
            self.Frame.dispose()
        except:
            pass

def ShowSpiceInveiglers():
    try:
        SpiceInveiglersWindow()
    except Exception as ex:
        print("[SpiceInveiglers] Failed to open window: " + str(ex))

ShowSpiceInveiglers()
