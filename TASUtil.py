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
# Shared helpers for the Timetable Automation System 

# IsDefaultReportingNumber(s):
#   Returns True iff s starts with uppercase 'TAS' and has at least one ASCII
#   alphanumeric character following (letters or digits). This treats both
#   auto-generated (e.g., 'TAS40') and user-supplied (e.g., 'TASX40') RNs as default.
def IsDefaultReportingNumber(s):
    try:
        x = str(s).strip()
    except Exception:
        return False
    if x == "":
        return False
    if not x.startswith("TAS"):
        return False
    # Require at least one ASCII letter or digit after 'TAS'
    rest = x[3:]
    if rest == "":
        return False
    for ch in rest:
        oc = ord(ch)
        is_digit = 48 <= oc <= 57
        is_upper = 65 <= oc <= 90
        is_lower = 97 <= oc <= 122
        if not (is_digit or is_upper or is_lower):
            return False
    return True

# MakeDefaultReportingNumberFromRow(rowNumber):
#   Returns 'TAS<rowNumber>' where rowNumber is expected to be an integer
#   matching the spreadsheet row (header counted).
def MakeDefaultReportingNumberFromRow(rowNumber):
    try:
        rn = int(rowNumber)
    except Exception:
        # Fallback: ensure we still return a usable ASCII string
        return "TAS{}".format(str(rowNumber).strip())
    return "TAS{}".format(rn)
