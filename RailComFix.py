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
# RailComFix.py
# Optional startup script. Disabled by default; enable in TASSetup.py General tab.
# Sends a spurious function-off command to listed decoder addresses so faulty
# decoders report on RailCom. Configuration is in profile:jython/config/railcomfix.tsv
# (tab separated, header: function<TAB>addresses, addresses separated by ";").
# The script runs once at start-up. Manual trigger is via Show(), called by the
# main menu through RunExternalScript.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.
#
# NAMING RULE FOR THIS FILE
# JMRI runs every start-up script through one shared JSR-223 script context, so
# top-level names in this file land in the same map as the names in every other
# start-up script. A name defined here that another start-up script also defines
# is overwritten, and functions in this file resolve that name at call time, so
# the other script's object would be used here. Every top-level name in this
# file therefore starts with RAILCOMFIX_ or _RailComFix, and objects used by
# functions are bound as default arguments so no later script can redirect them.

import os
import csv
import jmri
from java.lang import Runnable, Thread
from java.awt import BorderLayout, FlowLayout
from javax.swing import JButton, JDialog, JLabel, JPanel, JTextField
from javax.swing import JSpinner, SpinnerNumberModel, SwingUtilities

RAILCOMFIX_CONFIG_PROFILE_PATH = "profile:jython/config/railcomfix.tsv"
RAILCOMFIX_DEFAULT_FUNCTION = 4
RAILCOMFIX_DEFAULT_ADDRESSES = [1323, 1824]
RAILCOMFIX_MIN_ADDRESS = 1
RAILCOMFIX_MAX_ADDRESS = 9999
RAILCOMFIX_MIN_FUNCTION = 0
RAILCOMFIX_MAX_FUNCTION = 28


def _RailComFixLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


def RAILCOMFIX_GetConfigPath():
    try:
        return jmri.util.FileUtil.getExternalFilename(RAILCOMFIX_CONFIG_PROFILE_PATH)
    except Exception:
        return os.path.join("jython", "config", "railcomfix.tsv")


def RAILCOMFIX_ParseAddresses(text):
    result = []
    try:
        parts = str(text).replace(";", ",").split(",")
    except Exception:
        return result
    for part in parts:
        s = str(part).strip()
        if s == "":
            continue
        try:
            value = int(s)
        except Exception:
            continue
        if value >= RAILCOMFIX_MIN_ADDRESS and value <= RAILCOMFIX_MAX_ADDRESS:
            if value not in result:
                result.append(value)
    return result


def RAILCOMFIX_LoadConfig():
    function = RAILCOMFIX_DEFAULT_FUNCTION
    addresses = list(RAILCOMFIX_DEFAULT_ADDRESSES)
    path = RAILCOMFIX_GetConfigPath()
    try:
        if not os.path.isfile(path):
            return (function, addresses)
        fh = open(path, "r")
        try:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    rawFunc = str(row.get("function", "")).strip()
                    if rawFunc != "":
                        parsed = int(rawFunc)
                        if parsed >= RAILCOMFIX_MIN_FUNCTION and parsed <= RAILCOMFIX_MAX_FUNCTION:
                            function = parsed
                except Exception:
                    pass
                try:
                    rawAddr = str(row.get("addresses", "")).strip()
                    if rawAddr != "":
                        parsedAddrs = RAILCOMFIX_ParseAddresses(rawAddr.replace(";", ","))
                        if len(parsedAddrs) > 0:
                            addresses = parsedAddrs
                except Exception:
                    pass
                break
        finally:
            fh.close()
    except Exception as ex:
        _RailComFixLog("Could not load RailCom fix configuration: " + str(ex))
    return (function, addresses)


def RAILCOMFIX_SaveConfig(function, addresses):
    try:
        funcNum = int(function)
    except Exception:
        funcNum = RAILCOMFIX_DEFAULT_FUNCTION
    if funcNum < RAILCOMFIX_MIN_FUNCTION or funcNum > RAILCOMFIX_MAX_FUNCTION:
        funcNum = RAILCOMFIX_DEFAULT_FUNCTION
    clean = []
    try:
        for addr in list(addresses):
            try:
                value = int(str(addr).strip())
            except Exception:
                continue
            if value >= RAILCOMFIX_MIN_ADDRESS and value <= RAILCOMFIX_MAX_ADDRESS:
                if value not in clean:
                    clean.append(value)
    except Exception:
        pass
    path = RAILCOMFIX_GetConfigPath()
    parent = os.path.dirname(path)
    try:
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
    except Exception as ex:
        _RailComFixLog("Could not create RailCom fix config directory: " + str(ex))
        return False
    tempPath = path + ".tmp"
    try:
        fh = open(tempPath, "w")
        try:
            writer = csv.DictWriter(fh, fieldnames=["function", "addresses"],
                                    delimiter="\t", lineterminator="\n",
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerow({"function": str(funcNum),
                             "addresses": ";".join([str(a) for a in clean])})
        finally:
            fh.close()
        try:
            if os.path.isfile(path):
                os.remove(path)
            os.rename(tempPath, path)
        except Exception as ex:
            _RailComFixLog("Could not replace RailCom fix configuration: " + str(ex))
            return False
    except Exception as ex:
        _RailComFixLog("Could not save RailCom fix configuration: " + str(ex))
        return False
    return True


def RAILCOMFIX_ApplyAll(_log=_RailComFixLog, _loader=RAILCOMFIX_LoadConfig):
    try:
        (function, addresses) = _loader()
    except Exception as ex:
        _log("RailCom fix load failed: " + str(ex))
        return False
    if len(addresses) == 0:
        _log("RailCom fix: no addresses configured; nothing sent")
        return True
    worker = _RailComFixWorker(list(addresses), int(function))
    worker.setName("RailCom fix")
    worker.start()
    return True


class _RailComFixWorker(jmri.jmrit.automat.AbstractAutomaton):
    def __init__(self, addresses, function):
        jmri.jmrit.automat.AbstractAutomaton.__init__(self)
        self._addrs = list(addresses)
        try:
            self._func = int(function)
        except Exception:
            self._func = RAILCOMFIX_DEFAULT_FUNCTION

    def init(self):
        pass

    def handle(self):
        for addr in list(self._addrs):
            try:
                thr = self.getThrottle(int(addr), True)
            except Exception as ex:
                _RailComFixLog("RailCom fix: throttle not acquired for " + str(addr) + ": " + str(ex))
                continue
            if thr is None:
                _RailComFixLog("RailCom fix: throttle not acquired for " + str(addr))
                continue
            try:
                thr.setFunction(int(self._func), False)
                _RailComFixLog("RailCom fix: sent F" + str(int(self._func)) + " off to " + str(addr))
            except Exception as ex:
                _RailComFixLog("RailCom fix: send failed for " + str(addr) + ": " + str(ex))
            try:
                thr.release(None)
            except Exception:
                pass
        return False


class _RailComFixApplyTask(Runnable):
    def run(self):
        try:
            RAILCOMFIX_ApplyAll()
        except Exception as ex:
            _RailComFixLog("RailCom fix apply failed: " + str(ex))


def _RailComFixStart():
    th = Thread(_RailComFixApplyTask())
    th.setDaemon(True)
    th.start()


def Show():
    try:
        (function, addresses) = RAILCOMFIX_LoadConfig()
    except Exception:
        function = RAILCOMFIX_DEFAULT_FUNCTION
        addresses = list(RAILCOMFIX_DEFAULT_ADDRESSES)

    def _BuildAndShow(_func=function, _addrs=list(addresses)):
        try:
            import TASIcon
        except Exception:
            TASIcon = None
        dlg = JDialog(None, "RailCom fix", False)
        try:
            if TASIcon is not None:
                TASIcon.SetFrameClockIcon(dlg, 32)
        except Exception:
            pass
        dlg.setLayout(BorderLayout(8, 8))
        form = JPanel(FlowLayout(FlowLayout.LEFT, 8, 8))
        form.add(JLabel("Addresses (separated by ; or ,):"))
        addrField = JTextField(";".join([str(a) for a in _addrs]), 20)
        form.add(addrField)
        form.add(JLabel("Function:"))
        funcModel = SpinnerNumberModel(int(_func), RAILCOMFIX_MIN_FUNCTION,
                                      RAILCOMFIX_MAX_FUNCTION, 1)
        funcSpinner = JSpinner(funcModel)
        form.add(funcSpinner)
        dlg.add(form, BorderLayout.CENTER)
        status = JLabel("Sends function-off once per address, then releases the throttle.")
        btnPanel = JPanel(FlowLayout(FlowLayout.RIGHT, 8, 8))
        applyBtn = JButton("Send now")
        saveBtn = JButton("Save")
        closeBtn = JButton("Close")
        btnPanel.add(status)
        btnPanel.add(applyBtn)
        btnPanel.add(saveBtn)
        btnPanel.add(closeBtn)
        dlg.add(btnPanel, BorderLayout.SOUTH)

        def _ReadDialog():
            try:
                funcVal = int(str(funcSpinner.getValue()))
            except Exception:
                funcVal = RAILCOMFIX_DEFAULT_FUNCTION
            addrVal = RAILCOMFIX_ParseAddresses(addrField.getText())
            return (funcVal, addrVal)

        def OnApply(e=None, _field=addrField, _spinner=funcSpinner, _status=status):
            try:
                (funcVal, addrVal) = _ReadDialog()
                if len(addrVal) == 0:
                    _status.setText("Enter at least one address 1-9999.")
                    return
                ok = RAILCOMFIX_ApplyAll()
                if ok:
                    _status.setText("Sent F" + str(funcVal) + " off to " + str(len(addrVal)) + " address(es).")
                else:
                    _status.setText("Send failed; see system console.")
            except Exception as ex:
                try:
                    _status.setText("Send failed: " + str(ex))
                except Exception:
                    pass

        def OnSave(e=None, _field=addrField, _spinner=funcSpinner, _status=status):
            try:
                (funcVal, addrVal) = _ReadDialog()
                if len(addrVal) == 0:
                    _status.setText("Enter at least one address 1-9999.")
                    return
                if RAILCOMFIX_SaveConfig(funcVal, addrVal):
                    _status.setText("Saved.")
                else:
                    _status.setText("Save failed; see system console.")
            except Exception as ex:
                try:
                    _status.setText("Save failed: " + str(ex))
                except Exception:
                    pass

        def OnClose(e=None, _dlg=dlg):
            try:
                _dlg.setVisible(False)
                _dlg.dispose()
            except Exception:
                pass

        applyBtn.addActionListener(OnApply)
        saveBtn.addActionListener(OnSave)
        closeBtn.addActionListener(OnClose)
        dlg.pack()
        try:
            dlg.setLocationRelativeTo(None)
        except Exception:
            pass
        dlg.setVisible(True)

    try:
        SwingUtilities.invokeLater(_BuildAndShow)
    except Exception:
        _BuildAndShow()


try:
    _RailComFixStart()
except Exception as ex:
    try:
        print("[TAS] RailCom fix auto-start failed: " + str(ex))
    except Exception:
        pass
