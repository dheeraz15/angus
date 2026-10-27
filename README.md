# Angus Breeder Import (Apify actor)

Imports breeder contact details from the angus.org **Find a Breeder** search, one state at a time.
Each breeder becomes one dataset item with the same columns as the old Google Sheet tab, plus `State`.

## Input

| Field | Default | Meaning |
| --- | --- | --- |
| `states` | all 50 | Two-letter state codes, e.g. `["NE", "KS"]` |
| `delaySeconds` | `0.75` | Pause before each breeder contact request |
| `maxBreeders` | `0` (no limit) | Stop after this many breeders; handy for a test run |

## Output

Open the run's **Storage → Dataset** and export as **CSV** (or JSON/Excel).

`Status` is `OK`, `OK (no contact)` or `ERROR: …`. The run stops after 3 contact errors in a row,
or on any results-page problem (security challenge, pagination mismatch), instead of hammering the site.

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
