# This file is part of the Timetable Automation System by James E. Petts
#
# Helper functions for deciding whether the JMRI scripts path needs changing.
# Pure Python/Jython 2.7 code so that it can be unit tested outside JMRI.
import os
import tempfile


def CanonicalLower(path):
    try:
        if path is None:
            return ''
        s = str(path).strip()
        if s == '':
            return ''
        try:
            return os.path.normcase(os.path.realpath(s))
        except:
            return os.path.normcase(os.path.abspath(s))
    except:
        return ''


def PathsEqual(pathA, pathB):
    return CanonicalLower(pathA) == CanonicalLower(pathB)


def PathLooksLikeProgramDir(candidatePath, programPath):
    cp = CanonicalLower(candidatePath)
    pp = CanonicalLower(programPath)
    if cp == '' or pp == '':
        return False
    if cp == pp:
        return True
    if not pp.endswith(os.sep):
        pp = pp + os.sep
    return cp.startswith(pp)


def IsWritableDir(path, createTempFileFunc=None, deleteFileFunc=None):
    testPath = None
    try:
        if path is None:
            return False
        d = str(path).strip()
        if d == '' or (not os.path.isdir(d)):
            return False
        if createTempFileFunc is None:
            fd, testPath = tempfile.mkstemp(prefix='tas_write_test_', suffix='.tmp', dir=d)
            os.close(fd)
        else:
            testPath = createTempFileFunc(d)
            if testPath is None:
                return False
        try:
            if deleteFileFunc is None:
                os.remove(testPath)
            else:
                deleteFileFunc(testPath)
        except:
            pass
        return True
    except:
        try:
            if testPath is not None and os.path.exists(testPath):
                if deleteFileFunc is None:
                    os.remove(testPath)
                else:
                    deleteFileFunc(testPath)
        except:
            pass
        return False


def NeedsScriptsPathUpdate(currentScriptsPath, tasDir, programPath, isWritableDirFunc=None):
    try:
        if tasDir is None or str(tasDir).strip() == '':
            return False
        if currentScriptsPath is None or str(currentScriptsPath).strip() == '':
            return True
        if PathsEqual(currentScriptsPath, tasDir):
            return False
        if PathLooksLikeProgramDir(currentScriptsPath, programPath):
            return True
        if isWritableDirFunc is None:
            writable = IsWritableDir(currentScriptsPath)
        else:
            writable = bool(isWritableDirFunc(currentScriptsPath))
        return (not writable)
    except:
        return True


def EnsureScriptsPathChanged(currentScriptsPath, tasDir, programPath, setScriptsPathFunc,
                             getScriptsPathFunc=None, isWritableDirFunc=None):
    try:
        if not NeedsScriptsPathUpdate(currentScriptsPath, tasDir, programPath, isWritableDirFunc):
            return ('unchanged', currentScriptsPath)
        if tasDir is None or str(tasDir).strip() == '':
            return ('invalid-target', currentScriptsPath)
        setScriptsPathFunc(str(tasDir))
        updatedPath = None
        if getScriptsPathFunc is not None:
            try:
                updatedPath = getScriptsPathFunc()
            except:
                updatedPath = None
        if updatedPath is None or str(updatedPath).strip() == '':
            updatedPath = tasDir
        if PathsEqual(updatedPath, tasDir):
            return ('updated', updatedPath)
        return ('set-unverified', updatedPath)
    except:
        return ('set-failed', currentScriptsPath)
