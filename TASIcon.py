
# -*- coding: ascii -*-
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
# Clock icon: major ticks at 12/3/6/9, tiny ticks for others, time = 10:10, red second hand at 8.
# JMRI 5.12 / Jython 2.7. ASCII only.

from java.awt import Color, BasicStroke, RenderingHints
from java.awt.image import BufferedImage
from java.lang import Math
from java.lang import System

def _Log(msg):
    try:
        System.err.println("[TASIcon] " + str(msg))
    except:
        pass
    try:
        print("[TASIcon] " + str(msg))
    except:
        pass

def _LogExc(prefix, ex):
    try:
        System.err.println("[TASIcon] " + prefix + ": " + str(ex))
    except:
        pass
    try:
        import traceback
        print("[TASIcon] " + prefix + ": " + str(ex))
        print(traceback.format_exc())
    except:
        pass

def CreateClockIconImage(SizePx):
    """
    Draw analogue clock icon:
    - White face, black outline
    - Major ticks at 12, 3, 6, 9 (long)
    - Minor ticks at other hours (tiny)
    - Hour hand at 10:10, minute hand at 10 min, second hand at 8 o'clock (red)
    """
    try:
        s = max(16, min(256, int(SizePx)))
        img = BufferedImage(s, s, BufferedImage.TYPE_INT_ARGB)
        g = img.createGraphics()
        try:
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

            # Background
            g.setColor(Color(255, 255, 255))
            g.fillRect(0, 0, s, s)

            # Circle
            cx = s / 2.0
            cy = s / 2.0
            rOuter = (s - 2) / 2.0
            g.setColor(Color(0, 0, 0))
            g.setStroke(BasicStroke(2.0))
            g.drawOval(int(cx - rOuter), int(cy - rOuter), int(rOuter * 2), int(rOuter * 2))

            # Tick marks
            rMajorOuter = rOuter - 2.0
            rMajorInner = rMajorOuter - 6.0
            rMinorOuter = rOuter - 2.0
            rMinorInner = rMinorOuter - 2.0  # tiny ticks ~2px
            for i in range(12):
                ang = -Math.PI / 2.0 + i * (2.0 * Math.PI / 12.0)
                if i % 3 == 0:  # major tick
                    x1 = cx + rMajorInner * Math.cos(ang)
                    y1 = cy + rMajorInner * Math.sin(ang)
                    x2 = cx + rMajorOuter * Math.cos(ang)
                    y2 = cy + rMajorOuter * Math.sin(ang)
                else:  # minor tick
                    x1 = cx + rMinorInner * Math.cos(ang)
                    y1 = cy + rMinorInner * Math.sin(ang)
                    x2 = cx + rMinorOuter * Math.cos(ang)
                    y2 = cy + rMinorOuter * Math.sin(ang)
                g.drawLine(int(x1), int(y1), int(x2), int(y2))

            # Hands
            # Angles
            angHour = -Math.PI / 2.0 + (10 * Math.PI / 6.0) + (10 * Math.PI / 360.0)  # 10:10
            angMin = -Math.PI / 2.0 + (10 * Math.PI / 30.0)  # 10 minutes
            angSec = -Math.PI / 2.0 + (8 * Math.PI / 6.0)    # 8 o'clock

            # Minute hand (black)
            g.setColor(Color(0, 0, 0))
            g.setStroke(BasicStroke(2.0))
            rMin = rOuter - 6.0
            xMin = cx + rMin * Math.cos(angMin)
            yMin = cy + rMin * Math.sin(angMin)
            g.drawLine(int(cx), int(cy), int(xMin), int(yMin))

            # Hour hand (black, shorter & thicker)
            g.setStroke(BasicStroke(3.0))
            rHour = rOuter - 12.0
            xHour = cx + rHour * Math.cos(angHour)
            yHour = cy + rHour * Math.sin(angHour)
            g.drawLine(int(cx), int(cy), int(xHour), int(yHour))

            # Second hand (red, thin, slightly longer than minute)
            g.setColor(Color(200, 0, 0))
            g.setStroke(BasicStroke(1.5))
            rSec = rOuter - 4.0
            xSec = cx + rSec * Math.cos(angSec)
            ySec = cy + rSec * Math.sin(angSec)
            g.drawLine(int(cx), int(cy), int(xSec), int(ySec))

            # Center pin
            g.setColor(Color(0, 0, 0))
            g.fillOval(int(cx - 2), int(cy - 2), 4, 4)

        finally:
            g.dispose()
        return img
    except Exception as ex:
        _LogExc("CreateClockIconImage failed", ex)
        return None

def SetFrameClockIcon(Frame, SizePx=32):
    try:
        img = CreateClockIconImage(SizePx)
        if img is not None:
            Frame.setIconImage(img)
            _Log("Icon set on frame: " + str(Frame.getTitle()))
        else:
            _Log("Icon not set (image creation returned None)")
    except Exception as ex:
        _LogExc("SetFrameClockIcon failed", ex)
