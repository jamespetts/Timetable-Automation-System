# This file is part of the Timetable Automation System by James E. Petts
#
# Minimal path resolver for TAS.
# - JMRI 5.14 / Jython 2.7
# - ASCII only
# - No absolute paths
# - Read order: profile:jython -> scripts:
# - Write location for TAS-generated content: profile:jython
import os
import jmri
from jmri.util import FileUtil

try:
    import java.io as jio
except Exception:
    jio = None

# -------------------- Basic locations --------------------

def GetProfileJythonDir():
    """Return absolute filesystem path to profile:jython."""
    try:
        return FileUtil.getExternalFilename('profile:jython')
    except Exception:
        return None


def GetScriptsDir():
    """Return absolute filesystem path to the current scripts: location."""
    try:
        return jmri.util.FileUtil.getScriptsPath()
    except Exception:
        return None


def GetTimetableDir():
    """Return absolute filesystem path to profile:timetable."""
    try:
        return FileUtil.getExternalFilename('profile:timetable')
    except Exception:
        return None


def GetTimetableCsvPath(timetableName):
    """Return absolute filesystem path to profile:timetable/<name>.csv, or None."""
    try:
        name = '' if timetableName is None else str(timetableName).strip()
    except Exception:
        name = ''
    if name == '':
        return None
    try:
        # Use FileUtil scheme so it stays portable.
        return FileUtil.getExternalFilename('profile:timetable/' + name + '.csv')
    except Exception:
        # Fallback to joining the directory.
        d = GetTimetableDir()
        if not d:
            return None
        return os.path.join(str(d), name + '.csv')


# -------------------- File existence helpers --------------------

def _ExistsFile(path):
    try:
        if path is None:
            return False
        if jio is not None:
            f = jio.File(str(path))
            return f.exists() and f.isFile()
        return os.path.isfile(str(path))
    except Exception:
        return False


def _ExistsDir(path):
    try:
        if path is None:
            return False
        if jio is not None:
            f = jio.File(str(path))
            return f.exists() and f.isDirectory()
        return os.path.isdir(str(path))
    except Exception:
        return False


def EnsureDir(path):
    """Ensure that directory path exists. Returns True on success."""
    try:
        if path is None:
            return False
        if _ExistsDir(path):
            return True
        # Prefer JMRI helper if available
        try:
            FileUtil.createDirectory(str(path))
            return _ExistsDir(path)
        except Exception:
            pass
        try:
            os.makedirs(str(path))
            return _ExistsDir(path)
        except Exception:
            return False
    except Exception:
        return False


def IsDirWritable(path):
    """Best-effort check whether a directory is writable."""
    try:
        if path is None:
            return False
        if not _ExistsDir(path):
            return False
        testName = os.path.join(str(path), 'tas_write_test.tmp')
        try:
            f = open(testName, 'w')
            f.write('x')
            f.close()
            try:
                os.remove(testName)
            except Exception:
                pass
            return True
        except Exception:
            return False
    except Exception:
        return False


# -------------------- Script resolution --------------------

def ResolveScriptReadPath(fileName):
    """Return absolute path to a TAS script file, searching profile:jython then scripts:."""
    try:
        fn = '' if fileName is None else str(fileName).strip()
    except Exception:
        fn = ''
    if fn == '':
        return None

    # 1) profile:jython
    try:
        p1 = FileUtil.getExternalFilename('profile:jython/' + fn)
        if _ExistsFile(p1):
            return p1
    except Exception:
        pass

    # 2) scripts: directory
    try:
        sd = GetScriptsDir()
        if sd:
            p2 = os.path.join(str(sd), fn)
            if _ExistsFile(p2):
                return p2
    except Exception:
        pass

    # 3) scripts: scheme (in case scripts dir is non-standard)
    try:
        p3 = FileUtil.getExternalFilename('scripts:' + fn)
        if _ExistsFile(p3):
            return p3
    except Exception:
        pass

    return None


def ResolveWorkingScriptReadPath(direction, reportingNumber):
    """Return absolute path to a working script, preferring profile:jython/workings."""
    try:
        d = '' if direction is None else str(direction).strip()
        rn = '' if reportingNumber is None else str(reportingNumber).strip()
    except Exception:
        d = ''
        rn = ''
    if d == '' or rn == '':
        return None
    rel = 'workings' + os.sep + d + os.sep + rn + '.py'

    # profile first
    try:
        pj = GetProfileJythonDir()
        if pj:
            p1 = os.path.join(str(pj), rel)
            if _ExistsFile(p1):
                return p1
    except Exception:
        pass

    # scripts next
    try:
        sd = GetScriptsDir()
        if sd:
            p2 = os.path.join(str(sd), rel)
            if _ExistsFile(p2):
                return p2
    except Exception:
        pass

    return None


def GetWorkingsWriteDir(direction):
    """Return absolute dir for writing workings under profile:jython/workings/<direction>."""
    try:
        d = '' if direction is None else str(direction).strip()
    except Exception:
        d = ''
    if d == '':
        return None
    pj = GetProfileJythonDir()
    if not pj:
        return None
    target = os.path.join(str(pj), 'workings', d)
    EnsureDir(target)
    return target


# -------------------- InputStream resolution (text resources) --------------------

def FindInputStreamFor(fileName):
    """FindInputStream for a resource in profile:jython then scripts:. Returns stream or None."""
    try:
        fn = '' if fileName is None else str(fileName).strip()
    except Exception:
        fn = ''
    if fn == '':
        return None

    try:
        s = FileUtil.findInputStream('profile:jython/' + fn)
        if s is not None:
            return s
    except Exception:
        pass

    try:
        return FileUtil.findInputStream('scripts:' + fn)
    except Exception:
        return None
