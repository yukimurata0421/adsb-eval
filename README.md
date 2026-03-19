# adsb-eval

**ADS-B reception performance evaluation framework**  
*Designed for reproducibility, fault tolerance, and human decision-making.*

---

## Quick Start

This project is intended to be used together with an existing ADS-B receiver
that produces runtime data (e.g., `readsb`).

1. Prepare an ADS-B receiver and ensure JSON runtime outputs are available.
2. Configure input paths and receiver parameters in scripts under `src/`.
3. Run the logger / evaluator scripts directly.

For a minimal example using test fixtures, see [QUICKSTART.md](QUICKSTART.md).  
Detailed design notes are documented in `docs/`.

---

## What this project is NOT

This project is intentionally **not** designed to:

- Automatically optimize receiver parameters
- Judge performance using instantaneous values  
  (e.g., single-point maximum distance or momentary aircraft count)
- Treat dashboards, public rankings, or aggregator leaderboards
  as ground truth

---

## Design principles

This system is built on the following principles:

- **Systems are expected to fail**
  - Power loss, process crashes, partial file corruption are assumed
- **Evaluation must be reproducible**
  - All raw data is stored as append-only logs
  - Results can always be recalculated from original data
- **Execution is Web-independent**
  - Execution and supervision are handled outside the Web layer
  - Web/UI components, if any, are read-only and optional
- **Statistics support decisions, not automation**
  - The system provides evidence
  - Humans make the final judgment
- **External services are not blindly trusted**
  - Used only as consistency checks, never as ground truth

---

## Core concept

ADS-B reception quality cannot be reliably evaluated using
instantaneous values such as:

- maximum distance at a single moment
- current aircraft count
- UI-based or leaderboard-style rankings

Instead, this project focuses on **time-series behavior and state transitions**
derived from append-only logs, so that reception performance can be
re-evaluated, compared, and audited later.

---

## Current scope

At the current stage, this project provides:

- Reliable, append-only logging of ADS-B–related metrics
- A foundation for comparing reception performance across configurations
  using reproducible data
- A clear separation between data collection, evaluation logic, and presentation

Explicit scoring functions, block-based comparison models,
and uncertainty-aware evaluation are **not yet implemented**
and are treated as future extensions.

---

## Results (observed)

- The daily aircraft capture count increased by **more than 200%**
  after hardware and configuration changes at the author’s station.

**Note:**  
This improvement is an observed result under a specific location and environment.
One of the goals of this project is to make such improvements
**measurable, explainable, and reproducible** using logged data,
rather than relying on anecdotal or UI-based impressions.

---

## Roadmap (planned, not yet implemented)

The following items represent planned directions, not current behavior:

- Primary objective:
  - Maximize unique aircraft captured per day (`uniq ICAO / day`)
- Planned evaluation units:
  - Day-of-week × time-of-day blocks (e.g., 2-hour blocks)
  - One week = 84 comparison blocks
- Planned uncertainty handling:
  - Block-based resampling (e.g., bootstrap)
  - Confidence interval estimation for score distributions
  - Decision support using lower confidence bounds (LCB)

These extensions are intended to **support human decision-making**,
not to enable automatic optimization.

---

## Directory structure and responsibility

```text
adsb-eval/
├── src/
│   ├── lib/        # Internal modules (JSONL handling, locking, statistics)
│   └── *.py        # Executable evaluation logic
├── data/
│   ├── logs/       # Append-only JSONL raw logs
│   └── state/      # Minimal state (block flags, cooldowns)
├── examples/
│   └── systemd/    # Example systemd service/timer units (reference only)
└── docs/           # Design notes (optional)
```

**Notes:**

- `src/lib/` is not a public library.  
  It contains internal building blocks shared by executables.

- Example systemd unit files are provided for reference only.  
  Actual execution and supervision must be adapted to each environment’s
  operational requirements.

**Execution, evaluation, storage, and presentation are strictly separated.**

---

## Data philosophy

- **Append-only logs are the source of truth**
- Aggregated results are disposable
- No destructive writes
- All outputs are derived artifacts

This ensures:
- post-hoc verification
- regression analysis
- future re-interpretation

---

## External references

- ADS-B data is continuously fed to multiple public aggregators  
  (FlightRadar24 / PlaneFinder / ADSBexchange)  
  **for external consistency checks only**, not ranking or promotion.

- Design background and decision rationale are documented  
  in long-form articles (Qiita / Zenn).

---

## Intended audience

This project is intended for:

- ADS-B station operators
- Infrastructure / SRE engineers
- Engineers interested in reproducible evaluation systems
- Anyone designing systems where **judgment must remain human**

## Documentation

- Design background and evaluation philosophy: `docs/design.md`

---

Current development is based on the v2 design.

---
## License

MIT License
