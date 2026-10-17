"""
backend/issue_explorer/query_parser.py
─────────────────────────────────────────────────────────────────
SOLID  S — แปลง raw query string เป็น Structured ParsedQuery และ Parameterized SQL
GRASP  Information Expert — จัดการ parsing logic และ escape syntax
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


def escape_like(s: str) -> str:
    """Escape special characters (% _ \\) for SQLite LIKE queries with ESCAPE '\\'."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class ParsedQuery:
    # Each inner tuple represents OR-joined terms. The outer tuple represents AND-joined groups.
    # e.g. (("สตง", "คตง"), ("ไทยพีบีเอส",)) => (สตง OR คตง) AND (ไทยพีบีเอส)
    groups: tuple[tuple[str, ...], ...]
    excludes: tuple[str, ...]

    def to_sql(self, fields: Sequence[str] = ("title", "summary")) -> tuple[str, list[str]]:
        """
        Build a parameterized SQL WHERE clause snippet using ESCAPE '\\'.
        Returns (sql_where_snippet, params_list).
        """
        if not self.groups and not self.excludes:
            return "1=1", []

        clauses: list[str] = []
        params: list[str] = []

        # Positive AND groups
        for or_terms in self.groups:
            if not or_terms:
                continue
            or_parts: list[str] = []
            for term in or_terms:
                escaped = escape_like(term)
                pattern = f"%{escaped}%"
                for field in fields:
                    or_parts.append(f"{field} LIKE ? ESCAPE '\\'")
                    params.append(pattern)
            if or_parts:
                clauses.append(f"({' OR '.join(or_parts)})")

        # Excludes (AND NOT)
        for term in self.excludes:
            if not term:
                continue
            escaped = escape_like(term)
            pattern = f"%{escaped}%"
            ex_parts: list[str] = []
            for field in fields:
                ex_parts.append(f"{field} LIKE ? ESCAPE '\\'")
                params.append(pattern)
            if ex_parts:
                clauses.append(f"NOT ({' OR '.join(ex_parts)})")

        sql = " AND ".join(clauses) if clauses else "1=1"
        return sql, params


def parse_query(raw: str, max_terms: int = 6) -> ParsedQuery:
    """
    Parse a user query string into a structured ParsedQuery:
      - Quoted phrases: "ตึก สตง." -> kept intact
      - Negation: -กีฬา -> exclude term
      - Pipe: A | B -> OR group
      - Whitespace: A B -> AND groups
    """
    cleaned = raw.strip()
    if not cleaned:
        return ParsedQuery(groups=(), excludes=())

    # Tokenize preserving quoted strings
    # Regex matches: "quoted string" OR non-whitespace tokens
    token_pattern = re.compile(r'"([^"]+)"|(\S+)')
    raw_tokens: list[str] = []
    for match in token_pattern.finditer(cleaned):
        quoted, unquoted = match.groups()
        token = quoted if quoted is not None else unquoted
        if token and token.strip():
            raw_tokens.append(token.strip())

    excludes: list[str] = []
    positive_chunks: list[str] = []

    for tok in raw_tokens:
        if tok.startswith("-") and len(tok) > 1:
            ex_val = tok[1:].strip().strip('"')
            if ex_val:
                excludes.append(ex_val)
        else:
            positive_chunks.append(tok)

    # Process positive chunks for OR (|) vs AND (space)
    # Reassemble remaining tokens into groups separated by whitespace or pipe
    groups: list[tuple[str, ...]] = []
    
    # We examine if pipe syntax was used
    current_or_group: list[str] = []
    expecting_or = False

    for tok in positive_chunks:
        if tok == "|":
            expecting_or = True
            continue

        if "|" in tok:
            sub_parts = [p.strip() for p in tok.split("|") if p.strip()]
            if current_or_group and not expecting_or:
                groups.append(tuple(current_or_group))
                current_or_group = []
            current_or_group.extend(sub_parts)
            expecting_or = False
        else:
            if expecting_or:
                current_or_group.append(tok)
                expecting_or = False
            else:
                if current_or_group:
                    groups.append(tuple(current_or_group))
                    current_or_group = []
                current_or_group.append(tok)

    if current_or_group:
        groups.append(tuple(current_or_group))

    # Enforce max terms cap
    capped_groups = tuple(groups[:max_terms])
    capped_excludes = tuple(excludes[:max_terms])

    return ParsedQuery(groups=capped_groups, excludes=capped_excludes)
