"""Reusable table filter engine.

A filter is defined by a match_mode plus include_patterns / exclude_patterns.
Matching semantics: a table name is INCLUDED if it matches ANY include
pattern (or if include_patterns is empty, everything matches by default),
AND it is then EXCLUDED if it matches ANY exclude pattern.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from enum import Enum


class MatchMode(str, Enum):
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    CONTAINS = "contains"
    EXACT = "exact"
    WILDCARD = "wildcard"
    REGEX = "regex"


@dataclass
class FilterDefinition:
    name: str
    match_mode: str
    include_patterns: list[str]
    exclude_patterns: list[str]


def _pattern_matches(name: str, pattern: str, match_mode: str) -> bool:
    name_u = name.upper()
    pattern_u = pattern.upper()
    if match_mode == MatchMode.STARTS_WITH:
        return name_u.startswith(pattern_u)
    if match_mode == MatchMode.ENDS_WITH:
        return name_u.endswith(pattern_u)
    if match_mode == MatchMode.CONTAINS:
        return pattern_u in name_u
    if match_mode == MatchMode.EXACT:
        return name_u == pattern_u
    if match_mode == MatchMode.WILDCARD:
        return fnmatch.fnmatchcase(name_u, pattern_u)
    if match_mode == MatchMode.REGEX:
        return re.search(pattern, name) is not None
    raise ValueError(f"Unknown match_mode: {match_mode}")


def matches(name: str, filter_def: FilterDefinition) -> bool:
    includes = filter_def.include_patterns or []
    excludes = filter_def.exclude_patterns or []

    included = True if not includes else any(
        _pattern_matches(name, p, filter_def.match_mode) for p in includes
    )
    if not included:
        return False
    excluded = any(_pattern_matches(name, p, filter_def.match_mode) for p in excludes)
    return not excluded


def apply_filter(names: list[str], filter_def: FilterDefinition | None) -> list[str]:
    """Return the subset of `names` that pass the filter. None = pass-through."""
    if filter_def is None:
        return list(names)
    return [n for n in names if matches(n, filter_def)]
