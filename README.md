# Secret Thresholds: an operationally safe watermark for detecting forged tank levels in water distribution SCADA

Replication package for the paper *Secret Thresholds: An Operationally Safe Watermark for
Detecting Forged Tank Levels in Water Distribution SCADA* (M. R. Jasim).

The defence replaces the public hysteresis thresholds of on/off pump and valve rules with
secret thresholds drawn **inside** the public band and redrawn after every switch, so that
every natural switch probes a model-aware forger at no extra operational cost. A matched-event
CUSUM detector tests the reported level at each switch.

## Studies

| Study | Question | Networks | Seeds | Folder |
|-------|----------|----------|-------|--------|
| 3 | secret thresholds vs. toggle probing | C-Town, Richmond, Net6 | 300–309 | `results/study3_run15` |
| 4 | vs. prior watermark designs (random delay, parsimonious probing, autoencoder) | C-Town, Richmond, Net6 | 400–409 | `results/study4_run16` |
| 5 | network-fidelity check on a measured SCADA polling channel (DHALSIM) | C-Town | 500–509 | `results/study5_run17` |

All three studies were **pre-registered**: the code (by MD5 hash), arms, seeds, outcome,
hypotheses, statistical tests and validity rules were frozen before any test seed was run.
The registration files are in `registrations/`. Development seeds (100–101) were never reused.
Failed hypotheses are reported as such in the paper.

## Layout

- `code/` — the frozen simulation and analysis scripts.
  - `pilot15.py` / `pilot16.py` / `pilot17.py` — the test benches for Studies 3 / 4 / 5.
  - `analyse15.py` / `analyse16.py` / `analyse17.py` — per-study analysis (hypothesis tests).
  - `fit5a.py` — fits the two-state Markov polling channel from DHALSIM output (Study 5a).
- `registrations/` — the pre-registration text files with the frozen-code MD5 hashes.
- `results/` — the per-seed result JSON files (final only; EPANET intermediates omitted).
- `figures/` — the matplotlib scripts that produce the paper figures.
- `dhalsim_patch/` — a unified diff against DHALSIM (Murillo et al., 2023) adding the
  secret-threshold PLC controls, Linux-bridge switches and the Study 5 configs, plus an
  example PLC secret-config file.

## Reproducing

Requirements: Python 3.10+, `numpy`, `scipy`, `pandas`, `matplotlib`, and WNTR/EPANET
(for the simulation). Study 5a additionally needs DHALSIM with the patch in `dhalsim_patch/`
applied (`git apply dhalsim_secret_thresholds.patch` on the DHALSIM tree at commit 51a5e00).

Example — re-run and analyse Study 4 on C-Town:

```bash
MPLBACKEND=Agg EP=8 CAL=56 ALPHAS=0.0005,0.01 \
  python3 code/pilot16.py ctown 400,401,402,403,404,405,406,407,408,409
python3 code/analyse16.py ctown
```

Study 5b inserts the measured channel (`results/study5_run17/chan_ctown.json`):

```bash
CHAN=results/study5_run17/chan_ctown.json MPLBACKEND=Agg EP=8 CAL=56 \
  ARMS=passive,hyst0.3,delay0.3 python3 code/pilot17.py ctown 500,...,509
python3 code/analyse17.py ctown
```

## Integrity

`MD5SUMS.txt` lists the hashes of the code and figure scripts as published here. The
registration files record the hashes that were frozen before the test seeds were run.

## Citing

See the paper. DHALSIM: Murillo et al. (2023), *Journal of Water Resources Planning and
Management*, 149(5). No external funding.

## License

Code released under the MIT License (see `LICENSE`). The DHALSIM patch applies to DHALSIM,
which carries its own license.
