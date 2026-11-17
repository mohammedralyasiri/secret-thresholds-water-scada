# Study 5a: measure the SCADA polling channel in DHALSIM and fit the two-state Markov channel used in 5b.
# Stale step for a tag = SCADA value differs from ground truth at that step AND equals SCADA's previous value.
# Usage: python3 fit5a.py <dest.json> <run_dir> [<run_dir> ...]   (runs pooled; amendment A1)
import sys, json, numpy as np, pandas as pd
dest, run_dirs = sys.argv[1], sys.argv[2:]
W = 12                                                     # warm-up steps dropped per run (registered)
TANKS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']; ACTS = ['PU1', 'PU2', 'PU4', 'PU5', 'PU6', 'PU7', 'PU8', 'PU10', 'PU11', 'V2']

def load(d):
    s = pd.read_csv(f'{d}/scada_values.csv'); g = pd.read_csv(f'{d}/ground_truth.csv')
    n = min(len(s), len(g)); return s.iloc[:n].reset_index(drop=True), g.iloc[:n].reset_index(drop=True)
runs = [load(d) for d in run_dirs]

def stale_seq(sv, gv, tol):
    st = np.zeros(len(sv), bool)
    for k in range(1, len(sv)):
        st[k] = abs(sv[k] - gv[k]) > tol and abs(sv[k] - sv[k - 1]) <= tol
    return st[W:]

def fit(seqs):
    f2s, s2s, runs_, tot = [], [], [], []
    for st in seqs:
        f2s += [st[k] for k in range(1, len(st)) if not st[k - 1]]; s2s += [st[k] for k in range(1, len(st)) if st[k - 1]]
        tot += list(st); r = 0
        for x in st:
            if x: r += 1
            elif r: runs_.append(r); r = 0
        if r: runs_.append(r)
    a = float(np.mean(f2s)) if f2s else 0.0; b = float(np.mean(s2s)) if s2s else 0.0
    return a, b, float(np.mean(tot)), runs_, len(s2s)

res = {'levels': {}, 'acts': {}}; rep = {'runs': run_dirs, 'n_steps': int(sum(len(s) - W for s, g in runs)), 'levels': {}, 'acts': {}}
for t in TANKS:
    a, b, frac, rl, ns = fit([stale_seq(s[t].values, g[f'{t}_LEVEL'].values, 1e-6) for s, g in runs])
    res['levels'][t] = [a, b]; rep['levels'][t] = dict(a=a, b=b, stale_frac=frac, run_lengths=np.bincount(rl).tolist() if rl else [], n_stale_prev=ns)
for a_ in ACTS:
    seqs, lags = [], []
    for s, g in runs:
        col = f'{a_}_STATUS'
        if col not in g or a_ not in s: continue
        gs = (g[col].values > 0.5).astype(int); ss = (s[a_].values > 0.5).astype(int); n = len(gs)
        seqs.append(stale_seq(ss.astype(float), gs.astype(float), 0.5))
        for k in range(max(W, 1), n):
            if gs[k] != gs[k - 1]:
                lags.append(next((j - k for j in range(k, min(n, k + 20)) if ss[j] == gs[k]), None))
    if not seqs: continue
    a, b, frac, rl, ns = fit(seqs); res['acts'][a_] = [a, b]
    rep['acts'][a_] = dict(a=a, b=b, stale_frac=frac, switch_lags=lags)
json.dump(res, open(dest, 'w'), indent=1); json.dump(rep, open(dest.replace('.json', '_report.json'), 'w'), indent=1)
print('pooled post-warm-up steps:', rep['n_steps'])
for k, v in rep['levels'].items(): print('%-4s stale %.3f  a %.3f  b %.3f  runs %s' % (k, v['stale_frac'], v['a'], v['b'], v['run_lengths']))
for k, v in rep['acts'].items(): print('%-4s stale %.3f  a %.3f  b %.3f  lags %s' % (k, v['stale_frac'], v['a'], v['b'], v['switch_lags']))
