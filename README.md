# adsb-eval

**ADS-B reception performance evaluation framework**  
*Designed for reproducibility, fault tolerance, and human decision-making.*

---

## What this project is NOT

This project is intentionally **not** designed to:

- Automatically optimize receiver parameters
- Judge performance based on instantaneous values or UI metrics
- Depend on Web dashboards for execution or evaluation
- Produce a single “best” configuration automatically

All optimization decisions are **explicitly made by humans**,
based on reproducible statistical evidence.

---

## Design principles

This system is built on the following principles:

- **Systems are expected to fail**
  - Power loss, process crashes, partial file corruption are assumed
- **Evaluation must be reproducible**
  - All raw data is stored as append-only logs
  - Results can always be recalculated from original data
- **Execution is Web-independent**
  - `systemd` is the execution and supervision authority
  - Web/UI is read-only and optional
- **Statistics support decisions, not automation**
  - The system provides evidence
  - Humans make the final judgment
- **External services are not blindly trusted**
  - Used only as consistency checks, never as ground truth

---

## Core concept

ADS-B reception quality cannot be reliably evaluated using
instantaneous values such as:

- maximum distance
- current aircraft count
- UI-based rankings

Instead, this project evaluates **state transitions over time**
using statistically comparable units.

---

## Evaluation model (overview)

### Primary objective
- **Maximize unique aircraft captured per day**
  (`uniq ICAO / day`)

### Secondary indicators
- Position rate (data quality)
- Distance distribution (e.g. p95)
- Near-range degradation penalties

### Evaluation unit
- **Day-of-week × time-of-day blocks (2-hour blocks)**
- One week = 84 independent comparison blocks

This design minimizes bias caused by:
- traffic diurnal cycles
- curfews
- day-of-week effects
- seasonal variability

---

## Uncertainty handling (design note)

ADS-B reception performance is inherently non-deterministic due to:
- weather conditions
- traffic volume fluctuations
- temporary interference
- occasional low-traffic or no-flight days

At the current stage, this project focuses on
deterministic, block-based comparisons using aggregated metrics.

However, uncertainty-aware evaluation is considered an important
future extension of this framework.

### Planned direction (not yet implemented)

- Block-based resampling (e.g. bootstrap)
- Confidence interval estimation for score distributions
- Decision support using lower confidence bounds (LCB)

The intent is **not to automate optimization**, but to provide
quantitative uncertainty information so that humans can make
more robust configuration decisions.

---

## Directory structure and responsibility

```
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
- `src/lib/` is **not a public library**.  
  It contains internal building blocks shared by executables.
- Example systemd unit files are provided for reference only.  
  Actual execution and supervision must be adapted
  to each environment’s operational requirements.

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

---

## License

MIT License