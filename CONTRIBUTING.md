# Contributing to Thamizh MCP

Thanks for your interest in Thamizh MCP. This is a source-grounded tool for
Tamil word-grammar (சொல் இலக்கணம்) analysis. Its whole value rests on one
rule: **every answer is backed by an authentic source.** Please keep that in
mind for any contribution.

## Ways to contribute

- **Report a wrong answer.** If the server misclassifies a word, gives a wrong
  root, or attaches a citation that does not support the claim, open an issue
  with the input word, what you got, and what you expected. A source for the
  correct answer helps a lot.
- **Suggest or correct a source.** Pointers to authoritative Tamil grammar and
  lexical sources are welcome, especially anything that improves grounding.
- **Improve code or docs.** Bug fixes, tests, adapters, and documentation are
  all useful.

You do not need write access to contribute. Fork the repository, make your
change on a branch, and open a pull request. Maintainers review and merge.

## The grounding rule (read this before touching analysis code)

- Answers must cite a source. Do not add logic that returns a grammatical or
  lexical claim without a `SourceRef`.
- Grammar follows **Tholkappiyam first**, then Nannool, then later authorities.
  If sources disagree, surface the disagreement honestly rather than picking
  one silently.
- When the tool does not know, it says so (an honest gap), rather than guessing.
- New linguistic data must be pinned to a version and credited in `NOTICE`.

## Branching model

- `main` is the stable branch. It is protected: changes land only through a
  pull request, never a direct push.
- `develop` is the integration branch for day-to-day work.
- Branch off `develop` for a change (for example `feature/origin-classifier`),
  then open a PR into `develop`. Stable work is promoted from `develop` to
  `main` by a PR.
- External contributors: fork the repo and open a PR from your fork.

## Local setup

Requirements: Python 3.10+, [uv](https://docs.astral.sh/uv/), and `foma`
(for the morphological analyzer). On Debian/Ubuntu:

```bash
sudo apt install foma        # NOT foma-bin (that package is an empty transitional)
git clone https://github.com/ief-admin/thamizh-mcp.git
cd thamizh-mcp
uv sync                      # installs runtime + dev (pytest) dependencies
uv run pytest -q             # expect all tests to pass
```

The two live morphology tests are skipped automatically if `flookup` (foma)
is not on your PATH; the rest run without it.

## Tests

- Every bug fix or feature should come with a test.
- Run `uv run pytest -q` before opening a PR and make sure it is green.
- Parser or data changes should include a small fixture that captures the real
  input you fixed against, so the behavior stays pinned.

## Commits and pull requests

- Write clear commit messages in the imperative mood ("Add origin classifier",
  not "Added" or "Adds").
- Keep a PR focused on one thing. Describe what changed and why, and link any
  related issue.
- By contributing, you agree that your contribution is licensed under the
  project's Apache License 2.0 (see `LICENSE`).

## Data and licensing

- The code is Apache-2.0. Do not add third-party data or models without a
  license compatible with redistribution, and record the source, version pin,
  and license in `NOTICE`.
- Content derived from Tamil Wiktionary is CC BY-SA (share-alike). Be careful
  before bundling or redistributing any cached Wiktionary text.

## Conduct

Be respectful and constructive. Assume good faith. This project exists to serve
Tamil speakers and learners well; keep discussion focused on that.

## Contact

Questions can go through GitHub issues, or to saravanan3@duck.com.
Maintained under the International Educational Foundation (https://ief-global.org).
