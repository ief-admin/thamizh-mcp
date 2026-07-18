"""Runtime configuration — anchor locations, binaries, timeouts. Env-overridable."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ThamizhiMorph anchor (pins in data/PINS.md)
FST_DIR = Path(os.environ.get("THAMIZH_FST_DIR", REPO_ROOT / "data" / "fst"))
FLOOKUP = os.environ.get("THAMIZH_FLOOKUP") or shutil.which("flookup")
FLOOKUP_LIB = os.environ.get("THAMIZH_FLOOKUP_LIB")  # extra LD_LIBRARY_PATH if needed
THAMIZHIMORPH_PIN = "sarves/thamizhi-morph@adbacced (2026-07-02)"

# Primary FSTs (guessers excluded — they invent analyses for unknown words; that is
# exactly the unsourced-guess failure mode this project exists to remove).
PRIMARY_FSTS = ("noun.fst", "pronoun.fst", "adj.fst", "adv.fst", "part.fst",
                "verb-c3.fst", "verb-c4.fst", "verb-c11.fst", "verb-c12.fst",
                "verb-c62.fst", "verb-c-rest.fst")

FLOOKUP_TIMEOUT_S = float(os.environ.get("THAMIZH_FLOOKUP_TIMEOUT", "10"))
HTTP_TIMEOUT_S = float(os.environ.get("THAMIZH_HTTP_TIMEOUT", "10"))

# Indic-To-Pure-Tamil equivalents (evolving-tier, local vendored CSVs; pins in data/PINS.md).
# The four attributable community sub-lists — combined_all.csv is their dedup merge, but we load
# the sub-lists so every candidate cites the actual list(s) that attest it.
EQUIVALENTS_DIR = Path(os.environ.get(
    "THAMIZH_EQUIVALENTS_DIR", REPO_ROOT / "data" / "equivalents" / "indic-to-pure-tamil"))
I2PT_SUBLISTS = ("viruba.csv", "tamilchol.csv", "thamizhdna-org.csv", "tamilmandram.csv")
I2PT_PIN = "narVidhai/Indic-To-Pure-Tamil@f734646 (2026-07-02)"

DEFAULT_DB = Path(os.environ.get("THAMIZH_DB", REPO_ROOT / "data" / "knowledge.sqlite3"))

# Transaction logging (blueprint §12): every resolved analysis is logged as gold data, on by default.
TXN_LOG = os.environ.get("THAMIZH_TXN_LOG", "1") not in ("0", "false", "no", "")
# Contamination guard (D-005): words listed here are flagged eval_fixture on every logged transaction
# so the data-curation skill can drop them from published datasets. thamizh-eval extends the file.
EVAL_FIXTURES_FILE = Path(os.environ.get("THAMIZH_EVAL_FIXTURES", REPO_ROOT / "data" / "eval_fixtures.json"))


def flookup_available() -> bool:
    return bool(FLOOKUP) and Path(FLOOKUP).exists() and FST_DIR.is_dir()


def eval_fixture_words() -> frozenset[str]:
    """NFC-normalized set of eval/regression words to exclude from published data (best-effort load)."""
    import json
    import unicodedata
    try:
        data = json.loads(EVAL_FIXTURES_FILE.read_text("utf-8"))
        return frozenset(unicodedata.normalize("NFC", w) for w in data.get("words", []))
    except (OSError, ValueError):
        return frozenset()
