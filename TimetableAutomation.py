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
# This is a STARTUP SCRIPT
#
# TimetableAutomation.py
# Working Timetable-style startup UI for the Timetable Automation System (TAS)
# JMRI 5.12 / Jython 2.7. ASCII only. Thread-safe. No absolute paths.

VERSION = "1.4"
from javax.swing import JFrame
from javax.swing import JPanel
from javax.swing import JButton
from javax.swing import JLabel
from javax.swing import JDialog
from javax.swing import JScrollPane
from javax.swing import JTextArea
from javax.swing import SwingUtilities
from javax.swing import BorderFactory
from javax.swing import JTabbedPane
from javax.swing import JOptionPane
from javax.swing import UIManager
from javax.swing import Timer
from java.awt import BorderLayout
from java.awt import GridBagLayout, GridBagConstraints, Insets
from java.awt import Color, Font, RenderingHints, BasicStroke, Dimension
from java.awt import GraphicsEnvironment
from java.io import BufferedReader, InputStreamReader
import jmri
import os
import sys
from java.io import File # needed for canonical path comparison

# --- Scripts directory check ---
# JMRI defaults the portable "scripts:" location to program:jython, which is often unwritable.
# The Timetable Automation System expects to run from a writable scripts directory containing the
# Timetable Automation System scripts.
# If scripts is not writable (or appears to be under the program directory), prompt the user to
# change it to the folder where this TimetableAutomation.py is running from.

def _TasGetThisScriptDir():
    # Best effort: __file__ is usually set for file-based execution.
    try:
        p = globals().get('__file__', None)
        if p is not None and str(p).strip() != '':
            return str(File(str(p)).getParent())
    except Exception:
        pass
    # Fallback: assume profile:jython/TimetableAutomation.py
    try:
        f = jmri.util.FileUtil.getExternalFilename('profile:jython/TimetableAutomation.py')
        if f is not None and str(f).strip() != '':
            return str(File(str(f)).getParent())
    except Exception:
        pass
    return None

def _TasIsWritableDir(path):
    try:
        import tempfile
        if path is None:
            return False
        d = str(path).strip()
        if d == '' or (not os.path.isdir(d)):
            return False
        fd = None
        testPath = None
        try:
            fd, testPath = tempfile.mkstemp(prefix='tas_write_test_', suffix='.tmp', dir=d)
            os.close(fd)
            fd = None
            try:
                os.remove(testPath)
            except Exception:
                pass
            return True
        except Exception:
            try:
                if fd is not None:
                    os.close(fd)
            except Exception:
                pass
            try:
                if testPath is not None and os.path.exists(testPath):
                    os.remove(testPath)
            except Exception:
                pass
            return False
    except Exception:
        return False

def _TasScriptsPathLooksLikeProgramDir(scriptsPath):
    try:
        if scriptsPath is None:
            return False
        try:
            programPath = jmri.util.FileUtil.getProgramPath()
        except Exception:
            programPath = None
        if programPath is None:
            return False
        try:
            sp = os.path.normcase(os.path.realpath(str(scriptsPath)))
        except Exception:
            sp = os.path.normcase(os.path.abspath(str(scriptsPath)))
        try:
            pp = os.path.normcase(os.path.realpath(str(programPath)))
        except Exception:
            pp = os.path.normcase(os.path.abspath(str(programPath)))
        if sp == pp:
            return True
        if not pp.endswith(os.sep):
            pp = pp + os.sep
        return sp.startswith(pp)
    except Exception:
        return False

def _EnsureTasScriptsPath():
    try:
        # Ensure the TAS folder is importable in this session.
        tasDir = _TasGetThisScriptDir()
        if tasDir is not None:
            try:
                if tasDir not in sys.path:
                    sys.path.insert(0, tasDir)
            except Exception:
                pass
        if tasDir is None or str(tasDir).strip() == '':
            return

        # Import the pure-python helper only after the TAS folder is on sys.path.
        helper = None
        try:
            helper = __import__('TASScriptsPathGuard')
        except Exception:
            helper = None

        try:
            curScripts = jmri.util.FileUtil.getScriptsPath()
        except Exception:
            curScripts = None
        try:
            programPath = jmri.util.FileUtil.getProgramPath()
        except Exception:
            programPath = None

        try:
            if helper is not None:
                needPrompt = helper.NeedsScriptsPathUpdate(curScripts, tasDir, programPath)
            else:
                needPrompt = _TasScriptsPathLooksLikeProgramDir(curScripts) or (not _TasIsWritableDir(curScripts))
        except Exception:
            needPrompt = _TasScriptsPathLooksLikeProgramDir(curScripts) or (not _TasIsWritableDir(curScripts))
        if not needPrompt:
            return

        try:
            curDisp = '' if curScripts is None else str(curScripts)
        except Exception:
            curDisp = ''

        try:
            samePath = False
            if helper is not None:
                samePath = helper.PathsEqual(curDisp, tasDir)
            else:
                samePath = (os.path.normcase(os.path.abspath(str(curDisp))) == os.path.normcase(os.path.abspath(str(tasDir))))
            if samePath:
                return
        except Exception:
            pass

        msg = []
        msg.append('Timetable Automation System needs the JMRI scripts directory (the scripts: location)')
        msg.append('to be a writable folder containing the TAS scripts.')
        msg.append('')
        msg.append('Your JMRI scripts directory is currently:')
        msg.append(' ' + curDisp)
        msg.append('')
        msg.append('TAS was started from:')
        msg.append(' ' + str(tasDir))
        msg.append('')
        msg.append('Click OK to set the JMRI scripts directory to the TAS folder above, then restart JMRI.')
        msg.append('Click Cancel to leave it unchanged (TAS may malfunction).')
        txt = chr(10).join(msg)
        try:
            choice = JOptionPane.showConfirmDialog(None, txt, 'TAS scripts directory', JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE)
        except Exception:
            choice = JOptionPane.CANCEL_OPTION
        if choice != JOptionPane.OK_OPTION:
            return

        try:
            pm = jmri.profile.ProfileManager.getDefault()
            prof = pm.getActiveProfile() if pm is not None else None
        except Exception:
            prof = None
        if prof is None:
            return

        def _DoSetScriptsPath(targetPath):
            jmri.util.FileUtil.setScriptsPath(prof, str(targetPath))

        def _DoSaveFileLocationPreferences():
            prefMgr = None
            try:
                prefMgr = jmri.InstanceManager.getNullableDefault(jmri.implementation.FileLocationsPreferences)
            except Exception:
                prefMgr = None
            if prefMgr is None:
                try:
                    prefMgr = jmri.InstanceManager.getDefault(jmri.implementation.FileLocationsPreferences)
                except Exception:
                    prefMgr = None
            if prefMgr is None:
                return False
            try:
                prefMgr.savePreferences(prof)
                return True
            except Exception:
                return False

        try:
            if helper is not None:
                status, updatedPath = helper.EnsureScriptsPathChanged(curScripts, tasDir, programPath, _DoSetScriptsPath, jmri.util.FileUtil.getScriptsPath)
            else:
                try:
                    _DoSetScriptsPath(tasDir)
                    status = 'updated'
                    updatedPath = jmri.util.FileUtil.getScriptsPath()
                except Exception:
                    status = 'set-failed'
                    updatedPath = curScripts
        except Exception:
            status = 'set-failed'
            updatedPath = curScripts

        if status == 'updated':
            if _DoSaveFileLocationPreferences():
                try:
                    JOptionPane.showMessageDialog(None, 'Scripts directory updated. Please restart JMRI now.', 'TAS', JOptionPane.INFORMATION_MESSAGE)
                except Exception:
                    pass
                return
            warn = []
            warn.append('Scripts directory was updated for this session, but TAS could not save the change to preferences.')
            warn.append('')
            warn.append('Please open Preferences -> File Locations, click Save, and then restart JMRI.')
            warn.append('')
            warn.append('Requested location:')
            warn.append(' ' + str(tasDir))
            warn.append('Current reported location:')
            warn.append(' ' + str(updatedPath))
            try:
                JOptionPane.showMessageDialog(None, chr(10).join(warn), 'TAS', JOptionPane.WARNING_MESSAGE)
            except Exception:
                pass
            return

        warn = []
        warn.append('TAS could not confirm the scripts directory change automatically.')
        warn.append('')
        warn.append('Requested location:')
        warn.append(' ' + str(tasDir))
        warn.append('Current reported location:')
        warn.append(' ' + str(updatedPath))
        warn.append('')
        warn.append('Please set Preferences -> File Locations -> Jython Script Location manually,')
        warn.append('save preferences, and restart JMRI.')
        try:
            JOptionPane.showMessageDialog(None, chr(10).join(warn), 'TAS', JOptionPane.WARNING_MESSAGE)
        except Exception:
            pass
    except Exception:
        return

# Run the check early, before importing other TAS modules.
_EnsureTasScriptsPath()

import TASBeanLookup as TBL
# Optional resolver (profile-first script lookup)
try:
    import TASPathResolver as TPR
except Exception:
    TPR = None
# ------------------ Helpers - profile & memory (JMRI API validated) ------------------

def _IsStartUpScriptEnabled(scriptFileName):

    print("[TAS] Checking script enable for " + scriptFileName)
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
        if mgr is None:
            print("[TAS] StartupActionsManager is None")
            return False

        try:
            actions = mgr.getActions()  # array of StartupModel
        except Exception as ex:
            print("[TAS] getActions() failed: " + str(ex))
            return False

        # Target = portable profile path for comparison
        target = jmri.util.FileUtil.getExternalFilename("profile:jython/" + scriptFileName)
        try:
            TCanon = File(target).getCanonicalPath().lower()
        except Exception as ex:
            print("[TAS] Canonicalize target failed: " + str(ex) + " | target=" + str(target))
            return False

        BaseLower = File(scriptFileName).getName().lower()

        for m in actions:
            try:
                # Only enabled actions
                if not m.isEnabled():  # StartupModel.isEnabled()
                    continue

                # Only consider PerformScriptModel (avoid any getName() calls)
                if not isinstance(m, jmri.util.startup.PerformScriptModel):
                    continue

                # Script path
                Path = m.getFileName()  # PerformScriptModel.getFileName()
                if Path is None:
                    continue

                try:
                    PCanon = File(str(Path)).getCanonicalPath().lower()
                except Exception as exCanon:
                    print("[TAS] Canonicalize model path failed: " + str(exCanon) + " | path=" + str(Path))
                    continue

                # Robust match: canonical equality OR tolerant filename suffix
                if PCanon == TCanon:
                    print("[TAS] Match: canonical equality")
                    return True
                if PCanon.endswith(File.separator + BaseLower) or PCanon.endswith("/" + BaseLower) or PCanon.endswith("\\" + BaseLower):
                    print("[TAS] Match: tolerant filename suffix")
                    return True

            except Exception as exModel:
                print("[TAS] Model check failed: " + str(exModel))
                continue

        print("[TAS] Script not found as enabled Start-Up item")
        return False

    except Exception as ex:
        print("[TAS] Script checker exception: " + str(ex))
        return False

def _DebugPrintStartUp():
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
        actions = mgr.getActions()
        print("[TAS] -- Start-Up actions --")
        for m in actions:
            try:
                name = m.getName()
            except:
                name = "<no name>"
            enabled = False
            try:
                enabled = m.isEnabled()
            except:
                pass
            klass = m.getClass().getName()
            path = None
            if "PerformScriptModel" in klass:
                try:
                    path = m.getFileName()
                except:
                    path = "<no fileName>"
            print("[TAS]  class=" + klass + " | enabled=" + str(enabled) + " | name=" + str(name) + " | fileName=" + str(path))
    except Exception as ex:
        print("[TAS] Debug Start-Up print failed: " + str(ex))


# ------------------ Start-Up path mismatch detection & fix ------------------
# Detect when Start-Up actions point at a different copy of a TAS script than the profile:jython copy.
# Offer the user a modal dialog to fix this by disabling the wrong entries and enabling the correct ones.

# Scripts that TAS commonly installs as Start-Up actions.
_TASStartUpScriptNames = [
    'TimetableAutomation.py',
    'CheckWhenTimeChanges.py',
    'DayTracker.py',
    'TimeWarpChecker.py',
    'DayNight.py',
    'WeatherGenerator.py',
    'LastReportedDirection.py',
    'TASFastClockStartup.py',
]

_StartupPathCheckDone = False

def _CanonLower(p):
    try:
        return File(str(p)).getCanonicalPath().lower()
    except:
        try:
            return str(p).lower()
        except:
            return ''

def _StartupMgr():
    try:
        return jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
    except:
        return None

def _ActiveProfile():
    try:
        pm = jmri.profile.ProfileManager.getDefault()
        if pm is None:
            return None
        return pm.getActiveProfile()
    except:
        return None

def _ProfileJythonScriptPath(scriptFileName):
    try:
        return jmri.util.FileUtil.getExternalFilename('profile:jython/' + str(scriptFileName))
    except:
        return None

def _FindPerformScriptModelsByBaseName(baseLower):
    models = []
    mgr = _StartupMgr()
    if mgr is None:
        return models
    try:
        actions = mgr.getActions()
    except:
        return models
    for m in actions:
        try:
            if not isinstance(m, jmri.util.startup.PerformScriptModel):
                continue
            p = m.getFileName()
            if p is None:
                continue
            b = File(str(p)).getName().lower()
            if b == baseLower:
                models.append(m)
        except:
            continue
    return models

def _BuildStartUpPathMismatchReport():
    # Returns a list of dicts describing mismatches for scripts that are ENABLED from a non-profile path.
    mismatches = []
    for fn in _TASStartUpScriptNames:
        try:
            target = _ProfileJythonScriptPath(fn)
            if target is None:
                continue
            # Only attempt auto-fix if the profile copy actually exists.
            try:
                if not File(str(target)).exists():
                    continue
            except:
                continue
            targetCanon = _CanonLower(target)
            baseLower = File(fn).getName().lower()
            models = _FindPerformScriptModelsByBaseName(baseLower)
            wrongEnabled = []
            correctModel = None
            for m in models:
                try:
                    p = m.getFileName()
                    pCanon = _CanonLower(p)
                    if pCanon == targetCanon:
                        correctModel = m
                    else:
                        if m.isEnabled():
                            wrongEnabled.append({'model': m, 'path': str(p)})
                except:
                    continue
            if wrongEnabled:
                mismatches.append({
                    'file': fn,
                    'target': str(target),
                    'targetCanon': targetCanon,
                    'wrongEnabled': wrongEnabled,
                    'hasCorrect': (correctModel is not None),
                    'correctEnabled': (correctModel.isEnabled() if correctModel is not None else False),
                })
        except:
            continue
    return mismatches

def _ApplyStartUpPathFix(mismatches):
    # Disable wrong enabled entries and ensure a correct entry is enabled for each script.
    mgr = _StartupMgr()
    if mgr is None:
        return (False, 'StartupActionsManager unavailable')
    changed = False
    for rec in (mismatches or []):
        try:
            fn = rec.get('file')
            target = rec.get('target')
            if fn is None or target is None:
                continue
            try:
                if not File(str(target)).exists():
                    continue
            except:
                continue
            targetCanon = _CanonLower(target)
            baseLower = File(str(fn)).getName().lower()
            models = _FindPerformScriptModelsByBaseName(baseLower)
            correctModel = None
            for m in models:
                try:
                    p = m.getFileName()
                    if _CanonLower(p) == targetCanon:
                        correctModel = m
                        break
                except:
                    continue
            for w in rec.get('wrongEnabled', []):
                try:
                    m = w.get('model')
                    if m is not None and m.isEnabled():
                        m.setEnabled(False)
                        changed = True
                except:
                    continue
            if correctModel is None:
                try:
                    correctModel = jmri.util.startup.PerformScriptModel()
                    correctModel.setFileName(str(target))
                    correctModel.setEnabled(True)
                    mgr.addAction(correctModel)
                    changed = True
                except:
                    correctModel = None
            else:
                try:
                    if not correctModel.isEnabled():
                        correctModel.setEnabled(True)
                        changed = True
                except:
                    pass
        except:
            continue
    if changed:
        try:
            prof = _ActiveProfile()
            if prof is not None:
                mgr.savePreferences(prof)
        except:
            pass
        try:
            mgr.setRestartRequired()
        except:
            pass
    return (True, 'ok' if changed else 'nochange')

def _ShowStartUpPathMismatchDialog(mismatches):
    # Returns True if user chose to fix.
    try:
        if not mismatches:
            return False
        lines = []
        lines.append('Some Timetable Automation System start-up scripts are enabled from an unexpected folder.')
        lines.append('This can cause older versions of scripts to run even after you install an update.')
        lines.append('')
        for rec in mismatches:
            try:
                fn = rec.get('file')
                target = rec.get('target')
                lines.append('Script: ' + str(fn))
                lines.append('Expected: ' + str(target))
                for w in rec.get('wrongEnabled', []):
                    try:
                        lines.append('Currently enabled from: ' + str(w.get('path')))
                    except:
                        pass
                lines.append('')
            except:
                continue
        lines.append('Fixing this will disable the wrong entries and enable the correct ones.')
        lines.append('A restart of JMRI will be required for the change to take full effect.')
        msg = '\n'.join(lines)
        options = ['Fix now', 'Ignore']
        choice = JOptionPane.showOptionDialog(None, msg, 'TAS start-up scripts location',
            JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE, None, options, options[0])
        return (choice == 0)
    except:
        return False

def _CheckStartUpPathsOnce():
    global _StartupPathCheckDone
    if _StartupPathCheckDone:
        return
    _StartupPathCheckDone = True
    try:
        mismatches = _BuildStartUpPathMismatchReport()
    except:
        mismatches = []
    if not mismatches:
        return
    doFix = _ShowStartUpPathMismatchDialog(mismatches)
    if not doFix:
        return
    ok, status = _ApplyStartUpPathFix(mismatches)
    if ok:
        try:
            if status == 'ok':
                JOptionPane.showMessageDialog(None, 'Start-up script paths updated. Please restart JMRI.', 'TAS', JOptionPane.INFORMATION_MESSAGE)
        except:
            pass
    else:
        try:
            JOptionPane.showMessageDialog(None, 'Could not update start-up script paths: ' + str(status), 'TAS', JOptionPane.ERROR_MESSAGE)
        except:
            pass


# ------------------ Dual-install (both locations) detection ------------------
# Backwards compatibility: TAS can run from the legacy scripts directory OR from profile:jython.
# However, having TAS scripts in BOTH places is an error condition, because it can cause mixed versions
# to be loaded unpredictably.
# This check warns the user and explains how to fix it.

_TASDualInstallCheckDone = False

_TASCoreScriptNamesForLocationCheck = [
    'TimetableAutomation.py',
    'TASSetup.py',
    'TASWiz.py',
    'RunWTT.py',
    'CheckWhenTimeChanges.py',
    'WorkingCreator.py',
    'DisruptionGenerator.py',
    'TASFastClockStartup.py',
]

def _DirContainsAnyOf(dirPath, fileNames):
    try:
        if dirPath is None:
            return False
        d = str(dirPath)
        if d.strip() == '':
            return False
        for fn in (fileNames or []):
            try:
                p = os.path.join(d, str(fn))
                if File(p).exists() and File(p).isFile():
                    return True
            except:
                pass
        return False
    except:
        return False

def _DirHasAnyPyUnder(dirPath):
    try:
        if dirPath is None:
            return False
        d = str(dirPath)
        if d.strip() == '' or (not os.path.isdir(d)):
            return False
        for root, dirs, files in os.walk(d):
            for fn in files:
                try:
                    if str(fn).lower().endswith('.py'):
                        return True
                except:
                    pass
        return False
    except:
        return False

def _CheckForDualInstallAndWarnOnce():
    global _TASDualInstallCheckDone
    if _TASDualInstallCheckDone:
        return
    _TASDualInstallCheckDone = True

    profJython = None
    legacyScripts = None
    try:
        profJython = jmri.util.FileUtil.getExternalFilename('profile:jython')
    except:
        profJython = None
    try:
        legacyScripts = jmri.util.FileUtil.getScriptsPath()
    except:
        legacyScripts = None

    if profJython is None or legacyScripts is None:
        return

    try:
        profCanon = File(str(profJython)).getCanonicalPath()
    except:
        profCanon = str(profJython)
    try:
        legCanon = File(str(legacyScripts)).getCanonicalPath()
    except:
        legCanon = str(legacyScripts)

    try:
        if profCanon is not None and legCanon is not None and profCanon.lower() == legCanon.lower():
            return
    except:
        pass

    profHas = _DirContainsAnyOf(profCanon, _TASCoreScriptNamesForLocationCheck)
    legHas = _DirContainsAnyOf(legCanon, _TASCoreScriptNamesForLocationCheck)

    if not (profHas and legHas):
        return

    profWorkings = None
    legWorkings = None
    try:
        profWorkings = os.path.join(str(profCanon), 'workings')
    except:
        profWorkings = None
    try:
        legWorkings = os.path.join(str(legCanon), 'workings')
    except:
        legWorkings = None

    profWorkHas = _DirHasAnyPyUnder(profWorkings)
    legWorkHas = _DirHasAnyPyUnder(legWorkings)

    lines = []
    lines.append('TAS has been found in two different folders.')
    lines.append('This is a problem because it can cause mixed versions of scripts to run.')
    lines.append('')
    lines.append('Main (recommended) folder:')
    lines.append('  ' + str(profCanon))
    lines.append('Legacy folder:')
    lines.append('  ' + str(legCanon))
    lines.append('')
    lines.append('How to fix this:')
    lines.append('1) Close JMRI.')
    lines.append('2) Delete or rename the legacy TAS script files in the legacy folder above.')
    lines.append('   (If that folder is under Program Files, you may need administrator rights.)')
    if legWorkHas:
        lines.append('3) Move your working scripts from the legacy workings folder to the main folder:')
        lines.append('   From: ' + str(legWorkings))
        lines.append('   To:   ' + str(profWorkings))
        if profWorkHas:
            lines.append('   Note: working scripts already exist in the main folder; do not mix - choose one set to keep.')
    else:
        lines.append('3) No working scripts were found in the legacy workings folder.')
    lines.append('4) Restart JMRI after cleaning up.')
    lines.append('')
    lines.append('If you are unsure, keep the main folder and remove the legacy one.')

    msg = '\n'.join(lines)

    try:
        JOptionPane.showMessageDialog(None, msg, 'TAS installation problem', JOptionPane.WARNING_MESSAGE)
    except:
        try:
            print('[TAS] Dual-install warning dialog failed')
            print(msg)
        except:
            pass
def GetActiveProfileName():
    try:
        pm = jmri.profile.ProfileManager.getDefault()
        if pm is not None:
            name = pm.getActiveProfileName()
            if name is not None and len(name.strip()) > 0:
                return name.strip()
    except Exception as ex:
        print("Profile name lookup failed: " + str(ex))
    return "Current Profile"


def GetTimetableName():
    try:
        # CURRENTTIMETABLE stores the timetable *name* as the Memory value.
        # Use prefix-agnostic suffix lookup via TASBeanLookup.
        val = TBL.SafeGetMemoryValue(TIMETABLE_MEMORY_NAME, "")
        if val is not None:
            s = str(val).strip()
            if len(s) > 0:
                return s
    except Exception as ex:
        print("Timetable name lookup failed: " + str(ex))
    return "Not configured"

def RunExternalScript(FileName, FriendlyName, Arg=None):
    # Execute another script located in the JMRI scripts directory (portable path).
    # Log errors to console (with traceback) and also show a dialog.
    try:
        # Resolve script location (prefer profile:jython, then scripts:)
        fullPath = None
        try:
            if TPR is not None:
                fullPath = TPR.ResolveScriptReadPath(FileName)
        except Exception:
            fullPath = None
        if fullPath is None:
            fullPath = jmri.util.FileUtil.getExternalFilename("scripts:" + FileName)  # portable to external
        import java.io as jio
        f = jio.File(fullPath)
        if (not f.exists()) or (not f.isFile()):
            msg = FriendlyName + " is not yet implemented.\n(" + FileName + " was not found in the scripts folder.)"
            print("[TAS] " + msg)
            JOptionPane.showMessageDialog(None, msg, "TAS", JOptionPane.INFORMATION_MESSAGE)
            return

        # Fresh globals to avoid stale state between runs (prevents leaking names into the caller)
        SafeGlobals = {"__name__": "__main__", "jmri": jmri}
        try:
            if str(FileName) == 'TASSetup.py':
                SafeGlobals['TAS_MAINMENU_THEME_REFRESH_CALLBACK'] = RefreshMainMenuTheme
        except:
            pass
        execfile(fullPath, SafeGlobals)

        # If the loaded script defines an entrypoint Show(...), invoke it.
        try:
            if "Show" in SafeGlobals:
                fn = SafeGlobals["Show"]
                if hasattr(fn, "__call__"):
                    if Arg is None:
                        fn()              # default behaviour inside TASHelp is "General"
                    else:
                        fn(str(Arg))      # pass a topic name WITHOUT .txt (e.g., "Signals")
        except Exception as callEx:
            # Console (with traceback)
            try:
                import traceback
                print("[TAS] " + FriendlyName + " entrypoint failed: " + str(callEx))
                print(traceback.format_exc())
            except:
                print("[TAS] " + FriendlyName + " entrypoint failed (traceback unavailable): " + str(callEx))
            # Dialog
            try:
                JOptionPane.showMessageDialog(
                    None,
                    FriendlyName + " entrypoint failed: " + str(callEx),
                    "TAS",
                    JOptionPane.INFORMATION_MESSAGE
                )
            except:
                pass

    except Exception as ex:
        # Console (with traceback)
        try:
            import traceback
            print("[TAS] " + FriendlyName + " failed: " + str(ex))
            print(traceback.format_exc())
        except:
            print("[TAS] " + FriendlyName + " failed (traceback unavailable): " + str(ex))
        # Dialog
        try:
            JOptionPane.showMessageDialog(
                None,
                FriendlyName + " failed: " + str(ex),
                "TAS",
                JOptionPane.INFORMATION_MESSAGE
            )
        except:
            pass

# ------------------ Font helpers ------------------

def PreferredFontFamily():
    fams = set(GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames())
    for fam in ["Gill Sans MT", "Gill Sans", "Arial", "Helvetica", "SansSerif"]:
        if fam in fams:
            return fam
    return "SansSerif"

def FitFontForSingleLine(g, family, style, maxPt, minPt, text, maxWidth):
    size = maxPt
    while size >= minPt:
        f = Font(family, style, size)
        if g.getFontMetrics(f).stringWidth(text) <= maxWidth:
            return f
        size -= 1
    return Font(family, style, minPt)

def BuildTitleLines(g, family, style, maxPt, minPt, text, maxWidth):
    """
    Lossless two-line builder:
    - For size maxPt..minPt:
      * Fill line1 greedily (word by word) without exceeding width.
      * Put ALL remaining words on line2.
      * If both lines fit, return (font, [line1, line2]) where line2 may be "" if nothing remains.
    - If nothing fits in two lines even at minPt, fall back to single-line font sized to fit.
    """
    words = text.split()
    for size in range(maxPt, minPt - 1, -1):
        f = Font(family, style, size)
        fm = g.getFontMetrics(f)
        line1 = ""
        idx = 0
        while idx < len(words):
            trial = words[idx] if line1 == "" else (line1 + " " + words[idx])
            if fm.stringWidth(trial) <= maxWidth:
                line1 = trial
                idx += 1
            else:
                break
        line2 = " ".join(words[idx:]) if idx < len(words) else ""
        if line2 == "":
            return (f, [line1])
        if fm.stringWidth(line2) <= maxWidth:
            return (f, [line1, line2])
    f1 = FitFontForSingleLine(g, family, style, maxPt, minPt, text, maxWidth)
    return (f1, [text])

# ------------------ Licence loader - external scripts: Licence.txt (portable path) ------------------

def LoadLicenceText():
    try:
        stream = None
        try:
            if TPR is not None:
                stream = TPR.FindInputStreamFor("Licence.txt")
        except Exception:
            stream = None
        if stream is None:
            stream = jmri.util.FileUtil.findInputStream("scripts:Licence.txt")
        if stream is None:
            return None
        try:
            reader = BufferedReader(InputStreamReader(stream, "US-ASCII"))
            lines = []
            while True:
                line = reader.readLine()
                if line is None:
                    break
                lines.append(line)
            return "\n".join(lines)
        finally:
            stream.close()
    except Exception as ex:
        print("Licence load failed: " + str(ex))
        return None

# Compatibility helper for legacy external scripts that expect ReadMemStr(...)
def ReadMemStr(Name, Default=""):
    return TBL.SafeGetOrCreateMemoryValue(Name, Default)
    
# ------------------ Change log loader - external scripts: changelog.txt (portable path) ------------------

def LoadChangeLogText():
    try:
        stream = None
        try:
            if TPR is not None:
                stream = TPR.FindInputStreamFor("changelog.txt")
        except Exception:
            stream = None
        if stream is None:
            stream = jmri.util.FileUtil.findInputStream("scripts:changelog.txt")
        if stream is None:
            return None
        try:
            reader = BufferedReader(InputStreamReader(stream, "US-ASCII"))
            lines = []
            while True:
                line = reader.readLine()
                if line is None:
                    break
                lines.append(line)
            return "\n".join(lines)
        finally:
            stream.close()
    except Exception as ex:
        print("Change log load failed: " + str(ex))
        return None


# ------------------ Cover panel ------------------

class CoverPanel(JPanel):
    # Tunable layout constants
    TITLE_MAX_PT = 66
    TITLE_MIN_PT = 33
    TITLE_SAFETY_GAP = 2
    SUBTITLE_GAP = 14
    POST_SUBTITLE_GAP = 32
    PROFILE_MAX_PT = 44
    PROFILE_MIN_PT = 26
    PROFILE_TIMETABLE_GAP = 2
    TIMETABLE_PT = 24
    # Single-column button geometry
    BTN_W = 240
    BTN_H = 36
    BTN_BASELINE_Y = 18 + 14 + 356  # margin + innerPad + baseline

    def __init__(self):
        JPanel.__init__(self)
        self.setOpaque(True)
        # Use TASCOVERCOLOUR from memory (default "240,238,220")
        memRgb = TBL.SafeGetOrCreateMemoryValue("TASCOVERCOLOUR", "240,238,220")
        try:
            parts = [p.strip() for p in str(memRgb).split(",")]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))  
                b = max(0, min(255, int(float(parts[2]))))
                self.setBackground(Color(r, g, b))
            else:
                self.setBackground(Color(240, 238, 220))
        except:
            self.setBackground(Color(240, 238, 220))
            
        # Inner panel background colour from TASINNERCOLOUR (default "220,235,220")
        memRgbInner = TBL.SafeGetOrCreateMemoryValue("TASINNERCOLOUR", "220,235,220")
        try:
            parts = [p.strip() for p in str(memRgbInner).split(",")]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                self.InnerBgColor = Color(r, g, b)
            else:
                self.InnerBgColor = Color(220,235,220)
        except:
            self.InnerBgColor = Color(220,235,220)
        
        self.setLayout(None)
        
        # Ink (text/lines/boxes/button outlines) colour from TASINKCOLOUR (default "0,0,0")
        memRgbInk = TBL.SafeGetOrCreateMemoryValue("TASINKCOLOUR", "0,0,0")
        try:
            parts = [p.strip() for p in str(memRgbInk).split(",")]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                self.InkColor = Color(r, g, b)
            else:
                self.InkColor = Color(0, 0, 0)
        except:
            self.InkColor = Color(0, 0, 0)
        
        # Cover ink colour (main menu text/lines/button outlines) from TASCOVERINKCOLOUR.
        # This allows the cover (main menu) ink to differ from the general interface ink.
        # If not set or invalid, fall back to TASINKCOLOUR.
        self.CoverInkColor = self.InkColor
        memRgbCoverInk = TBL.SafeGetOrCreateMemoryValue("TASCOVERINKCOLOUR", "")
        try:
            if memRgbCoverInk is not None and len(str(memRgbCoverInk).strip()) > 0:
                parts = [p.strip() for p in str(memRgbCoverInk).split(",")]
                if len(parts) == 3:
                    r = max(0, min(255, int(float(parts[0]))))
                    g = max(0, min(255, int(float(parts[1]))))
                    b = max(0, min(255, int(float(parts[2]))))
                    self.CoverInkColor = Color(r, g, b)
        except:
            self.CoverInkColor = self.InkColor
        # Helper: if ink changes at runtime, apply to all buttons
        def _ApplyInkToButtons():
            try:
                for b in (self.BtnShowTimetable, self.BtnTimeWarp, self.BtnPublic, self.BtnSignallers,
                          self.BtnWeather, self.BtnSetup, self.BtnHelp, self.BtnAbout):
                    b.setForeground(getattr(self, 'CoverInkColor', self.InkColor))
                    b.setBorder(BorderFactory.createLineBorder(getattr(self, 'CoverInkColor', self.InkColor), 1))
            except:
                pass

        # Expose helper for possible runtime use
        self.ApplyInkToButtons = _ApplyInkToButtons

        memFont = TBL.SafeGetOrCreateMemoryValue("TAS_FONT_FAMILY", PreferredFontFamily())
        self.FontFamily = memFont if memFont else PreferredFontFamily()
        self.ProfileName = GetActiveProfileName()
        self.TimetableName = GetTimetableName()

        # Buttons (single column; Show/Time warp at top)
        self.BtnShowTimetable = self.MakeBtn("Show timetable")
        self.BtnTimeWarp = self.MakeBtn("Time warp")
        self.BtnPublic = self.MakeBtn("Public information displays")
        self.BtnSignallers = self.MakeBtn("Signallers' displays")
        self.BtnWeather = self.MakeBtn("Weather forecast")
        self.BtnSetup = self.MakeBtn("Setup")
        self.BtnHelp = self.MakeBtn("Help")
        self.BtnAbout = self.MakeBtn("About")
        for b in (self.BtnShowTimetable, self.BtnTimeWarp, self.BtnPublic, self.BtnSignallers,
                  self.BtnWeather, self.BtnSetup, self.BtnHelp, self.BtnAbout):
            self.add(b)

        # Apply ink colour to buttons now that they exist
        try:
            self.ApplyInkToButtons()
        except:
            pass
        
        # Actions
        self.BtnShowTimetable.addActionListener(lambda e: RunExternalScript("WTTDisplay.py", "Show timetable"))
        self.BtnTimeWarp.addActionListener(lambda e: self.OnTimeWarp(e))
        self.BtnPublic.addActionListener(lambda e: self.RunConfiguredPublic())
        self.BtnSignallers.addActionListener(lambda e: self.RunConfiguredSignallers())
        self.BtnWeather.addActionListener(lambda e: self.OnWeatherForecast())
        self.BtnSetup.addActionListener(lambda e: RunExternalScript("TASSetup.py", "Setup"))
        self.BtnHelp.addActionListener(lambda e: RunExternalScript("TASHelp.py", "Help"))
        self.BtnAbout.addActionListener(lambda e: self.ShowAbout())

        # Initial enabled/disabled state based on IMALLOWTIMEWARP
        self.UpdateTimeWarpEnabled()
        # Update enabled/disabled every second on the EDT
        self.TimeWarpTimer = Timer(1000, lambda e: self.UpdateTimeWarpEnabled())
        self.TimeWarpTimer.setRepeats(True)
        self.TimeWarpTimer.start()

    def MakeBtn(self, text):
        btn = JButton(text)
        btn.setFont(Font(self.FontFamily, Font.BOLD, 14))
        btn.setFocusPainted(False)
        btn.setContentAreaFilled(False)
        btn.setOpaque(False)
        # Use ink colour for the button text AND outline
        btn.setForeground(getattr(self, 'CoverInkColor', self.InkColor))
        btn.setBorder(BorderFactory.createLineBorder(getattr(self, 'CoverInkColor', self.InkColor), 1))
        return btn

    def ShowStub(self, name):
        JOptionPane.showMessageDialog(self, name + " is not implemented yet.", "TAS", JOptionPane.INFORMATION_MESSAGE)

    def ShowAbout(self):
        dlg = AboutDialog(self, self.FontFamily)
        dlg.setLocationRelativeTo(self)
        dlg.setVisible(True)

    def IsTimeWarpAllowed(self):
        s = str(TBL.SafeGetOrCreateMemoryValue("ALLOWTIMEWARP", "")).strip().lower()
        return s in ("true", "yes", "1", "on", "enabled")

    def UpdateTimeWarpEnabled(self):
        try:
            self.BtnTimeWarp.setEnabled(self.IsTimeWarpAllowed())
        except Exception:
            pass

    def OnTimeWarp(self, e):
        if self.IsTimeWarpAllowed():
            RunExternalScript("TimeWarp.py", "Time warp")
    
    def OnWeatherForecast(self):
        # Decide which UI to run based on Memories, and handle disabled generator.
        wxEnabled = _IsStartUpScriptEnabled("WeatherGenerator.py")  # from Start-Up list  [1]
        uiChoice  = str(TBL.SafeGetOrCreateMemoryValue("WX_UI", "Newspaper")).strip()
        cloudStr  = str(TBL.SafeGetOrCreateMemoryValue("CLOUDCOVERPCT", "0")).strip()
        try:
            cloud = int(float(cloudStr))
        except:
            cloud = 0
        cloud = max(0, min(100, cloud))

        if not wxEnabled:
            # Basic dialog per spec
            JOptionPane.showMessageDialog(self,
                "Weather generation disabled. Fixed cloud cover: %d%%" % cloud,
                "Weather forecast", JOptionPane.INFORMATION_MESSAGE)
            return

        # Weather generation enabled -> run chosen UI
        if uiChoice.lower() == "app":
            RunExternalScript("WeatherForecastUIApp.py", "Weather forecast (App)")
        else:
            # Newspaper UI
            RunExternalScript("WeatherForecastUINewspaper.py", "Weather forecast (Newspaper)")
    
    # Run configured Display scripts (CSV of .py filenames in memories)
    def RunConfiguredPublic(self):
        try:
            raw = TBL.SafeGetOrCreateMemoryValue("PUBLICDISPLAYLIST", "")
            names = [s.strip() for s in raw.split(",") if len(s.strip()) > 0]
            # Run each chosen script (do nothing if none selected)
            for fname in names:
                RunExternalScript(fname, self.FRIENDLY_NAME(fname, "Public display"))
        except Exception as ex:
            try:
                import traceback
                print("[TAS] Public displays failed: " + str(ex))
                print(traceback.format_exc())
            except:
                pass

    def RunConfiguredSignallers(self):
        try:
            raw = TBL.SafeGetOrCreateMemoryValue("SIGNALLERDISPLAYLIST", "")
            names = [s.strip() for s in raw.split(",") if len(s.strip()) > 0]
            for fname in names:
                RunExternalScript(fname, self.FRIENDLY_NAME(fname, "Signallers' display"))
        except Exception as ex:
            try:
                import traceback
                print("[TAS] Signallers' displays failed: " + str(ex))
                print(traceback.format_exc())
            except:
                pass

    # Friendly name mapping for well-known scripts (fallback to filename)
    def FRIENDLY_NAME(self, FileName, Fallback):
        try:
            m = {
                "NSEClock.py": "NSE clock",
                "PIDCRTSingle.py": "Per platform CRT PID",
                "PIDCRTSummary.py": "Summary of departures CRT PID",
                "PIDFingerboard.py": "Fingerboard",
                "PIDSmall.py": "Small modern platform PID",
                "TRUST-TRJA.py": "TRUST TRJA",
            }
            return m.get(FileName, Fallback)
        except:
            return Fallback


    # Refresh theme values (colours/fonts) from memories and repaint.
    def RefreshThemeFromMemories(self):
        # Re-read all theme-related memories used by the main menu.
        try:
            memRgb = TBL.SafeGetOrCreateMemoryValue('TASCOVERCOLOUR', '240,238,220')
            parts = [p.strip() for p in str(memRgb).split(',')]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                self.setBackground(Color(r, g, b))
        except:
            pass
        try:
            memRgbInner = TBL.SafeGetOrCreateMemoryValue('TASINNERCOLOUR', '220,235,220')
            parts = [p.strip() for p in str(memRgbInner).split(',')]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                self.InnerBgColor = Color(r, g, b)
        except:
            pass
        try:
            memRgbInk = TBL.SafeGetOrCreateMemoryValue('TASINKCOLOUR', '0,0,0')
            parts = [p.strip() for p in str(memRgbInk).split(',')]
            if len(parts) == 3:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                self.InkColor = Color(r, g, b)
        except:
            pass
        # Cover ink colour may differ; fall back to TASINKCOLOUR if missing/invalid.
        try:
            self.CoverInkColor = getattr(self, 'InkColor', Color(0,0,0))
            memRgbCoverInk = TBL.SafeGetOrCreateMemoryValue('TASCOVERINKCOLOUR', '')
            if memRgbCoverInk is not None and len(str(memRgbCoverInk).strip()) > 0:
                parts = [p.strip() for p in str(memRgbCoverInk).split(',')]
                if len(parts) == 3:
                    r = max(0, min(255, int(float(parts[0]))))
                    g = max(0, min(255, int(float(parts[1]))))
                    b = max(0, min(255, int(float(parts[2]))))
                    self.CoverInkColor = Color(r, g, b)
        except:
            try:
                self.CoverInkColor = getattr(self, 'InkColor', Color(0,0,0))
            except:
                pass
        try:
            memFont = TBL.SafeGetOrCreateMemoryValue('TAS_FONT_FAMILY', PreferredFontFamily())
            self.FontFamily = memFont if memFont else PreferredFontFamily()
        except:
            pass
        # Apply ink and font to buttons if they exist.
        try:
            fam = getattr(self, 'FontFamily', PreferredFontFamily())
            ink = getattr(self, 'CoverInkColor', getattr(self, 'InkColor', Color(0,0,0)))
            for b in (self.BtnShowTimetable, self.BtnTimeWarp, self.BtnPublic, self.BtnSignallers,
                self.BtnWeather, self.BtnSetup, self.BtnHelp, self.BtnAbout):
                try:
                    b.setFont(Font(fam, Font.BOLD, 14))
                except:
                    pass
                try:
                    b.setForeground(ink)
                    b.setBorder(BorderFactory.createLineBorder(ink, 1))
                except:
                    pass
        except:
            pass
        # Refresh cached profile and timetable names (these are not re-read in paintComponent).
        try:
            self.ProfileName = GetActiveProfileName()
        except:
            pass
        try:
            self.TimetableName = GetTimetableName()
        except:
            pass
        try:
            self.repaint()
        except:
            pass


    def paintComponent(self, g):
        super(CoverPanel, self).paintComponent(g)
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        w = self.getWidth()
        h = self.getHeight()

        # Outer and inner borders
        margin = 18
        innerPad = 14
        g.setColor(self.InnerBgColor)
        g.fillRect(margin, margin, w - 2 * margin, h - 2 * margin)
        g.setColor(self.CoverInkColor)
        g.setStroke(BasicStroke(1.5))
        g.drawRect(margin, margin, w - 2 * margin, h - 2 * margin)
        g.drawRect(margin + innerPad, margin + innerPad, w - 2 * (margin + innerPad), h - 2 * (margin + innerPad))
        innerLeft = margin + innerPad + 20
        innerRight = w - (margin + innerPad + 20)
        innerWidth = innerRight - innerLeft

        # Top line + SECTION box
        y = margin + innerPad + 40
        g.setFont(Font(self.FontFamily, Font.PLAIN, 14))
        railwayText = TBL.SafeGetOrCreateMemoryValue("RAILWAYCO", "BRITISH RAILWAYS")
        regionText = TBL.SafeGetOrCreateMemoryValue("REGION", "LONDON MIDLAND REGION")
        g.drawString(railwayText + " " + regionText, innerLeft, y)
        
        g.setFont(Font(self.FontFamily, Font.BOLD, 14))
        secText = TBL.SafeGetOrCreateMemoryValue("SECTION", "SECTION B")

        # If SECTION text is blank/whitespace, do NOT draw the box or the label
        if secText is not None and len(str(secText).strip()) > 0:
            fmSec = g.getFontMetrics()
            textW = fmSec.stringWidth(secText)
            textH = fmSec.getAscent() + fmSec.getDescent()
            # Padding inside the box (left/right/top/bottom)
            padX = 12
            padY = 6
            # Compute box width/height to fit the text with padding
            secW = textW + 2 * padX
            secH = textH + 2 * padY
            # Position box flush to the inner right edge, aligned with the railway/region baseline
            secX = innerRight - secW
            secY = y - (fmSec.getAscent() + padY)  # align text baseline with 'y'
            # Draw the box
            g.drawRect(secX, secY, secW, secH)
            # Center the text horizontally and vertically inside the box
            textX = secX + (secW - textW) // 2
            textY = secY + padY + fmSec.getAscent()
            g.drawString(secText, textX, textY)
        # else: box is intentionally omitted

        # Headline (lossless two-line builder; never drops words)
        y += 54
        titleText = "TIMETABLE AUTOMATION SYSTEM"
        (titleFont, titleLines) = BuildTitleLines(
            g, self.FontFamily, Font.BOLD, self.TITLE_MAX_PT, self.TITLE_MIN_PT, titleText, innerWidth
        )
        g.setFont(titleFont)
        fmTitle = g.getFontMetrics()
        for i in range(len(titleLines)):
            line = titleLines[i]
            x = innerLeft + (innerWidth - fmTitle.stringWidth(line)) // 2
            g.drawString(line, x, y + i * fmTitle.getHeight())
        lastBaseline = y + (len(titleLines) - 1) * fmTitle.getHeight()
        lastBottom = lastBaseline + fmTitle.getDescent()
        y = lastBottom + self.TITLE_SAFETY_GAP

        y += self.SUBTITLE_GAP
        subText = "(For automatic and manual running of trains to a timetable)"
        g.setFont(Font(self.FontFamily, Font.PLAIN, 14))
        fmSub = g.getFontMetrics()
        g.drawString(subText, innerLeft + (innerWidth - fmSub.stringWidth(subText)) // 2, y)
        subtitleBottom = y + fmSub.getDescent()

        # Short horizontal line between subtitle and profile (centered)
        lineLen1 = 100
        lineY1 = subtitleBottom + self.POST_SUBTITLE_GAP - 12
        lineX1 = innerLeft + (innerWidth - lineLen1) // 2
        g.drawLine(lineX1, lineY1, lineX1 + lineLen1, lineY1)

        # Profile name (larger; wraps to 2 lines max)
        profText = self.ProfileName.upper()
        (profFont, profLines) = BuildTitleLines(
            g, self.FontFamily, Font.BOLD, self.PROFILE_MAX_PT, self.PROFILE_MIN_PT, profText, innerWidth
        )
        g.setFont(profFont)
        fmProf = g.getFontMetrics()
        y = subtitleBottom + self.POST_SUBTITLE_GAP + fmProf.getAscent()
        for i in range(len(profLines)):
            line = profLines[i]
            x = innerLeft + (innerWidth - fmProf.stringWidth(line)) // 2
            g.drawString(line, x, y + i * fmProf.getHeight())
        y += len(profLines) * fmProf.getHeight()
        y += self.PROFILE_TIMETABLE_GAP

        # Timetable name (fixed size)
        ttName = self.TimetableName
        g.setFont(Font(self.FontFamily, Font.PLAIN, self.TIMETABLE_PT))
        fmTT = g.getFontMetrics()
        g.drawString(ttName, innerLeft + (innerWidth - fmTT.stringWidth(ttName)) // 2, y)

        # Short horizontal line between profile/timetable block and buttons (centered)
        lineLen2 = 100
        lineY2 = y + fmTT.getDescent() + 18
        lineX2 = innerLeft + (innerWidth - lineLen2) // 2
        g.drawLine(lineX2, lineY2, lineX2 + lineLen2, lineY2)

        # --- Single-column buttons (Show/Time warp first) ---
        gridTop = self.BTN_BASELINE_Y
        btnW = self.BTN_W
        btnH = self.BTN_H
        x = innerLeft + (innerWidth - btnW) // 2
        rowY = gridTop
        rowGap = 60
        self.BtnShowTimetable.setBounds(x, rowY, btnW, btnH)
        self.BtnTimeWarp.setBounds(x, rowY + rowGap, btnW, btnH)
        self.BtnPublic.setBounds(x, rowY + 2 * rowGap, btnW, btnH)
        self.BtnSignallers.setBounds(x, rowY + 3 * rowGap, btnW, btnH)
        self.BtnWeather.setBounds(x, rowY + 4 * rowGap, btnW, btnH)
        self.BtnSetup.setBounds(x, rowY + 5 * rowGap, btnW, btnH)
        self.BtnHelp.setBounds(x, rowY + 6 * rowGap, btnW, btnH)
        self.BtnAbout.setBounds(x, rowY + 7 * rowGap, btnW, btnH)

        # Footer
        g.setFont(Font(self.FontFamily, Font.PLAIN, 12))
        g.drawString("This system is subject to the GNU GPL v3.0. See About for details.", innerLeft, h - margin - innerPad - 20)

# ------------------ About dialog (external Licence.txt or concise GPL summary) ------------------


class AboutDialog(JDialog):
    def __init__(self, Parent, FontFamily):
        JDialog.__init__(self, SwingUtilities.getWindowAncestor(Parent), "About the Timetable Automation System", True)
        self.setLayout(BorderLayout(8, 8))
        self.setMinimumSize(Dimension(720, 840))
        self.FontFamily = FontFamily

        Header = JPanel()
        Header.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = Insets(8, 8, 4, 8)

        Title = JLabel(SYSTEM_NAME + " - About")
        Title.setFont(Font(FontFamily, Font.BOLD, 18))
        Header.add(Title, gbc)

        gbc.gridy = 1
        Ver = JLabel("Version: " + VERSION)
        Ver.setFont(Font(FontFamily, Font.PLAIN, 14))
        Header.add(Ver, gbc)

        gbc.gridy = 2
        Notice = JLabel("Licensed under the GNU General Public License v3.0.")
        Notice.setFont(Font(FontFamily, Font.PLAIN, 14))
        Header.add(Notice, gbc)

        self.add(Header, BorderLayout.NORTH)

        Tabs = JTabbedPane()

        AboutPanel = JPanel()
        AboutPanel.setLayout(GridBagLayout())
        gbc2 = GridBagConstraints()
        gbc2.gridx = 0
        gbc2.gridy = 0
        gbc2.weightx = 1.0
        gbc2.weighty = 1.0
        gbc2.fill = GridBagConstraints.BOTH

        Info = JTextArea()
        Info.setEditable(False)
        Info.setLineWrap(True)
        Info.setWrapStyleWord(True)
        Info.setFont(Font(FontFamily, Font.PLAIN, 13))
        Info.setText(
            "By James E. Petts 2025-6. Written with the assistance of AI.\n\n"
            "This software is a suite of scripts written for JMRI to allow easy set up and maintenance of realistic U. K. "
            "timetable based model railway operation, including accurate displays of timetables, signallers' interfaces (e.g. TRUST) "
            "and public information displays.\n\n"
            "It also incorporates a system for creating realistic delays and cancellations to scheduled services, as well "
            "as a system for providing accurate, configurable day/night lighting for the layout (using a mix of warm and cool "
            "white LED strips driven by DCC decoders), featuring weather simulation and simulated weather forecasting to explain "
            "the lighting levels and colour balance at any given time.\n\n"
            "This entire suite of scripts is free software: you can redistribute it and/or modify it under the terms of "
            "the GNU General Public License as published by the Free Software Foundation, either version 3 "
            "of the License, or (at your option) any later version."
        )
        AboutPanel.add(JScrollPane(Info), gbc2)
        Tabs.addTab("About", AboutPanel)
             
        # Acknowledgements tab 
        AckPanel = JPanel()
        AckPanel.setLayout(BorderLayout())
        AckText = JTextArea()
        AckText.setEditable(False)
        AckText.setLineWrap(True)
        AckText.setWrapStyleWord(True)
        AckText.setFont(Font(FontFamily, Font.PLAIN, 13))
        AckScroll = JScrollPane(AckText)
        AckPanel.add(AckScroll, BorderLayout.CENTER)

        # Placeholder content (ASCII only). Feel free to overwrite this at runtime.
        AckText.setText(
            "Acknowledgements\n\n"
            "- David Sand (JMRI scripting assistance)\n"
            "- Torben (early testting and bug reporting)\n"
            "- Jean-Louis (early testing and bug reporting)\n"
            "- Jennifer E. Kirk (use of 'Billy's Replacement Speakers')\n"
            "- Microsoft Copilot (doing most of the actual work)\n"
        )
        AckText.setCaretPosition(0)  # Ensure that the top of the text is shown

        Tabs.addTab("Acknowledgements", AckPanel)   

        LicencePanel = JPanel()
        LicencePanel.setLayout(BorderLayout())
        self.Txt = JTextArea()
        self.Txt.setEditable(False)
        self.Txt.setLineWrap(True)
        self.Txt.setWrapStyleWord(True)
        self.Txt.setFont(Font(FontFamily, Font.PLAIN, 12))
        LicencePanel.add(JScrollPane(self.Txt), BorderLayout.CENTER)       
        Tabs.addTab("Licence", LicencePanel)

        # --- Change log tab (reads scripts:changelog.txt) ---
        ChgPanel = JPanel()
        ChgPanel.setLayout(BorderLayout())
        self.ChgTxt = JTextArea()
        self.ChgTxt.setEditable(False)
        self.ChgTxt.setLineWrap(True)
        self.ChgTxt.setWrapStyleWord(True)
        self.ChgTxt.setFont(Font(FontFamily, Font.PLAIN, 12))
        ChgPanel.add(JScrollPane(self.ChgTxt), BorderLayout.CENTER)
        Tabs.addTab("Change log", ChgPanel)

        self.add(Tabs, BorderLayout.CENTER)

        lic = LoadLicenceText()

        if lic is None or len(lic.strip()) == 0:
            self.Txt.setText(
                "GNU GPL v3.0 (summary)\n\n"
                "- Strong copyleft: recipients get complete corresponding source and must preserve the licence.\n"
                "- No warranty: provided \"as is\" without any implied warranties.\n"
                "- Patent protection: prevents discriminatory patent arrangements.\n"
                "- Protects users against restrictions that prevent running modified versions.\n\n"
                "Full licence text:\n"
                "https://www.gnu.org/licenses/gpl-3.0.en.html\n"
            )

        else:
            self.Txt.setText(lic)
        self.Txt.setCaretPosition(0)

        # Load and set Change log text
        chg = LoadChangeLogText()
        if chg is None or len(chg.strip()) == 0:
            self.ChgTxt.setText(
                "Change log\n\n"
                "No changelog.txt found in the scripts folder.\n"
                "Create 'changelog.txt' next to 'Licence.txt' to populate this tab.\n"
            )
        else:
            self.ChgTxt.setText(chg)
        self.ChgTxt.setCaretPosition(0)

        Buttons = JPanel()
        BtnClose = JButton("Close")
        Buttons.add(BtnClose)
        self.add(Buttons, BorderLayout.SOUTH)

        def OnClose(e):
            self.dispose()
        BtnClose.addActionListener(OnClose)

# ------------------ Main frame ------------------


# ---------------- Main menu theme refresh callback ----------------
# TASSetup can call this (when launched from the main menu) to apply any theme changes immediately.
_TASMainMenuFrame = None

def RefreshMainMenuTheme():
    # Refresh the main menu UI (if open) from current memory values.
    def _Do():
        f = None
        try:
            f = _TASMainMenuFrame
        except:
            f = None
        if f is None:
            return
        try:
            if not f.isDisplayable():
                return
        except:
            pass
        p = None
        try:
            p = getattr(f, 'Cover', None)
        except:
            p = None
        if p is None:
            return
        try:
            if hasattr(p, 'RefreshThemeFromMemories'):
                p.RefreshThemeFromMemories()
        except:
            pass
        try:
            p.repaint()
        except:
            pass
        try:
            f.repaint()
        except:
            pass
    try:
        SwingUtilities.invokeLater(_Do)
    except:
        try:
            _Do()
        except:
            pass
class TASWTTStartup(JFrame):
    def __init__(self):
        JFrame.__init__(self, "Timetable Automation System")
        self.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        self.setLayout(BorderLayout())
        self.Cover = CoverPanel()
        self.add(self.Cover, BorderLayout.CENTER)
        self.setSize(600, 980)  # portrait (height fixed)
        self.setLocationByPlatform(True)
      
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)  # 32px icon size
        except Exception as ex:
            print("[TAS] Failed to set main menu icon: " + str(ex))

def Run():
    try:
        UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName())
    except:
        pass
    def Create():
        try:
            _CheckStartUpPathsOnce()
        except Exception as ex:
            try:
                print('[TAS] Start-Up path check failed: ' + str(ex))
            except:
                pass
        try:
            _CheckForDualInstallAndWarnOnce()
        except Exception as ex:
            try:
                print('[TAS] Dual-install check failed: ' + str(ex))
            except:
                pass
        f = TASWTTStartup()
        global _TASMainMenuFrame
        _TASMainMenuFrame = f
        f.setVisible(True)
    SwingUtilities.invokeLater(Create)


SYSTEM_NAME = "Timetable Automation System"
TIMETABLE_MEMORY_NAME = "CURRENTTIMETABLE"  # Memory holding the current timetable name
Run()
