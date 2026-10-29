# Angus Breeder Import (Apify actor)

Imports breeder contact details from the angus.org **Find a Breeder** search, one state at a time.
Each breeder becomes one dataset item with the same columns as the old Google Sheet tab, plus `State`.

## Input

| Field | Default | Meaning |
| --- | --- | --- |
| `states` | all 50 | Two-letter state codes, e.g. `["NE", "KS"]` |
| `targetWithPhones` | `0` (no limit) | Stop once this many breeders with a phone number are saved |
| `onlyWithPhones` | `false` | Skip breeders with no phone number |
| `delaySeconds` | `3` | Pause before each breeder contact lookup |
| `blockPauseMinutes` | `15` | Wait this long when throttled; doubles each time, up to 120 |
| `maxBreeders` | `0` (no limit) | Stop after this many breeders; handy for a test run |
| `whenThrottled` | `stop` | `stop`: save progress and end the run when angus.org throttles (rerun or schedule it later). `wait`: pause inside the run |
| `excludeDatasetIds` | none | Dataset IDs from runs made before this version; their breeders are skipped |
| `resetProgress` | `false` | Forget earlier runs and import everything again |
| `allRowsDatasetName` | `angus-breeders` | Named dataset that collects new rows from every run (empty = off) |
| `progressStoreName` | `angus-breeder-progress` | Named key-value store that remembers imported breeders |

## Output

Open the run's **Storage → Dataset** and export as **CSV** (or JSON/Excel).

`Status` is `OK`, `OK (no contact)` or `ERROR: …`.

## Reruns only import new breeders

Every breeder imported with a contact (`OK` or `OK (no contact)`) is remembered in the named key-value
store `angus-breeder-progress`, and so are states that finished completely. A new run skips those
breeders and states, so each run only adds new rows. Rows that ended in `ERROR`, or lookups that were
still unconfirmed when a run stopped, are not remembered, so the next run tries them again.

Each run's own dataset holds only that run's new rows. The named dataset `angus-breeders` collects the
new rows from every run in one place: export it from **Storage → Datasets** for the full list.

Breeders from runs made before this version are not in the store yet. Put those runs' dataset IDs in
`excludeDatasetIds` once (e.g. your first Nebraska run) and they will be skipped from then on.
To start again from scratch, tick `resetProgress`.

## Rate limiting

angus.org allows a short burst of contact lookups, then answers every lookup with an empty
"Search error". The actor treats 5 empty or failed lookups in a row as throttling, not as breeders
without contacts: it discards those 5, rewinds, and tries them once more on a fresh session. If it is
still throttled:

- `whenThrottled: stop` (default) saves progress and ends the run straight away, so no compute is
  spent waiting. Run it again later, or add a **Schedule** (e.g. every 30 minutes) so it keeps going
  on its own; each run continues with new breeders only.
- `whenThrottled: wait` pauses inside the run (`blockPauseMinutes`, doubling each time up to 120) and
  looks the same breeders up again. After 6 pauses with no real contact it stops. Waiting still
  counts as run time, so this uses more compute.

Lookups are paced with random jitter around `delaySeconds`. Each time the actor is throttled it slows
down by 1.5× (up to 4×), and it speeds back up after 25 clean lookups in a row. The learned pace is
kept in the progress store, so the next run starts at that pace.

It stops on any results-page problem (security challenge, pagination mismatch) instead of retrying.
Progress within a run is saved in the run's key-value store under `STATE`, so a migrated or
resurrected run continues where it left off without duplicating rows.

## Importing into Apify

1. Push this folder to a Git repository.
2. In Apify Console: **Actors → Develop new → Link Git repository**, and paste the repo URL
   (for a private GitHub repo, connect GitHub or add Apify's deploy key).
3. Build, then start a run with `states: ["NE"]` and `maxBreeders: 10` to check it works.

## Running locally

    pip install -r requirements.txt
    apify run --input '{"states": ["NE"], "maxBreeders": 5}'
