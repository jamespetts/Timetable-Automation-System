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
import os
import java
from java.awt import Color, Font, BasicStroke, RenderingHints, Dimension, Rectangle, Polygon
from javax.swing import JPanel, Timer, JOptionPane
from java.awt.event import KeyAdapter, KeyEvent
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
LEVEL_SPEED_INCREMENT = 0.15

# Animation pacing (larger = slower alien wiggle)
ANIM_TICKS_PER_FLIP = 8

# Dynamic speed-up as aliens are destroyed
# EffectiveSpeed = Base * (1 + DeadFraction * (ALIEN_ACCEL_MAX_MULT - 1))
ALIEN_ACCEL_MAX_MULT = 2.2

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

# Colors (game)
CLR_BG = Color(16, 16, 20)
CLR_TEXT = Color(240, 240, 240)
CLR_PANEL = Color(24, 24, 30)
CLR_PLAYER = Color(255, 210, 60)
CLR_SHOT = Color(255, 255, 100)
CLR_ENEMY_SHOT = Color(255, 90, 90)
CLR_UI = Color(180, 180, 200)

# ----------------------------------------------------------------------
# High score file path (profile-relative, no absolute paths)
# ----------------------------------------------------------------------
def GetHighScorePath():
    try:
        return jmri.util.FileUtil.getExternalFilename("profile:jython/config/" + HS_FILE_NAME)
    except:
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

def DrawAlienSprite(g2, x, y, w, h, kind, phase, rowIdx):
    ax = int(x); ay = int(y); aw = int(w); ah = int(h)
    baseCol = ROW_COLORS_PHASE0[min(max(0, rowIdx), len(ROW_COLORS_PHASE0)-1)]
    altCol = ROW_COLORS_PHASE1[min(max(0, rowIdx), len(ROW_COLORS_PHASE1)-1)]
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
        if d and not os.path.exists(d):
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
        self.PlayerX = PANEL_W / 2 - PLAYER_W / 2
        self.PlayerY = PANEL_H - 64
        self.PlayerCooldownMs = 0
        self.PlayerShots = []
        self.EnemyShots = []
        self.AlienDir = 1
        self.AlienSpeed = ALIEN_BASE_SPEED
        self.AlienStepDownPending = False
        self.TickPhase = 0
        self.AnimTickCount = 0
        self.BuildAliens()

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

        if self.GameOver:
            if not self.PromptedHS:
                self.PromptHighScoreIfQualified()
                self.Attract = True
                self.ShowScores = True
                self.PromptedHS = True
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
        effSpeed = baseSpeed * (1.0 + deadFraction * (ALIEN_ACCEL_MAX_MULT - 1.0))

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

        # Enemy shooting: lowest alive per column
        for c in range(ALIEN_COLS):
            lowest = None
            for r in range(ALIEN_ROWS - 1, -1, -1):
                a = self.Aliens[r][c]
                if a["alive"]:
                    lowest = a
                    break
            if lowest and self.Rng.nextFloat() < ALIEN_SHOOT_CHANCE:
                sx = lowest["x"] + lowest["w"] / 2 - ENEMY_SHOT_W / 2
                sy = lowest["y"] + lowest["h"]
                self.EnemyShots.append(Rect(sx, sy, ENEMY_SHOT_W, ENEMY_SHOT_H))

        # Collisions: player shots vs aliens
        for i in range(len(self.PlayerShots) - 1, -1, -1):
            ps = self.PlayerShots[i]
            hit = False
            for r in range(ALIEN_ROWS):
                for c in range(ALIEN_COLS):
                    a = self.Aliens[r][c]
                    if not a["alive"]:
                        continue
                    if Intersects(ps, Rect(a["x"], a["y"], a["w"], a["h"])):
                        a["alive"] = False
                        self.Score += 10
                        del self.PlayerShots[i]
                        hit = True
                        break
                if hit:
                    break

        # Collisions: enemy shots vs player
        playerRect = Rect(self.PlayerX, self.PlayerY, PLAYER_W, PLAYER_H)
        for i in range(len(self.EnemyShots) - 1, -1, -1):
            es = self.EnemyShots[i]
            if Intersects(es, playerRect):
                del self.EnemyShots[i]
                self.LoseLife()
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
            self.BuildAliens()

        self.repaint()

    def LoseLife(self):
        self.Lives -= 1
        self.EnemyShots[:] = []
        self.PlayerShots[:] = []
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                a = self.Aliens[r][c]
                if a["alive"]:
                    a["y"] = max(ALIEN_START_Y, a["y"] - ALIEN_STEP_DOWN)
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
        hud = "Score: %d    Lives: %d    Level: %d" % (self.Score, self.Lives, self.Level)
        g2.drawString(hud, 20, 30)

        # Attract mode
        if self.Attract:
            if self.ShowScores:
                self.DrawHighScores(g2)
            else:
                g2.setFont(self.FontIntroTitle)
                g2.setColor(CLR_TEXT)
                g2.drawString(TITLE_TEXT, 20, 78)

                g2.setFont(self.FontHud)
                g2.setColor(CLR_UI)
                g2.drawString("Left/Right = Move, Space = Fire, Esc = Quit", 20, 110)
                g2.drawString("Press Space to start", 20, 130)
                g2.drawString("Press H for High Scores", 20, 150)
            return

        # Player
        g2.setColor(CLR_PLAYER)
        DrawShip(g2, int(self.PlayerX), int(self.PlayerY), PLAYER_W, PLAYER_H)

        # Aliens (per-row color)
        for r in range(ALIEN_ROWS):
            for c in range(ALIEN_COLS):
                a = self.Aliens[r][c]
                if not a["alive"]:
                    continue
                DrawAlienSprite(g2, int(a["x"]), int(a["y"]), a["w"], a["h"], a["kind"], self.TickPhase, r)

        # Shots
        for ps in self.PlayerShots:
            DrawShot(g2, ps.x, ps.y, ps.width, ps.height, friendly=True)
        for es in self.EnemyShots:
            DrawShot(g2, es.x, es.y, es.width, es.height, friendly=False)

        if self.GameOver:
            g2.setFont(self.FontBig)
            g2.setColor(CLR_TEXT)
            g2.drawString("Game Over", 220, 220)
            g2.setFont(self.FontHud)
            g2.drawString("Press Space to restart, or Esc to quit", 180, 250)

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
                self.ResetFull()
                self.Attract = False
            else:
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
            def keyPressed(_, e): self.Panel.OnKeyPress(e.getKeyCode(), e.isControlDown())
            def keyReleased(_, e): self.Panel.OnKeyRelease(e.getKeyCode())
        self.Frame.addKeyListener(_Keys())


    def Close(self):
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
