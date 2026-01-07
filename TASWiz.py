# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>.
#
# TAS Setup Wizard (TASWiz.py)
#
# Wizard-style setup helper.
# - ASCII-only, portable paths, thread-safe.
# - Designed for JMRI 5.14 + Jython (Python 2.7).
#
# Notes:
# - Left sidebar image: put a PNG at profile:jython/TASWizard.png.
# - Optional override: set memory TAS_WIZARD_IMAGE to a filename under profile:jython, or a full "profile:" path.
# - Test harness override: set memory TAS_WIZARD_TEST_MISSINGFONTS to an integer to force step 3 behavior.

import java
import traceback
import os
import csv

from java.awt import (BorderLayout, Color, Dimension, Font, GridBagConstraints,
GridBagLayout, Insets, RenderingHints)
from java.awt.image import BufferedImage
from java.lang import Runnable

from javax.swing import (Box, JButton, JDialog, JLabel, JPanel, JScrollPane,
                        SwingUtilities, BorderFactory, JTextArea, JOptionPane,
                        JTextField, JCheckBox, JComboBox, DefaultComboBoxModel,
JFileChooser, JList, ListSelectionModel)
from javax.swing import JList, ListSelectionModel
from javax.swing.filechooser import FileNameExtensionFilter

# JMRI
import jmri
from jmri.util import FileUtil

# TAS helpers
import TASBeanLookup as TBL

# Image loading
from javax.imageio import ImageIO
from java.io import File

# ------------------------------- Logging ---------------------------------
TAG = "[TASWiz] "

def LogInfo(msg):
    try:
        print(TAG + str(msg))
    except:
        pass


def LogWarn(msg):
    try:
        print(TAG + 'WARN: ' + str(msg))
    except:
        pass

def LogError(msg, ex=None):
    try:
        print(TAG + "ERROR: " + str(msg))
        if ex is not None:
            print(TAG + "TRACEBACK:")
            traceback.print_exc()
    except:
        pass

        # ------------------------------- Theme -----------------------------------

def _RgbStrToColorOrDefault(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3:
            return defaultColor
        r, g, b = [max(0, min(255, int(float(x)))) for x in parts]
        return Color(r, g, b)
    except:
        return defaultColor


THEME_FONT_FAMILY = TBL.SafeGetOrCreateMemoryValue("TAS_FONT_FAMILY", "Gill Sans MT")
THEME_TEXT_COLOR = Color(30, 30, 30)
THEME_PAPER = _RgbStrToColorOrDefault(
    TBL.SafeGetOrCreateMemoryValue("TASPAPERCOLOUR", "249,246,238"),
    Color(249, 246, 238)
)
THEME_ACCENT = Color(80, 80, 80)
THEME_BORDER = Color(180, 170, 150)


def ApplyTheme(component):
    try:
        component.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
    except:
        pass



        # ------------------------------ Font fallback helpers ------------------------------
def _GetInstalledFontFamiliesLowerSet():
    try:
        from java.awt import GraphicsEnvironment
        ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
        names = ge.getAvailableFontFamilyNames()
        out = set([])
        for n in names:
            try:
                out.add(str(n).strip().lower())
            except:
                pass
        return out
    except:
        return set([])

def _FirstInstalledFont(candidates, fallbackName):
# Return the first candidate present on this system; else fallbackName.
    try:
        avail = _GetInstalledFontFamiliesLowerSet()
        for nm in (candidates or []):
            try:
                if str(nm).strip().lower() in avail:
                    return nm
            except:
                pass
    except:
        pass
    try:
        return fallbackName if fallbackName is not None else 'SansSerif'
    except:
        return 'SansSerif'
def MakePaperPanel():
    class PaperPanel(JPanel):
        def __init__(self):
            JPanel.__init__(self)
            self.setOpaque(True)
            self.setBackground(THEME_PAPER)
            self.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createMatteBorder(1, 1, 1, 1, THEME_BORDER),
                BorderFactory.createEmptyBorder(12, 12, 12, 12)
            ))
            self.texture = self._MakeTexture()

        def _MakeTexture(self):
            w, h = 64, 64
            img = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
            g = img.createGraphics()
            g.setColor(THEME_PAPER)
            g.fillRect(0, 0, w, h)
            try:
                g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            except:
                pass
            g.setColor(Color(200, 196, 184, 22))
            for _i in range(150):
                x = int(java.lang.Math.random() * w)
                y = int(java.lang.Math.random() * h)
                g.fillRect(x, y, 1, 1)
            g.dispose()
            return img

        def paintComponent(self, g):
        # Jython-safe superclass paint call.
            super(PaperPanel, self).paintComponent(g)
            iw = self.texture.getWidth()
            ih = self.texture.getHeight()
            for y in range(0, self.getHeight(), ih):
                for x in range(0, self.getWidth(), iw):
                    g.drawImage(self.texture, x, y, None)

    p = PaperPanel()
    ApplyTheme(p)
    return p


def MakeHeading(text):
    lbl = JLabel(text)
    try:
        lbl.setForeground(THEME_ACCENT)
        lbl.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 16))
    except:
        pass
    return lbl


def MakeWrappedTextArea(text, fontSize=13):
# JTextArea wrapping avoids HTML JLabel measurement quirks that can clip horizontally.
    ta = JTextArea()
    try:
        ta.setText("" if text is None else str(text))
    except:
        ta.setText("")
    ta.setEditable(False)
    ta.setLineWrap(True)
    ta.setWrapStyleWord(True)
    ta.setOpaque(False)
    try:
        ta.setForeground(THEME_TEXT_COLOR)
    except:
        pass
    try:
        ta.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, int(fontSize)))
    except:
        pass
    try:
        ta.setBorder(None)
    except:
        pass
    return ta


def MakeScrollForText(textArea):
    sp = JScrollPane(textArea)
    try:
        sp.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0))
    except:
        pass
    try:
        sp.getViewport().setOpaque(False)
    except:
        pass
    try:
        sp.setOpaque(False)
    except:
        pass
    return sp

    # -------------------------- Wizard image helper ---------------------------

DEFAULT_WIZARD_IMAGE_PROFILE_PATH = "profile:jython/TASWizard.png"


def _ResolveWizardImageProfilePath():
# Returns a profile: path string.
    try:
        raw = TBL.SafeGetOrCreateMemoryValue("TAS_WIZARD_IMAGE", "").strip()
    except:
        raw = ""
    if raw is None:
        raw = ""
    raw = str(raw).strip()
    if raw != "":
        if raw.lower().startswith("profile:"):
            return raw
        return "profile:jython/" + raw
    return DEFAULT_WIZARD_IMAGE_PROFILE_PATH


def _CandidateWizardImageProfilePaths():
    p = _ResolveWizardImageProfilePath()
    return [p, "profile:jython/TASWizardSidebar.png", "profile:jython/TASWizardLeft.png"]


def _LoadWizardImage():
# Returns a BufferedImage or None.
    try:
        for profPath in _CandidateWizardImageProfilePaths():
            try:
                pth = FileUtil.getExternalFilename(profPath)
            except:
                pth = None
            if not pth:
                continue
            f = File(pth)
            if (not f.exists()) or (not f.isFile()):
                continue
            img = ImageIO.read(f)
            if img is None:
                continue
            iw = img.getWidth(None)
            ih = img.getHeight(None)
            if iw <= 0 or ih <= 0:
                continue
            return img
        return None
    except Exception as ex:
        LogInfo("Wizard image load skipped: " + str(ex))
        return None


class WizardSidebarImagePanel(JPanel):
# Paints the sidebar image scaled to fill the sidebar area (classic wizard look).
# Uses a cover scale: the image fills the panel and is cropped as needed.
    def __init__(self, img):
        JPanel.__init__(self)
        self.Image = img
        self.setOpaque(True)
        try:
            self.setBackground(THEME_PAPER)
        except:
            pass

    def paintComponent(self, g):
        try:
            super(WizardSidebarImagePanel, self).paintComponent(g)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()
        if w <= 0 or h <= 0:
            return

        img = self.Image
        if img is None:
            return

        try:
            iw = img.getWidth(None)
            ih = img.getHeight(None)
        except:
            iw = -1
            ih = -1

        if iw <= 0 or ih <= 0:
            return

            # Scale to cover the panel.
        sx = float(w) / float(iw)
        sy = float(h) / float(ih)
        scale = sx if sx > sy else sy
        if scale <= 0.0:
            return

            # Center crop: compute source rectangle in original image coords.
        srcW = int(float(w) / float(scale))
        srcH = int(float(h) / float(scale))
        if srcW <= 0 or srcH <= 0:
            return

        sx1 = int((iw - srcW) / 2)
        sy1 = int((ih - srcH) / 2)
        if sx1 < 0:
            sx1 = 0
        if sy1 < 0:
            sy1 = 0
        sx2 = sx1 + srcW
        sy2 = sy1 + srcH
        if sx2 > iw:
            sx2 = iw
        if sy2 > ih:
            sy2 = ih

        try:
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC)
        except:
            pass

        try:
            g.drawImage(img, 0, 0, w, h, sx1, sy1, sx2, sy2, None)
        except:
            try:
                g.drawImage(img, 0, 0, w, h, None)
            except:
                pass

                # ------------------------------ Font check --------------------------------

FONT_CHECK_SCRIPT = "TASFontCheck.py"

WORKING_CREATOR_SCRIPT = 'WorkingCreator_HeadlessAudit_20260106_v2.py'
WORKINGS_UI_SCRIPT = 'TASWorkingsUi.py'
def LoadWorkingsUiModule():
# Returns a loaded module or None.
    try:
        import imp
        pth = ProfileJythonFilePath(WORKINGS_UI_SCRIPT)
        if not pth:
            return None
        if not File(pth).exists():
            return None
        return imp.load_source('TASWorkingsUi_i', pth)
    except Exception as ex:
        LogInfo('Workings UI module load failed: ' + str(ex))
        return None

def MakeWrappedLabel(htmlText, widthPx=560, lineHeight=1.25, bold=False):
# Create a JLabel that wraps text using HTML with an explicit width.
    try:
        html = "<html><div style='width:%dpx; line-height:%s;'>%s</div></html>" % (int(widthPx), str(float(lineHeight)), str(htmlText))
    except:
        html = "<html>%s</html>" % str(htmlText)
    lbl = JLabel(html)
    try:
        style = Font.BOLD if bool(bold) else Font.PLAIN
        size = 16 if bool(bold) else 13
        lbl.setFont(Font(THEME_FONT_FAMILY, style, size))
        try:
            lbl.setForeground(THEME_ACCENT if bool(bold) else THEME_TEXT_COLOR)
        except:
            pass
    except:
        pass
    return lbl


def LoadWorkingCreatorModule():
# Returns a loaded module or None.
    try:
        import imp
        pth = ProfileJythonFilePath(WORKING_CREATOR_SCRIPT)
        if not pth:
            return None
        try:
            if not File(pth).exists():
                pth2 = ProfileJythonFilePath('WorkingCreator.py')
                if pth2 and File(pth2).exists():
                    pth = pth2
                else:
                    return None
        except:
            return None
        return imp.load_source('WorkingCreator_i', pth)
    except Exception as ex:
        LogInfo('Working creator module load failed: ' + str(ex))
        return None



def ProfileJythonFilePath(name):
    try:
        return FileUtil.getExternalFilename("profile:jython/" + str(name))
    except:
        return None

def _LoadNamedPresetsFromConfigCsv(fileName, defaultNames):
# Read preset names from profile:jython/config/<fileName> (tab-delimited, ASCII).
    names = list(defaultNames or [])
    try:
        path = FileUtil.getExternalFilename('profile:jython/config/' + str(fileName))
    except:
        return names
    try:
        import java.io as jio
        f = jio.File(path)
        if (not f.exists()) or (not f.isFile()):
            return names
        fis = jio.FileInputStream(f)
        isr = java.io.InputStreamReader(fis, 'US-ASCII')
        br = java.io.BufferedReader(isr)
        header = br.readLine()
        idx = -1
        if header:
            cols = header.split('\t')
            for i,c in enumerate(cols):
                try:
                    if str(c).strip().lower() == 'name':
                        idx = int(i)
                        break
                except:
                    pass
        seen = set(names)
        line = br.readLine()
        while line is not None:
            parts = line.split('\t')
            if idx >= 0 and idx < len(parts):
                try:
                    val = str(parts[idx]).strip()
                    if val and (val not in seen):
                        names.append(val)
                        seen.add(val)
                except:
                    pass
            line = br.readLine()
        try:
            br.close()
            isr.close()
            fis.close()
        except:
            pass
    except Exception as ex:
        try:
            LogInfo('Could not read presets from ' + str(fileName) + ': ' + str(ex))
        except:
            pass
    return names

def _LoadClimateNames():
    return _LoadNamedPresetsFromConfigCsv('climate.csv', ['SouthWales_EarlySep'])

def _LoadDayNightNames():
    return _LoadNamedPresetsFromConfigCsv('daynight.csv', ['Maesteg_Sep2017'])



class RestrictedCsvChooserWizard(JFileChooser):
    def __init__(self, baseDir):
        JFileChooser.__init__(self, baseDir)
        self.baseDir = baseDir.getCanonicalFile()
        self.setDialogTitle('Select timetable CSV')
        self.setFileSelectionMode(JFileChooser.FILES_ONLY)
        self.setAcceptAllFileFilterUsed(False)
        try:
            self.addChoosableFileFilter(FileNameExtensionFilter('CSV files (*.csv)', ['csv']))
        except:
            pass

    def approveSelection(self):
        sel = self.getSelectedFile()
        if sel is None:
            return
        try:
            canonical = sel.getCanonicalFile()
            if not canonical.getName().lower().endswith('.csv'):
                try:
                    JOptionPane.showMessageDialog(None, 'Please select a .csv file.', 'Timetable', JOptionPane.WARNING_MESSAGE)
                except:
                    pass
                return
            allowed = self.baseDir.getPath()
            cpath = canonical.getPath()
            if not (cpath == allowed or cpath.startswith(allowed + File.separator)):
                try:
                    JOptionPane.showMessageDialog(None, 'Please choose a timetable.', 'Timetable', JOptionPane.WARNING_MESSAGE)
                except:
                    pass
                return
        except Exception as ex:
            try:
                JOptionPane.showMessageDialog(None, 'Error validating selection: ' + str(ex), 'Timetable', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return
        JFileChooser.approveSelection(self)


def LoadFontCheckModule():
# Returns a loaded module or None.
    try:
        import imp
        pth = ProfileJythonFilePath(FONT_CHECK_SCRIPT)
        if not pth:
            return None
        if not File(pth).exists():
            return None
        return imp.load_source("TASFontCheck_i", pth)
    except Exception as ex:
        LogInfo("Font check module load failed: " + str(ex))
        return None


def CountMissingFonts(mod):
# Returns int or None.
    if mod is None:
        return None
    try:
        if hasattr(mod, "CountMissingFonts"):
            return int(mod.CountMissingFonts(False))
    except:
        pass
    try:
        if hasattr(mod, "GetMissingFontsCount"):
            return int(mod.GetMissingFontsCount(False))
    except:
        pass
    try:
        if hasattr(mod, "RunFontCheck"):
        # silent=True should not show UI.
            return int(mod.RunFontCheck(True, None))
    except:
        pass
    return None


def OpenFontCheckUi(mod, parentWindow):
# Best-effort UI opener.
# Try module entry points if available, then fall back to execfile.
    if mod is not None:
        try:
            if hasattr(mod, "RunFontCheckDialog"):
                mod.RunFontCheckDialog(parentWindow)
                return True
        except:
            pass
        try:
            if hasattr(mod, "RunFontCheck"):
                mod.RunFontCheck(False, parentWindow)
                return True
        except:
            pass
    try:
        pth = ProfileJythonFilePath(FONT_CHECK_SCRIPT)
        if pth and File(pth).exists():
            execfile(pth, {"__name__": "__main__"})
            return True
    except:
        pass
    return False

    # ----------------------------- Wizard Dialog ------------------------------

class RunnableAdapter(Runnable):
    def __init__(self, func):
        self.Func = func

    def run(self):
        self.Func()


class TASWizardDialog(JDialog):
    def __init__(self):
    # Modeless so helper tools can be used.
        JDialog.__init__(self, None, "Timetable Automation System setup wizard", False)
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
        try:
            self.setModal(False)
        except:
            pass

            # Set window icon.
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)
        except Exception as ex:
            LogInfo("Failed to set wizard window icon: " + str(ex))

        self.setSize(760, 500)
        try:
            self.setMinimumSize(Dimension(760, 500))
        except:
            pass

        self.StepIndex = 0
        self.Steps = []

        self.SidebarImage = _LoadWizardImage()

        # Font check cache.
        self.FontCheckMod = None
        self.MissingFontsCount = None

        # Cache test harness override at dialog creation time (wizard is modeless).
        self.TestMissingFontsOverride = None
        try:
            raw = TBL.SafeGetOrCreateMemoryValue('TAS_WIZARD_TEST_MISSINGFONTS', '').strip()
        except:
            raw = ''
        try:
            if raw is not None and str(raw).strip() != '':
                self.TestMissingFontsOverride = int(float(str(raw).strip()))
        except:
            self.TestMissingFontsOverride = None

            # Step 4 values (not stored long-term).
        self.LayoutYear = None
        self.ProfileNameField = None
        self.YearField = None
        # Step 5 values (stored long-term in memories; UI references cached here).
        self.CompanyCombo = None
        self.CompanyOtherField = None
        self.CompanyOtherLabel = None
        self.RegionCombo = None 
        self.RegionLabel = None
        self.RegionOtherField = None 
        self.RegionOtherLabel = None 
        self.SectionField = None 
        self.ApplyDefaultsCheck = None 
        self.ApplyDefaultsAppearanceCheck = None 
        self.ApplyDefaultsPublicDisplaysCheck = None 
        self.ApplyDefaultsSignallersDisplaysCheck = None 
        self.ApplyDefaultsWeatherForecastingCheck = None 
        self.UseAutoTrainsCheck = None 
        self.UseLightingCheck = None 
        self.UseOrientationCheck = None 
        self.Step2aTextArea = None
        self.TimetableNameField = None
        self.TimetableChosenLabel = None
        self.TimetableBrowseButton = None
        self.Step2bExtraTextArea = None
        self.Step2bExtraScroll = None
        self.Step2bwTextArea = None
        self.Step2bwScroll = None
        self.WorkingsCreateButton = None
        self.WorkingsOk = False
        self.MissingWorkings = []
        self.InvalidWorkings = []
        self.DispatcherHelpButton = None
        self.Step2cExtraTextArea = None
        self.Step2cExtraScroll = None
        self.Step2chTextArea = None
        self.Step2chScroll = None
        self.Step2chConfigButton = None
        self.Step2dExtraTextArea = None
        self.Step2dExtraScroll = None
        self.LowCtAddrField = None
        self.HighCtAddrField = None
        self.Step2fClimateCombo = None
        self.Step2fDaylightCombo = None
        # Step 2bd (disruption) UI references cached here.
        self.Step2bdInfoTextArea = None
        self.Step2bdInfoScroll = None
        self.EnableDelaysCheck = None
        self.EnableCancellationsCheck = None
        # Cached feature selections (wizard only; not persisted).
        self.UseAutoTrainsSelected = False
        self.UseOrientationSelected = False
        self.UseLightingSelected = False
        self.SuppressLightingListener = False
        self.InitialDayNightEnabled = False
        self.RestartNeeded = False
        self.SuppressAutoTrainsListener = False
        self.SuppressOrientationListener = False
        self.InitialOrientationSensingEnabled = False
 
        self.getContentPane().setLayout(BorderLayout())

        self.CardHost = JPanel()
        try:
            from java.awt import CardLayout
            self.CardLayout = CardLayout()
            self.CardHost.setLayout(self.CardLayout)
        except:
            self.CardLayout = None
            self.CardHost.setLayout(BorderLayout())
        self.getContentPane().add(self.CardHost, BorderLayout.CENTER)

        nav = JPanel()
        nav.setOpaque(True)
        nav.setBackground(THEME_PAPER)
        nav.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createMatteBorder(1, 0, 0, 0, THEME_BORDER),
            BorderFactory.createEmptyBorder(8, 12, 8, 12)
        ))
        nav.setLayout(GridBagLayout())
        ng = GridBagConstraints()
        ng.insets = Insets(0, 0, 0, 0)
        ng.gridy = 0
        ng.fill = GridBagConstraints.NONE

        self.BtnBack = JButton("< Back")
        self.BtnForward = JButton("Forward >")
        self.BtnCancel = JButton("Cancel")
        self.BtnHelp = JButton("Help")

        ApplyTheme(self.BtnBack)
        ApplyTheme(self.BtnForward)
        ApplyTheme(self.BtnCancel)
        ApplyTheme(self.BtnHelp)

        ng.gridx = 0
        ng.weightx = 0.0
        ng.anchor = GridBagConstraints.WEST
        nav.add(self.BtnHelp, ng)

        ng.gridx = 1
        ng.weightx = 1.0
        ng.fill = GridBagConstraints.HORIZONTAL
        nav.add(Box.createHorizontalGlue(), ng)

        rightBox = Box.createHorizontalBox()
        rightBox.add(self.BtnBack)
        rightBox.add(Box.createHorizontalStrut(10))
        rightBox.add(self.BtnForward)
        rightBox.add(Box.createHorizontalStrut(10))
        rightBox.add(self.BtnCancel)
        ApplyTheme(rightBox)

        ng.gridx = 2
        ng.weightx = 0.0
        ng.fill = GridBagConstraints.NONE
        ng.anchor = GridBagConstraints.EAST
        nav.add(rightBox, ng)

        self.getContentPane().add(nav, BorderLayout.SOUTH)

        self.BtnBack.addActionListener(lambda e: self.GoBack())
        self.BtnForward.addActionListener(lambda e: self.GoForward())
        self.BtnCancel.addActionListener(lambda e: self.OnCancelOrFinished())
        self.BtnHelp.addActionListener(lambda e: self.OnHelp())

        try:
            self.InitialDayNightEnabled = bool(self._GetDayNightEnabled())
        except:
            self.InitialDayNightEnabled = False
        try:
            self.InitialOrientationSensingEnabled = bool(self._GetOrientationSensingEnabled())
        except:
            self.InitialOrientationSensingEnabled = False
            # Apply default fonts via UIManager so all labels/controls use THEME_FONT_FAMILY.
        try:
            from javax.swing import UIManager
            UIManager.put('Label.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('Button.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('CheckBox.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('ComboBox.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('List.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('TextField.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('TextArea.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('ScrollPane.font', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            UIManager.put('OptionPane.messageFont', Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
        except:
            pass

        self.BuildSteps()
        self.ShowStep(0)

        try:
            self.setLocationRelativeTo(None)
        except:
            pass
        self.setVisible(True)

    def _BuildSidebar(self):
        sidebarW = 220
        sidebar = JPanel()
        sidebar.setOpaque(False)
        sidebar.setLayout(BorderLayout())
        try:
            sidebar.setPreferredSize(Dimension(sidebarW, 1))
        except:
            pass
        try:
            sidebar.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createMatteBorder(0, 0, 0, 1, THEME_BORDER),
                BorderFactory.createEmptyBorder(4, 4, 4, 4)
            ))
        except:
            pass
        imgPanel = WizardSidebarImagePanel(self.SidebarImage)
        sidebar.add(imgPanel, BorderLayout.CENTER)
        return sidebar

    def MakeWizardStep(self, titleText, bodyText):
        root = MakePaperPanel()
        root.setLayout(BorderLayout())
        root.add(self._BuildSidebar(), BorderLayout.WEST)

        center = JPanel()
        center.setOpaque(False)
        center.setLayout(GridBagLayout())
        g = GridBagConstraints()
        g.insets = Insets(6, 12, 6, 6)
        g.gridx = 0
        g.gridy = 0
        g.weightx = 1.0
        g.weighty = 0.0
        g.fill = GridBagConstraints.HORIZONTAL
        center.add(MakeHeading(titleText), g)

        g.gridy = 1
        g.weighty = 1.0
        g.fill = GridBagConstraints.BOTH
        ta = MakeWrappedTextArea(bodyText, fontSize=13)
        sp = MakeScrollForText(ta)
        center.add(sp, g)

        root.add(center, BorderLayout.CENTER)
        return root

    def MakeWizardStepWithButton(self, titleText, bodyText, buttonText, onClick):
        root = self.MakeWizardStep(titleText, bodyText)
        # The right-hand content panel is the CENTER component of root.
        # Add a button row at the bottom of that panel.
        try:
            center = root.getComponent(1)
        except:
            center = None
        if center is None:
            return root
        try:
        # center uses GridBagLayout; add a new row after the scroll pane.
            btn = JButton(buttonText)
            ApplyTheme(btn)
            btn.addActionListener(lambda e: onClick())

            g = GridBagConstraints()
            g.insets = Insets(6, 12, 6, 6)
            g.gridx = 0
            g.gridy = 2
            g.weightx = 1.0
            g.weighty = 0.0
            g.fill = GridBagConstraints.NONE
            g.anchor = GridBagConstraints.WEST
            center.add(btn, g)
        except:
            pass
        return root

    def EnsureFontCheck(self):
    # Populate self.FontCheckMod and self.MissingFontsCount.
    # Test harness override: if set at dialog creation time, forces the result.
        try:
            if self.TestMissingFontsOverride is not None:
                self.MissingFontsCount = int(self.TestMissingFontsOverride)
                return
        except:
            pass

        if self.MissingFontsCount is not None:
            return

        try:
            self.FontCheckMod = LoadFontCheckModule()
        except:
            self.FontCheckMod = None

        try:
            self.MissingFontsCount = CountMissingFonts(self.FontCheckMod)
        except:
            self.MissingFontsCount = None

    def ShouldSkipFontStep(self):
    # Returns True only when we have already computed the count and it is zero.
        try:
            return (self.MissingFontsCount is not None) and (int(self.MissingFontsCount) == 0)
        except:
            return False

    def _GetActiveProfile(self):
        try:
            pm = jmri.profile.ProfileManager.getDefault()
            if pm is None:
                return None
            return pm.getActiveProfile()
        except:
            return None

    def _GetActiveProfileName(self):
        try:
            pm = jmri.profile.ProfileManager.getDefault()
            if pm is None:
                return ''
            nm = pm.getActiveProfileName()
            return '' if nm is None else str(nm)
        except:
            try:
                p = self._GetActiveProfile()
                if p is not None:
                    return str(p.getName())
            except:
                pass
            return ''

    def _DefaultLayoutYear(self):
        try:
            from java.util import Calendar
            return int(Calendar.getInstance().get(Calendar.YEAR))
        except:
            return 2000

    def _ApplyLayoutDetailsFromStep4(self):
    # Apply profile name change and cache year for later steps.
    # Year is not persisted.
        try:
            if self.ProfileNameField is None or self.YearField is None:
                return True
        except:
            return True

        try:
            newName = str(self.ProfileNameField.getText()).strip()
        except:
            newName = ''
        if newName == '':
            try:
                JOptionPane.showMessageDialog(self, 'Please the name of your layout.', 'Layout details', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return False

        try:
            yrRaw = str(self.YearField.getText()).strip()
        except:
            yrRaw = ''
        try:
            yr = int(float(yrRaw))
        except:
            yr = None
        if yr is None or yr < 1800 or yr > 2200:
            try:
                JOptionPane.showMessageDialog(self, 'Please enter a valid year (e.g. 2017).', 'Layout details', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return False

        try:
            self.LayoutYear = int(yr)
        except:
            self.LayoutYear = None
        try:
            self._RefreshCompanyOptionsForYear()
        except:
            pass

        try:
            p = self._GetActiveProfile()
            if p is not None:
                curName = ''
                try:
                    curName = str(p.getName())
                except:
                    curName = ''
                if curName != newName:
                    p.setName(newName)
        except Exception as ex:
            LogInfo('Failed to set profile name: ' + str(ex))
            try:
                JOptionPane.showMessageDialog(self, 'Could not change the profile name.\n\nDetails: ' + str(ex), 'Layout details', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return False

        return True

    def _CompanyOptionsForYear(self, yearVal):
    # Returns a list of company names valid for the given year. Always includes 'Other...'.
        companies = [
            ('Network Rail', 2002, None),
            ('Railtrack', 1994, 2003),
            ('British Rail', 1966, 1995),
            ('British Railways', 1948, 1966),
            ('Transport for London', 2000, None),
            ('London Transport', 1933, 2000),
            ('London Midland and Scottish Railway', 1923, 1947),
            ('London & North Eastern Railway', 1923, 1947),
            ('Southern Railway', 1923, 1947),
            ('Great Western Railway', 1835, 1947),
            ('London, Brighton & South Coast Railway', 1846, 1922),
            ('London and South Western Railway', 1838, 1922),
            ('South-Eastern and Chatham Railway', 1899, 1922),
            ('London, Chatham and Dover Railway', 1859, 1899),
            ('South-Eastern Railway', 1836, 1922),
            ('Great Northern Railway', 1846, 1922),
            ('North Eastern Railway', 1854, 1922),
            ('North British Railway', 1844, 1922),
            ('Great North of Scotland Railway', 1845, 1922),
            ('Great Eastern Railway', 1862, 1922),
            ('Eastern Counties Railway', 1851, 1862),
            ('Great Central Railway', 1897, 1922),
            ('Manchester, Sheffield & Lincolnshire Railway', 1847, 1897),
            ('Metropolitan Railway', 1862, 1933),
            ('Metropolitan District Railway', 1868, 1933),
            ('Underground Electric Railways of London', 1902, 1933),
            ('London and North Western Railway', 1846, 1922),
            ('Midland Railway', 1844, 1922),
            ('Caledonian Railway', 1845, 1922),
            ('Highland Railway', 1865, 1922),
            ('North London Railway', 1850, 1922),
            ('London, Tilbury & Southend Railway', 1848, 1913),
            ('Lancashire & Yorkshire Railway', 1847, 1922),
            ('Cambrian Railway', 1864, 1922),
            ('Glasgow & South-Western Railway', 1850, 1922),
        ]
        yr = None
        try:
            yr = int(yearVal)
        except:
            yr = None
        out = []
        if yr is not None:
            for name, start, end in companies:
                try:
                    if yr < int(start):
                        continue
                    if end is not None and yr > int(end):
                        continue
                    out.append(name)
                except:
                    continue
        if yr is None:
            out = [c[0] for c in companies]
        try:
            def _Key(nm):
                for name, start, end in companies:
                    if name == nm:
                        try:
                            return (int(start), str(name).lower())
                        except:
                            return (9999, str(name).lower())
                return (9999, str(nm).lower())
            out.sort(key=_Key)
        except:
            pass
        out.append('Other...')
        return ['Select...'] + out

    def _RegionOptionsForCompany(self, companyName):
        nm = ''
        try:
            nm = str(companyName).strip()
        except:
            nm = ''
        regions = []
        if nm in ['British Railways', 'British Rail']:
            regions = ['Scottish Region', 'Southern Region', 'Midland Region', 'Western Region', 'Eastern Region']
        elif nm == 'Southern Railway':
            regions = ['Western Division', 'Central Division', 'Eastern Division']
        elif nm in ['London Transport', 'Transport for London']:
            y = None
            try:
                y = int(self.LayoutYear) if self.LayoutYear is not None else None
            except:
                y = None
            if y is None:
                y = 2000
            y = None
            try:
                y = int(self.LayoutYear) if self.LayoutYear is not None else None
            except:
                y = None
            if y is None:
                y = 2000
            regions = []
            # Sub-surface lines
            regions.append('District line')
            regions.append('Metropolitan line')
            # The Circle line name was used officially from 1936; before then it was referred to as the Inner Circle.
            if y < 1936:
                regions.append('Inner Circle')
            else:
                regions.append('Circle line')
            # The East London line was part of London Underground from 1933, but closed for transition to Overground in 2007
            if y >= 1933 and y < 2008:
                regions.append('East London line')
            # The Hammersmith & City line was redesignated as a separate line on 30 July 1990.
            if y >= 1990:
                regions.append('Hammersmith & City line')
            # Deep-level lines
            regions.append('Bakerloo line')
            regions.append('Central line')
            regions.append('Northern line')
            regions.append('Piccadilly line')
            if y >= 1968:
                regions.append('Victoria line')
            if y >= 1979:
                regions.append('Jubilee line')
            if y >= 1994:
                regions.append('Waterloo & City line')
            # Sub-surface lines
            regions.append('District line')
            regions.append('Metropolitan line')
            if y < 1936:
                regions.append('Inner Circle')
            else:
                regions.append('Circle line')
            # The Hammersmith & City line was redesignated as a separate line on 30 July 1990.
            if y >= 1990:
                regions.append('Hammersmith & City line')
            # Deep-level lines
            regions.append('Bakerloo line')
            regions.append('Central line')
            regions.append('Northern line')
            regions.append('Piccadilly line')
            if y >= 1968:
                regions.append('Victoria line')
            if y >= 1979:
                regions.append('Jubilee line')
            if y >= 1994:
                regions.append('Waterloo & City line')
        regions.append('Other...')
        return ['Select...'] + regions

    def _SetComboItems(self, combo, items):
        try:
            combo.setModel(DefaultComboBoxModel(items))
        except:
            try:
                combo.removeAllItems()
                for it in items:
                    combo.addItem(it)
            except:
                pass
    def _FindItemCaseInsensitive(self, items, value):
        try:
            v = str(value).strip().lower()
        except:
            v = ''
        if v == '':
            return None
        try:
            for it in items:
                try:
                    if str(it).strip().lower() == v:
                        return it
                except:
                    pass
        except:
            pass
        return None



    def _RefreshCompanyOptionsForYear(self):
    # Rebuild the company list based on self.LayoutYear.
    # The wizard builds all panels up-front, so refresh when Step 4 sets the year.
        try:
            if self.CompanyCombo is None:
                return
        except:
            return

        try:
            items = self._CompanyOptionsForYear(self.LayoutYear)
        except:
            items = ['Select...', 'Other...']

        curSel = ''
        try:
            sel = self.CompanyCombo.getSelectedItem()
            curSel = '' if sel is None else str(sel).strip()
        except:
            curSel = ''

        try:
            memCompany = TBL.SafeGetMemoryValue('RAILWAYCO', '').strip()
        except:
            memCompany = ''
        # Treat blank company as Network Rail from 2002 onward (Network Rail does not appear on printed timetables).
        try:
            yr = int(self.LayoutYear) if self.LayoutYear is not None else None
        except:
            yr = None
        if memCompany == '' and yr is not None and yr >= 2002:
            memCompany = 'Network Rail'
        try:
            memRegion = TBL.SafeGetOrCreateMemoryValue('REGION', '').strip()
        except:
            memRegion = ''

        self._SetComboItems(self.CompanyCombo, items)

        chosen = ''
        if curSel != '' and curSel in items and curSel != 'Select...':
            chosen = curSel
        elif memCompany != '':
            ci = self._FindItemCaseInsensitive(items, memCompany)
            if ci is not None:
                chosen = ci

        if chosen != '':
            try:
                self.CompanyCombo.setSelectedItem(chosen)
            except:
                pass
        elif memCompany != '':
            try:
                self.CompanyCombo.setSelectedItem('Other...')
            except:
                pass
            try:
                if self.CompanyOtherField is not None:
                    self.CompanyOtherField.setText(memCompany)
                    self.CompanyOtherField.setEnabled(True)
            except:
                pass
            try:
                if self.CompanyOtherLabel is not None:
                    self.CompanyOtherLabel.setEnabled(True)
            except:
                pass
        else:
            try:
                self.CompanyCombo.setSelectedItem('Select...')
            except:
                pass

        try:
            self._OnCompanyChanged()
        except:
            pass

        try:
            if self.RegionCombo is not None and memRegion != '':
                found = False
                for i in range(self.RegionCombo.getItemCount()):
                    it = str(self.RegionCombo.getItemAt(i))
                    if str(it).strip().lower() == str(memRegion).strip().lower():
                        self.RegionCombo.setSelectedItem(it)
                        found = True
                        break
                if not found:
                    self.RegionCombo.setSelectedItem('Other...')
                    if self.RegionOtherField is not None:
                        self.RegionOtherField.setEnabled(True)
                        self.RegionOtherField.setText(memRegion)
                    if self.RegionOtherLabel is not None:
                        self.RegionOtherLabel.setEnabled(True)
        except:
            pass

    def _OnCompanyChanged(self):
        try:
            if self.CompanyCombo is None:
                return
        except:
            return
        try:
            sel = self.CompanyCombo.getSelectedItem()
        except:
            sel = None
        s = '' if sel is None else str(sel)
        isOther = (s == 'Other...')
        isPrompt = (s == 'Select...')
        try:
            if self.RegionLabel is not None:
                if s in ['London Transport', 'Transport for London']:
                    self.RegionLabel.setText('Line:')
                else:
                    self.RegionLabel.setText('Region/division:')
        except:
            pass
        try:
            if self.CompanyOtherField is not None:
                self.CompanyOtherField.setEnabled(isOther)
                if self.CompanyOtherLabel is not None:
                    self.CompanyOtherLabel.setEnabled(isOther)
        except:
            pass
        try:
            if self.RegionCombo is not None:
                self.RegionCombo.setEnabled(not isPrompt)
        except:
            pass
        try:
            if self.RegionCombo is not None:
                items = self._RegionOptionsForCompany(s)
                self._SetComboItems(self.RegionCombo, items)
                try:
                    self.RegionCombo.setSelectedItem('Select...')
                except:
                    pass
        except:
            pass
        try:
            if self.RegionOtherField is not None:
                self.RegionOtherField.setEnabled(False)
                if self.RegionOtherLabel is not None:
                    self.RegionOtherLabel.setEnabled(False)
        except:
            pass

    def _OnRegionChanged(self):
        try:
            if self.RegionCombo is None:
                return
        except:
            return
        try:
            sel = self.RegionCombo.getSelectedItem()
        except:
            sel = None
        s = '' if sel is None else str(sel)
        isOther = (s == 'Other...')
        try:
            if self.RegionOtherField is not None:
                self.RegionOtherField.setEnabled(isOther)
                if self.RegionOtherLabel is not None:
                    self.RegionOtherLabel.setEnabled(isOther)
        except:
            pass

    def _GetStep5CompanyValue(self):
        try:
            if self.CompanyCombo is None:
                return ''
            sel = self.CompanyCombo.getSelectedItem()
            s = '' if sel is None else str(sel).strip()
            if s == 'Other...':
                try:
                    return str(self.CompanyOtherField.getText()).strip()
                except:
                    return ''
            if s == 'Select...':
                return ''
            if s == 'Network Rail':
                return ''
            return s
        except:
            return ''

    def _GetStep5RegionValue(self):
        try:
            if self.RegionCombo is None:
                return ''
            sel = self.RegionCombo.getSelectedItem()
            s = '' if sel is None else str(sel).strip()
            if s == 'Other...':
                try:
                    return str(self.RegionOtherField.getText()).strip()
                except:
                    return ''
            if s == 'Select...':
                return ''
            return s
        except:
            return ''

    def _ApplyRailwayDetailsFromStep5(self):
    # Set RAILWAYCO, REGION, SECTION to match TASSetup.py.
    # If the user selects 'Other...', allow the free-text field to be blank.

    # Company selection
        try:
            sel = self.CompanyCombo.getSelectedItem() if self.CompanyCombo is not None else None
        except:
            sel = None
        selStr = '' if sel is None else str(sel).strip()
        if selStr == '' or selStr == 'Select...':
            try:
                JOptionPane.showMessageDialog(self, 'Please select a railway company (or choose Other...).', 'Railway details', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return False

        if selStr == 'Other...':
            try:
                company = '' if self.CompanyOtherField is None else str(self.CompanyOtherField.getText()).strip()
            except:
                company = ''
        else:
            company = selStr
            if selStr == 'Network Rail':
                company = ''
            # Region selection
            # Region/division is optional: if the user does not select anything, treat it as blank.
        try:
            rsel = self.RegionCombo.getSelectedItem() if self.RegionCombo is not None else None
        except:
            rsel = None
        rselStr = '' if rsel is None else str(rsel).strip()
        if rselStr == 'Other...':
            try:
                region = '' if self.RegionOtherField is None else str(self.RegionOtherField.getText()).strip()
            except:
                region = ''
        elif rselStr == '' or rselStr == 'Select...':
            region = ''
        else:
            region = rselStr

            # Section (blank -> default)
        try:
            section = ''
            if self.SectionField is not None:
                section = str(self.SectionField.getText()).strip()
        except:
            section = ''
        if section == '':
            section = 'SECTION B'

        try:
            TBL.SafeSetMemoryValue('RAILWAYCO', '' if company is None else str(company).upper())
            TBL.SafeSetMemoryValue('REGION', '' if region is None else str(region).upper())
            TBL.SafeSetMemoryValue('SECTION', section)
        except Exception as ex:
            LogInfo('Failed to set railway details: ' + str(ex))
            try:
                JOptionPane.showMessageDialog(self, 'Could not save railway details.\\n\\nDetails: ' + str(ex), 'Railway details', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return False
        return True



    def _Norm(self, s):
        try:
            return str(s).strip()
        except:
            return ''

    def _NormLower(self, s):
        try:
            return str(s).strip().lower()
        except:
            return ''

    def _SetBoolMem(self, memName, val):
        try:
            TBL.SafeSetMemoryValue(memName, 'true' if bool(val) else 'false')
        except:
            pass

    def _SetStrMem(self, memName, val):
        try:
            TBL.SafeSetMemoryValue(memName, '' if val is None else str(val))
        except:
            pass

    def _WeatherAccuracyForYear(self, yr):
    # Forecast reliability (%) defaults.
    # These are approximate values intended to reflect the broad historic improvements
    # in observational networks and numerical weather prediction.
    # Please update these values if better research becomes available.
    # Bins are 30-year chunks spanning 1800-2025.
        try:
            y = int(yr)
        except:
            y = 2000

            # 1800-1829: essentially no operational public forecasting.
        if y <= 1829:
            return 40
            # 1830-1859: early instrument-based local rules.
        if y <= 1859:
            return 50
            # 1860-1889: telegraph-era observation networks; early storm warnings.
        if y <= 1889:
            return 60
            # 1890-1919: expanding synoptic practice.
        if y <= 1919:
            return 65
            # 1920-1949: improved observations; still pre-computer guidance.
        if y <= 1949:
            return 70
            # 1950-1979: first operational numerical weather prediction and satellites.
        if y <= 1979:
            return 80
            # 1980-2009: modern NWP era; major skill gains.
        if y <= 2009:
            return 90
            # 2010-date: current-era guidance (including ensemble use and high resolution).
        return 95
 
    def _ApplyDefaultsFromStep6(self): 
    # Apply defaults based on the user's selections from Step 4 (year) and Step 5 (railway details). 
    # The user can opt out per category using the tick boxes on Step 6. 

        def _IsChecked(chk, defaultVal): 
            try: 
                if chk is None: 
                    return bool(defaultVal) 
                return bool(chk.isSelected()) 
            except: 
                return bool(defaultVal) 

                # Backward compatibility: if the legacy single checkbox exists and is unticked, skip everything. 
        if not _IsChecked(getattr(self, 'ApplyDefaultsCheck', None), True): 
            return True 

        applyAppearance = _IsChecked(getattr(self, 'ApplyDefaultsAppearanceCheck', None), True) 
        applyPublic = _IsChecked(getattr(self, 'ApplyDefaultsPublicDisplaysCheck', None), True) 
        applySignallers = _IsChecked(getattr(self, 'ApplyDefaultsSignallersDisplaysCheck', None), True) 
        applyWeather = _IsChecked(getattr(self, 'ApplyDefaultsWeatherForecastingCheck', None), True) 

        if (not applyAppearance) and (not applyPublic) and (not applySignallers) and (not applyWeather): 
            return True 

            # Gather year and selected company/region for branching. 
        try: 
            year = int(self.LayoutYear) if self.LayoutYear is not None else 2000 
        except: 
            year = 2000 

        try: 
            companySel = self.CompanyCombo.getSelectedItem() if self.CompanyCombo is not None else None 
        except: 
            companySel = None 
        companySelStr = self._Norm(companySel) 

        try: 
            regionSel = self.RegionCombo.getSelectedItem() if self.RegionCombo is not None else None 
        except: 
            regionSel = None 
        regionSelStr = self._Norm(regionSel) 

        regionLower = self._NormLower(regionSelStr) 
        # Added: derive actual company value (handles 'Other...' free text) and lower-case for matching
        try:
            _companyActual = self._GetStep5CompanyValue()
        except:
            _companyActual = companySelStr
        companyLower = self._NormLower(_companyActual)
        # Treat blank company as Network Rail from 2002 onward (Network Rail does not appear on printed timetables).
        if companyLower == '' and year >= 2002:
            companyLower = 'network rail'


        # ----------------------------- 
        # Weather forecasting defaults 
        # ----------------------------- 
        if applyWeather: 
        # Forecast type: 
        # - before 1962: old newspaper 
        # - 1963-2010: new newspaper 
        # - 2010 and later: mobile app 
            if year <= 1962: 
                self._SetStrMem('WX_UI', 'Newspaper') 
                self._SetStrMem('WX_NEWS_STYLE', 'Old') 
            elif year <= 2010: 
                self._SetStrMem('WX_UI', 'Newspaper') 
                self._SetStrMem('WX_NEWS_STYLE', 'Modern') 
            else: 
                self._SetStrMem('WX_UI', 'App') 

                # Forecast reliability (%) 
            self._SetStrMem('WX_FORECAST_ACCURACY', str(self._WeatherAccuracyForYear(year))) 

            # ----------------------------- 
            # Timetable appearance defaults 
            # (includes the main menu and TASSetup) 
            # ----------------------------- 
        if applyAppearance: 
        # WTT display defaults 
        # Use 24 hour time: checked if 1964 or later, unchecked if 1963 or earlier. 
            self._SetBoolMem('WTT_TIME_24H', year >= 1964) 

            # Time separator: space if 1923 or later, '.' if 1922 or earlier. 
            self._SetStrMem('WTT_TIME_SEPARATOR', ' ' if year >= 1923 else '.') 

            # Reporting number row name defaults by railway company. 
            # NOTE: Blank means use the WTTDisplay default. 
            repNoLabel = None 
            if companyLower == 'british rail': 
                repNoLabel = '' 
            elif companyLower == 'railtrack': 
                repNoLabel = 'Train ID' 
            elif companyLower == 'network rail': 
                repNoLabel = 'Signal ID' 
            elif companyLower == 'london transport': 
                repNoLabel = 'Train no.' 
            elif companyLower == 'transport for london': 
                repNoLabel = '' 
            elif companyLower == 'british railways': 
                repNoLabel = 'Rep. no.' 
            elif companyLower == 'london & north eastern railway': 
                repNoLabel = 'No.' 
            if repNoLabel is not None: 
                self._SetStrMem('WTT_REP_NO_LABEL', repNoLabel) 

                # Timing load label defaults. 
                # Please update these values if further research indicates different historic conventions. 
            timingLoadLabel = None 
            if companyLower in ['british rail', 'railtrack', 'network rail']: 
                timingLoadLabel = 'Timing load' 
            elif companyLower in ['london transport', 'transport for london']:
                # For London Transport/TfL, REGION is treated as the Underground line.
                subsurface = set(['district line', 'metropolitan line', 'circle line', 'inner circle', 'hammersmith & city line'])
                deeplevel = set(['bakerloo line', 'central line', 'jubilee line', 'northern line', 'piccadilly line', 'victoria line', 'waterloo & city line'])
                if regionLower in subsurface:
                    timingLoadLabel = 'Make Up'
                elif regionLower in deeplevel:
                    timingLoadLabel = 'No. Cars'
                else:
                    timingLoadLabel = 'Make Up'
            elif companyLower in ['metropolitan railway']:
                timingLoadLabel = 'Make Up'
            elif companyLower in ['underground electric railways of london', 'metropolitan district railway']:
                timingLoadLabel = 'No. Cars'
            elif companyLower == 'southern railway': 
                timingLoadLabel = 'Electric Head Code' 
            elif companyLower == 'british railways' and regionLower == 'southern region': 
                timingLoadLabel = 'Electric Head Code' 
            elif companyLower == 'london & north eastern railway': 
                timingLoadLabel = 'Description.' 
            elif companyLower == 'great western railway': 
                timingLoadLabel = 'Reporting No.' 
            if timingLoadLabel is not None: 
                self._SetStrMem('WTT_TIMING_LOAD_LABEL', timingLoadLabel) 

                # Vertical headers: 
                # before 1966 if not London Transport, Metropolitan Railway, Underground Electric Railways of London, Metropolitan District Railway. 
            isUnderground = companyLower in ['london transport', 'transport for london', 'metropolitan railway', 'metropolitan district railway', 'underground electric railways of london'] 
            self._SetBoolMem('WTT_OD_HEADER_VERTICAL', (year < 1966) and (not isUnderground)) 

            # ECS label: 
            # if < 1923 or if London Transport/Transport for London/Metropolitan Railway/Metropolitan District Railway/Underground Electric Railways of London -> \"ety.\" else \"ECS\". 
            self._SetStrMem('WTT_ECS_LABEL', 'ety.' if (year < 1923 or isUnderground) else 'ECS') 

            # Page mode: 
            # - Weekdays, Saturdays, Sundays after 1960 for all 
            # - always for London Transport and Underground Electric Railways of London 
            # - otherwise Weekdays (including Saturdays), Sundays 
            if companyLower in ['london transport', 'underground electric railways of london']: 
                self._SetStrMem('WTT_PAGE_MODE', 'WEEKDAYS_SAT_SUN') 
            elif year > 1960: 
                self._SetStrMem('WTT_PAGE_MODE', 'WEEKDAYS_SAT_SUN') 
            else: 
                self._SetStrMem('WTT_PAGE_MODE', 'MONSAT_PLUS_SUN') 

                # Interface defaults (main menu + paper/ink/bands + font) 
                # NOTE: RGB values below are intended defaults and are easy to change. 
                # Please update these values if further research indicates different historic corporate styles. 
            defaultCover = '240,238,220' 
            defaultInner = '220,235,220' 
            defaultPaper = '249,246,238' 
            defaultInk = '0,0,0' 
            defaultBandLight = '255,253,247' 
            defaultBandDark = '245,242,235' 

            # New option: main menu ink colour. 
            # Stored in memory TASCOVERINKCOLOUR. 
            defaultCoverInk = '0,0,0' 

            def SetScheme(coverRgb, innerRgb, paperRgb, inkRgb, bandLightRgb, bandDarkRgb, fontFamily, coverInkRgb): 
                self._SetStrMem('TASCOVERCOLOUR', coverRgb) 
                self._SetStrMem('TASINNERCOLOUR', innerRgb) 
                self._SetStrMem('TASPAPERCOLOUR', paperRgb) 
                self._SetStrMem('TASINKCOLOUR', inkRgb) 
                self._SetStrMem('TASWTTBANDLIGHT', paperRgb)
                self._SetStrMem('TASWTTBANDDARK', paperRgb)
                if fontFamily is not None: 
                    self._SetStrMem('TAS_FONT_FAMILY', fontFamily) 
                self._SetStrMem('TASCOVERINKCOLOUR', coverInkRgb) 

                # Choose a font family default using installed-font fallback (GraphicsEnvironment).
            fontFamily = None
            fontFamilyCandidates = []
            if companyLower in ['british railways', 'london & north eastern railway']:
                fontFamilyCandidates = ['Gill Sans MT','Gill Sans','Liberation Sans','Arial','SansSerif']
            elif companyLower in ['british rail']:
                fontFamilyCandidates = ['Arial Narrow','Liberation Sans Narrow','SansSerif']
            elif companyLower in ['railtrack', 'network rail']:
                fontFamilyCandidates = ['Arial','Helvetica','Liberation Sans','SansSerif']
            elif companyLower in ['london transport', 'transport for london']:
                if year < 1955:
                    fontFamilyCandidates = ['Serif']
                else:
                # Preference cascade: Johnston 100, Railway Sans, Granby, Gill Sans MT, Arial, SansSerif
                    fontFamilyCandidates = ['Johnston 100','Railway Sans','Granby','Gill Sans MT','Arial','SansSerif']
            else:
                if year < 1948:
                    fontFamilyCandidates = ['Serif']
                else:
                    fontFamilyCandidates = ['Gill Sans MT','Gill Sans','Arial','SansSerif']
            try:
                fallbackName = fontFamilyCandidates[0] if len(fontFamilyCandidates)>0 else 'SansSerif'
            except:
                fallbackName = 'SansSerif'
            fontFamily = _FirstInstalledFont(fontFamilyCandidates, fallbackName)
            
            if year < 1948:
                defaultInner = '249,246,238'
            
            if companyLower == 'british railways': 
                SetScheme(defaultCover, defaultInner, defaultPaper, defaultInk, defaultBandLight, defaultBandLight, fontFamily, defaultCoverInk) 
            elif companyLower == 'british rail': 
                brRed = '165,50,60' 
                SetScheme(brRed, brRed, defaultPaper, defaultInk, defaultBandLight, defaultBandDark, fontFamily, defaultCoverInk) 
            elif companyLower == 'railtrack': 
                railtrackBg = '60,10,25' 
                SetScheme(railtrackBg, railtrackBg, '255,255,255', defaultInk, defaultBandLight, defaultBandDark, fontFamily, '255,255,255') 
            elif companyLower == 'network rail': 
                SetScheme('220,220,220', '255,255,255', '255,255,255', defaultInk, defaultBandLight, defaultBandDark, fontFamily, '0,0,0') 
            elif companyLower in ['london transport', 'transport for london']: 
                coverRgb = defaultPaper 
                coverInk = '0,0,0' 
                if year >= 1977 and year <= 2000: 
                    coverRgb = '255,255,255' 
                    # Choose cover text colour based on the selected London Underground line (region/division).
                    coverInk = '200,0,0'
                    try:
                        lineInk = {
                            'bakerloo line': '178,99,0',
                            'central line': '220,36,31',
                            'inner circle': '0,0,0',
                            'circle line': '0,0,0',
                            'district line': '0,125,50',
                            'hammersmith & city line': '245,137,166',
                            'jubilee line': '131,141,147',
                            'metropolitan line': '155,0,88',
                            'northern line': '0,0,0',
                            'piccadilly line': '0,25,168',
                            'victoria line': '3,155,229',
                            'waterloo & city line': '118,208,189',
                            'east london line': '255,163,0',
                        }
                        # East London line: before 1990 it used Metropolitan line colour on maps; from 1990 it was changed to orange.
                        if regionLower == 'east london line':
                            if year < 1990:
                                coverInk = '155,0,88'
                            else:
                                coverInk = '255,163,0'
                        if regionLower in lineInk:
                            coverInk = lineInk.get(regionLower)
                    except:
                        pass
                elif year > 2000: 
                    coverRgb = '255,255,255' 
                    coverInk = '0,0,0' 
                innerRgb = defaultPaper
                paperRgb = defaultPaper
                if str(coverRgb).strip() == '255,255,255':
                    innerRgb = '255,255,255'
                    paperRgb = '255,255,255'
                SetScheme(coverRgb, innerRgb, paperRgb, defaultInk, defaultBandLight, defaultBandLight, fontFamily, coverInk)
            else: 
                SetScheme(defaultPaper, defaultInner, defaultPaper, defaultInk, defaultBandLight, defaultBandLight, fontFamily, defaultCoverInk)
                try: 
                    self._SetStrMem('TAS_FONT_FAMILY', fontFamily) 
                except: 
                    pass 
                self._SetStrMem('TASCOVERINKCOLOUR', defaultCoverInk) 

                # ----------------------------- 
                # Ensure no banding by default (unconditional in wizard): set dark equal to light
        try:
            _light = str(TBL.SafeGetOrCreateMemoryValue('TASWTTBANDLIGHT', '255,253,247')).strip()
        except:
            _light = '255,253,247'
        self._SetStrMem('TASWTTBANDDARK', _light)

        # Paper colour policy overrides:
        # - TfL always white
        # - London Transport white from 1977
        # - Always white after 2002 irrespective of company
        # ----------------------------- 
        if companyLower == 'transport for london' or ((companyLower == 'london transport') and (year >= 1977)) or year >= 2002:
            self._SetStrMem('TASPAPERCOLOUR', '255,255,255')       
            self._SetStrMem('TASWTTBANDLIGHT', '255,255,255')
            self._SetStrMem('TASWTTBANDDARK', '255,255,255')
        
            # ----------------------------- 
            # Signallers' display defaults
            # ----------------------------- 
        if applySignallers: 
            sigScript = 'NotebookDisruption.py' 
            if year >= 1989: 
                sigScript = 'TRUST-TRJA.py' 
            elif year >= 1964: 
                sigScript = 'TeleprinterDisruption.py' 
            self._SetStrMem('SIGNALLERDISPLAYLIST', sigScript) 
            
            # ----------------------------- 
            # Public information display defaults 
            # ----------------------------- 
        if applyPublic: 
            pidScripts = [] 
            if companyLower in ['london transport', 'transport for london']: 
                if year >= 1985: 
                    pidScripts = ['PIDUndergroundLED.py'] 
                else: 
                    if regionLower == 'district line':
                        pidScripts = ['PIDLightboxSingleArrow.py']
                    else:
                        pidScripts = ['PIDLightboxSingle.py']
            else: 
                if year >= 2005: 
                    pidScripts = ['PIDSmall.py'] 
                elif year >= 1995: 
                    pidScripts = ['PIDCRTPlatformSingleColour.py', 'PIDCRTPlatformSummaryColour.py'] 
                elif year >= 1985: 
                    pidScripts = ['PIDCRTSingle.py', 'PIDCRTSummary.py'] 
                elif year >= 1975: 
                    pidScripts = ['PIDSolariSingle.py'] 
                elif year >= 1966: 
                    pidScripts = ['PIDFingerboardBR.py'] 
                elif year >= 1925: 
                    pidScripts = ['PIDRotorSingle.py'] 
                else: 
                    pidScripts = ['PIDFingerboard.py'] 
            self._SetStrMem('PUBLICDISPLAYLIST', ','.join(pidScripts)) 

        return True 


    def _GetAutoWorkingEnabled(self):
    # Mirror TASSetup.py: IMTASAutoWorking = 'TASAUTOWORKING'
        try:
            v = TBL.SafeGetOrCreateMemoryValue('TASAUTOWORKING', '')
        except:
            v = ''
        try:
            if isinstance(v, bool):
                return bool(v)
        except:
            pass
        try:
            t = str(v).strip().lower()
        except:
            t = ''
        if t in ['1', 'true', 'yes', 'y', 'on', 'enabled']:
            return True
        if t in ['0', 'false', 'no', 'n', 'off', 'disabled']:
            return False
        return False

    def _SetAutoWorkingEnabled(self, enabled):
        try:
            TBL.SafeSetMemoryValue('TASAUTOWORKING', 'true' if bool(enabled) else 'false')
        except:
            pass

    def _IsSelectedSafe(self, chk):
        try:
            return (chk is not None) and bool(chk.isSelected())
        except:
            return False
    def _BuildStep2aText(self):
    # Step 2a text is independent of the other 'Before you start' substeps.
        lines = []
        lines.append('Before you can use the Timetable Automation System, you need to have created a timetable.')
        lines.append('')
        lines.append('Find out more about how to create a timetable from the Timetable Automation System help.')
        lines.append('')
        lines.append('If you have already created your timetable, click Forward. Otherwise, cancel this wizard and restart when you are ready.')
        return '\n'.join(lines)

    def _RefreshStep2aText(self):
        try:
            if self.Step2aTextArea is None:
                return
            self.Step2aTextArea.setText(self._BuildStep2aText())
            try:
                self.Step2aTextArea.setCaretPosition(0)
            except:
                pass
        except:
            pass

    def _UpdateFeatureCache(self):
    # Cache the user's selections within the wizard only.
    # Automatic running is driven by TASAUTOWORKING (same as TASSetup.py).
        useAuto = False
        try:
            useAuto = self._GetAutoWorkingEnabled()
        except:
            useAuto = self._IsSelectedSafe(getattr(self, 'UseAutoTrainsCheck', None))
            # Keep the checkbox in sync in case TASAUTOWORKING was changed elsewhere while the wizard is open.
        try:
            if self.UseAutoTrainsCheck is not None:
                self.SuppressAutoTrainsListener = True
                try:
                    self.UseAutoTrainsCheck.setSelected(bool(useAuto))
                except:
                    pass
                self.SuppressAutoTrainsListener = False
        except:
            try:
                self.SuppressAutoTrainsListener = False
            except:
                pass

        useLight = False
        try:
            useLight = bool(self._GetDayNightEnabled())
        except:
            useLight = self._IsSelectedSafe(getattr(self, 'UseLightingCheck', None))
            # Keep the checkbox in sync in case DayNight.py start-up was changed elsewhere while the wizard is open.
        try:
            if self.UseLightingCheck is not None:
                self.SuppressLightingListener = True
                try:
                    self.UseLightingCheck.setSelected(bool(useLight))
                except:
                    pass
                self.SuppressLightingListener = False
        except:
            try:
                self.SuppressLightingListener = False
            except:
                pass
        useOrient = False
        try:
            useOrient = bool(self._GetOrientationSensingEnabled())
        except:
            useOrient = self._IsSelectedSafe(getattr(self, 'UseOrientationCheck', None))
            # Keep the checkbox in sync in case LastReportedDirection.py start-up was changed elsewhere while the wizard is open.
        try:
            if self.UseOrientationCheck is not None:
                self.SuppressOrientationListener = True
                try:
                    self.UseOrientationCheck.setSelected(bool(useOrient))
                except:
                    pass
                self.SuppressOrientationListener = False
        except:
            try:
                self.SuppressOrientationListener = False
            except:
                pass

                # Orientation sensing is meaningful only with automatic running.
        if not useAuto:
            useOrient = False
            try:
                if self.UseOrientationCheck is not None:
                    try:
                        self.UseOrientationCheck.setSelected(self._GetOrientationSensingEnabled())
                    except:
                        self.SuppressOrientationListener = True
                        try:
                            self.UseOrientationCheck.setSelected(False)
                        except:
                            pass
                        self.SuppressOrientationListener = False
            except:
                pass

        self.UseAutoTrainsSelected = bool(useAuto)
        self.UseOrientationSelected = bool(useOrient)
        self.UseLightingSelected = bool(useLight)

    def _RefreshStep2bUi(self):
        self._UpdateFeatureCache()
        if self.UseAutoTrainsSelected:
            txt = []
            txt.append('Before you continue, you will need to make sure that you can already run individual trains automatically using the Dispatcher.')
            txt.append('')
            txt.append('For more information on how to set up your layout to do this, see the JMRI Dispatcher documentation.')
            txt.append('')
            txt.append('If you have already set this up, click "Forward" to continue, or else cancel the wizard and set up your layout before continuing.')
            try:
                if self.Step2bExtraTextArea is not None:
                    self.Step2bExtraTextArea.setText('\n'.join(txt))
            except:
                pass
            try:
                if self.Step2bExtraTextArea is not None:
                    self.Step2bExtraTextArea.setCaretPosition(0)
            except:
                pass

            try:
                if self.DispatcherHelpButton is not None:
                    self.DispatcherHelpButton.setVisible(True)
            except:
                pass
        else:
        # Keep space reserved; just clear the text.
            try:
                if self.Step2bExtraTextArea is not None:
                    self.Step2bExtraTextArea.setText('')
            except:
                pass
            try:
                if self.DispatcherHelpButton is not None:
                    self.DispatcherHelpButton.setVisible(False)
            except:
                pass
    def _GetLightingDccAddressSet(self):
        # Return a set of DCC addresses (as normalized strings) used by the layout lighting decoders.
        addrs = set([])
        for memName in ['LOWCTTHROTTLEADDR', 'HIGHCTTHROTTLEADDR']:
            try:
                raw = str(TBL.SafeGetOrCreateMemoryValue(memName, '')).strip()
            except:
                raw = ''
            if raw is None:
                raw = ''
            raw = str(raw).strip()
            if raw != '' and raw.isdigit():
                try:
                    addrs.add(str(int(raw)))
                except:
                    try:
                        addrs.add(raw.lstrip('0') or '0')
                    except:
                        pass
        return addrs

    def _ListRosterIds(self):
        try:
            out = []
            lightingAddrs = set([])
            try:
                lightingAddrs = self._GetLightingDccAddressSet()
            except:
                lightingAddrs = set([])
            import jmri.jmrit.roster as JR
            roster = JR.Roster.getDefault()
            if roster is None:
                return out
            entries = roster.matchingList(None, None, None, None, None, None, None)
            seq = entries.toArray() if hasattr(entries, 'toArray') else list(entries)
            for re in seq:
                try:
                    rid = re.getId()
                    if rid is None:
                        continue
                    ridStr = str(rid)
                    addrStr = ''
                    try:
                        if hasattr(re, 'getDccAddress'):
                            addrStr = str(re.getDccAddress())
                    except:
                        addrStr = ''
                    if addrStr is None:
                        addrStr = ''
                    addrStr = str(addrStr).strip()
                    addrNorm = addrStr
                    if addrStr != '' and addrStr.isdigit():
                        try:
                            addrNorm = str(int(addrStr))
                        except:
                            addrNorm = addrStr.lstrip('0') or '0'
                    # Filter out the layout lighting decoders (warm/cool) by DCC address.
                    if addrNorm != '' and addrNorm in lightingAddrs:
                        continue
                    out.append(ridStr)
                except:
                    pass
            return out
        except:
            return []

    def _NormalDirectionRegisterSetLower(self):
    # Return a set of roster IDs that have a hardware orientation setting.
    # This uses NormalDirectionRegister only (matches HardwareDirectionConfig.py).
        out = set([])
        try:
            import NormalDirectionRegister as NDR
            d = None
            try:
                d = NDR.GetCopy()
            except:
                d = None
            if d is None:
                return out
            for k in d.keys():
                try:
                    out.add(str(k).strip().lower())
                except:
                    pass
        except Exception as ex:
            try:
                LogWarn('NormalDirectionRegister not available: ' + str(ex))
            except:
                pass
        return out

    def _GetRosterIdsWithoutNormalDirectionRegister(self):
    # Compare roster IDs to NormalDirectionRegister (case-insensitive).
        try:
            rosterIds = self._ListRosterIds()
        except:
            rosterIds = []
        try:
            reg = self._NormalDirectionRegisterSetLower()
        except:
            reg = set([])
        out = []
        for rid in (rosterIds or []):
            try:
                if str(rid).strip().lower() not in reg:
                    out.append(rid)
            except:
                pass
        return out

    def _HasRosterIdsWithoutNormalDirectionRegister(self):
        try:
            return len(self._GetRosterIdsWithoutNormalDirectionRegister()) > 0
        except:
            return False


    def _RefreshStep2cUi(self):
        self._UpdateFeatureCache()
        if self.UseOrientationSelected:
            txt = []
            txt.append('To proceed with setting up automatic orientation sensing, you will need to have configured compatible hardware to work with the Timetable Automation System.')
            txt.append('')
            txt.append('See the Timetable Automation System help for more information on what hardware is compatible and how to configure it.')
            txt.append('')
            txt.append('You can set up orientation sensing later if your hardware is not configured now.')
            try:
                if self.Step2cExtraTextArea is not None:
                    self.Step2cExtraTextArea.setText('\n'.join(txt))
            except:
                pass
            try:
                if self.Step2cExtraTextArea is not None:
                    self.Step2cExtraTextArea.setCaretPosition(0)
            except:
                pass
        else:
        # Keep space reserved; just clear the text.
            try:
                if self.Step2cExtraTextArea is not None:
                    self.Step2cExtraTextArea.setText('')
            except:
                pass

    def _RefreshStep2chUi(self):
        self._UpdateFeatureCache()
        ids = []
        try:
            ids = self._GetRosterIdsWithoutNormalDirectionRegister()
        except:
            ids = []
        lines = []
        try:
            lines.append('Roster entries not configured for orientation sensing: %d' % int(len(ids)))
        except:
            lines.append('Roster entries not configured for orientation sensing:')
        try:
            show = ids[:20] if len(ids) > 20 else ids
            for rid in show:
                lines.append(' - ' + str(rid))
            if len(ids) > 20:
                lines.append(' ... and more')
        except:
            pass
        try:
            if self.Step2chTextArea is not None:
                self.Step2chTextArea.setText('\n'.join(lines))
                try:
                    self.Step2chTextArea.setCaretPosition(0)
                except:
                    pass
        except:
            pass


    def _RefreshStep2dUi(self):
        self._UpdateFeatureCache()
        if self.UseLightingSelected:
            txt = []
            txt.append('To proceed, you will need to have configured your day/night lighting hardware.')
            txt.append('')
            txt.append('See the Timetable Automation System help for more information on how to set that up and what hardware is compatible with the Timetable Automation System.')
            txt.append('')
            txt.append('If you have set up your hardware, click "Forward" to proceed; otherwise, cancel this wizard and run it again when you have set up your hardware.')
            try:
                if self.Step2dExtraTextArea is not None:
                    self.Step2dExtraTextArea.setText('\n'.join(txt))
            except:
                pass
            try:
                if self.Step2dExtraTextArea is not None:
                    self.Step2dExtraTextArea.setCaretPosition(0)
            except:
                pass
        else:
        # Keep space reserved; just clear the text.
            try:
                if self.Step2dExtraTextArea is not None:
                    self.Step2dExtraTextArea.setText('')
            except:
                pass

    def _TimetableDirFile(self):
        try:
            pth = FileUtil.getExternalFilename('profile:timetable')
        except:
            pth = None
        if not pth:
            return None
        try:
            return File(pth)
        except:
            return None

    def _StripCsvExt(self, name):
        try:
            s = '' if name is None else str(name).strip()
        except:
            s = ''
        if s.lower().endswith('.csv'):
            return s[:-4]
        return s

    def _GetCurrentTimetableName(self):
        try:
            return str(TBL.SafeGetOrCreateMemoryValue('CURRENTTIMETABLE', '')).strip()
        except:
            return ''

    def _SetCurrentTimetableName(self, name):
        try:
            TBL.SafeSetMemoryValue('CURRENTTIMETABLE', '' if name is None else str(name).strip())
        except:
            pass

    def _TimetableFileExists(self, bareName):
        bn = self._StripCsvExt(bareName)
        if bn == '':
            return False
        d = self._TimetableDirFile()
        if d is None:
            return False
        try:
            f = File(d, bn + '.csv')
            return f.exists() and f.isFile()
        except:
            return False

    def _RefreshTimetableChooserUi(self):
    # Populate the chooser controls from the current timetable memory.
        try:
            if self.TimetableNameField is None:
                return
        except:
            return
        name = self._GetCurrentTimetableName()
        try:
            self.TimetableNameField.setText(name)
        except:
            pass
        try:
            if self.TimetableChosenLabel is not None:
                if name != '' and self._TimetableFileExists(name):
                    self.TimetableChosenLabel.setText('Current timetable: ' + name + '.csv')
                elif name != '':
                    self.TimetableChosenLabel.setText('Current timetable: ' + name + ' (file not found)')
                else:
                    self.TimetableChosenLabel.setText('No timetable selected yet.')
        except:
            pass

    def _ParseTimetableTimeToMinutes(self, timeStr):
    # Parse 12h/24h times to minutes since midnight. Seconds are not supported.
    # Accepts: '13:37', '1:37 PM', '01:37 pm'.
        if timeStr is None:
            return None
        try:
            s = str(timeStr).strip()
        except:
            return None
        if s == '':
            return None
        try:
            import re as _re
            s = _re.sub(r'\s+', ' ', s)
        except:
            pass
        try:
            if s.lower().endswith('h'):
                s = s[:-1].strip()
        except:
            pass
        try:
            import re as _re
            m = _re.match(r'^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*([AaPp][Mm])?$', s)
            if not m:
                return None
            hour = int(m.group(1))
            minute = int(m.group(2))
            sec = m.group(3)
            if sec is not None and str(sec).strip() != '':
                return None
            ampm = m.group(4)
            if minute < 0 or minute >= 60 or hour < 0 or hour > 24:
                return None
            if ampm:
                a = str(ampm).lower()
                hour = hour % 12
                if a == 'pm':
                    hour += 12
            else:
                if hour == 24:
                    hour = 0
            return (hour * 60) + minute
        except:
            return None

    def _ValidateTimetableFile(self, bareName):
    # Validate a timetable as described in TAS help. Only compulsory columns are required.
    # Returns (ok, message).
        try:
            bn = self._StripCsvExt(bareName)
        except:
            bn = ''
        if bn is None:
            bn = ''
        bn = str(bn).strip()
        if bn == '':
            return (False, 'No timetable selected.')
            # Reject anything that looks like a path.
        try:
            if ('/' in bn) or ('\\' in bn) or (':' in bn):
                return (False, 'Please choose a timetable from the timetable folder.')
        except:
            pass
        if not self._TimetableFileExists(bn):
            return (False, 'The selected timetable file could not be found in the timetable folder: ' + bn + '.csv')
        try:
            import csv as _csv
            from java.io import File as _JFile
            d = self._TimetableDirFile()
            if d is None:
                return (False, 'Timetable folder is not available.')
            fp = _JFile(d, bn + '.csv')
            try:
                pth = fp.getPath()
            except:
                pth = None
            if not pth:
                return (False, 'Timetable file path could not be resolved.')
            f = open(str(pth), 'r')
            try:
                reader = _csv.DictReader(f, delimiter='\t')
                header = reader.fieldnames or []
                if header is None or len(header) == 0:
                    return (False, 'Timetable file has no header row.')
                days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
                for dcol in days:
                    if dcol not in header:
                        return (False, 'Missing compulsory column: ' + dcol)
                if 'Dep' not in header:
                    return (False, 'Missing compulsory column: Dep')
                if ('Arr' not in header) and ('Trigger' not in header):
                    return (False, 'Missing compulsory column: Arr or Trigger')
                saw = False
                rowIndex = 2
                for row in reader:
                    saw = True
                    # Each row must have at least one time in Trigger/Arr/Dep.
                    vals = []
                    for k in ['Trigger','Arr','Dep']:
                        if k in header:
                            try:
                                vals.append((row.get(k,'') or '').strip())
                            except:
                                vals.append('')
                    emptyAll = True
                    for v in vals:
                        if v != '':
                            emptyAll = False
                            break
                    if emptyAll:
                        return (False, 'Row %d: no time in Trigger/Arr/Dep.' % int(rowIndex))
                        # Validate times (seconds not supported).
                    for k in ['Trigger','Arr','Dep']:
                        if k in header:
                            v = (row.get(k,'') or '').strip()
                            if v != '':
                                if self._ParseTimetableTimeToMinutes(v) is None:
                                    return (False, 'Row %d: invalid %s time: %s.' % (int(rowIndex), str(k), str(v)))
                                    # Validate day columns contain TRUE or FALSE (case-insensitive).
                    for dcol in days:
                        dv = (row.get(dcol,'') or '').strip().lower()
                        if dv not in ['true','false','1','0','yes','no','y','n']:
                            return (False, 'Row %d: invalid day value in %s.' % (int(rowIndex), str(dcol)))
                    rowIndex += 1
                if not saw:
                    return (False, 'Timetable has no data rows.')
            finally:
                try:
                    f.close()
                except:
                    pass
        except Exception as ex:
            return (False, 'Error reading timetable: ' + str(ex))
        return (True, '')

    def _RefreshStep2bttUi(self, showErrorDialog=False):
    # Validate the currently selected timetable and gate the Forward button on the chooser step.
        try:
            if self.TimetableNameField is None:
                return False
        except:
            return False
        try:
            name = self._StripCsvExt(self.TimetableNameField.getText())
        except:
            name = ''
        if name is None:
            name = ''
        name = str(name).strip()
        if name == '':
            try:
                if self.TimetableChosenLabel is not None:
                    self.TimetableChosenLabel.setText('No timetable selected yet.')
            except:
                pass
            try:
                if self.Steps[int(self.StepIndex)] == 'step2btt':
                    self.BtnForward.setEnabled(False)
            except:
                pass
            return False
        ok = False
        msg = ''
        try:
            ok, msg = self._ValidateTimetableFile(name)
        except Exception as ex:
            ok = False
            msg = 'Error reading timetable: ' + str(ex)
        if not ok:
            try:
                if self.TimetableChosenLabel is not None:
                    self.TimetableChosenLabel.setText(msg)
            except:
                pass
            if showErrorDialog:
                try:
                    JOptionPane.showMessageDialog(self, msg, 'Timetable', JOptionPane.ERROR_MESSAGE)
                except:
                    pass
            try:
                if self.Steps[int(self.StepIndex)] == 'step2btt':
                    self.BtnForward.setEnabled(False)
            except:
                pass
            return False
            # Valid: show summary, save memory and enable Forward on this step.
        try:
            if self.TimetableChosenLabel is not None:
                self.TimetableChosenLabel.setText('Selected timetable: ' + name + '.csv')
        except:
            pass
        try:
            if self.Steps[int(self.StepIndex)] == 'step2btt':
                self.BtnForward.setEnabled(True)
        except:
            pass
        return True


    def _ApplyTimetableFromChooserStep(self):
    # Called when leaving the timetable chooser step.
        try:
            if self.TimetableNameField is None:
                return True
        except:
            return True
        try:
            name = self._StripCsvExt(self.TimetableNameField.getText())
        except:
            name = ''
        if name == '':
            try:
                JOptionPane.showMessageDialog(self, 'Please select a timetable before continuing.', 'Timetable', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return False
        ok = False
        msg = ''
        try:
            ok, msg = self._ValidateTimetableFile(name)
        except Exception as ex:
            ok = False
            msg = 'Error reading timetable: ' + str(ex)
        if not ok:
            try:
                JOptionPane.showMessageDialog(self, msg, 'Timetable', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return False
            # Save the bare name (without extension) like TASSetup, but only if it changed.
        try:
            cur = self._GetCurrentTimetableName()
        except:
            cur = ''
        try:
            if str(cur).strip() != str(name).strip():
                self._SetCurrentTimetableName(name)
        except:
            try:
                self._SetCurrentTimetableName(name)
            except:
                pass
        return True
    def _StartupMgr(self):
        try:
            return jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
        except:
            return None

    def _ActiveProfile(self):
        try:
            pm = jmri.profile.ProfileManager.getDefault()
            if pm is None:
                return None
            return pm.getActiveProfile()
        except:
            return None

    def _CanonLower(self, p):
        try:
            return File(str(p)).getCanonicalPath().lower()
        except:
            try:
                return str(p).lower()
            except:
                return ""

    def _MatchScriptPath(self, model, scriptFileName):
    # True iff model's script path points to profile:jython/<scriptFileName>.
        try:
            path = model.getFileName()
            if path is None:
                return False
            pcanon = self._CanonLower(str(path))
            target = self._CanonLower(ProfileJythonFilePath(scriptFileName))
            base = File(scriptFileName).getName().lower()
            if pcanon == target:
                return True
            if pcanon.endswith(File.separator + base):
                return True
            if pcanon.endswith("/" + base):
                return True
            if pcanon.endswith("\\" + base):
                return True
            return False
        except:
            return False

    def _FindPerformScriptModelFor(self, scriptFileName):
        mgr = self._StartupMgr()
        if mgr is None:
            return None
        try:
            actions = mgr.getActions()
        except:
            return None
        for m in actions:
            try:
                if not isinstance(m, jmri.util.startup.PerformScriptModel):
                    continue
                if self._MatchScriptPath(m, scriptFileName):
                    return m
            except:
                continue
        return None

    def _IsStartupScriptEnabled(self, scriptFileName):
        m = self._FindPerformScriptModelFor(scriptFileName)
        try:
            return (m is not None) and bool(m.isEnabled())
        except:
            return False

    def _EnsureStartupScriptEnabled(self, scriptFileName, enabled):
        mgr = self._StartupMgr()
        if mgr is None:
            return False
        model = self._FindPerformScriptModelFor(scriptFileName)
        if model is None and enabled:
            try:
                model = jmri.util.startup.PerformScriptModel()
                model.setFileName(ProfileJythonFilePath(scriptFileName))
                model.setEnabled(True)
                mgr.addAction(model)
            except:
                return False
        elif model is not None:
            try:
                model.setEnabled(bool(enabled))
            except:
                return False
        else:
            pass
        try:
            prof = self._ActiveProfile()
            if prof is not None:
                mgr.savePreferences(prof)
        except:
            pass
        try:
            mgr.setRestartRequired()
        except:
            pass
        return True

    def _GetDayNightEnabled(self):
        return self._IsStartupScriptEnabled("DayNight.py")

    def _SetDayNightEnabled(self, enabled):
        ok = self._EnsureStartupScriptEnabled("DayNight.py", bool(enabled))
        try:
            cur = bool(self._GetDayNightEnabled())
        except:
            cur = bool(enabled)
        try:
            self.RestartNeeded = bool(self.RestartNeeded) or (bool(self.InitialDayNightEnabled) != bool(cur))
        except:
            self.RestartNeeded = True
        return ok




    def _GetOrientationSensingEnabled(self):
        return self._IsStartupScriptEnabled('LastReportedDirection.py')

    def _SetOrientationSensingEnabled(self, enabled):
        ok = self._EnsureStartupScriptEnabled('LastReportedDirection.py', bool(enabled))
        try:
            cur = bool(self._GetOrientationSensingEnabled())
        except:
            cur = bool(enabled)
        try:
            self.RestartNeeded = bool(self.RestartNeeded) or (bool(self.InitialOrientationSensingEnabled) != bool(cur))
        except:
            self.RestartNeeded = True
        return ok

    def _ParseDccAddr(self, rawText):
    # 1..9999, max 4 digits, 0 not valid.
        try:
            s = '' if rawText is None else str(rawText).strip()
        except:
            s = ''
        if s == '':
            return None
            # Reject non-digits (allow leading/trailing spaces already stripped)
        for ch in s:
            if ch < '0' or ch > '9':
                return None
        if len(s) > 4:
            return None
        try:
            n = int(s)
        except:
            return None
        if n <= 0 or n > 9999:
            return None
        return n

    def _RefreshStep2eUi(self):
    # Populate the lighting address fields from memory.
        try:
            low = str(TBL.SafeGetOrCreateMemoryValue('LOWCTTHROTTLEADDR', '990')).strip()
        except:
            low = '990'
        try:
            high = str(TBL.SafeGetOrCreateMemoryValue('HIGHCTTHROTTLEADDR', '991')).strip()
        except:
            high = '991'
        try:
            if self.LowCtAddrField is not None:
                self.LowCtAddrField.setText(low)
        except:
            pass
        try:
            if self.HighCtAddrField is not None:
                self.HighCtAddrField.setText(high)
        except:
            pass

    def _RefreshStep2fUi(self):
    # Sync the climate and daylight preset combos from memory.
        try:
            curClimate = str(TBL.SafeGetOrCreateMemoryValue('WX_CLIMATE', 'SouthWales_EarlySep')).strip()
        except:
            curClimate = 'SouthWales_EarlySep'
        try:
            curDay = str(TBL.SafeGetOrCreateMemoryValue('DAYNIGHT_PRESET', 'Maesteg_Sep2017')).strip()
        except:
            curDay = 'Maesteg_Sep2017'
        try:
            if self.Step2fClimateCombo is not None:
                self.Step2fClimateCombo.setSelectedItem(curClimate)
        except:
            pass
        try:
            if self.Step2fDaylightCombo is not None:
                self.Step2fDaylightCombo.setSelectedItem(curDay)
        except:
            pass
            # Commit immediately on selection changes.
        try:
            if self.Step2fClimateCombo is not None:
                def _ApplyClimate():
                    try:
                        val = str(self.Step2fClimateCombo.getSelectedItem()).strip()
                        TBL.SafeSetMemoryValue('WX_CLIMATE', val)
                    except:
                        pass
                        # Avoid stacking listeners by clearing and re-adding is hard in Swing; add once guarded.
                if not hasattr(self, '_Step2fClimateHooked'):
                    self._Step2fClimateHooked = True
                    self.Step2fClimateCombo.addActionListener(lambda e: _ApplyClimate())
        except:
            pass
        try:
            if self.Step2fDaylightCombo is not None:
                def _ApplyDay():
                    try:
                        val = str(self.Step2fDaylightCombo.getSelectedItem()).strip()
                        TBL.SafeSetMemoryValue('DAYNIGHT_PRESET', val)
                    except:
                        pass
                if not hasattr(self, '_Step2fDayHooked'):
                    self._Step2fDayHooked = True
                    self.Step2fDaylightCombo.addActionListener(lambda e: _ApplyDay())
        except:
            pass

    def _ApplyLightingAddressesFromStep2e(self):
    # Validate and store lighting DCC addresses.
        try:
            lowRaw = '' if self.LowCtAddrField is None else self.LowCtAddrField.getText()
        except:
            lowRaw = ''
        try:
            highRaw = '' if self.HighCtAddrField is None else self.HighCtAddrField.getText()
        except:
            highRaw = ''
        low = self._ParseDccAddr(lowRaw)
        high = self._ParseDccAddr(highRaw)
        if low is None or high is None:
            try:
                JOptionPane.showMessageDialog(self, 'Please enter valid DCC addresses (1-9999).', 'Lighting addresses', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return False
            # Accept low==high? This is probably not useful; treat as invalid.
        try:
            if int(low) == int(high):
                JOptionPane.showMessageDialog(self, 'The warm and cool addresses must be different.', 'Lighting addresses', JOptionPane.INFORMATION_MESSAGE)
                return False
        except:
            pass
        try:
            TBL.SafeSetMemoryValue('LOWCTTHROTTLEADDR', str(int(low)))
            TBL.SafeSetMemoryValue('HIGHCTTHROTTLEADDR', str(int(high)))
        except Exception as ex:
            try:
                JOptionPane.showMessageDialog(self, 'Could not save lighting addresses.\n\nDetails: ' + str(ex), 'Lighting addresses', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return False
        return True


    def _NormLower(self, s):
        try:
            return str(s).strip().lower()
        except:
            return ""

    def _DefaultWorkingRN(self, rowNumber):
    # Header row is 1, first data row is 2.
        try:
            return "TAS" + str(int(rowNumber))
        except:
            return "TAS"

    def _CurrentTimetableCsvPath(self):
    # Returns filesystem path to CURRENTTIMETABLE.csv under profile:timetable, or None.
        try:
            name = str(TBL.SafeGetOrCreateMemoryValue("CURRENTTIMETABLE", "")).strip()
        except:
            name = ""
        if name == "":
            return None
        try:
            d = FileUtil.getExternalFilename("profile:timetable")
        except:
            d = None
        if not d:
            return None
        try:
            return os.path.join(str(d), str(name) + ".csv")
        except:
            return None

    def _DetermineWorkingDirection(self, rowDict):
    # Priority: Trigger, then Arr, then Dep.
        try:
            t = (rowDict.get("Trigger", "") or "").strip()
            if t != "":
                return "Trigger"
        except:
            pass
        try:
            t = (rowDict.get("Arr", "") or "").strip()
            if t != "":
                return "Arr"
        except:
            pass
        try:
            t = (rowDict.get("Dep", "") or "").strip()
            if t != "":
                return "Dep"
        except:
            pass
        return None

    def _WorkingScriptPath(self, direction, rn):
        try:
            scriptsPath = jmri.util.FileUtil.getScriptsPath()
        except:
            scriptsPath = None
        if not scriptsPath:
            return None
        try:
            return os.path.join(str(scriptsPath), "workings", str(direction), str(rn) + ".py")
        except:
            return None


    def _GetWorkingsStatusFromWorkingCreator(self):
    # Try to use WorkingCreator headless audit if available.
        csvPath = None
        try:
            csvPath = self._CurrentTimetableCsvPath()
        except:
            csvPath = None
        mod = None
        try:
            mod = LoadWorkingCreatorModule()
        except:
            mod = None
        if mod is None:
            return None
        try:
            if hasattr(mod, 'GetWorkingsStatusForTimetable'):
                return mod.GetWorkingsStatusForTimetable(csvPath)
        except:
            return None
        return None


    def _ReadTimetableRows(self, csvPath):
    # Read timetable file rows as list of dicts.
    # Timetable files are commonly tab-separated, but older examples may use commas.
    # Try a small set of delimiters rather than relying on csv.Sniffer (which can be unreliable with free-text fields).
        rows = []
        if csvPath is None:
            return rows
        if not os.path.isfile(csvPath):
            return rows
            # Try delimiters in order of likelihood.
        delims = ['\t', ",", ' ' ]
        for delim in delims:
            rows = []
            try:
                f = open(csvPath, 'r')
                try:
                    reader = csv.DictReader(f, delimiter=delim)
                    fieldnames = []
                    try:
                        fieldnames = list(reader.fieldnames or [])
                    except:
                        fieldnames = []
                        # We need at least these columns.
                    need = ['Reporting number', 'Forms']
                    haveNeed = True
                    for n in need:
                        if n not in fieldnames:
                            haveNeed = False
                            break
                    if not haveNeed:
                        continue
                    for r in reader:
                        rows.append(r)
                        # Delimiter accepted.
                    return rows
                finally:
                    try:
                        f.close()
                    except:
                        pass
            except:
                rows = []
        return rows

    def _ListMissingWorkings(self):
    # Returns a list of dicts: {rn, direction, rowIndex, formsNext, path}
        out = []
        csvPath = self._CurrentTimetableCsvPath()
        if csvPath is None or (not os.path.isfile(csvPath)):
            return out

        rows = self._ReadTimetableRows(csvPath)
        if rows is None:
            rows = []
        if len(rows) == 0:
            return out

            # Formation mapping: destination RN -> forming RN.
        formedBy = {}
        try:
            ridx = 2
            for r in rows:
                rnCell = (r.get("Reporting number", "") or "").strip()
                formingRN = rnCell if rnCell != "" else self._DefaultWorkingRN(ridx)
                formsCell = (r.get("Forms", "") or "").strip()
                if formsCell != "":
                    formedBy[self._NormLower(formsCell)] = formingRN
                ridx += 1
        except:
            formedBy = {}

        ridx = 2
        for r in rows:
            direction = self._DetermineWorkingDirection(r)
            rnCell = (r.get("Reporting number", "") or "").strip()
            rn = rnCell if rnCell != "" else self._DefaultWorkingRN(ridx)
            formsNext = None
            try:
                if self._NormLower(rn) in formedBy:
                    formsNext = formedBy[self._NormLower(rn)]
            except:
                formsNext = None
            pth = self._WorkingScriptPath(direction, rn)
            missing = False
            try:
                if direction is None or pth is None:
                    missing = True
                elif not os.path.isfile(pth):
                    missing = True
                else:
                    try:
                        if os.path.getsize(pth) <= 0:
                            missing = True
                    except:
                        pass
            except:
                missing = True
            if missing:
                out.append({"rn": rn, "direction": direction, "rowIndex": ridx, "formsNext": formsNext, "path": pth})
            ridx += 1
        return out



    def _ListAllWorkingsEntries(self):
    # Returns a list of dicts: {rn, direction, rowIndex, formsNext, path, exists}
        out = []
        csvPath = self._CurrentTimetableCsvPath()
        if csvPath is None or (not os.path.isfile(csvPath)):
            return out
        rows = self._ReadTimetableRows(csvPath)
        if rows is None:
            rows = []
        if len(rows) == 0:
            return out
            # Formation mapping: destination RN -> forming RN.
        formedBy = {}
        try:
            ridx = 2
            for r in rows:
                rnCell = (r.get("Reporting number", "") or "").strip()
                formingRN = rnCell if rnCell != "" else self._DefaultWorkingRN(ridx)
                formsCell = (r.get("Forms", "") or "").strip()
                if formsCell != "":
                    formedBy[self._NormLower(formsCell)] = formingRN
                ridx += 1
        except:
            formedBy = {}
        ridx = 2
        for r in rows:
            direction = self._DetermineWorkingDirection(r)
            rnCell = (r.get("Reporting number", "") or "").strip()
            rn = rnCell if rnCell != "" else self._DefaultWorkingRN(ridx)
            formsNext = None
            try:
                if self._NormLower(rn) in formedBy:
                    formsNext = formedBy[self._NormLower(rn)]
            except:
                formsNext = None
            pth = self._WorkingScriptPath(direction, rn)
            exists = False
            try:
                exists = (pth is not None) and os.path.isfile(pth) and (os.path.getsize(pth) > 0)
            except:
                exists = False
            timeVal = ''
            try:
                if direction is not None:
                    timeVal = (r.get(direction, '') or '').strip()
            except:
                timeVal = ''
            origin = ''
            destination = ''
            try:
                origin = (r.get('Origin', '') or '').strip()
            except:
                origin = ''
            try:
                destination = (r.get('Destination', '') or '').strip()
            except:
                destination = ''
            out.append({"rn": rn, "direction": direction, "rowIndex": ridx, "formsNext": formsNext, "path": pth, "exists": exists, "time": timeVal, "origin": origin, "destination": destination})
            ridx += 1
        return out

    def _RefreshStep2bwUi(self):
    # Workings validation step: only relevant when automatic running is enabled.
        try:
            self._UpdateFeatureCache()
        except:
            pass

        ok = False
        missing = []
        invalid = []

        status = None
        try:
            status = self._GetWorkingsStatusFromWorkingCreator()
        except:
            status = None

        if status is not None and isinstance(status, dict):
            try:
                ok = bool(status.get('ok', False))
            except:
                ok = False
            try:
                missing = status.get('missing', []) or []
            except:
                missing = []
            try:
                invalid = status.get('invalid', []) or []
            except:
                invalid = []
        else:
            try:
                missing = self._ListMissingWorkings()
                ok = (missing is not None) and (len(missing) == 0)
            except:
                missing = []
                ok = False

        self.WorkingsOk = bool(ok)
        try:
            self.MissingWorkings = missing
        except:
            self.MissingWorkings = []
        try:
            self.InvalidWorkings = invalid
        except:
            self.InvalidWorkings = []

        lines = []
        if ok:
            lines.append('All your workings have valid scripts.')
            lines.append('')
            lines.append('You can click Forward to continue.')
            lines.append('')
            lines.append('If you want to review or modify a working script, click the button below.')
        else:
            lines.append('Automatic running requires a script for every timetable entry to tell the system what to do at that time.')
            lines.append('')
            lines.append('You can either write them manually or create them easily using the working creator tool.')
            lines.append('')
            try:
                lines.append('Missing workings: %d' % int(len(missing)))
            except:
                lines.append('Missing workings:')
            try:
                lines.append('Invalid workings: %d' % int(len(invalid)))
            except:
                lines.append('Invalid workings:')

                # Show a short list (first 8) to avoid huge blocks.
            try:
                show = (missing + invalid)[:8]
            except:
                show = []
            for it in show:
                try:
                    lines.append('  Row %d: %s (%s)' % (int(it.get('rowIndex', 0)), str(it.get('rn', '')), str(it.get('direction', ''))))
                except:
                    pass
            try:
                if (len(missing) + len(invalid)) > 8:
                    lines.append('  ... and more')
            except:
                pass
            lines.append('')
            lines.append('Click the button below to create or edit working scripts.')

        try:
            if self.Step2bwTextArea is not None:
                self.Step2bwTextArea.setText('\n'.join(lines))
                try:
                    self.Step2bwTextArea.setCaretPosition(0)
                except:
                    pass
        except:
            pass

            # Button visible/enabled always so the user can open Working Creator even when all workings are present.
        try:
            if self.WorkingsCreateButton is not None:
                self.WorkingsCreateButton.setVisible(True)
                self.WorkingsCreateButton.setEnabled(True)
        except:
            pass

            # Gate Forward while missing.
        try:
            if self.Steps[int(self.StepIndex)] == 'step2bw':
                self.BtnForward.setEnabled(bool(ok))
        except:
            pass

    def BuildSteps(self):
        intro = (
            "Welcome to the Timetable Automation System setup wizard.\n\n"
            "This wizard will guide you through the initial configuration of the Timetable Automation System one step at a time.\n\n"
            "Use Forward and Back to move between steps, or Cancel to exit at any time."
        )
        p1 = self.MakeWizardStep("Welcome", intro)

        # Step 2a: before you start (timetable)
        p2a = MakePaperPanel()
        p2a.setLayout(BorderLayout())
        p2a.add(self._BuildSidebar(), BorderLayout.WEST)
        center2a = JPanel()
        center2a.setOpaque(False)
        center2a.setLayout(GridBagLayout())
        g2a = GridBagConstraints()
        g2a.insets = Insets(6, 12, 6, 6)
        g2a.gridx = 0
        g2a.gridy = 0
        g2a.weightx = 1.0
        g2a.weighty = 0.0
        g2a.fill = GridBagConstraints.HORIZONTAL
        center2a.add(MakeHeading('Before you start'), g2a)
        g2a.gridy = 1
        g2a.weighty = 1.0
        g2a.fill = GridBagConstraints.BOTH
        self.Step2aTextArea = MakeWrappedTextArea('', fontSize=13)
        sp2a = MakeScrollForText(self.Step2aTextArea)
        center2a.add(sp2a, g2a)
        p2a.add(center2a, BorderLayout.CENTER)


        # Step 2b: choose timetable
        p2btt = MakePaperPanel()
        p2btt.setLayout(BorderLayout())
        p2btt.add(self._BuildSidebar(), BorderLayout.WEST)
        center2btt = JPanel()
        center2btt.setOpaque(False)
        center2btt.setLayout(GridBagLayout())
        g2btt = GridBagConstraints()
        g2btt.insets = Insets(6, 12, 6, 6)
        g2btt.gridx = 0
        g2btt.gridy = 0
        g2btt.weightx = 1.0
        g2btt.weighty = 0.0
        g2btt.fill = GridBagConstraints.HORIZONTAL
        center2btt.add(MakeHeading('Choose timetable'), g2btt)

        g2btt.gridy = 1
        info2btt = (
            'Select the timetable that this layout should use.\n\n'
            'The Timetable Automation System expects timetables to be stored in a standard location inside your JMRI profile directory.'
        )
        center2btt.add(MakeWrappedTextArea(info2btt, fontSize=13), g2btt)

        g2btt.gridy = 2
        row2btt = JPanel()
        row2btt.setOpaque(False)
        row2btt.setLayout(GridBagLayout())
        rg = GridBagConstraints()
        rg.insets = Insets(0, 0, 0, 0)
        rg.gridx = 0
        rg.gridy = 0
        rg.weightx = 0.0
        rg.fill = GridBagConstraints.NONE
        row2btt.add(JLabel('Timetable:'), rg)
        rg.gridx = 1
        rg.weightx = 1.0
        rg.fill = GridBagConstraints.HORIZONTAL
        self.TimetableNameField = JTextField(28)
        ApplyTheme(self.TimetableNameField)
        row2btt.add(self.TimetableNameField, rg)
        rg.gridx = 2
        rg.weightx = 0.0
        rg.fill = GridBagConstraints.NONE
        self.TimetableBrowseButton = JButton('Browse...')
        ApplyTheme(self.TimetableBrowseButton)
        row2btt.add(self.TimetableBrowseButton, rg)
        center2btt.add(row2btt, g2btt)

        g2btt.gridy = 3
        self.TimetableChosenLabel = JLabel('')
        ApplyTheme(self.TimetableChosenLabel)
        center2btt.add(self.TimetableChosenLabel, g2btt)

        def _CommitTimetableField2btt(showErrorDialog):
            return self._RefreshStep2bttUi(bool(showErrorDialog))

        def _BrowseTimetable2btt():
            try:
                d = self._TimetableDirFile()
                if d is None or (not d.exists()) or (not d.isDirectory()):
                    JOptionPane.showMessageDialog(self, 'The timetable folder could not be found.', 'Timetable', JOptionPane.ERROR_MESSAGE)
                    return
                chooser = RestrictedCsvChooserWizard(d)
                cur = self._GetCurrentTimetableName()
                if cur != '':
                    try:
                        chooser.setSelectedFile(File(d, self._StripCsvExt(cur) + '.csv'))
                    except:
                        pass
                res = chooser.showOpenDialog(self)
                if res == JFileChooser.APPROVE_OPTION:
                    sel = chooser.getSelectedFile()
                    if sel is not None:
                        try:
                            bare = self._StripCsvExt(sel.getName())
                        except:
                            bare = ''
                        if bare != '':
                            try:
                                self.TimetableNameField.setText(bare)
                            except:
                                pass
                            _CommitTimetableField2btt(True)
            except Exception as ex:
                try:
                    JOptionPane.showMessageDialog(self, 'Timetable selection failed:\\n\\n' + str(ex), 'Timetable', JOptionPane.ERROR_MESSAGE)
                except:
                    pass

        try:
            self.TimetableBrowseButton.addActionListener(lambda e: _BrowseTimetable2btt())
        except:
            pass
        try:
            self.TimetableNameField.addActionListener(lambda e: _CommitTimetableField2btt(False))
        except:
            pass
        try:
            wiz = self
            class CommitOnTimetableFocusLost2btt(java.awt.event.FocusAdapter):
                def focusLost(self, e):
                    try:
                        wiz._RefreshStep2bttUi(False)
                    except:
                        pass
            wiz.TimetableNameField.addFocusListener(CommitOnTimetableFocusLost2btt())
        except:
            pass



            # Filler row to keep the content top-aligned (leave unused space at the bottom).
        g2btt.gridy = 4
        g2btt.weighty = 1.0
        g2btt.fill = GridBagConstraints.BOTH
        filler2btt = JPanel()
        filler2btt.setOpaque(False)
        center2btt.add(filler2btt, g2btt)

        p2btt.add(center2btt, BorderLayout.CENTER)

        # Step 2b: before you start (automatic running)
        p2b = MakePaperPanel()
        p2b.setLayout(BorderLayout())
        p2b.add(self._BuildSidebar(), BorderLayout.WEST)
        center2b = JPanel()
        center2b.setOpaque(False)
        center2b.setLayout(GridBagLayout())
        g2b = GridBagConstraints()
        g2b.insets = Insets(6, 12, 6, 6)
        g2b.gridx = 0
        g2b.gridy = 0
        g2b.weightx = 1.0
        g2b.weighty = 0.0
        g2b.fill = GridBagConstraints.HORIZONTAL
        center2b.add(MakeHeading('Automatic running'), g2b)

        g2b.gridy = 1
        info2b = (
            'The Timetable Automation System can automatically run trains from your timetable using the Dispatcher.\n\n'
            'Do you want to run trains automatically?'
        )
        center2b.add(MakeWrappedTextArea(info2b, fontSize=13), g2b)

        g2b.gridy = 2
        self.UseAutoTrainsCheck = JCheckBox('Yes - run trains automatically')
        self.UseAutoTrainsCheck.setOpaque(False)
        try:
            self.UseAutoTrainsCheck.setSelected(self._GetAutoWorkingEnabled())
        except:
            self.UseAutoTrainsCheck.setSelected(False)
        ApplyTheme(self.UseAutoTrainsCheck)
        center2b.add(self.UseAutoTrainsCheck, g2b)

        # Extra text for this step. Give it the remaining vertical space when visible.
        g2bExtra = GridBagConstraints()
        g2bExtra.insets = Insets(6, 12, 6, 6)
        g2bExtra.gridx = 0
        g2bExtra.gridy = 3
        g2bExtra.weightx = 1.0
        g2bExtra.weighty = 1.0
        g2bExtra.fill = GridBagConstraints.BOTH
        self.Step2bExtraTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2bExtraScroll = MakeScrollForText(self.Step2bExtraTextArea)
        try:
            self.Step2bExtraScroll.setVisible(True)
        except:
            pass
        center2b.add(self.Step2bExtraScroll, g2bExtra)

        def _OnAutoTrainsToggled2b():
            try:
                if not self.SuppressAutoTrainsListener:
                    try:
                        self._SetAutoWorkingEnabled(self.UseAutoTrainsCheck.isSelected())
                    except:
                        pass
            except:
                pass
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                self._RefreshStep2bUi()
            except:
                pass
            try:
                center2b.revalidate()
                center2b.repaint()
            except:
                pass

        try:
            self.UseAutoTrainsCheck.addActionListener(lambda e: _OnAutoTrainsToggled2b())
        except:
            pass


            # Button to open the JMRI DispatcherPro help.
        g2bDisp = GridBagConstraints()
        g2bDisp.insets = Insets(6, 12, 6, 6)
        g2bDisp.gridx = 0
        g2bDisp.gridy = 4
        g2bDisp.weightx = 1.0
        g2bDisp.weighty = 0.0
        g2bDisp.fill = GridBagConstraints.NONE
        g2bDisp.anchor = GridBagConstraints.WEST
        self.DispatcherHelpButton = JButton('Open JMRI DispatcherPro help')
        ApplyTheme(self.DispatcherHelpButton)
        try:
            self.DispatcherHelpButton.setVisible(False)
        except:
            pass
        center2b.add(self.DispatcherHelpButton, g2bDisp)

        def _OpenDispatcherHelp():
            try:
                jmri.util.HelpUtil.displayHelpRef('package.jmri.jmrit.dispatcher.Dispatcher')
            except Exception as ex:
                try:
                    JOptionPane.showMessageDialog(self, 'Could not open the Dispatcher help\n\nDetails: ' + str(ex), 'Dispatcher help', JOptionPane.ERROR_MESSAGE)
                except:
                    pass

        try:
            self.DispatcherHelpButton.addActionListener(lambda e: _OpenDispatcherHelp())
        except:
            pass

        g2b.gridy = 5
        g2b.weighty = 0.0
        g2b.fill = GridBagConstraints.BOTH
        filler2b = JPanel()
        filler2b.setOpaque(False)
        center2b.add(filler2b, g2b)
        p2b.add(center2b, BorderLayout.CENTER)

        # Step 2bw: working scripts check (shown only if automatic running is selected)
        p2bw = MakePaperPanel()
        p2bw.setLayout(BorderLayout())
        p2bw.add(self._BuildSidebar(), BorderLayout.WEST)
        center2bw = JPanel()
        center2bw.setOpaque(False)
        center2bw.setLayout(GridBagLayout())
        g2bw = GridBagConstraints()
        g2bw.insets = Insets(6, 12, 6, 6)
        g2bw.gridx = 0
        g2bw.gridy = 0
        g2bw.weightx = 1.0
        g2bw.weighty = 0.0
        g2bw.fill = GridBagConstraints.HORIZONTAL
        center2bw.add(MakeHeading('Workings for automatic running'), g2bw)

        g2bw.gridy = 1
        info2bw = (
            'To run trains automatically, the Timetable Automation System needs a working script for every timetable entry.\n\n'
            'This step checks whether those scripts exist in the correct location.'
        )
        center2bw.add(MakeWrappedTextArea(info2bw, fontSize=13), g2bw)

        g2bw.gridy = 2
        g2bw.weighty = 1.0
        g2bw.fill = GridBagConstraints.BOTH
        self.Step2bwTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2bwScroll = MakeScrollForText(self.Step2bwTextArea)
        center2bw.add(self.Step2bwScroll, g2bw)

        g2bw.gridy = 3
        g2bw.weighty = 0.0
        g2bw.fill = GridBagConstraints.NONE
        g2bw.anchor = GridBagConstraints.WEST
        self.WorkingsCreateButton = JButton('Create or edit workings...')
        ApplyTheme(self.WorkingsCreateButton)
        center2bw.add(self.WorkingsCreateButton, g2bw)

        def _OpenWorkingCreatorForNextMissing():

        # Open the shared Workings UI (same as TASSetup Workings tab) in a dialog owned by the wizard.

            mod = None

            try:

                mod = LoadWorkingsUiModule()

            except:

                mod = None

            if mod is None or not hasattr(mod, 'ShowWorkingsDialog'):

                try:

                    JOptionPane.showMessageDialog(self, 'Shared workings UI module could not be loaded.\n\nPlease ensure TASWorkingsUi.py is present in profile:jython.', 'Workings', JOptionPane.ERROR_MESSAGE)

                except:

                    pass

                return

            def _GetTTPath():

                try:

                    return self._CurrentTimetableCsvPath()

                except:

                    return None

            try:

                selBg = Color(210, 225, 235)

                selFg = Color(20, 20, 20)

            except:

                selBg = THEME_PAPER

                selFg = THEME_TEXT_COLOR

            try:

                mod.ShowWorkingsDialog(self, _GetTTPath, ProfileJythonFilePath, ApplyTheme, MakePaperPanel, MakeHeading, MakeWrappedLabel, THEME_PAPER, THEME_FONT_FAMILY, THEME_TEXT_COLOR, selBg, selFg, LogInfo, LogWarn, LogError, title='Workings')

            except Exception as ex:

                try:

                    JOptionPane.showMessageDialog(self, 'Could not open workings editor.\n\nDetails: ' + str(ex), 'Workings', JOptionPane.ERROR_MESSAGE)

                except:

                    pass
        try:
            self.WorkingsCreateButton.addActionListener(lambda e: _OpenWorkingCreatorForNextMissing())
        except:
            pass

        p2bw.add(center2bw, BorderLayout.CENTER)

        # Step 2bd: disruption configuration (only shown when automatic running is enabled)
        p2bd = MakePaperPanel()
        p2bd.setLayout(BorderLayout())
        p2bd.add(self._BuildSidebar(), BorderLayout.WEST)
        center2bd = JPanel()
        center2bd.setOpaque(False)
        center2bd.setLayout(GridBagLayout())
        g2bd = GridBagConstraints()
        g2bd.insets = Insets(6, 12, 6, 6)
        g2bd.gridx = 0
        g2bd.gridy = 0
        g2bd.weightx = 1.0
        g2bd.weighty = 0.0
        g2bd.fill = GridBagConstraints.HORIZONTAL
        center2bd.add(MakeHeading('Disruption'), g2bd)
        g2bd.gridy = 1
        info2bd = (
            'The Timetable Automation System can simulate delays and cancellations for trains that are run automatically.\n\n'
            'To enable this feature, you must set up disruption groups and provide a Disruption.csv file in the timetable folder.'
        )
        center2bd.add(MakeWrappedTextArea(info2bd, fontSize=13), g2bd)
        g2bd.gridy = 2
        g2bd.weighty = 0.0
        g2bd.fill = GridBagConstraints.HORIZONTAL
        box2bd = Box.createHorizontalBox()
        self.EnableDelaysCheck = JCheckBox('Enable delays')
        self.EnableDelaysCheck.setOpaque(False)
        self.EnableCancellationsCheck = JCheckBox('Enable cancellations')
        self.EnableCancellationsCheck.setOpaque(False)
        def _OnEnableDelays(e=None):
            try:
                TBL.SafeSetMemoryValue('ALLOWDELAYS', 'true' if self.EnableDelaysCheck.isSelected() else 'false')
            except:
                pass
            try:
                self._RefreshStep2bdUi()
            except:
                pass
        def _OnEnableCancellations(e=None):
            try:
                TBL.SafeSetMemoryValue('ALLOWCANCELLATIONS', 'true' if self.EnableCancellationsCheck.isSelected() else 'false')
            except:
                pass
            try:
                self._RefreshStep2bdUi()
            except:
                pass
        self.EnableDelaysCheck.addActionListener(lambda e: _OnEnableDelays())
        self.EnableCancellationsCheck.addActionListener(lambda e: _OnEnableCancellations())
        box2bd.add(self.EnableDelaysCheck)
        box2bd.add(Box.createHorizontalStrut(18))
        box2bd.add(self.EnableCancellationsCheck)
        center2bd.add(box2bd, g2bd)
        g2bd.gridy = 3
        g2bd.weighty = 1.0
        g2bd.fill = GridBagConstraints.BOTH
        self.Step2bdInfoTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2bdInfoScroll = MakeScrollForText(self.Step2bdInfoTextArea)
        center2bd.add(self.Step2bdInfoScroll, g2bd)
        p2bd.add(center2bd, BorderLayout.CENTER)


        # Step 2c: before you start (orientation sensing) - shown only if automatic running is selected
        p2c = MakePaperPanel()
        p2c.setLayout(BorderLayout())
        p2c.add(self._BuildSidebar(), BorderLayout.WEST)
        center2c = JPanel()
        center2c.setOpaque(False)
        center2c.setLayout(GridBagLayout())
        g2c = GridBagConstraints()
        g2c.insets = Insets(6, 12, 6, 6)
        g2c.gridx = 0
        g2c.gridy = 0
        g2c.weightx = 1.0
        g2c.weighty = 0.0
        g2c.fill = GridBagConstraints.HORIZONTAL
        center2c.add(MakeHeading('Orientation sensing'), g2c)

        g2c.gridy = 1
        info2c = (
            'If you are using automatically running trains, the Timetable Automation System can optionally use orientation sensing.\n\n'
            'Do you want to use automatic orientation sensing?'
        )
        center2c.add(MakeWrappedTextArea(info2c, fontSize=13), g2c)

        g2c.gridy = 2
        self.UseOrientationCheck = JCheckBox('Yes - use automatic orientation sensing')
        self.UseOrientationCheck.setOpaque(False)
        self.UseOrientationCheck.setSelected(False)
        ApplyTheme(self.UseOrientationCheck)
        center2c.add(self.UseOrientationCheck, g2c)

        # Extra text for this step. Give it the remaining vertical space when visible.
        g2cExtra = GridBagConstraints()
        g2cExtra.insets = Insets(6, 12, 6, 6)
        g2cExtra.gridx = 0
        g2cExtra.gridy = 3
        g2cExtra.weightx = 1.0
        g2cExtra.weighty = 1.0
        g2cExtra.fill = GridBagConstraints.BOTH
        self.Step2cExtraTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2cExtraScroll = MakeScrollForText(self.Step2cExtraTextArea)
        try:
            self.Step2cExtraScroll.setVisible(True)
        except:
            pass
        center2c.add(self.Step2cExtraScroll, g2cExtra)

        def _OnOrientationToggled2c():
            try:
                if not self.SuppressOrientationListener:
                    try:
                        self._SetOrientationSensingEnabled(self.UseOrientationCheck.isSelected())
                    except:
                        pass
                self._UpdateFeatureCache()
            except:
                pass
            try:
                self._RefreshStep2cUi()
            except:
                pass
            try:
                center2c.revalidate()
                center2c.repaint()
            except:
                pass

        try:
            self.UseOrientationCheck.addActionListener(lambda e: _OnOrientationToggled2c())
        except:
            pass

        g2c.gridy = 4
        g2c.weighty = 0.0
        g2c.fill = GridBagConstraints.BOTH
        filler2c = JPanel()
        filler2c.setOpaque(False)
        center2c.add(filler2c, g2c)
        p2c.add(center2c, BorderLayout.CENTER)


        # Step 2ch: hardware orientation sensing setup (only when enabled and required)
        p2ch = MakePaperPanel()
        p2ch.setLayout(BorderLayout())
        p2ch.add(self._BuildSidebar(), BorderLayout.WEST)
        center2ch = JPanel()
        center2ch.setOpaque(False)
        center2ch.setLayout(GridBagLayout())
        g2ch = GridBagConstraints()
        g2ch.insets = Insets(6, 12, 6, 6)
        g2ch.gridx = 0
        g2ch.gridy = 0
        g2ch.weightx = 1.0
        g2ch.weighty = 0.0
        g2ch.fill = GridBagConstraints.HORIZONTAL
        center2ch.add(MakeHeading('Hardware orientation sensing setup'), g2ch)
        g2ch.gridy = 1
        info2ch = (
            'You have enabled hardware orientation sensing.\n\n'
            'Hardware orientation sensing only works for trains that have been configured for this. Some of your roster entries have not been fully configured.\n\n'
            'Click the button below to configure hardware orientation sensing for the missing roster entries.'
        )
        center2ch.add(MakeWrappedTextArea(info2ch, fontSize=13), g2ch)
        g2ch.gridy = 2
        g2ch.weighty = 1.0
        g2ch.fill = GridBagConstraints.BOTH
        self.Step2chTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2chScroll = MakeScrollForText(self.Step2chTextArea)
        center2ch.add(self.Step2chScroll, g2ch)
        g2ch.gridy = 3
        g2ch.weighty = 0.0
        g2ch.fill = GridBagConstraints.NONE
        g2ch.anchor = GridBagConstraints.WEST
        self.Step2chConfigButton = JButton('Configure hardware orientation sensing...')
        ApplyTheme(self.Step2chConfigButton)
        center2ch.add(self.Step2chConfigButton, g2ch)
        def _OpenHardwareOrientationConfig():
            try:
                pth = ProfileJythonFilePath('HardwareDirectionConfig.py')
                if pth and File(pth).exists():
                    execfile(pth, {'__file__': pth, '__name__': '__main__'})
                else:
                    JOptionPane.showMessageDialog(self, 'HardwareDirectionConfig.py was not found in profile:jython.', 'Orientation sensing', JOptionPane.ERROR_MESSAGE)
            except Exception as ex:
                try:
                    JOptionPane.showMessageDialog(self, 'Could not open HardwareDirectionConfig.py.\n\nDetails: ' + str(ex), 'Orientation sensing', JOptionPane.ERROR_MESSAGE)
                except:
                    pass
        try:
            self.Step2chConfigButton.addActionListener(lambda e: _OpenHardwareOrientationConfig())
        except:
            pass
        p2ch.add(center2ch, BorderLayout.CENTER)
        # Step 2d: before you start (day/night lighting)
        p2d = MakePaperPanel()
        p2d.setLayout(BorderLayout())
        p2d.add(self._BuildSidebar(), BorderLayout.WEST)
        center2d = JPanel()
        center2d.setOpaque(False)
        center2d.setLayout(GridBagLayout())
        g2d = GridBagConstraints()
        g2d.insets = Insets(6, 12, 6, 6)
        g2d.gridx = 0
        g2d.gridy = 0
        g2d.weightx = 1.0
        g2d.weighty = 0.0
        g2d.fill = GridBagConstraints.HORIZONTAL
        center2d.add(MakeHeading('Day and night lighting'), g2d)

        g2d.gridy = 1
        info2d = (
            'The Timetable Automation System can optionally control a day and night lighting cycle.\n\n'
            'Do you want to use a day and night lighting cycle?'
        )
        center2d.add(MakeWrappedTextArea(info2d, fontSize=13), g2d)

        g2d.gridy = 2
        self.UseLightingCheck = JCheckBox('Yes - use day/night lighting')
        self.UseLightingCheck.setOpaque(False)
        try:
            self.UseLightingCheck.setSelected(self._GetDayNightEnabled())
        except:
            self.UseLightingCheck.setSelected(False)
        ApplyTheme(self.UseLightingCheck)
        center2d.add(self.UseLightingCheck, g2d)

        # Extra text for this step. Give it the remaining vertical space when visible.
        g2dExtra = GridBagConstraints()
        g2dExtra.insets = Insets(6, 12, 6, 6)
        g2dExtra.gridx = 0
        g2dExtra.gridy = 3
        g2dExtra.weightx = 1.0
        g2dExtra.weighty = 1.0
        g2dExtra.fill = GridBagConstraints.BOTH
        self.Step2dExtraTextArea = MakeWrappedTextArea('', fontSize=13)
        self.Step2dExtraScroll = MakeScrollForText(self.Step2dExtraTextArea)
        try:
            self.Step2dExtraScroll.setVisible(True)
        except:
            pass
        center2d.add(self.Step2dExtraScroll, g2dExtra)

        def _OnLightingToggled2d():
            try:
                if not self.SuppressLightingListener:
                    try:
                        self._SetDayNightEnabled(self.UseLightingCheck.isSelected())
                    except:
                        pass
            except:
                pass
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                self._RefreshStep2dUi()
            except:
                pass
            try:
                center2d.revalidate()
                center2d.repaint()
            except:
                pass

        try:
            self.UseLightingCheck.addActionListener(lambda e: _OnLightingToggled2d())
        except:
            pass

        g2d.gridy = 4
        g2d.weighty = 0.0
        g2d.fill = GridBagConstraints.BOTH
        filler2d = JPanel()
        filler2d.setOpaque(False)
        center2d.add(filler2d, g2d)
        p2d.add(center2d, BorderLayout.CENTER)


        # Step 2e: lighting addresses (only if day/night lighting is enabled)
        p2e = MakePaperPanel()
        p2e.setLayout(BorderLayout())
        p2e.add(self._BuildSidebar(), BorderLayout.WEST)
        center2e = JPanel()
        center2e.setOpaque(False)
        center2e.setLayout(GridBagLayout())
        g2e = GridBagConstraints()
        g2e.insets = Insets(6, 12, 6, 6)
        g2e.gridx = 0
        g2e.gridy = 0
        g2e.weightx = 1.0
        g2e.weighty = 0.0
        g2e.fill = GridBagConstraints.HORIZONTAL
        center2e.add(MakeHeading('Lighting DCC addresses'), g2e)

        g2e.gridy = 1
        info2e = (
            'Enter the DCC addresses of the decoders used to control your day/night lighting.\n\n'
            'The warm (low colour temperature) and cool (high colour temperature) lighting must be on separate addresses.'
        )
        center2e.add(MakeWrappedTextArea(info2e, fontSize=13), g2e)

        # Warm address row
        g2e.gridy = 2
        warmRow = JPanel()
        warmRow.setOpaque(False)
        warmRow.setLayout(GridBagLayout())
        wg = GridBagConstraints()
        wg.insets = Insets(0, 0, 0, 0)
        wg.gridy = 0
        wg.gridx = 0
        wg.weightx = 0.0
        wg.fill = GridBagConstraints.NONE
        warmRow.add(JLabel('Warm (low colour temperature):'), wg)
        wg.gridx = 1
        wg.weightx = 1.0
        wg.fill = GridBagConstraints.HORIZONTAL
        self.LowCtAddrField = JTextField(8)
        ApplyTheme(self.LowCtAddrField)
        warmRow.add(self.LowCtAddrField, wg)
        center2e.add(warmRow, g2e)

        # Cool address row
        g2e.gridy = 3
        coolRow = JPanel()
        coolRow.setOpaque(False)
        coolRow.setLayout(GridBagLayout())
        cg = GridBagConstraints()
        cg.insets = Insets(0, 0, 0, 0)
        cg.gridy = 0
        cg.gridx = 0
        cg.weightx = 0.0
        cg.fill = GridBagConstraints.NONE
        coolRow.add(JLabel('Cool (high colour temperature):'), cg)
        cg.gridx = 1
        cg.weightx = 1.0
        cg.fill = GridBagConstraints.HORIZONTAL
        self.HighCtAddrField = JTextField(8)
        ApplyTheme(self.HighCtAddrField)
        coolRow.add(self.HighCtAddrField, cg)
        center2e.add(coolRow, g2e)

        # Filler to keep top-aligned
        g2e.gridy = 4
        g2e.weighty = 1.0
        g2e.fill = GridBagConstraints.BOTH
        filler2e = JPanel()
        filler2e.setOpaque(False)
        center2e.add(filler2e, g2e)

        p2e.add(center2e, BorderLayout.CENTER)


        # Step 2f: day/night presets (only when day/night lighting is enabled)
        p2f = MakePaperPanel()
        p2f.setLayout(BorderLayout())
        p2f.add(self._BuildSidebar(), BorderLayout.WEST)
        center2f = JPanel()
        center2f.setOpaque(False)
        center2f.setLayout(GridBagLayout())
        g2f = GridBagConstraints()
        g2f.insets = Insets(6, 12, 6, 6)
        g2f.gridx = 0
        g2f.gridy = 0
        g2f.weightx = 1.0
        g2f.weighty = 0.0
        g2f.fill = GridBagConstraints.HORIZONTAL
        center2f.add(MakeHeading('Day/night presets'), g2f)
        g2f.gridy = 1
        info2f = (
            'Choose the preset data used by the day/night cycle and weather generator.\n\n'
            'The climate preset controls typical weather patterns, and the daylight hours preset controls sunrise and sunset times.'
        )
        center2f.add(MakeWrappedTextArea(info2f, fontSize=13), g2f)
        # Climate preset
        g2f.gridy = 2
        rowClimate = JPanel()
        rowClimate.setOpaque(False)
        rowClimate.setLayout(GridBagLayout())
        cg = GridBagConstraints()
        cg.insets = Insets(0, 0, 0, 0)
        cg.gridx = 0
        cg.gridy = 0
        cg.weightx = 0.0
        cg.fill = GridBagConstraints.NONE
        rowClimate.add(JLabel('Climate preset:'), cg)
        cg.gridx = 1
        cg.weightx = 1.0
        cg.fill = GridBagConstraints.HORIZONTAL
        climateNames = _LoadClimateNames()
        self.Step2fClimateCombo = JComboBox(climateNames)
        ApplyTheme(self.Step2fClimateCombo)
        rowClimate.add(self.Step2fClimateCombo, cg)
        center2f.add(rowClimate, g2f)
        # Daylight hours preset
        g2f.gridy = 3
        rowDaylight = JPanel()
        rowDaylight.setOpaque(False)
        rowDaylight.setLayout(GridBagLayout())
        dg = GridBagConstraints()
        dg.insets = Insets(0, 0, 0, 0)
        dg.gridx = 0
        dg.gridy = 0
        dg.weightx = 0.0
        dg.fill = GridBagConstraints.NONE
        rowDaylight.add(JLabel('Daylight hours preset:'), dg)
        dg.gridx = 1
        dg.weightx = 1.0
        dg.fill = GridBagConstraints.HORIZONTAL
        daylightNames = _LoadDayNightNames()
        self.Step2fDaylightCombo = JComboBox(daylightNames)
        ApplyTheme(self.Step2fDaylightCombo)
        rowDaylight.add(self.Step2fDaylightCombo, dg)
        center2f.add(rowDaylight, g2f)
        # Filler
        g2f.gridy = 4
        g2f.weighty = 1.0
        g2f.fill = GridBagConstraints.BOTH
        filler2f = JPanel()
        filler2f.setOpaque(False)
        center2f.add(filler2f, g2f)
        p2f.add(center2f, BorderLayout.CENTER)
        # Step 3: fonts (optional)
        fontText = (
            "The Timetable Automation System looks best if you have the recommended fonts installed.\n\n"
            "You are seeing this step because you are missing at least one recommended font.\n\n"
            "The Timetable Automation System will still work if you do not have all the recommended fonts, but some displays may not look their best.\n\n"
            "Click 'More...' to see which fonts are missing and how to obtain them."
        )

        def MoreFonts():
            try:
                self.EnsureFontCheck()
            except:
                pass
            if self.FontCheckMod is None:
                try:
                    self.FontCheckMod = LoadFontCheckModule()
                except:
                    self.FontCheckMod = None
            ok = False
            try:
                ok = OpenFontCheckUi(self.FontCheckMod, self)
            except Exception as ex:
                LogInfo("Font check UI failed: " + str(ex))
            if not ok:
                try:
                    JOptionPane.showMessageDialog(
                        self,
                        "Font checker could not be opened.\n\nPlease ensure TASFontCheck.py is present in profile:jython, then try again.",
                        "Fonts",
                        JOptionPane.INFORMATION_MESSAGE
                    )
                except:
                    pass

        p3 = self.MakeWizardStepWithButton("Fonts", fontText, "More...", MoreFonts)

        # Step 4: layout details
        p4 = MakePaperPanel()
        p4.setLayout(BorderLayout())
        p4.add(self._BuildSidebar(), BorderLayout.WEST)

        layoutInfo = (
            "Give some more information about your layout.\n\n"
            "If you have not already set the name, set it here. This name is used in timetables as the name of the station or other location where your layout is set.\n\n"
            "The year is used only to choose sensible defaults in this wizard; it is not saved."
        )

        center = JPanel()
        center.setOpaque(False)
        center.setLayout(GridBagLayout())
        g = GridBagConstraints()
        g.insets = Insets(6, 12, 6, 6)
        g.gridx = 0
        g.gridy = 0
        g.weightx = 1.0
        g.weighty = 0.0
        g.fill = GridBagConstraints.HORIZONTAL
        center.add(MakeHeading("Layout details"), g)

        g.gridy = 1
        infoTa = MakeWrappedTextArea(layoutInfo, fontSize=13)
        center.add(infoTa, g)

        # Name row
        g.gridy = 2
        nameRow = JPanel()
        nameRow.setOpaque(False)
        nameRow.setLayout(GridBagLayout())
        ng = GridBagConstraints()
        ng.insets = Insets(0, 0, 0, 0)
        ng.gridx = 0
        ng.gridy = 0
        ng.weightx = 0.0
        ng.fill = GridBagConstraints.NONE
        nameRow.add(JLabel('Layout name:'), ng)
        ng.gridx = 1
        ng.weightx = 1.0
        ng.fill = GridBagConstraints.HORIZONTAL
        self.ProfileNameField = JTextField(self._GetActiveProfileName(), 24)
        ApplyTheme(self.ProfileNameField)
        nameRow.add(self.ProfileNameField, ng)
        center.add(nameRow, g)

        # Year row
        g.gridy = 3
        yearRow = JPanel()
        yearRow.setOpaque(False)
        yearRow.setLayout(GridBagLayout())
        yg = GridBagConstraints()
        yg.insets = Insets(0, 0, 0, 0)
        yg.gridx = 0
        yg.gridy = 0
        yg.weightx = 0.0
        yg.fill = GridBagConstraints.NONE
        yearRow.add(JLabel('Layout year:'), yg)
        yg.gridx = 1
        yg.weightx = 0.0
        yg.fill = GridBagConstraints.NONE
        self.YearField = JTextField(str(self._DefaultLayoutYear()), 6)
        ApplyTheme(self.YearField)
        yearRow.add(self.YearField, yg)
        center.add(yearRow, g)

        # filler
        g.gridy = 4
        g.weighty = 1.0
        g.fill = GridBagConstraints.BOTH
        filler = JPanel()
        filler.setOpaque(False)
        center.add(filler, g)

        p4.add(center, BorderLayout.CENTER)

        # Step 5: railway details (company, region/division, section)
        p5 = MakePaperPanel()
        p5.setLayout(BorderLayout())
        p5.add(self._BuildSidebar(), BorderLayout.WEST)

        info = (
            "Choose your railway company and region/division. \n\n"
            "The railway company affects some display and interface defaults and is shown on the main menu.\n\n"
            "The region/division and section affect only the text shown on the main menu."
        )

        center5 = JPanel()
        center5.setOpaque(False)
        center5.setLayout(GridBagLayout())
        g5 = GridBagConstraints()
        g5.insets = Insets(6, 12, 6, 6)
        g5.gridx = 0
        g5.gridy = 0
        g5.weightx = 1.0
        g5.weighty = 0.0
        g5.fill = GridBagConstraints.HORIZONTAL

        center5.add(MakeHeading('Railway details'), g5)

        g5.gridy = 1
        center5.add(MakeWrappedTextArea(info, fontSize=13), g5)

        try:
            existingSection = TBL.SafeGetOrCreateMemoryValue('SECTION', 'SECTION B')
        except:
            existingSection = 'SECTION B'

            # Company row (combo only)
        g5.gridy = 2
        rowC = JPanel()
        rowC.setOpaque(False)
        rowC.setLayout(GridBagLayout())
        cg = GridBagConstraints()
        cg.insets = Insets(0, 0, 0, 0)
        cg.gridy = 0
        cg.gridx = 0
        cg.weightx = 0.0
        cg.fill = GridBagConstraints.NONE
        rowC.add(JLabel('Railway company:'), cg)
        cg.gridx = 1
        cg.weightx = 1.0
        cg.fill = GridBagConstraints.HORIZONTAL
        companyItems = self._CompanyOptionsForYear(self.LayoutYear)
        self.CompanyCombo = JComboBox(companyItems)
        ApplyTheme(self.CompanyCombo)
        try:
            ph = self.CompanyCombo.getPreferredSize().height
            self.CompanyCombo.setPreferredSize(Dimension(360, ph))
        except:
            pass
        rowC.add(self.CompanyCombo, cg)
        center5.add(rowC, g5)

        # Other company row
        g5.gridy = 3
        rowCO = JPanel()
        rowCO.setOpaque(False)
        rowCO.setLayout(GridBagLayout())
        cog = GridBagConstraints()
        cog.insets = Insets(0, 0, 0, 0)
        cog.gridy = 0
        cog.gridx = 0
        cog.weightx = 0.0
        cog.fill = GridBagConstraints.NONE
        self.CompanyOtherLabel = JLabel('Other railway company:')
        self.CompanyOtherLabel.setEnabled(False)
        rowCO.add(self.CompanyOtherLabel, cog)
        cog.gridx = 1
        cog.weightx = 1.0
        cog.fill = GridBagConstraints.HORIZONTAL
        self.CompanyOtherField = JTextField('', 28)
        ApplyTheme(self.CompanyOtherField)
        self.CompanyOtherField.setEnabled(False)
        rowCO.add(self.CompanyOtherField, cog)
        center5.add(rowCO, g5)

        # Region row (combo only)
        g5.gridy = 4
        rowR = JPanel()
        rowR.setOpaque(False)
        rowR.setLayout(GridBagLayout())
        rg = GridBagConstraints()
        rg.insets = Insets(0, 0, 0, 0)
        rg.gridy = 0
        rg.gridx = 0
        rg.weightx = 0.0
        rg.fill = GridBagConstraints.NONE
        self.RegionLabel = JLabel('Region/division:')
        rowR.add(self.RegionLabel, rg)
        rg.gridx = 1
        rg.weightx = 1.0
        rg.fill = GridBagConstraints.HORIZONTAL
        self.RegionCombo = JComboBox(['Select...', 'Other...'])
        ApplyTheme(self.RegionCombo)
        try:
            ph = self.RegionCombo.getPreferredSize().height
            self.RegionCombo.setPreferredSize(Dimension(360, ph))
        except:
            pass
        self.RegionCombo.setEnabled(False)
        rowR.add(self.RegionCombo, rg)
        center5.add(rowR, g5)

        # Other region row
        g5.gridy = 5
        rowRO = JPanel()
        rowRO.setOpaque(False)
        rowRO.setLayout(GridBagLayout())
        rog = GridBagConstraints()
        rog.insets = Insets(0, 0, 0, 0)
        rog.gridy = 0
        rog.gridx = 0
        rog.weightx = 0.0
        rog.fill = GridBagConstraints.NONE
        self.RegionOtherLabel = JLabel('Other region/division:')
        self.RegionOtherLabel.setEnabled(False)
        rowRO.add(self.RegionOtherLabel, rog)
        rog.gridx = 1
        rog.weightx = 1.0
        rog.fill = GridBagConstraints.HORIZONTAL
        self.RegionOtherField = JTextField('', 28)
        ApplyTheme(self.RegionOtherField)
        self.RegionOtherField.setEnabled(False)
        rowRO.add(self.RegionOtherField, rog)
        center5.add(rowRO, g5)

        # Section row
        g5.gridy = 6
        rowS = JPanel()
        rowS.setOpaque(False)
        rowS.setLayout(GridBagLayout())
        sg = GridBagConstraints()
        sg.insets = Insets(0, 0, 0, 0)
        sg.gridy = 0
        sg.gridx = 0
        sg.weightx = 0.0
        sg.fill = GridBagConstraints.NONE
        rowS.add(JLabel('Section:'), sg)
        sg.gridx = 1
        sg.weightx = 1.0
        sg.fill = GridBagConstraints.HORIZONTAL
        self.SectionField = JTextField(str(existingSection), 28)
        ApplyTheme(self.SectionField)
        rowS.add(self.SectionField, sg)
        center5.add(rowS, g5)

        # Filler
        g5.gridy = 7
        g5.weighty = 1.0
        g5.fill = GridBagConstraints.BOTH
        filler5 = JPanel()
        filler5.setOpaque(False)
        center5.add(filler5, g5)

        p5.add(center5, BorderLayout.CENTER)

        try:
            self.CompanyCombo.addActionListener(lambda e: self._OnCompanyChanged())
        except:
            pass
        try:
            self.RegionCombo.addActionListener(lambda e: self._OnRegionChanged())
        except:
            pass
        try:
            self._RefreshCompanyOptionsForYear()
        except:
            pass

            # Step 6: apply defaults based on user choices
        p6 = MakePaperPanel() 
        p6.setLayout(BorderLayout()) 
        p6.add(self._BuildSidebar(), BorderLayout.WEST) 

        info6 = ( 
            "The Timetable Automation System can automatically configure itself based on the year and railway company that you set earlier.\n\n" 
            "Select which categories of things to set up automatically below. You can change any of these later by clicking 'Setup' in the main menu.\n\n" 
            "Untick any category that you do not want to configure automatically now." 
        ) 

        center6 = JPanel() 
        center6.setOpaque(False) 
        center6.setLayout(GridBagLayout()) 
        g6 = GridBagConstraints() 
        g6.insets = Insets(6, 12, 6, 6) 
        g6.gridx = 0 
        g6.gridy = 0 
        g6.weightx = 1.0 
        g6.weighty = 0.0 
        g6.fill = GridBagConstraints.HORIZONTAL 

        center6.add(MakeHeading('Automatic configuration'), g6) 

        g6.gridy = 1 
        center6.add(MakeWrappedTextArea(info6, fontSize=13), g6) 

        g6.gridy = 2 
        self.ApplyDefaultsAppearanceCheck = JCheckBox('Timetable appearance (main menu, setup and timetable display)') 
        self.ApplyDefaultsAppearanceCheck.setOpaque(False) 
        self.ApplyDefaultsAppearanceCheck.setSelected(True) 
        ApplyTheme(self.ApplyDefaultsAppearanceCheck) 
        center6.add(self.ApplyDefaultsAppearanceCheck, g6) 

        g6.gridy = 3 
        self.ApplyDefaultsPublicDisplaysCheck = JCheckBox('Public information displays') 
        self.ApplyDefaultsPublicDisplaysCheck.setOpaque(False) 
        self.ApplyDefaultsPublicDisplaysCheck.setSelected(True) 
        ApplyTheme(self.ApplyDefaultsPublicDisplaysCheck) 
        center6.add(self.ApplyDefaultsPublicDisplaysCheck, g6) 

        g6.gridy = 4 
        self.ApplyDefaultsSignallersDisplaysCheck = JCheckBox("Signallers' displays") 
        self.ApplyDefaultsSignallersDisplaysCheck.setOpaque(False) 
        self.ApplyDefaultsSignallersDisplaysCheck.setSelected(True) 
        ApplyTheme(self.ApplyDefaultsSignallersDisplaysCheck) 
        center6.add(self.ApplyDefaultsSignallersDisplaysCheck, g6) 

        g6.gridy = 5 
        self.ApplyDefaultsWeatherForecastingCheck = JCheckBox('Weather forecasting') 
        self.ApplyDefaultsWeatherForecastingCheck.setOpaque(False) 
        self.ApplyDefaultsWeatherForecastingCheck.setSelected(True) 
        ApplyTheme(self.ApplyDefaultsWeatherForecastingCheck) 
        center6.add(self.ApplyDefaultsWeatherForecastingCheck, g6) 

        g6.gridy = 6 
        g6.weighty = 1.0 
        g6.fill = GridBagConstraints.BOTH 
        filler6 = JPanel() 
        filler6.setOpaque(False) 
        center6.add(filler6, g6) 

        p6.add(center6, BorderLayout.CENTER)


        # Step 7: finished
        p7 = self.MakeWizardStep('Finished', 'Setup wizard complete.\n\nYou can reopen TASSetup at any time to change these settings.')

        self.AddStep("step1", p1)
        self.AddStep("step2a", p2a)
        self.AddStep("step2btt", p2btt)
        self.AddStep("step2b", p2b)
        self.AddStep("step2bw", p2bw)
        self.AddStep("step2bd", p2bd)
        self.AddStep("step2c", p2c)
        self.AddStep("step2ch", p2ch)
        self.AddStep("step2d", p2d)
        self.AddStep("step2e", p2e) 
        self.AddStep("step2f", p2f)
        self.AddStep("step3", p3) 
        self.AddStep("step4", p4) 
        self.AddStep("step5", p5) 
        self.AddStep("step6", p6) 
        self.AddStep("step7", p7) 
        
    def AddStep(self, key, panel):
        self.Steps.append(key)
        try:
            self.CardHost.add(panel, key)
        except:
            self.CardHost.add(panel, BorderLayout.CENTER)

    def IsSkippableIndex(self, idx):
        try:
            key = self.Steps[int(idx)]
        except:
            return False
            # Step 2c is optional: show it only when automatic running is selected.
        if key == "step2c":
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                return not bool(self.UseAutoTrainsSelected)
            except:
                return True
                # Step 2bw is optional: show it only when automatic running is selected.
        if key == "step2bw":
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                return not bool(self.UseAutoTrainsSelected)
            except:
                return True

                # Step 2ch is optional: show it only when hardware orientation sensing is enabled and at least one roster entry is not in the normal direction register.

                # Step 2bd is optional: show it only when automatic running is selected.
        if key == "step2bd":
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                return not bool(self.UseAutoTrainsSelected)
            except:
                return True
        if key == "step2ch":
            try:
                enabled = bool(self._GetOrientationSensingEnabled())
            except:
                enabled = False
            if not enabled:
                return True
            try:
                return not bool(self._HasRosterIdsWithoutNormalDirectionRegister())
            except:
                return True

                # Step 2e is optional: show it only when day/night lighting is selected.
        if key == "step2e":
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                return not bool(self.UseLightingSelected)
            except:
                return True
                # Step 2f is optional: show it only when day/night lighting is selected.
        if key == "step2f":
            try:
                self._UpdateFeatureCache()
            except:
                pass
            try:
                return not bool(self.UseLightingSelected)
            except:
                return True

                # Step 3 (fonts) is optional when no recommended fonts are missing.
        if key != "step3":
            return False
        return self.ShouldSkipFontStep()

    def NextIndex(self, idx):
        i = int(idx) + 1
        while i < len(self.Steps) and self.IsSkippableIndex(i):
            i += 1
        if i >= len(self.Steps):
            i = len(self.Steps) - 1
        return i

    def PrevIndex(self, idx):
        i = int(idx) - 1
        while i >= 0 and self.IsSkippableIndex(i):
            i -= 1
        if i < 0:
            i = 0
        return i


    def ShowStep(self, idx):
        try:
            idx = int(idx)
        except:
            idx = 0
        idx = max(0, min(len(self.Steps) - 1, idx))
        self.StepIndex = idx
        key = self.Steps[idx]

        try:
            if key == 'step2a':
                self._RefreshStep2aText()
            if key == 'step2btt':
                self._RefreshTimetableChooserUi()
                try:
                    self._RefreshStep2bttUi(False)
                except:
                    pass
            if key == 'step2b':
                self._UpdateFeatureCache()
                self._RefreshStep2bUi()
            if key == 'step2bw':
                self._RefreshStep2bwUi()
            if key == 'step2bd':
                self._RefreshStep2bdUi()
            if key == 'step2c':
                self._UpdateFeatureCache()
                self._RefreshStep2cUi()
            if key == 'step2ch':
                self._RefreshStep2chUi()
            if key == 'step2d':
                self._RefreshStep2dUi()
            if key == 'step2e':
                self._RefreshStep2eUi()
            if key == 'step2f':
                self._RefreshStep2fUi()
        except:
            pass

        if self.CardLayout is not None:
            try:
                self.CardLayout.show(self.CardHost, key)
            except:
                pass

        try:
            self.BtnBack.setEnabled(self.PrevIndex(self.StepIndex) < self.StepIndex)
        except:
            pass

        try:
            self.BtnForward.setEnabled(self.NextIndex(self.StepIndex) > self.StepIndex)
        except:
            pass
            # Step 2btt: gate Forward until a valid timetable is selected.
        try:
            if key == 'step2btt':
                self.BtnForward.setEnabled(bool(self._RefreshStep2bttUi(False)))
        except:
            pass

            # Step 2bw: gate Forward until all required working scripts exist.
        try:
            if key == 'step2bw':
                self.BtnForward.setEnabled(bool(getattr(self, 'WorkingsOk', False)))
        except:
            pass
        try:
            if int(self.StepIndex) == (len(self.Steps) - 1):
                self.BtnCancel.setText('Finish')
            else:
                self.BtnCancel.setText('Cancel')
        except:
            pass

        try:
            self.CardHost.revalidate()
            self.CardHost.repaint()
        except:
            pass


    def _ParseBool(self, v, defaultVal=False):
        try:
            if isinstance(v, bool):
                return bool(v)
        except:
            pass
        try:
            t = str(v).strip().lower()
        except:
            t = ""
        if t in ["1", "true", "yes", "y", "on", "enabled"]:
            return True
        if t in ["0", "false", "no", "n", "off", "disabled"]:
            return False
        return bool(defaultVal)

    def _DisruptionCsvPath(self):
    # DisruptionGenerator expects Disruption.csv in the timetable folder.
        try:
            ttDir = FileUtil.getExternalFilename('profile:timetable')
        except:
            ttDir = None
        if not ttDir:
            return None
        try:
            return os.path.join(str(ttDir), 'Disruption.csv')
        except:
            return None

    def _GetTimetablePath(self):
        try:
            name = str(TBL.SafeGetOrCreateMemoryValue('CURRENTTIMETABLE', '')).strip()
        except:
            name = ''
        if not name:
            return None
        try:
            ttDir = FileUtil.getExternalFilename('profile:timetable')
        except:
            ttDir = None
        if not ttDir:
            return None
        try:
            return os.path.join(str(ttDir), name + '.csv')
        except:
            return None

    def _DisruptionGroupsUsedByTimetable(self):
    # Return (usedExactSet, usedLowerSet, hadColumn, errorMsg)
        path = self._GetTimetablePath()
        if not path or (not os.path.isfile(path)):
            return (set([]), set([]), False, 'No timetable file is selected.')
        try:
            with open(path, 'r') as f:
                r = csv.DictReader(f, delimiter='\t')
                header = r.fieldnames or []
                if 'Disruption group' not in header:
                    return (set([]), set([]), False, "Timetable does not have a 'Disruption group' column.")
                usedExact = set([])
                usedLower = set([])
                for row in r:
                    try:
                        g = (row.get('Disruption group', '') or '').strip()
                    except:
                        g = ''
                    if g:
                        usedExact.add(g)
                        usedLower.add(g.lower())
                return (usedExact, usedLower, True, '')
        except Exception as ex:
            return (set([]), set([]), False, 'Error reading timetable: ' + str(ex))

    def _DisruptionGroupsProvidedByCsv(self):
    # Return (providedExactSet, providedLowerSet, ok, errorMsg)
        path = self._DisruptionCsvPath()
        if not path or (not os.path.isfile(path)):
            return (set([]), set([]), False, 'Disruption.csv was not found in the timetable folder.')
        try:
            with open(path, 'r') as f:
                r = csv.DictReader(f, delimiter='\t')
                header = r.fieldnames or []
                if 'Disruption group' not in header:
                    return (set([]), set([]), False, "Disruption.csv is missing the 'Disruption group' column.")
                providedExact = set([])
                providedLower = set([])
                for row in r:
                    try:
                        nm = (row.get('Disruption group', '') or '').strip()
                    except:
                        nm = ''
                    if nm:
                        providedExact.add(nm)
                        providedLower.add(nm.lower())
                return (providedExact, providedLower, True, '')
        except Exception as ex:
            return (set([]), set([]), False, 'Error reading Disruption.csv: ' + str(ex))

    def _ValidateDisruptionConfiguration(self):
        usedExact, usedLower, hadCol, msg = self._DisruptionGroupsUsedByTimetable()
        if msg:
            return (False, msg)
        if not usedExact:
            return (False, 'No workings in the timetable have a Disruption group configured.')

        provExact, provLower, ok, msg2 = self._DisruptionGroupsProvidedByCsv()
        if not ok:
            return (False, msg2)

        missing = []
        caseMismatch = []
        for g in sorted(list(usedExact)):
            if g in provExact:
                continue
            if g.lower() in provLower:
                caseMismatch.append(g)
            else:
                missing.append(g)

        if caseMismatch:
            return (False, 'Disruption.csv has group names with different letter case for: ' + ', '.join(caseMismatch) + '. Make them match exactly.')
        if missing:
            return (False, 'Disruption.csv does not contain rows for these Disruption groups: ' + ', '.join(missing) + '.')

        return (True, '')

    def _RefreshStep2bdUi(self):
        try:
            self._UpdateFeatureCache()
        except:
            pass

        autoEnabled = False
        try:
            autoEnabled = bool(self.UseAutoTrainsSelected)
        except:
            autoEnabled = False

        ok = False
        msg = ''
        if autoEnabled:
            try:
                ok, msg = self._ValidateDisruptionConfiguration()
            except Exception as ex:
                ok = False
                msg = 'Error validating disruptions: ' + str(ex)
        else:
            ok = False
            msg = 'Disruptions are available only when automatic running is enabled.'

        try:
            curDelays = self._ParseBool(TBL.SafeGetOrCreateMemoryValue('ALLOWDELAYS', ''), False)
        except:
            curDelays = False
        try:
            curCancels = self._ParseBool(TBL.SafeGetOrCreateMemoryValue('ALLOWCANCELLATIONS', ''), False)
        except:
            curCancels = False

        try:
            if self.EnableDelaysCheck is not None:
                self.EnableDelaysCheck.setSelected(bool(curDelays))
        except:
            pass
        try:
            if self.EnableCancellationsCheck is not None:
                self.EnableCancellationsCheck.setSelected(bool(curCancels))
        except:
            pass

        enabled = bool(autoEnabled) and bool(ok)
        try:
            if self.EnableDelaysCheck is not None:
                self.EnableDelaysCheck.setEnabled(enabled)
        except:
            pass
        try:
            if self.EnableCancellationsCheck is not None:
                self.EnableCancellationsCheck.setEnabled(enabled)
        except:
            pass

        lines = []

        if enabled:

            lines.append('Disruption is configured for this timetable.')

            lines.append('')

            lines.append('Use the tick boxes above to control enable or disable delays and cancellations. This can be changed later.')

        else:

            lines.append('Disruption is not configured for this timetable yet.')

            lines.append('')

            if msg:

                lines.append('Current status: ' + str(msg))

            lines.append('')

            lines.append('To enable disruption, add a disruption group to at least one timetable entry and create timetable/Disruption.csv with a row for each group used.')

            lines.append('')

            lines.append('See the Disruption help for full instructions on how to configure disruptions.')


        try:

            if self.Step2bdInfoTextArea is not None:

                self.Step2bdInfoTextArea.setText('\n'.join(lines))
                try:
                    self.Step2bdInfoTextArea.setCaretPosition(0)
                except:
                    pass
        except:
            pass

    def _HelpTopicForKey(self, key):
        try:
            k = '' if key is None else str(key)
        except:
            k = ''
        if k == 'step2a':
            return 'Timetable'
        if k == 'step2btt':
            return 'Timetable'
        if k == 'step2b':
            return 'Train orientation'
        if k == 'step2bw':
            return 'Timetable'
        if k == 'step2d':
            return 'Day and night cycle'
        if k == 'step2e':
            return 'Day and night cycle'
        if k == 'step2f':
            return 'Day and night cycle'
        if k == 'step2bd':
            return 'Disruption'
        return 'General'

    def _HelpTopicForCurrentStep(self):
        try:
            key = self.Steps[int(self.StepIndex)]
        except:
            key = ''
        return self._HelpTopicForKey(key)

    def OnHelp(self):
        topic = self._HelpTopicForCurrentStep()
        mod = None
        try:
            import TASHelp
            mod = TASHelp
        except:
            mod = None
        if mod is None:
            try:
                import imp
                pth = None
                try:
                    pth = FileUtil.getExternalFilename('profile:jython/TASHelp.py')
                except:
                    pth = None
                if pth is not None:
                    try:
                        mod = imp.load_source('TASHelp_i', pth)
                    except:
                        mod = None
            except:
                mod = None
        if mod is None:
            try:
                JOptionPane.showMessageDialog(self, 'Could not open help because TASHelp.py could not be loaded.\n\nPlease ensure TASHelp.py is in profile:jython.', 'Help', JOptionPane.ERROR_MESSAGE)
            except:
                pass
            return
        try:
            mod.Show(topic)
        except Exception as ex:
            try:
                JOptionPane.showMessageDialog(self, 'Could not open help.\n\nDetails: ' + str(ex), 'Help', JOptionPane.ERROR_MESSAGE)
            except:
                pass

    def OnCancelOrFinished(self):
    # Only apply defaults and show restart encouragement when the wizard has reached the final step.
        isFinal = False
        try:
            isFinal = (int(self.StepIndex) == (len(self.Steps) - 1))
        except:
            isFinal = False

        if isFinal:
        # Apply automatic configuration defaults (Step 6) when finishing, regardless of where Step 6 is in the flow.
            try:
                self._ApplyDefaultsFromStep6()
            except:
                pass

            try:
                if bool(getattr(self, 'RestartNeeded', False)):
                    JOptionPane.showMessageDialog(self, 'One or more changes require a restart to take effect\n\nPlease close and restart JMRI now.', 'Restart recommended', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass

        try:
            self.dispose()
        except:
            pass



    def GoBack(self):
        prevIdx = self.PrevIndex(self.StepIndex)
        self.ShowStep(prevIdx)

    def GoForward(self):
    # Keep cached feature selections in sync as the user moves forward.
        try:
            if self.Steps[int(self.StepIndex)] in ['step2b', 'step2c', 'step2d', 'step2e']:
                self._UpdateFeatureCache()
        except:
            pass

            # Do not allow leaving the workings check step until all required scripts exist.
        try:
            if self.Steps[int(self.StepIndex)] == 'step2bw':
                try:
                    self._RefreshStep2bwUi()
                except:
                    pass
                if not bool(getattr(self, 'WorkingsOk', False)):
                    return
        except:
            pass
            # Compute font status before step3 so we can skip it when appropriate.
        try:
            curKey = self.Steps[int(self.StepIndex)]
        except:
            curKey = ''
        try:
            if self.MissingFontsCount is None:
                if curKey == 'step2e' or curKey == 'step2f':
                    self.EnsureFontCheck()
                elif curKey == 'step2d':
                # If step2e will be skipped, ensure font check now.
                    try:
                        if self.NextIndex(self.StepIndex) != (int(self.StepIndex) + 1):
                            self.EnsureFontCheck()
                    except:
                        pass
        except:
            pass
            # If leaving the timetable chooser step, validate and apply the selection.
        try:
            if self.Steps[int(self.StepIndex)] == 'step2btt':
                if not self._ApplyTimetableFromChooserStep():
                    return
        except:
            pass

            # If leaving the lighting addresses step, validate and save the addresses.
        try:
            if self.Steps[int(self.StepIndex)] == 'step2e':
                if not self._ApplyLightingAddressesFromStep2e():
                    return
        except:
            pass


            # If leaving step4, apply layout details.
        try:
            if self.Steps[int(self.StepIndex)] == 'step4':
                if not self._ApplyLayoutDetailsFromStep4():
                    return
        except:
            pass

            # If leaving step5, apply railway details.
        try:
            if self.Steps[int(self.StepIndex)] == 'step5':
                if not self._ApplyRailwayDetailsFromStep5():
                    return
        except:
            pass

        nextIdx = self.NextIndex(self.StepIndex)
        self.ShowStep(nextIdx)
def ShowTASWizard():
    def _Run():
        try:
            TASWizardDialog()
        except Exception as ex:
            LogError("Failed to open wizard: " + str(ex), ex=ex)

    if SwingUtilities.isEventDispatchThread():
        _Run()
    else:
        SwingUtilities.invokeLater(RunnableAdapter(_Run))


        # Entry
ShowTASWizard() 