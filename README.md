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

## Output

Open the run's **Storage → Dataset** and export as **CSV** (or JSON/Excel).

`Status` is `OK`, `OK (no contact)` or `ERROR: …`.

## Rate limiting

angus.org allows a short burst of contact lookups (about 20), then answers every lookup with an empty
"Search error". The actor treats 5 empty or failed lookups in a row as throttling, not as breeders
without contacts: it discards those 5, pauses (`blockPauseMinutes`, doubling each time up to 120),
and looks the same breeders up again. After 6 pauses with no real contact it stops; **Resurrect** the
run later to continue. A run that ends on a few empty lookups pauses once and re-checks them.

So a run is slow: set a long run **Timeout** (Settings), e.g. 24 hours for 300 rows with phones.
It stops on any results-page problem (security challenge, pagination mismatch) instead of retrying.

Progress is saved in the run's key-value store under `STATE`, so a migrated or resurrected run
continues where it left off without duplicating rows.

## Importing into Apify

1. Push this folder to a Git repository.
2. In Apify Console: **Actors → Develop new → Link Git repository**, and paste the repo URL
   (for a private GitHub repo, connect GitHub or add Apify's deploy key).
3. Build, then start a run with `states: ["NE"]` and `maxBreeders: 10` to check it works.

## Running locally

    pip install -r requirements.txt
    apify run --input '{"states": ["NE"], "maxBreeders": 5}'
