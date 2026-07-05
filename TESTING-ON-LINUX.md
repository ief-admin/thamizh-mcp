# Testing thamizh-mcp on minnaham (Claude Code)

Why this route: the Cowork sandbox blocks ta.wiktionary.org / dsal.uchicago.edu /
tamilvu.org and can't run git over the E:\ mount. minnaham has open network + real
foma + the cloned repo, so live evolving-source tests and the lexicon-snapshot jobs
belong here.

## 0. Get the latest code (repo is already cloned on `develop`)
```bash
cd ~/projects/thamizh-mcp
git checkout develop
git pull
git log --format='%an <%ae>' -1     # must read: Saran Saravanan <saravanan3@duck.com>
```
(First time only, if the repo isn't here yet: `git clone -b develop https://github.com/ief-admin/thamizh-mcp.git ~/projects/thamizh-mcp`)

## 1. One-time setup
```bash
sudo apt update && sudo apt install -y foma            # real flookup on PATH (NOT foma-bin — that deb is empty)
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv (skip if already installed)
cd ~/projects/thamizh-mcp && uv sync                            # installs deps incl. pytest (dependency-groups)
which flookup && echo "மரம்" | flookup data/fst/noun.fst   # expect: மரம்	மரம்+noun+nom
```
No env vars needed: `config.py` auto-detects flookup on PATH and `data/fst/`.

## 2. Test ladder (run in order)
```bash
uv run pytest -v                       # expect 27 passed with live foma (25 without)
uv run python scripts/analyze.py மரத்தில்            # lemma மரம், both loc|soc kept, Tholkappiyam cites
uv run python scripts/analyze.py புத்தகம் --include meaning   # live Wiktionary pull (2 senses expected)
uv run python scripts/analyze.py புத்தகம் --include meaning   # again → must serve from cache
sqlite3 data/knowledge.sqlite3 'select word,field,source,tier,retrieved from claims;'  # write-back proof
```
What to verify on the live pull: senses carry `citation` URLs; `sources[].retrieved`
is today's date; a nonsense/rare word returns a meaning **gap**, not a guess.

## 3. Register with Claude Code as a real MCP server
```bash
claude mcp add thamizh -- uv --directory ~/projects/thamizh-mcp run thamizh-mcp
claude mcp list                        # should show thamizh (stdio)
```
Then in a Claude Code session: "Use analyze_word on மரத்தில் and show me the provenance."
Optional deeper poke: `npx @modelcontextprotocol/inspector uv run thamizh-mcp` (needs Node).

## 4. Committing work back
```bash
git add -A && git commit -m "..."      # identity is already the duck alias
git push origin develop
```
Open a PR `develop → main` at milestones (`main` is protected: PR-only).

## 5. Jobs that NEED this box (network-open)
1. **Madras Tamil Lexicon snapshot** — source the digitized data, pin it in `data/`
   (blueprint §10 open decision).
2. **TVA / govt கலைச்சொல் glossaries** — same: snapshot + pin.
3. Live Wiktionary shakedown across the 7 fixture words (`tests/fixtures/words.json`).

## Gotchas
- **foma:** package `foma`, NOT `foma-bin`.
- `data/knowledge.sqlite3` is gitignored — the self-enriching cache is machine-local.
- Wikimedia UA policy: descriptive UA is in the adapter (`THAMIZH_HTTP_UA` overrides).
- Wiktionary licence (CC BY-SA) — fine for private testing; resolve before any public release.
- `--include meaning` skips morphology by design (empty lemma there is not