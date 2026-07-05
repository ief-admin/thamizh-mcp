"""Tamil Wiktionary (EVOLVING) — meaning pulled at query time, cached with retrieval date.

httpx.AsyncClient with a hard timeout; miss/timeout → honest NoEntry. Kept only if
attributable (URL recorded per pull). Licence: CC BY-SA — cache/serve obligations must be
resolved before public release (blueprint §10).
NOTE: unreachable from the Cowork sandbox (allowlist); unit tests mock the client, live
integration runs in deployment (Cloud Run / local with network).
"""
from __future__ import annotations

import datetime as _dt
import os
import re

import httpx

from thamizh_mcp import config
from thamizh_mcp.adapters.base import AdapterResult, NoEntry, SourceAdapter
from thamizh_mcp.schema import SourceRef

_API = "https://ta.wiktionary.org/w/api.php"
# Wikimedia UA policy (meta.wikimedia.org/wiki/User-Agent_policy): generic client UAs get 403.
# Must be descriptive + carry contact info. Env-overridable for deployments.
_UA = os.environ.get(
    "THAMIZH_HTTP_UA",
    "ThamizhMCP/0.1 (Tamil word-grammar MCP server; contact: saravanan3@duck.com) httpx",
)
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}
_MARKUP = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]|'''?|\{\{[^}]*\}\}")
_HEADING = re.compile(r"^=+\s*(.*?)\s*=+\s*$")
_PORUL_TMPL = re.compile(r"^\{\{\s*பொருள்")   # {{பொருள்}} template opens the meaning section
_TMPL_LINE = re.compile(r"^\{\{")              # any other top-of-line template closes it


def extract_glosses(wikitext: str, limit: int = 8) -> list[str]:
    """Definition lines → clean Tamil gloss strings.

    ta.wiktionary formats seen in the wild (fixture-tested):
      - en-style:      '# gloss' lines anywhere (examples '#:' skipped)
      - heading style: '*'/':'/':*' bullets under a ==பொருள்== heading or ';பொருள்' line
      - template style ({{பொருள்}} … {{விளக்கம்}}): ':*' definition bullets between the
        {{பொருள்}} template line and the next template/heading section marker
    Latin-dominant lines (e.g. '*[[book]] (ஆங்)' translations) are dropped — Tamil glosses
    only; gloss_en comes later from proper bilingual sources.
    """
    glosses: list[str] = []
    in_porul = False
    wikitext = re.sub(r"<!--.*?-->", "", wikitext, flags=re.DOTALL)
    for raw in wikitext.splitlines():
        line = raw.strip()
        if not line:
            continue
        h = _HEADING.match(line)
        if h:
            in_porul = "பொருள்" in h.group(1)
            continue
        if line.startswith(";"):
            in_porul = "பொருள்" in line
            continue
        if _TMPL_LINE.match(line):
            in_porul = bool(_PORUL_TMPL.match(line))
            continue
        take = None
        if line.startswith("#") and not line.startswith(("#:", "#*", "##")):
            take = line
        elif in_porul and line[0] in ":*":
            take = line
        if take:
            take = take.lstrip(":*#").strip()
            g = _MARKUP.sub(lambda mm: mm.group(1) or "", take).strip(" .;–—\t'")
            if g and not _latin_dominant(g):
                glosses.append(g)
            if len(glosses) >= limit:
                break
    return glosses


def _latin_dominant(text: str) -> bool:
    """True when a cleaned line is mostly Latin script — a translation, not a Tamil gloss."""
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    tamil = sum(1 for ch in text if 0x0B80 <= ord(ch) <= 0x0BFF)
    return latin > tamil


class TamilWiktionaryAdapter(SourceAdapter):
    name = "Tamil Wiktionary"
    tier = "evolving"

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_s: float | None = None):
        self._client = client  # injectable for tests
        self.timeout_s = timeout_s or config.HTTP_TIMEOUT_S

    async def lookup(self, normalized_word: str) -> AdapterResult | NoEntry:
        params = {"action": "query", "titles": normalized_word, "prop": "revisions",
                  "rvprop": "content", "rvslots": "main", "format": "json", "formatversion": "2"}
        try:
            if self._client is not None:
                resp = await self._client.get(_API, params=params, headers=_HEADERS)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_s, headers=_HEADERS) as client:
                    resp = await client.get(_API, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            return NoEntry(source=self.name, reason="timeout", note=f"no response in {self.timeout_s}s")
        except Exception as exc:  # network/HTTP/JSON — honest gap, never a guess
            return NoEntry(source=self.name, reason="error", note=f"{type(exc).__name__}: {exc}"[:200])

        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or "revisions" not in pages[0]:
            return NoEntry(source=self.name, reason="no_entry", note=f"no ta.wiktionary page for {normalized_word}")
        wikitext = pages[0]["revisions"][0]["slots"]["main"]["content"]
        glosses = extract_glosses(wikitext)
        if not glosses:
            return NoEntry(source=self.name, reason="no_entry", note="page exists but no definition lines parsed")
        today = _dt.date.today().isoformat()
        url = f"https://ta.wiktionary.org/wiki/{normalized_word}"
        return AdapterResult(
            fields={"senses": [{"gloss_ta": g, "citation": url} for g in glosses]},
            sources=[SourceRef(name=self.name, tier="evolving", ref=url, retrieved=today)],
            tier="evolving")
