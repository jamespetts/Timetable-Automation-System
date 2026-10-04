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
# Purpose
# -------
# Provide an ultra-lightweight, JMRI-accurate function to search the roster
# by three fields: Roster ID, Model, Comment.
#
# Public API
# ----------
# def rosterSearch(idList, modelList, commentList) -> list[str]
#
# Arguments
# ---------
# Each argument is either:
#   * None
#   * an empty list: []
#   * a list whose first element may be the Python value None followed by one
#     or more string tokens: [None, "token1", "token2", ...]
#   * a list of one or more string tokens without a leading None:
#       ["token1", "token2", ...]
#
# Tokens:
#   * Tokens are matched case-insensitively as substrings.
#   * Whitespace-only tokens are ignored.
#
# Field-usage rules
# -----------------
# 1) Ignore rule
#    If a list is None, empty ([]), or exactly [None], that field is ignored
#    entirely when matching. Examples:
#      - idList=None           => ID is ignored
#      - modelList=[]          => Model is ignored
#      - commentList=[None]    => Comment is ignored
#
# 2) Required vs Optional fields
#    - If a list STARTS with the Python value None AND contains one or more
#      additional tokens (e.g. [None, "X", "Y"]), that field is REQUIRED and
#      must match at least one of its tokens.
#    - If a list does NOT start with None and contains one or more tokens
#      (e.g. ["X", "Y"]), that field is OPTIONAL and may match any of its
#      tokens.
#
# 3) No tokens at all (wildcard)
#    If ALL three lists are ignored (per rule 1) AND contain no usable tokens,
#    return ALL roster IDs (randomized).
#
# 4) Combining logic
#    Let R = the set of REQUIRED fields that have tokens.
#    Let O = the set of OPTIONAL fields that have tokens.
#
#    - If R is empty and O is non-empty:
#        Match if ANY one optional field matches (logical OR across fields).
#        Example:
#          idList=["158"] , modelList=["Class 158"], commentList=None
#          => match if ID contains "158" OR Model contains "Class 158".
#
#    - If R is non-empty and O is empty:
#        Match if ALL required fields match their tokens (logical AND).
#        Example:
#          idList=[None,"158"] , modelList=[None,"Class 158"] , commentList=[None]
#          => must match ID contains "158" AND Model contains "Class 158",
#             Comment ignored.
#
#    - If both R and O are non-empty:
#        Match if (ALL required fields match) AND (at least one optional field
#        matches).
#        This preserves the "as well as at least one from the other lists"
#        requirement when there are optional lists present.
#
# Return
# ------
# A list of roster IDs (strings). The list:
#   * contains each roster ID only once;
#   * is in random order on each call;
#   * is empty if nothing matches.
#
# Notes on JMRI API usage
# -----------------------
# - The roster is read via jmri.jmrit.roster.Roster.getDefault().getAllEntries().
# - Field access is via:
#       RosterEntry.getId(), RosterEntry.getModel(), RosterEntry.getComment()
#   These are read-only operations and are safe under normal use.
#
# Examples
# --------
# 1) Any-field OR (no required fields):
#    rosterSearch(["158"], ["Class 158"], None)
#    => match entries whose ID contains "158" OR Model contains "Class 158".
#
# 2) Required AND, with comment ignored:
#    rosterSearch([None, "158"], ["Class 158"], [None])
#    => match entries whose ID contains "158" AND Model contains "Class 158".
#
# 3) Wildcard (all entries):
#    rosterSearch(None, [], [None])
#    => return all roster IDs in random order.
#
# Implementation
# --------------
# - ASCII-only.
# - CamelCase identifiers (module-level function name uses lower camelCase to
#   match existing helper style in this codebase).
# - No external dependencies; suitable for JMRI's Jython runtime.
#
# Copyright
# ---------
# (c) James E. Petts. 

import jmri
from jmri.jmrit.roster import Roster
import random

def rosterSearch(idList, modelList, commentList):
    """
    See the header comment for full API details.
    """

    def Prepare(listArg):
        # Returns (ignored, required, tokens)
        if listArg is None:
            return True, False, []
        if isinstance(listArg, list) and len(listArg) == 0:
            return True, False, []
        if isinstance(listArg, list) and len(listArg) == 1 and listArg[0] is None:
            return True, False, []

        if isinstance(listArg, list) and len(listArg) > 0 and listArg[0] is None:
            # Required field with tokens after the leading None
            tokens = [str(t).strip() for t in listArg[1:] if t is not None and str(t).strip() != ""]
            if len(tokens) == 0:
                # No usable tokens after None => treat as ignored
                return True, False, []
            return False, True, tokens
        else:
            # Optional field tokens
            tokens = []
            if isinstance(listArg, list):
                for t in listArg:
                    if t is not None:
                        s = str(t).strip()
                        if s != "":
                            tokens.append(s)
            else:
                # Non-list value: ignore
                return True, False, []
            if len(tokens) == 0:
                return True, False, []
            return False, False, tokens

    # Normalize inputs
    IdIgnored, IdRequired, IdTokens = Prepare(idList)
    ModelIgnored, ModelRequired, ModelTokens = Prepare(modelList)
    CommentIgnored, CommentRequired, CommentTokens = Prepare(commentList)

    HasAnyTokens = (len(IdTokens) + len(ModelTokens) + len(CommentTokens)) > 0
    if not HasAnyTokens and IdIgnored and ModelIgnored and CommentIgnored:
        # Wildcard: return all roster IDs in random order
        allIds = [e.getId() for e in Roster.getDefault().getAllEntries()]
        # Defensive: filter out Nones or blanks if ever present
        allIds = [rid for rid in allIds if rid is not None and str(rid).strip() != ""]
        random.shuffle(allIds)
        return allIds

    HasRequired = IdRequired or ModelRequired or CommentRequired
    HasOptional = ((not IdRequired and not IdIgnored and len(IdTokens) > 0) or
                   (not ModelRequired and not ModelIgnored and len(ModelTokens) > 0) or
                   (not CommentRequired and not CommentIgnored and len(CommentTokens) > 0))

    def FieldMatches(textValue, tokens):
        if tokens is None or len(tokens) == 0:
            return False
        tv = "" if textValue is None else str(textValue)
        tl = tv.lower()
        for tok in tokens:
            if tok.lower() in tl:
                return True
        return False

    results = []
    entries = Roster.getDefault().getAllEntries()

    for entry in entries:
        # Read fields with robust fallbacks
        try:
            idText = entry.getId()
        except:
            idText = ""
        try:
            modelText = entry.getModel()
        except:
            modelText = ""
        try:
            commentText = entry.getComment()
        except:
            commentText = ""

        # Evaluate required fields (AND across all required)
        if IdRequired and not FieldMatches(idText, IdTokens):
            continue
        if ModelRequired and not FieldMatches(modelText, ModelTokens):
            continue
        if CommentRequired and not FieldMatches(commentText, CommentTokens):
            continue

        # Evaluate optional fields
        if HasOptional:
            matchedOptional = False
            if (not IdRequired) and (not IdIgnored) and FieldMatches(idText, IdTokens):
                matchedOptional = True
            if (not ModelRequired) and (not ModelIgnored) and FieldMatches(modelText, ModelTokens):
                matchedOptional = True
            if (not CommentRequired) and (not CommentIgnored) and FieldMatches(commentText, CommentTokens):
                matchedOptional = True
            if not matchedOptional:
                continue

        # If we reached here, it matches
        rid = entry.getId()
        if rid is not None and str(rid).strip() != "":
            results.append(str(rid))

    # Unique and randomized
    # (Roster IDs are unique in JMRI by definition, but de-dup for safety.)
    if len(results) > 1:
        results = list(dict.fromkeys(results))
        random.shuffle(results)

    return results
