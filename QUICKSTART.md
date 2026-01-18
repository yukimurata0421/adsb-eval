QUICKSTART
==========

This document provides the minimum steps required to run adsb-eval
using deterministic test data.

No configuration files are used.
All configuration is provided explicitly via environment variables.

-------------------------------------------------------------------------------

Prerequisites
-------------

- Python 3.9 or later
- Requires Python 3.10+ and requests (see requirements.txt)

-------------------------------------------------------------------------------

Quick start using test fixtures
-------------------------------

This mode runs adsb-eval against a fixed input file instead of a live
readsb instance.  
It is intended for first-time users and reproducible evaluation.

Step 1: Set environment variables
---------------------------------

Set the following environment variables before execution.

Example:

READSB_AIRCRAFT_JSON=tests/fixtures/aircraft_small.json
ADSB_SITE_LAT=36.120055
ADSB_SITE_LON=140.2323

No other configuration is required.

-------------------------------------------------------------------------------

Step 2: Run the distance logger
-------------------------------

Execute the distance logger script.

Example:

PYTHONPATH=src python3 src/adsb_dist_logger.py

This generates an append-only JSONL file at:

data/logs/dist_1m.jsonl

-------------------------------------------------------------------------------

Step 3: Generate summary output
-------------------------------

Generate a derived summary from accumulated JSONL logs.

Example:

PYTHONPATH=src python3 src/make_summary.py

This generates:

data/logs/summary.json

-------------------------------------------------------------------------------

Output notes
------------

- All files under data/ are runtime-generated artifacts
- data/ is intentionally ignored by git
- JSONL logs are append-only and never modified in place
- Low-sample or non-evaluable records are preserved

-------------------------------------------------------------------------------

Next steps
----------

For design rationale, evaluation methodology, and quality semantics,
see README.txt.

For continuous operation, these scripts are intended to be executed
periodically using cron or systemd timers.
