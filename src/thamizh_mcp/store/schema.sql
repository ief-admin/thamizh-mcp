-- THAMIZH MCP knowledge store (blueprint §5): self-enriching cache, keyed by normalized word.
-- One row per (word, field, source) claim — provenance is per-claim, not per-word.
CREATE TABLE IF NOT EXISTS claims (
    word        TEXT NOT NULL,              -- normalized form
    field       TEXT NOT NULL,              -- origin | lemma | meaning | formation | grammar | native_equivalent
    value_json  TEXT NOT NULL,              -- the claim payload (schema fragment)
    source      TEXT NOT NULL,              -- e.g. ThamizhiMorph, Tamil Wiktionary
    tier        TEXT NOT NULL CHECK (tier IN ('anchor', 'evolving')),
    authority   TEXT CHECK (authority IN ('Tholkappiyam', 'Nannūl')),
    confidence  REAL,
    retrieved   TEXT NOT NULL,              -- ISO date (evolving) or version pin (anchor)
    PRIMARY KEY (word, field, source)
);
CREATE INDEX IF NOT EXISTS idx_claims_word ON claims(word);
CREATE INDEX IF NOT EXISTS idx_claims_stale ON claims(tier, retrieved);

-- Transaction log (blueprint §12): every resolved analysis, kept as gold data for the future SLM
-- corpus. Not telemetry — a first-class output. eval_fixture=1 words are excluded from any published
-- dataset by the data-curation contamination guard. analysis_json is the full WordAnalysis.
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,              -- ISO-8601 UTC timestamp
    tool          TEXT NOT NULL,              -- the MCP tool that produced it (analyze_word, get_root, …)
    word          TEXT NOT NULL,              -- as received
    normalized    TEXT NOT NULL,              -- NFC normalized form
    eval_fixture  INTEGER NOT NULL DEFAULT 0, -- 1 → never publish (contamination guard)
    analysis_json TEXT NOT NULL               -- full WordAnalysis payload
);
CREATE INDEX IF NOT EXISTS idx_txn_normalized ON transactions(normalized);
CREATE INDEX IF NOT EXISTS idx_txn_fixture ON transactions(eval_fixture);
