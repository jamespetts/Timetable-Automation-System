import re, sys, threading, traceback

src = open('TASSetup.py', 'rb').read().decode('ascii')
lines = src.split('\n')
start = None
end = None
for i, l in enumerate(lines, 1):
    if 'def BuildTrainDetectionTab' in l:
        start = i
    if start and 'def BuildOrientationTab' in l:
        end = i
        break
body = lines[start:end]
# drop the def line, dedent the method body by 4
body = body[1:]
ded = []
for l in body:
    if l.startswith('    '):
        ded.append(l[4:])
    else:
        ded.append(l)
method = '\n'.join(ded)

import java
from java.awt import (BorderLayout, Color, Dimension, Font, GridBagConstraints,
                      GridBagLayout, Insets, RenderingHints)
from java.lang import Runnable, Boolean, String
from javax.swing import (Box, JButton, JCheckBox, JLabel, JList, JScrollPane,
                         JSplitPane, DefaultListModel, DefaultListCellRenderer,
                         JSpinner, SpinnerNumberModel, ListSelectionModel,
                         SwingUtilities, JTable, JOptionPane, JPanel)
from javax.swing.table import AbstractTableModel
from javax.swing.event import ListSelectionListener
import RailComDetect as RCD


def MakePaperPanel():
    p = JPanel()
    p.setOpaque(True)
    p.setLayout(GridBagLayout())
    return p


def MakeHeading(t):
    return JLabel(t)


def MakeWrappedLabel(t, widthPx=560, **kw):
    return JLabel(t[:80])


def ApplyTheme(c):
    pass


def ScriptExists(n):
    return True


def _IsScriptEnabled(n):
    return False


def _EnsureScriptEnabled(n, e):
    return True


def LogWarn(m, **kw):
    print("WARN " + str(m))


class RunnableAdapter(Runnable):
    def __init__(self, func):
        self.func = func

    def run(self):
        self.func()


ns = dict(globals())
exec(compile(method, 'BuildTrainDetectionTab', 'exec'), ns)


class FakeSelf(object):
    def __init__(self):
        self.InitialRailComFix = False
        self.CurrentRailComFix = False


holder = FakeSelf()
try:
    ns['BuildTrainDetectionTab'](holder)
    print('TAB BODY BUILT OK')
except Exception:
    print('EXCEPTION WHILE BUILDING TAB:')
    traceback.print_exc(file=sys.stdout)

# Give the worker thread a moment to report any failure.
threading.Event().wait(3.0)
print('harness done')
