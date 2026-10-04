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

# NOTE: Increment the version in devel *just after* publishing a new version on master.
VERSION = "1.5"
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
# TAS_SYS_PATH_SNIPPET: make the TAS folder importable even when scripts: still points elsewhere.
try:
    import os as _tas_os_path
    import sys as _tas_sys_path
    _tas_script_dir = None
    try:
        _tas_self_file = globals().get('__file__', None)
        if _tas_self_file:
            _tas_script_dir = _tas_os_path.path.dirname(_tas_os_path.path.abspath(str(_tas_self_file)))
    except Exception:
        _tas_script_dir = None
    if not _tas_script_dir:
        try:
            import jmri as _tas_jmri_path
            _tas_script_dir = _tas_jmri_path.util.FileUtil.getExternalFilename('profile:jython/TAS')
        except Exception:
            _tas_script_dir = None
    if not _tas_script_dir:
        try:
            import jmri as _tas_jmri_path
            _tas_script_dir = _tas_jmri_path.util.FileUtil.getExternalFilename('scripts:TAS')
        except Exception:
            _tas_script_dir = None
    if not _tas_script_dir:
        try:
            import jmri as _tas_jmri_path
            _tas_scripts_root = _tas_jmri_path.util.FileUtil.getExternalFilename('scripts:')
            if _tas_scripts_root:
                for _tas_candidate in (_tas_scripts_root, _tas_os_path.path.join(_tas_scripts_root, 'TAS')):
                    try:
                        if _tas_os_path.path.isfile(_tas_os_path.path.join(_tas_candidate, 'TASMainMenu.py')):
                            _tas_script_dir = _tas_candidate
                            break
                    except Exception:
                        continue
        except Exception:
            _tas_script_dir = None
    if _tas_script_dir and _tas_script_dir not in _tas_sys_path.path:
        _tas_sys_path.path.insert(0, _tas_script_dir)
except Exception:
    pass
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
    # Fallback: the active Start Up list, which stores the full path JMRI
    # launched this script from. JSR-223 does not set __file__, so this is
    # the reliable way to find the entry script directory during start-up.
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
        actions = mgr.getActions() if mgr is not None else []
        _fallback_dir = None
        for m in actions:
            try:
                if not isinstance(m, jmri.util.startup.PerformScriptModel):
                    continue
                try:
                    if not m.isEnabled():
                        continue
                except Exception:
                    pass
                p = m.getFileName()
                if p is None:
                    continue
                if str(p).replace('\\', '/').lower().endswith('timetableautomation.py'):
                    fp = jmri.util.FileUtil.getExternalFilename(str(p))
                    if fp is not None and os.path.isfile(str(fp)):
                        d = str(File(str(fp)).getParent())
                        try:
                            _norm = str(fp).replace('\\', '/').lower()
                            if '/tas/' in _norm:
                                return d
                        except Exception:
                            pass
                        if _fallback_dir is None:
                            _fallback_dir = d
            except Exception:
                continue
        if _fallback_dir is not None:
            return _fallback_dir
    except Exception:
        pass
    # Fallbacks: the installed TAS folder, then the scripts: location.
    try:
        for key in ('profile:jython/TAS/TimetableAutomation.py', 'scripts:TimetableAutomation.py', 'scripts:TAS/TimetableAutomation.py'):
            try:
                f = jmri.util.FileUtil.getExternalFilename(key)
            except Exception:
                f = None
            if f is None or str(f).strip() == '':
                continue
            try:
                if os.path.isfile(str(f)):
                    return str(File(str(f)).getParent())
            except Exception:
                continue
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

def _TasScriptsIsParentOfTasDir(scriptsPath, tasDir):
    # True when the scripts directory is the parent folder of the TAS install
    # (for example profile:jython when TAS lives in profile:jython/TAS).
    # TAS modules and working scripts resolve against the TAS folder itself,
    # so leaving scripts: at the parent breaks imports and workings.
    try:
        if scriptsPath is None or tasDir is None:
            return False
        if str(scriptsPath).strip() == '' or str(tasDir).strip() == '':
            return False
        if not os.path.isdir(str(tasDir)):
            return False
        try:
            parent = os.path.dirname(os.path.abspath(str(tasDir)))
        except:
            return False
        try:
            cur = os.path.abspath(str(scriptsPath))
        except:
            return False
        return os.path.normcase(cur) == os.path.normcase(parent)
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

        # TAS must own the scripts: location so old helper code that resolves
        # trainFinder.py/startTrain.py from getScriptsPath() works. Do not ask
        # in normal usage: change it automatically, save, and only fall back to
        # instructions when verification fails.
        try:
            if helper is not None:
                _NeedScriptsUpdate = helper.NeedsScriptsPathUpdate(curScripts, tasDir, programPath)
            else:
                _NeedScriptsUpdate = _TasScriptsPathLooksLikeProgramDir(curScripts) or (not _TasIsWritableDir(curScripts))
        except Exception:
            _NeedScriptsUpdate = _TasScriptsPathLooksLikeProgramDir(curScripts) or (not _TasIsWritableDir(curScripts))
        try:
            if not _NeedScriptsUpdate:
                _NeedScriptsUpdate = _TasScriptsIsParentOfTasDir(curScripts, tasDir)
        except Exception:
            pass
        try:
            if not _NeedScriptsUpdate and curScripts is not None and str(curScripts).strip() != '':
                _sc = str(curScripts)
                try:
                    _is_tas_scripts = os.path.isfile(os.path.join(_sc, 'TASBeanLookup.py'))
                except Exception:
                    _is_tas_scripts = False
                if not _is_tas_scripts:
                    _NeedScriptsUpdate = True
        except Exception:
            pass
        if not _NeedScriptsUpdate:
            return

        try:
            if helper is not None and helper.PathsEqual(str(curScripts), tasDir):
                return
        except Exception:
            pass

        # Only auto-set scripts: when TAS is already in its canonical profile
        # folder. If this copy runs from a download folder, migration copies it
        # first and the next run sets scripts:.
        try:
            _canonical_tas = jmri.util.FileUtil.getExternalFilename('profile:jython/TAS')
        except Exception:
            _canonical_tas = None
        try:
            if _canonical_tas and helper is not None and (not helper.PathsEqual(str(tasDir), str(_canonical_tas))):
                return
        except Exception:
            pass
        try:
            if _canonical_tas and helper is None:
                if os.path.normcase(os.path.abspath(str(tasDir))) != os.path.normcase(os.path.abspath(str(_canonical_tas))):
                    return
        except Exception:
            pass

        try:
            pm = jmri.profile.ProfileManager.getDefault()
            prof = pm.getActiveProfile() if pm is not None else None
            jmri.util.FileUtil.setScriptsPath(prof, str(tasDir))
            try:
                updatedPath = jmri.util.FileUtil.getScriptsPath()
            except Exception:
                updatedPath = None
            ok = False
            try:
                if helper is not None:
                    ok = helper.PathsEqual(str(updatedPath), tasDir)
                else:
                    ok = (os.path.normcase(os.path.abspath(str(updatedPath))) == os.path.normcase(os.path.abspath(str(tasDir))))
            except Exception:
                ok = False
            if not ok:
                raise Exception('scripts path was requested as ' + str(tasDir) + ' but JMRI reports ' + str(updatedPath))
            try:
                prefMgr = jmri.InstanceManager.getNullableDefault(jmri.implementation.FileLocationsPreferences)
                if prefMgr is None:
                    prefMgr = jmri.InstanceManager.getDefault(jmri.implementation.FileLocationsPreferences)
                if prefMgr is not None:
                    prefMgr.savePreferences(prof)
            except Exception:
                pass
            print('[TAS] scripts: location changed to ' + str(updatedPath))
            try:
                JOptionPane.showMessageDialog(None, 'TAS has set the JMRI scripts directory to:\n  ' + str(updatedPath) + '\n\nRestart JMRI for the change to take full effect.', 'TAS', JOptionPane.INFORMATION_MESSAGE)
            except Exception:
                pass
            return
        except Exception as exAuto:
            try:
                print('[TAS] Automatic scripts: update failed: ' + str(exAuto))
            except Exception:
                pass
            # Fall through to the manual-instruction dialog below.

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
# Optional window registry (main menu button toggles)
try:
    import TASWindowRegistry as TASWINREG
except Exception:
    TASWINREG = None
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

        # Target = portable profile TAS path for comparison
        target = jmri.util.FileUtil.getExternalFilename("profile:jython/TAS/" + scriptFileName)
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
# Detect when Start-Up actions point at a different copy of a TAS script than the profile:jython/TAS copy.
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
    'BlockFlickerMonitor.py',
    'DccPowerOnStart.py',
    'DccPowerOffOnClose.py',
    'RailComFix.py',
    'StreetLightController.py',
    'TASHelp.py',
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
        return jmri.util.FileUtil.getExternalFilename('profile:jython/TAS/' + str(scriptFileName))
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


# ------------------ TAS folder migration and self-install (version 1.5) ------------------
# Version 1.5 moved all TAS files from the profile jython root into a TAS
# subfolder. This check makes that move seamless:
# - running the new code from anywhere else (Downloads, Desktop, a flat copy)
#   offers to install it into profile:jython/TAS;
# - leftover TAS files from an older flat install at the profile jython root
#   are moved into profile:jython/TAS on confirmation;
# - Start-Up entries pointing at old locations are updated at the same time.
# Every step is explained in a dialogue before anything is changed.

_TASMigrateCheckDone = False
_TAS_USER_DATA_DIRS = ('workings', 'config')

def _TasTargetDir():
    try:
        t = jmri.util.FileUtil.getExternalFilename('profile:jython/TAS')
        if t is not None and str(t).strip() != '':
            return str(t)
    except:
        pass
    return None

def _TasProfileJythonDir():
    try:
        p = jmri.util.FileUtil.getExternalFilename('profile:jython')
        if p is not None and str(p).strip() != '':
            return str(p)
    except:
        pass
    return None

def _TasListNames(dirPath):
    try:
        if dirPath is None or (not os.path.isdir(str(dirPath))):
            return []
        return os.listdir(str(dirPath))
    except:
        return []

def _TasReadVersion(path):
    try:
        f = open(str(path), 'r')
        try:
            text = f.read(8192)
        finally:
            f.close()
    except:
        return None
    try:
        for ln in str(text).split('\n'):
            s = ln.strip()
            if s.startswith('VERSION'):
                for q in ('"', "'"):
                    i1 = s.find(q)
                    if i1 >= 0:
                        i2 = s.find(q, i1 + 1)
                        if i2 > i1:
                            return s[i1 + 1:i2]
                return None
    except:
        return None
    return None

def _TasVersionKey(s):
    try:
        parts = str(s).strip().split('.')
        return tuple([int(p) for p in parts])
    except:
        return None

def _TasSameContent(a, b):
    try:
        fa = open(str(a), 'rb')
        try:
            ca = fa.read()
        finally:
            fa.close()
        fb = open(str(b), 'rb')
        try:
            cb = fb.read()
        finally:
            fb.close()
        return ca == cb
    except:
        return False

def _TasCopyFile(src, dst):
    try:
        import shutil
        parent = os.path.dirname(str(dst))
        if parent != '' and (not os.path.isdir(parent)):
            os.makedirs(parent)
        shutil.copy2(str(src), str(dst))
        return True
    except:
        return False

def _TasCopyTreeContents(srcDir, dstDir, preserveDirs, backupDir=None, excludePaths=None):
    # Copy every file under srcDir into dstDir. For top-level dirs named in
    # preserveDirs (user data: workings, config), existing dst files are kept
    # unless byte-identical, and conflicts are counted, never overwritten.
    # For other files, an existing dst file with different content is copied
    # to backupDir first (when supplied) before it is overwritten.
    # excludePaths is an optional list of canonical source paths to skip,
    # used to avoid copying the TAS folder into itself.
    # Returns (copied, skipped, conflicts).
    copied = 0
    skipped = 0
    conflicts = 0
    try:
        try:
            names = os.listdir(str(srcDir))
        except:
            return (0, 0, 0)
        for n in names:
            s = os.path.join(str(srcDir), str(n))
            d = os.path.join(str(dstDir), str(n))
            try:
                if excludePaths:
                    try:
                        if _CanonLower(s) in excludePaths:
                            continue
                    except:
                        pass
                preserve = False
                try:
                    preserve = str(n) in (preserveDirs or ())
                except:
                    preserve = False
                if os.path.isdir(s) and (not os.path.islink(s)):
                    if preserve and os.path.isdir(d):
                        for root, dirs, files in os.walk(s):
                            try:
                                rel = os.path.relpath(root, s)
                            except:
                                continue
                            for fn in files:
                                sf = os.path.join(root, str(fn))
                                df = os.path.join(d, rel, str(fn)) if rel != '.' else os.path.join(d, str(fn))
                                try:
                                    if os.path.isfile(df):
                                        if _TasSameContent(sf, df):
                                            skipped += 1
                                        else:
                                            conflicts += 1
                                    else:
                                        if _TasCopyFile(sf, df):
                                            copied += 1
                                        else:
                                            conflicts += 1
                                except:
                                    conflicts += 1
                    else:
                        for root, dirs, files in os.walk(s):
                            try:
                                rel = os.path.relpath(root, s)
                            except:
                                continue
                            for fn in files:
                                sf = os.path.join(root, str(fn))
                                df = os.path.join(d, rel, str(fn)) if rel != '.' else os.path.join(d, str(fn))
                                try:
                                    if os.path.isfile(df) and (not _TasSameContent(sf, df)):
                                        if backupDir is None:
                                            continue
                                        bf = os.path.join(str(backupDir), str(n), rel, str(fn)) if rel != '.' else os.path.join(str(backupDir), str(n), str(fn))
                                        if not _TasCopyFile(df, bf):
                                            continue
                                    if _TasCopyFile(sf, df):
                                        copied += 1
                                except:
                                    pass
                elif os.path.isfile(s):
                    if preserve and os.path.isfile(d) and (not _TasSameContent(s, d)):
                        conflicts += 1
                    else:
                        if (not preserve) and os.path.isfile(d) and (not _TasSameContent(s, d)):
                            if backupDir is None:
                                continue
                            bf = os.path.join(str(backupDir), str(n))
                            if not _TasCopyFile(d, bf):
                                continue
                        if _TasCopyFile(s, d):
                            if preserve and os.path.isfile(d):
                                skipped += 1
                            else:
                                copied += 1
            except:
                continue
    except:
        pass
    return (copied, skipped, conflicts)

def _TasDeleteEmptyDirsBottomUp(topDir):
    try:
        for root, dirs, files in os.walk(str(topDir), topdown=False):
            for dn in dirs:
                try:
                    p = os.path.join(root, str(dn))
                    if len(os.listdir(p)) == 0:
                        os.rmdir(p)
                except:
                    pass
        return True
    except:
        return False

def _TasMoveUserDataDir(srcDir, dstDir, backupDir=None):
    # Move user data (workings, config) from srcDir to dstDir. The source is
    # the live install being migrated, so it wins: files already present with
    # identical content are just removed at the source, while files present
    # with different content are first backed up under backupDir (keeping
    # their relative path) and then overwritten. Nothing that fails to copy
    # is ever deleted at the source.
    # Returns (moved, alreadyThere, backedUp, failed).
    moved = 0
    already = 0
    backedUp = 0
    failed = 0
    try:
        if not os.path.isdir(str(srcDir)):
            return (0, 0, 0, 0)
        if not os.path.isdir(str(dstDir)):
            try:
                os.makedirs(str(dstDir))
            except:
                return (0, 0, 0, 0)
        for root, dirs, files in os.walk(str(srcDir)):
            try:
                rel = os.path.relpath(root, str(srcDir))
            except:
                continue
            for fn in files:
                sf = os.path.join(root, str(fn))
                df = os.path.join(str(dstDir), rel, str(fn)) if rel != '.' else os.path.join(str(dstDir), str(fn))
                try:
                    if os.path.isfile(df) and (not _TasSameContent(sf, df)):
                        if backupDir is None:
                            failed += 1
                            continue
                        bf = os.path.join(str(backupDir), rel, str(fn)) if rel != '.' else os.path.join(str(backupDir), str(fn))
                        if not _TasCopyFile(df, bf):
                            failed += 1
                            continue
                        backedUp += 1
                    parent = os.path.dirname(df)
                    if parent != '' and (not os.path.isdir(parent)):
                        try:
                            os.makedirs(parent)
                        except:
                            pass
                    if _TasCopyFile(sf, df):
                        try:
                            os.remove(sf)
                        except:
                            pass
                        moved += 1
                    else:
                        if os.path.isfile(df) and _TasSameContent(sf, df):
                            try:
                                os.remove(sf)
                                already += 1
                            except:
                                failed += 1
                        else:
                            failed += 1
                except:
                    failed += 1
                    continue
        _TasDeleteEmptyDirsBottomUp(srcDir)
    except:
        pass
    return (moved, already, backedUp, failed)

def _TasDeleteSuperseded(rootDir, refDir, names, backupDir=None):
    # Delete files and folders at rootDir whose layout matches refDir (the new
    # TAS copy). Files with identical content are removed. Files with different
    # content are first copied to backupDir (when supplied) and then removed,
    # so a user-edited old script is never lost. Extra files are kept.
    # Returns (deleted, backedUp).
    deleted = 0
    backedUp = 0
    try:
        for n in (names or []):
            try:
                if str(n).startswith('_TAS-migration-backup'):
                    continue
            except:
                pass
            rp = os.path.join(str(rootDir), str(n))
            fp = os.path.join(str(refDir), str(n))
            try:
                if os.path.isfile(rp) and os.path.isfile(fp):
                    try:
                        if _TasSameContent(rp, fp):
                            os.remove(rp)
                            deleted += 1
                        elif backupDir is not None:
                            bf = os.path.join(str(backupDir), str(n))
                            if _TasCopyFile(rp, bf):
                                os.remove(rp)
                                backedUp += 1
                    except:
                        pass
                elif os.path.isdir(rp) and os.path.isdir(fp) and (not os.path.islink(rp)):
                    for root, dirs, files in os.walk(fp):
                        try:
                            rel = os.path.relpath(root, fp)
                        except:
                            continue
                        for fn in files:
                            dp = os.path.join(rp, rel, str(fn)) if rel != '.' else os.path.join(rp, str(fn))
                            sp = os.path.join(fp, rel, str(fn)) if rel != '.' else os.path.join(fp, str(fn))
                            try:
                                if not os.path.isfile(dp):
                                    continue
                                if _TasSameContent(dp, sp):
                                    os.remove(dp)
                                    deleted += 1
                                elif backupDir is not None:
                                    bf = os.path.join(str(backupDir), str(n), rel, str(fn)) if rel != '.' else os.path.join(str(backupDir), str(n), str(fn))
                                    if _TasCopyFile(dp, bf):
                                        os.remove(dp)
                                        backedUp += 1
                            except:
                                pass
                    _TasDeleteEmptyDirsBottomUp(rp)
                    try:
                        if len(os.listdir(rp)) == 0:
                            os.rmdir(rp)
                    except:
                        pass
            except:
                continue
    except:
        pass
    return (deleted, backedUp)

def _TasRepointStartUpEntriesQuiet():
    # Repoint any Start-Up script entry that still uses the old flat jython
    # path for a script that now exists in the TAS folder. This catches
    # scripts that are not in _TASStartUpScriptNames, including optional ones.
    mgr = _StartupMgr()
    if mgr is None:
        return
    try:
        actions = mgr.getActions()
    except:
        return
    changed = False
    for m in actions:
        try:
            if not isinstance(m, jmri.util.startup.PerformScriptModel):
                continue
            p = m.getFileName()
            if p is None:
                continue
            base = File(str(p)).getName()
            target = jmri.util.FileUtil.getExternalFilename('profile:jython/TAS/' + str(base))
            if target is None or not os.path.isfile(str(target)):
                continue
            if _CanonLower(str(p)) == _CanonLower(str(target)):
                continue
            m.setFileName(str(target))
            changed = True
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

def _TasFixStartupPathsQuiet():
    try:
        mismatches = _BuildStartUpPathMismatchReport()
    except:
        mismatches = []
    if mismatches:
        try:
            _ApplyStartUpPathFix(mismatches)
        except:
            pass
    try:
        _TasRepointStartUpEntriesQuiet()
    except:
        pass

def _TasOptionDialog(msg, title, options):
    try:
        return JOptionPane.showOptionDialog(None, msg, title,
            JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE, None, options, options[0])
    except:
        return -1

def _CheckTasLocationAndMigrateOnce():
    global _TASMigrateCheckDone
    if _TASMigrateCheckDone:
        return
    _TASMigrateCheckDone = True
    try:
        ownDir = _TasGetThisScriptDir()
        profJython = _TasProfileJythonDir()
        tasTarget = _TasTargetDir()
        if ownDir is None or profJython is None or tasTarget is None:
            return
        ownCanon = _CanonLower(ownDir)
        tasCanon = _CanonLower(tasTarget)
        profCanon = _CanonLower(profJython)
        ownNames = _TasListNames(ownDir)

        if ownCanon == tasCanon:
            # Running from the installed TAS folder: look for leftovers.
            # User data folders (workings, config) are also checked at the
            # profile root, since they are sometimes left behind there even
            # when they are not present in the TAS copy.
            hits = []
            try:
                candidates = list(ownNames)
                for ud in _TAS_USER_DATA_DIRS:
                    if str(ud) not in candidates:
                        candidates.append(str(ud))
            except:
                candidates = list(ownNames)
            for n in candidates:
                try:
                    rp = os.path.join(profJython, str(n))
                    op = os.path.join(ownDir, str(n))
                    if _CanonLower(rp) == _CanonLower(op):
                        continue
                    if os.path.isfile(rp) or (os.path.isdir(rp) and len(_TasListNames(rp)) > 0):
                        hits.append(str(n))
                except:
                    continue
            if not hits:
                return
            lines = []
            lines.append('The Timetable Automation System now keeps all of its files in one TAS folder:')
            lines.append('  ' + str(tasTarget))
            lines.append('')
            lines.append('Files from your older version were found directly in the jython folder.')
            lines.append('TAS will move your timetables, working scripts and settings into the TAS folder')
            lines.append('and update your JMRI Start Up entries to the new location.')
            lines.append('Files that only belong to the new version are left alone.')
            lines.append('')
            lines.append('After the move, TAS starts automatically with JMRI; no panels or scripts need to be edited.')
            lines.append('A restart of JMRI is required afterwards.')
            choice = _TasOptionDialog('\n'.join(lines), 'TAS move to TAS folder', ['Move now', 'Later'])
            if choice != 0:
                return
            movedMsg = []
            backupRoot = os.path.join(profJython, '_TAS-migration-backup')
            for dn in _TAS_USER_DATA_DIRS:
                try:
                    if str(dn) in hits:
                        m, a, b, c = _TasMoveUserDataDir(os.path.join(profJython, str(dn)), os.path.join(tasTarget, str(dn)), os.path.join(backupRoot, str(dn)))
                        if b > 0:
                            movedMsg.append(str(dn) + ': ' + str(b) + ' pre-existing file(s) with different contents were backed up to ' + os.path.join(backupRoot, str(dn)))
                        if c > 0:
                            movedMsg.append(str(dn) + ': ' + str(c) + ' file(s) could not be moved - please merge them by hand.')
                except:
                    pass
            try:
                d, b = _TasDeleteSuperseded(profJython, ownDir, [n for n in hits if str(n) not in _TAS_USER_DATA_DIRS], backupRoot)
                if b > 0:
                    movedMsg.append(str(b) + ' file(s) with different contents were backed up to ' + str(backupRoot))
            except:
                pass
            _TasFixStartupPathsQuiet()
            done = ['The move is complete. Please restart JMRI now.']
            done.append('')
            done.append('TAS is installed and will start automatically with JMRI. No panels or scripts need to be edited.')
            done.append('')
            done.append('These entries in your Start-Up list now point at the TAS folder:')
            done.append('  ' + str(tasTarget))
            done.append('')
            done.append('If any LogixNG action, panel script action or other JMRI configuration still refers to')
            done.append('preference:jython/<script>.py, change it to preference:jython/TAS/<script>.py')
            done.append('and save the panel or configuration once.')
            if movedMsg:
                done.append('')
                done.extend(movedMsg)
            try:
                JOptionPane.showMessageDialog(None, '\n'.join(done), 'TAS', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return

        # Running from somewhere else.
        if _TasScriptsPathLooksLikeProgramDir(ownDir):
            lines = []
            lines.append('You started TAS from the JMRI program folder:')
            lines.append('  ' + str(ownDir))
            lines.append('')
            lines.append('That copy is outdated and cannot be updated automatically.')
            try:
                if os.path.isfile(os.path.join(tasTarget, 'TimetableAutomation.py')):
                    lines.append('Run your installed copy instead (Preferences > Start Up points at it, so TAS starts with JMRI):')
                    lines.append('  ' + os.path.join(tasTarget, 'TimetableAutomation.py'))
                else:
                    lines.append('Install a current copy into your JMRI profile first (see README.md),')
                    lines.append('then run it from there.')
            except:
                pass
            try:
                JOptionPane.showMessageDialog(None, '\n'.join(lines), 'TAS installation problem', JOptionPane.WARNING_MESSAGE)
            except:
                pass
            return

        installedMain = os.path.join(tasTarget, 'TimetableAutomation.py')
        installed = False
        try:
            installed = os.path.isfile(installedMain)
        except:
            installed = False
        legacyFlat = False
        try:
            for cn in _TASCoreScriptNamesForLocationCheck:
                if os.path.isfile(os.path.join(profJython, str(cn))):
                    legacyFlat = True
                    break
            if not legacyFlat:
                for wd in ('workings', 'config'):
                    try:
                        cand = os.path.join(profJython, wd)
                        if os.path.isdir(cand) and _DirHasAnyPyUnder(cand):
                            legacyFlat = True
                            break
                    except:
                        pass
        except:
            pass

        if installed and legacyFlat:
            try:
                JOptionPane.showMessageDialog(None,
                    'An installed TAS copy exists at:\n  ' + str(tasTarget) + '\n\nPlease run it from there. It will move any leftover older files itself.',
                    'TAS', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return

        if installed:
            ownVer = _TasReadVersion(os.path.join(ownDir, 'TimetableAutomation.py'))
            instVer = _TasReadVersion(installedMain)
            ok = _TasVersionKey(ownVer)
            ik = _TasVersionKey(instVer)
            if ok is not None and ik is not None and ok > ik:
                lines = []
                lines.append('This copy of TAS (version ' + str(ownVer) + ') is newer than your installed copy (version ' + str(instVer) + ').')
                lines.append('Update the installed copy at:')
                lines.append('  ' + str(tasTarget))
                lines.append('')
                lines.append('Your workings, configuration and settings are kept.')
                choice = _TasOptionDialog('\n'.join(lines), 'TAS update', ['Update installed copy', 'Cancel'])
                if choice != 0:
                    return
                try:
                    updateBackup = os.path.join(profJython, '_TAS-migration-backup', 'update')
                    _TasCopyTreeContents(ownDir, tasTarget, _TAS_USER_DATA_DIRS, updateBackup, [tasCanon])
                except:
                    pass
                _TasFixStartupPathsQuiet()
                try:
                    JOptionPane.showMessageDialog(None, 'The installed copy was updated. Please restart JMRI now.', 'TAS', JOptionPane.INFORMATION_MESSAGE)
                except:
                    pass
            else:
                lines = []
                lines.append('Your installed TAS copy is at:')
                lines.append('  ' + str(tasTarget))
                if instVer:
                    lines.append('Installed version: ' + str(instVer))
                if ownVer:
                    lines.append('This copy: ' + str(ownVer))
                lines.append('')
                lines.append('Please run the installed copy instead of this one from now on.\nIt will start automatically with JMRI.')
                try:
                    JOptionPane.showMessageDialog(None, '\n'.join(lines), 'TAS', JOptionPane.INFORMATION_MESSAGE)
                except:
                    pass
            return

        if legacyFlat:
            lines = []
            lines.append('The Timetable Automation System now keeps all of its files in one TAS folder.')
            lines.append('This copy will move your older files from the jython folder into:')
            lines.append('  ' + str(tasTarget))
            lines.append('')
            lines.append('Your timetables, working scripts and settings are kept,')
            lines.append('and your JMRI Start Up entries are updated to the new location.')
            lines.append('')
            lines.append('TAS will start automatically with JMRI after the move; no panels or scripts need to be edited.')
            lines.append('')
            lines.append('A restart of JMRI is required afterwards.')
            choice = _TasOptionDialog('\n'.join(lines), 'TAS move to TAS folder', ['Move now', 'Later'])
            if choice != 0:
                return
            try:
                if not os.path.isdir(tasTarget):
                    os.makedirs(tasTarget)
            except:
                pass
            excludeSelf = (ownCanon == profCanon)
            try:
                srcNames = [n for n in ownNames if (not excludeSelf) or _CanonLower(os.path.join(ownDir, str(n))) != tasCanon]
                for n in srcNames:
                    s = os.path.join(ownDir, str(n))
                    d = os.path.join(tasTarget, str(n))
                    try:
                        if os.path.isdir(s) and (not os.path.islink(s)):
                            _TasCopyTreeContents(s, d, _TAS_USER_DATA_DIRS, None, [tasCanon])
                        elif os.path.isfile(s):
                            if str(n) in _TAS_USER_DATA_DIRS:
                                pass
                            else:
                                _TasCopyFile(s, d)
                    except:
                        continue
            except:
                pass
            if excludeSelf:
                try:
                    for dn in _TAS_USER_DATA_DIRS:
                        try:
                            _TasMoveUserDataDir(os.path.join(profJython, str(dn)), os.path.join(tasTarget, str(dn)), os.path.join(profJython, '_TAS-migration-backup', str(dn)))
                        except:
                            pass
                    for n in _TasListNames(profJython):
                        try:
                            if str(n) in _TAS_USER_DATA_DIRS:
                                continue
                            if str(n) == 'TAS':
                                continue
                            if str(n).startswith('_TAS-migration-backup'):
                                continue
                            rp = os.path.join(profJython, str(n))
                            fp = os.path.join(tasTarget, str(n))
                            if os.path.isdir(rp) and (not os.path.islink(rp)):
                                if os.path.isdir(fp):
                                    try:
                                        for root, dirs, files in os.walk(fp):
                                            try:
                                                rel = os.path.relpath(root, fp)
                                            except:
                                                continue
                                            for fn in files:
                                                srcSub = os.path.join(fp, rel, str(fn)) if rel != '.' else os.path.join(fp, str(fn))
                                                dp = os.path.join(rp, rel, str(fn)) if rel != '.' else os.path.join(rp, str(fn))
                                                try:
                                                    if os.path.isfile(dp) and _TasSameContent(srcSub, dp):
                                                        os.remove(dp)
                                                except:
                                                    pass
                                    except:
                                        pass
                                    try:
                                        _TasDeleteEmptyDirsBottomUp(rp)
                                    except:
                                        pass
                                    try:
                                        if os.path.isdir(rp) and len(os.listdir(rp)) == 0:
                                            os.rmdir(rp)
                                    except:
                                        pass
                            elif os.path.isfile(rp) and os.path.isfile(fp) and _TasSameContent(rp, fp):
                                try:
                                    os.remove(rp)
                                except:
                                    pass
                        except:
                            continue
                except:
                    pass
            else:
                for dn in _TAS_USER_DATA_DIRS:
                    try:
                        _TasMoveUserDataDir(os.path.join(profJython, str(dn)), os.path.join(tasTarget, str(dn)), os.path.join(profJython, '_TAS-migration-backup', str(dn)))
                    except:
                        pass
            _TasFixStartupPathsQuiet()
            try:
                JOptionPane.showMessageDialog(None,
                    'The move is complete. Please restart JMRI now.\n\nTAS is installed and will start automatically with JMRI. No panels or scripts need to be edited.\n\nIf any LogixNG action or panel script action still refers to preference:jython/<script>.py, change it to preference:jython/TAS/<script>.py and save the panel once.',
                    'TAS', JOptionPane.INFORMATION_MESSAGE)
            except:
                pass
            return

        # Fresh install: nothing TAS-related in the profile yet.
        lines = []
        lines.append('This copy of TAS is running from:')
        lines.append('  ' + str(ownDir))
        lines.append('')
        lines.append('It is not installed in your JMRI profile yet. TAS will copy itself to:')
        lines.append('  ' + str(tasTarget))
        lines.append('')
        lines.append('Afterwards, add it to Preferences > Start Up so that it starts with JMRI.')
        choice = _TasOptionDialog('\n'.join(lines), 'TAS install', ['Install now', 'Cancel'])
        if choice != 0:
            return
        try:
            if not os.path.isdir(tasTarget):
                os.makedirs(tasTarget)
        except:
            pass
        try:
            _TasCopyTreeContents(ownDir, tasTarget, (), None, [tasCanon])
        except:
            pass
        try:
            JOptionPane.showMessageDialog(None,
                'TAS was installed to:\n  ' + str(tasTarget) + '\n\nPlease run it from there from now on.\nTAS will start automatically with JMRI after you add it under Preferences > Start Up.',
                'TAS', JOptionPane.INFORMATION_MESSAGE)
        except:
            pass
    except Exception as exMig:
        try:
            print('[TAS] Location check failed: ' + str(exMig))
        except:
            pass


# ------------------ Copies outside the profile TAS folder detection ------------------
# The canonical home for TAS files since version 1.5 is profile:jython/TAS.
# Having TAS scripts anywhere else (JMRI program folder, a different scripts
# folder) is an error condition, because it can cause mixed versions
# to be loaded unpredictably.
# This check warns the user and explains how to fix it. Leftover flat files
# at the profile jython root are moved automatically by the TAS folder
# migration below instead of being reported here.

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
    'StreetLightController.py',
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

    # Canonical home since version 1.5: profile:jython/TAS.
    # Leftover flat files at the profile jython root are handled by the
    # TAS folder migration prompt, so this check only warns about copies
    # outside the profile that the migration cannot move by itself.
    tasTarget = None
    try:
        tasTarget = jmri.util.FileUtil.getExternalFilename('profile:jython/TAS')
    except:
        tasTarget = None
    try:
        tasCanon = File(str(tasTarget)).getCanonicalPath().lower() if tasTarget else None
    except:
        tasCanon = str(tasTarget).lower() if tasTarget else None

    suspects = []  # (label, dirPath)
    try:
        programPath = jmri.util.FileUtil.getProgramPath()
    except:
        programPath = None
    if programPath:
        try:
            progJy = os.path.join(str(programPath), 'jython')
            if _DirContainsAnyOf(progJy, _TASCoreScriptNamesForLocationCheck):
                suspects.append(('JMRI program folder (needs administrator rights to delete)', progJy))
        except:
            pass
    try:
        scriptsDir = jmri.util.FileUtil.getScriptsPath()
    except:
        scriptsDir = None
    if scriptsDir:
        try:
            scrCanon = File(str(scriptsDir)).getCanonicalPath().lower()
        except:
            scrCanon = str(scriptsDir).lower()
        # Leftover flat files at the profile root are the TAS folder
        # migration's job, not this warning's: never report them here, and
        # never report the canonical TAS folder itself (it can appear as the
        # TAS subfolder of scripts: when scripts: is the profile root).
        try:
            profJy = jmri.util.FileUtil.getExternalFilename('profile:jython')
            profCanon = File(str(profJy)).getCanonicalPath().lower()
        except:
            profCanon = None
        try:
            tasSubCanon = File(os.path.join(str(scriptsDir), 'TAS')).getCanonicalPath().lower()
        except:
            tasSubCanon = None
        if scrCanon != tasCanon:
            try:
                if scrCanon != profCanon and _DirContainsAnyOf(scriptsDir, _TASCoreScriptNamesForLocationCheck):
                    suspects.append(('JMRI scripts folder', str(scriptsDir)))
                elif tasSubCanon != tasCanon and _DirContainsAnyOf(os.path.join(str(scriptsDir), 'TAS'), _TASCoreScriptNamesForLocationCheck):
                    suspects.append(('TAS subfolder of the JMRI scripts folder', os.path.join(str(scriptsDir), 'TAS')))
            except:
                pass

    if not suspects:
        return

    lines = []
    lines.append('TAS has been found outside its folder in your JMRI profile.')
    lines.append('This is a problem because it can cause mixed versions of scripts to run.')
    lines.append('')
    lines.append('Keep this folder (all TAS files live here since version 1.5):')
    lines.append('  ' + str(tasTarget))
    lines.append('')
    lines.append('Delete the TAS files in:')
    for label, d in suspects:
        lines.append('  ' + str(d))
        lines.append('  (' + str(label) + ')')
    lines.append('')
    lines.append('If you are unsure, keep the profile folder and remove the others.')
    lines.append('Restart JMRI after cleaning up.')

    msg = '\n'.join(lines)

    try:
        JOptionPane.showMessageDialog(None, msg, 'TAS installation problem', JOptionPane.WARNING_MESSAGE)
    except:
        try:
            print('[TAS] Dual-install warning dialog failed')
            print(msg)
        except:
            pass


# ------------------ Own Start-Up entry reminder ------------------
# First-limit detection: TAS only starts automatically with JMRI when the user
# has completed installation by adding TimetableAutomation.py to the JMRI
# Start Up list. If the user runs it by hand from Scripting > Run Script and
# that step was never done, explain what to do. The reminder can be muted.

_TASOwnStartupReminderDone = False
_TAS_STARTUP_REMINDER_MUTED_MEMORY = "TAS_STARTUP_REMINDER_MUTED"

def _IsTasStartupReminderMuted():
    try:
        v = TBL.SafeGetMemoryValue(_TAS_STARTUP_REMINDER_MUTED_MEMORY, "")
        return str(v).strip().lower() in ("true", "yes", "1", "on", "muted")
    except:
        return False

def _CheckTasOwnStartupEntryOnce():
    global _TASOwnStartupReminderDone
    if _TASOwnStartupReminderDone:
        return
    _TASOwnStartupReminderDone = True
    try:
        if _IsTasStartupReminderMuted():
            return
    except:
        return
    try:
        if _IsStartUpScriptEnabled('TimetableAutomation.py'):
            return
    except:
        return
    try:
        lines = []
        lines.append('The Timetable Automation System is running, but it has not been added to the JMRI Start Up list.')
        lines.append('You started it by hand. To finish installing it so that it starts automatically with JMRI:')
        lines.append('')
        lines.append('1) In JMRI, open Preferences, then the Start Up section.')
        lines.append('2) Click Add and choose the Run script action.')
        lines.append('3) Select TimetableAutomation.py from your TAS folder.')
        lines.append('4) Save the preferences and restart JMRI.')
        lines.append('')
        lines.append('The Setup wizard will offer to add the other background scripts for you.')
        msg = '\n'.join(lines)
        options = ['Remind me later', 'Do not show again']
        choice = JOptionPane.showOptionDialog(None, msg, 'TAS installation incomplete',
            JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE, None, options, options[0])
        if choice == 1:
            try:
                TBL.SafeSetMemoryValue(_TAS_STARTUP_REMINDER_MUTED_MEMORY, "true")
            except:
                pass
    except:
        try:
            print('[TAS] Own Start-Up entry reminder failed')
        except:
            pass



import TASMainMenu
TASMainMenu.VERSION = VERSION
TASMainMenu.SYSTEM_NAME = "Timetable Automation System"
TASMainMenu.TIMETABLE_MEMORY_NAME = "CURRENTTIMETABLE"
TASMainMenu._IsStartUpScriptEnabled = _IsStartUpScriptEnabled


def Run():
    def Create():
        try:
            _CheckTasLocationAndMigrateOnce()
        except Exception as ex:
            try:
                print('[TAS] Location check failed: ' + str(ex))
            except:
                pass
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
        try:
            _CheckTasOwnStartupEntryOnce()
        except Exception as ex:
            try:
                print('[TAS] Own Start-Up entry check failed: ' + str(ex))
            except:
                pass
        TASMainMenu.ShowMainMenu()
    SwingUtilities.invokeLater(Create)


Run()
