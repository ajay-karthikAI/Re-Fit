# WATCHED_BOARDS — Phase 4 seed list (scratch)

Seed SourceBoards for job aggregation. **Per-company only** — there is no
cross-company search (see the Phase 4 scope lock in `CLAUDE.md`). This is a
starting seed; users register their own boards on top of it.

All entries below were **probed live against the public APIs on 2026-07-06**;
`~jobs` is the posting count seen that day (it drifts). Endpoints:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{token}/jobs`
- Lever: `https://api.lever.co/v0/postings/{site}?mode=json`

Both are public, no auth. A `404` here is exactly the "board went stale" case
ingestion must degrade to `unhealthy` on — do not let a 404 break the run.

## Greenhouse (token)

| Company        | token          | focus                         | ~jobs |
|----------------|----------------|-------------------------------|-------|
| Anthropic      | `anthropic`    | AI/ML — frontier lab          | 782   |
| Databricks     | `databricks`   | AI/ML + data infra            | 2367  |
| Scale AI       | `scaleai`      | AI/ML — data labeling         | 540   |
| Together AI    | `togetherai`   | AI/ML — inference infra       | 59    |
| Figma          | `figma`        | creative AI — design tools    | 168   |
| Descript       | `descript`     | creative AI — audio/video     | 7     |
| Stability AI   | `stabilityai`  | creative AI — generative      | 1     |
| Komodo Health  | `komodohealth` | healthcare AI — data platform | 43    |
| PathAI         | `pathai`       | healthcare AI — pathology     | 18    |

## Lever (site)

| Company     | site          | focus                          | ~jobs |
|-------------|---------------|--------------------------------|-------|
| Mistral AI  | `mistral`     | AI/ML — foundation models      | 177   |
| Anyscale    | `anyscale`    | AI/ML — Ray / distributed      | 1     |
| Palantir    | `palantir`    | data/AI — platforms            | 275   |
| Spotify     | `spotify`     | creative/audio ML              | 114   |
| Sword Health| `swordhealth` | healthcare AI — digital care   | 39    |

## RSS/Atom (feed URL)

Curated feed URLs — the third allowed source. Standalone *company* career-page
RSS is genuinely scarce in 2026 (most careers pages moved to Greenhouse/Lever/
Ashby, which don't emit RSS), so this list mixes a true company career feed with
a curated jobs feed. All were fetched live via `registry.fetch_board` on
2026-07-06 and came back `health=healthy`; `~n` is entries seen that day.

| Company / source | feed URL                                                    | focus                    | ~n |
|------------------|-------------------------------------------------------------|--------------------------|----|
| Mozilla          | `https://blog.mozilla.org/careers/feed/`                    | true company career page | 10 |
| RemoteOK (ML)    | `https://remoteok.com/remote-machine-learning-jobs.rss`     | AI/ML curated jobs feed  | 32 |

- **Mozilla** is a real company career-page feed (WordPress `Life@Mozilla`);
  entries are actual roles. This is the model the scope lock intends.
- **RemoteOK ML** is an aggregator jobs feed, not a single company — included
  because it's AI/ML-targeted and genuinely live. Flagged so nobody mistakes it
  for a company board.
- RSS entries carry **no** structured location/department (`None` by design —
  feeds are heterogeneous); matching leans on title + summary.

## Notes for whoever wires this up

- Mix is 9 Greenhouse / 5 Lever — Lever's AI-space footprint is thin now
  (many companies migrated to Greenhouse or Ashby), so probe before assuming a
  Lever site exists. Several plausible names (Cohere, Hugging Face, Runway,
  ElevenLabs, Glean, Harvey) returned `404` on both APIs on the probe date —
  they're likely on **Ashby**, which is a **stretch goal only** this phase.
- `stabilityai` (1) and `anyscale` (1) had almost nothing open on the probe
  date. Kept for topical relevance; they're good `unhealthy`-vs-just-empty
  test cases (200 with an empty list ≠ a dead board).
- RSS/Atom feeds are user-curated per the scope lock (never auto-discovered);
  the two above are a starting seed, added by hand.
