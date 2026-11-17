# EXPLORATORY (development seeds only). Unified test bench:
#   arms = passive | toggle probes (v13-style, single-best or game) | secret hysteresis (dithered thresholds, no toggles)
#   strict false-alarm budgets, placebo episodes (no attack, same seeds) so that false alarms are not counted as detections.
import sys, os, importlib, json, time, numpy as np
net = sys.argv[1]; seeds = [int(x) for x in sys.argv[2].split(',')]; EP = int(os.environ.get('EP', 4))
ALPHAS = [float(x) for x in os.environ.get('ALPHAS', '0.0005,0.01').split(',')]      # total per-step false-alarm targets
CAL = int(os.environ.get('CAL', 28)); TAG = os.environ.get('TAG', 'd')
ARMS = os.environ.get('ARMS', 'passive,tog-rival,tog-game,hyst0.08,hyst0.08+ogame,hyst0.08+unif').split(',')
root = './pilot'; wd = f'{root}/run15/{net}'; os.makedirs(wd, exist_ok=True); os.chdir(wd)
sys.path.insert(0, f'{root}/run13/{net}')
P = importlib.import_module(f'pilot13_{net}')
# --- simulator guards (found 15 Nov): the Richmond and Net6 files say "Unbalanced Stop", which silently ends the EPANET run
_prep0 = P.prepare_inp
def _prep(tag='base', n_demand=12, seed=0):
    import wntr; out = []
    for p in _prep0(tag, n_demand, seed):
        wn = wntr.network.WaterNetworkModel(p); wn.options.hydraulic.unbalanced = 'CONTINUE'; wn.options.hydraulic.unbalanced_value = 10; wn.options.hydraulic.trials = 200
        q = p.replace('.inp', '_uc.inp'); wntr.network.write_inpfile(wn, q, units='LPS') if net != 'ctown' else wntr.network.write_inpfile(wn, q); out.append(q)
    return out
P.prepare_inp = _prep
_step0 = P.Plant.step
def _step(self, status):
    t0 = self.t; out = _step0(self, status)
    if self.t == t0: raise RuntimeError('simulator clock did not advance (silent halt)')
    return out
P.Plant.step = _step
TANKS, RULES, ACTS, PROBE_ACTS, STEP = P.TANKS, P.RULES, P.ACTS, P.PROBE_ACTS, P.STEP
NT = len(TANKS); FORCE = getattr(P, 'FORCE', {a: 1 for a in ACTS}); LMIN, LMAX = getattr(P, 'LMIN', 0.3), getattr(P, 'LMAX', 6.5)
KAPPA, ZCLIP, NOISE = P.KAPPA, P.ZCLIP, P.LEVEL_NOISE
INM = ['twin', 'replay', 'observer-lag', 'zero-residual']; KINDS = ['none'] + INM + ['observer-rt']

class SecretPLC:
    def __init__(self, rng, frac):
        self.rng, self.frac = rng, frac; self.off = {a: self._draw(a) for a in RULES}
    def _draw(self, a):
        t, lo, hi = RULES[a]; w = self.frac * (hi - lo)
        return (self.rng.uniform(0, w), self.rng.uniform(0, w)) if w > 0 else (0.0, 0.0)
    def __call__(self, levels_shown, state):
        lv = dict(zip(TANKS, levels_shown))
        for a, (t, lo, hi) in RULES.items():
            dlo, dhi = self.off[a]; new = state[a]
            if lv[t] < lo + dlo: new = 1
            elif lv[t] > hi - dhi: new = 0
            if new != state[a]: state[a] = new; self.off[a] = self._draw(a)
        return state

def nat_events(st, prev): return [(a, st[a], 'n') for a in ACTS if st[a] != prev[a]]

def fit_model(plant, seed, cfg, frac):
    rng = np.random.default_rng(seed); X, Y, EV = [], [], []
    for d in range(cfg['fit_days']):
        plant.reset(rng, start=0); st = P.init_state(); sp = SecretPLC(np.random.default_rng(900_000 + 10 * seed + d), frac)
        lv = plant.levels() + rng.normal(0, NOISE, NT); prev = dict(st)
        for k in range(288):
            st = sp(lv, st); ev = nat_events(st, prev); stx = dict(st)
            if rng.random() < 0.05: j = PROBE_ACTS[rng.integers(len(PROBE_ACTS))]; stx[j] = 1 - stx[j]; ev = [(j, stx[j], 't')]
            nl = plant.step(stx) + rng.normal(0, NOISE, NT)
            X.append(P.features(lv, stx, k)); Y.append(nl - lv); EV.append(ev); lv = nl; prev = dict(st)
    X, Y = np.array(X), np.array(Y); W = np.linalg.lstsq(X, Y, rcond=None)[0]; R = Y - X @ W
    Rh = np.zeros_like(R); m = np.zeros(R.shape[1])
    for t in range(len(R)): Rh[t] = R[t] - m; m = 0.9 * m + 0.1 * R[t]
    sig = Rh.std(0) + 1e-6; J = np.abs(W[:len(ACTS)]); Tv = {(a, c): [] for a in ACTS for c in 'nt'}
    for t, ev in enumerate(EV):
        for a, s, c in ev:
            d = (2 * s - 1) * W[ACTS.index(a)] / sig
            Tv[(a, c)].append(-(np.clip(Rh[t] / sig, -ZCLIP, ZCLIP) @ d) / (np.linalg.norm(d) + 1e-12))
    Tm = {k: (np.sum(v) / (len(v) + 5.0) if len(v) else 0.0) for k, v in Tv.items()}
    Ts = {k: max(1.0, float(np.std(v)) if len(v) > 2 else 1.0) for k, v in Tv.items()}
    return dict(W=W, sig=sig, J=J, Tm2=Tm, Ts2=Ts, Tm={a: Tm[(a, 't')] for a in PROBE_ACTS}, Ts={a: Ts[(a, 't')] for a in PROBE_ACTS},
                nev={a: len(Tv[(a, 'n')]) / cfg['fit_days'] for a in ACTS})

class Det:
    def __init__(self, model):
        self.W, self.sig, self.Tm, self.Ts = model['W'], model['sig'], model['Tm2'], model['Ts2']
        self.k = self.h = self.hp = None; self.reset()
    def reset(self): self.S = 0.0; self.Sp = 0.0; self.m = np.zeros(NT)
    def stat(self, prev_lv, lv, status, step_idx, ev):
        r = (lv - prev_lv) - P.features(prev_lv, status, step_idx) @ self.W
        rh = r - self.m; self.m = 0.9 * self.m + 0.1 * r; z = rh / self.sig; s = np.minimum(z ** 2, 50.0).mean(); T = []
        for a, snew, c in ev:
            d = (2 * snew - 1) * self.W[ACTS.index(a)] / self.sig
            T.append((-(np.clip(z, -ZCLIP, ZCLIP) @ d) / (np.linalg.norm(d) + 1e-12) - self.Tm[(a, c)]) / self.Ts[(a, c)])
        return (s, T)
    def update(self, st):
        s, T = st; al = False
        self.S = max(0.0, self.S + s - self.k)
        if self.S > self.h: self.S = 0.0; al = True
        if self.hp is not None:
            for t in T:
                self.Sp = max(0.0, self.Sp + t - KAPPA)
                if self.Sp > self.hp: self.Sp = 0.0; al = True
        return al

class Sched2(P.Scheduler):
    """v13 scheduler, but a toggle is only released when the controlling tank is outside the dither zone (and the v13 margin)."""
    def __init__(self, pi, per_day, rng, frac): super().__init__(pi, per_day, rng, 0.5); self.frac = frac
    def draw(self, shown_levels):
        self.gap += 1
        if self.pending is None:
            if self.p == 0 or self.gap < self.gmin or self.rng.random() >= self.p_eff: return None
            self.pending = PROBE_ACTS[self.rng.choice(len(PROBE_ACTS), p=self.pi)]
        j = self.pending
        if j in RULES:
            t, lo, hi = RULES[j]; l = shown_levels[TANKS.index(t)]; mg = max(0.1, self.frac + 0.02) * (hi - lo)
            if not (lo + mg < l < hi - mg) and not (net == 'ctown' and j == 'PU1'): return None
        self.pending = None; self.gap = 0; return j

def one_step(sp, sch, lv_seen, st, prev_st):
    """Defender's command for this step: secret-threshold PLC state, plus an optional one-step toggle probe."""
    st = sp(lv_seen, st); ev = nat_events(st, prev_st); cmd = dict(st); j = sch.draw(lv_seen) if sch is not None else None
    if j: cmd[j] = 1 - cmd[j]; ev = ev + [(j, cmd[j], 't')]
    return st, cmd, ev, j

def run_normal(plant, det, arm, rng_env, rng_sec, days):
    plant.reset(rng_env, start=0); st = P.init_state(); sp = SecretPLC(rng_sec, arm['frac'])
    sch = Sched2(arm['pi'], arm['B'], rng_sec, arm['frac']) if arm['B'] > 0 else None
    lv = plant.levels() + rng_env.normal(0, NOISE, NT); stats, nsw, alarms = [], 0, []; det.reset(); prev = dict(st)
    for k in range(288 * days):
        st, cmd, ev, j = one_step(sp, sch, lv, st, prev); nsw += len(ev) + (1 if j else 0)
        nl = plant.step(cmd) + rng_env.normal(0, NOISE, NT)
        s = det.stat(lv, nl, cmd, k, ev if arm['events'] else []); stats.append(s)
        if det.k is not None: alarms.append(det.update(s))
        lv = nl; prev = dict(st)
    return stats, nsw / days, np.array(alarms)

_rn0 = run_normal
def run_normal(plant, det, arm, rng_env, rng_sec, days):
    if days > 28:                                   # amendment 1: the simulator's run length is limited, so long runs are split
        S, N, A = [], [], []
        for c in range(0, days, 28):
            d = min(28, days - c); s_, n_, a_ = run_normal(plant, det, arm, rng_env, rng_sec, d); S += s_[12:] if c else s_; N.append(n_ * d); A.append(a_)
        return S, sum(N) / days, np.concatenate(A)
    for r in range(6):
        try: return _rn0(plant, det, arm, rng_env, rng_sec, days)
        except Exception as ex:
            print('  normal run failed, redraw:', str(ex)[:60], flush=True); plant.en = None; plant.cur = None; plant.open_ = False
            rng_env = np.random.default_rng(int(rng_env.integers(1 << 30)))
    raise RuntimeError('normal run failed 6 times')

def calibrate(det, stats, alpha):
    sv = np.array([x[0] for x in stats], float); Tv = [t for x in stats for t in x[1]]; probing = len(Tv) > 0
    ap = alpha / 2 if probing else 0.0
    det.k = sv.mean() + 0.5 * sv.std()
    det.h = P._first_h(sv, det.k, alpha - ap, len(sv), np.linspace(0.5, 400, 800))
    det.hp = P._first_h(Tv, KAPPA, ap, len(sv), np.linspace(0.25, 40, 160)) if probing else None
    det.reset()

def replay_library(plant, seed, frac):
    rng = np.random.default_rng(424_242 + seed); plant.reset(rng, start=0); st = P.init_state(); sp = SecretPLC(np.random.default_rng(31_337 + seed), frac)
    lv = plant.levels() + rng.normal(0, NOISE, NT); out = [lv]
    for k in range(288 * 3):
        st = sp(lv, st); lv = plant.step(st) + rng.normal(0, NOISE, NT); out.append(lv)
    return np.array(out)

def attack_episode(plant, twin, det, arm, scen, kind, env_seed, sec_seed, cfg, lib):
    rng = np.random.default_rng(env_seed); rs = np.random.default_rng(sec_seed); sp = SecretPLC(rs, arm['frac'])
    sch = Sched2(arm['pi'], arm['B'], rs, arm['frac']) if arm['B'] > 0 else None
    plant.reset(rng, start=0); st = P.init_state(); lv = plant.levels() + rng.normal(0, NOISE, NT); det.reset(); prev = dict(st)
    for k in range(cfg['warm']):
        st, cmd, ev, j = one_step(sp, sch, lv, st, prev)
        nl = plant.step(cmd) + rng.normal(0, NOISE, NT); det.update(det.stat(lv, nl, cmd, k, ev if arm['events'] else [])); lv = nl; prev = dict(st)
    K = scen['K']; a = scen['force']; rng_att = np.random.default_rng(env_seed + 999)
    twin.reset(rng_att, levels=plant.levels(), start=cfg['warm'] * STEP); tst = dict(st); tlv = lv.copy()
    shown = lv.copy(); alarms = []; ri = 0; prev_cmd = dict(st); prev_j = None; est = dict(st); prev_shown = lv.copy()
    if lib is not None: ri = int(np.argmin(np.abs(lib[:-cfg['att'] - 1][:, K] - lv[K]).sum(1)))
    for k in range(cfg['warm'], cfg['warm'] + cfg['att']):
        prev_st = dict(st); st, cmd, ev, j = one_step(sp, sch, shown, st, prev_st)
        real = dict(cmd)
        if kind != 'none': real[a] = FORCE[a]
        true_lv = plant.step(real) + rng.normal(0, NOISE, NT)
        if kind == 'none': new_shown = true_lv
        else:
            # what the forger believes the commanded status is at this step
            if arm['frac'] > 0:                                             # secret thresholds: forger tracks the PLC state from commands seen one step late
                for a_ in ACTS:
                    if prev_cmd[a_] != est[a_]:
                        t_, lo_, hi_ = RULES[a_]; w_ = arm['frac'] * (hi_ - lo_); l_ = prev_shown[TANKS.index(t_)]
                        if (prev_cmd[a_] == 1 and l_ < lo_ + w_) or (prev_cmd[a_] == 0 and l_ > hi_ - w_): est[a_] = prev_cmd[a_]   # natural switch
                est = P.plc(shown, est); bel = dict(est)
            else: bel = dict(st)                                            # public thresholds: natural switches are predictable
            if kind == 'twin':
                tst = P.plc(tlv, tst); tlv = twin.step(tst) + rng_att.normal(0, NOISE, NT); forged = tlv
            elif kind == 'observer-lag':
                b2 = dict(bel)
                if prev_j: b2[prev_j] = 1 - b2[prev_j]                      # mirrors a toggle one step late (as in v13)
                tlv = twin.step(b2) + rng_att.normal(0, NOISE, NT); forged = tlv
            elif kind == 'observer-rt':
                tlv = twin.step(dict(cmd)) + rng_att.normal(0, NOISE, NT); forged = tlv
            elif kind == 'replay':
                ri += 1; forged = lib[ri]
            elif kind == 'zero-residual':
                forged = np.clip(shown + P.features(shown, bel, k) @ det.W + rng_att.normal(0, 0.5 * det.sig), LMIN, LMAX)
            new_shown = true_lv.copy(); new_shown[K] = forged[K]
        alarms.append(det.update(det.stat(shown, new_shown, cmd, k, ev if arm['events'] else []))); prev_shown = shown; shown = new_shown; prev_j = j; prev_cmd = dict(cmd)
    return np.array(alarms)

def safe_episode(*args):
    a = list(args)
    for r in range(4):
        try: return attack_episode(*a)
        except Exception as ex:
            print('  hydraulic failure, redraw:', str(ex)[:60], flush=True); a[6] = a[6] + 500_000
            for p in (a[0], a[1]): p.en = None; p.cur = None; p.open_ = False
    raise RuntimeError('episode failed 4 times')

BUD = int(os.environ.get('BUD', 12))
def offset_game(model, scen, B):
    """max_pi min_s [ N_s + B * sum_j pi_j M[j,s] ]: N_s = expected drift per day already supplied by natural (secret-time) switches."""
    from scipy.optimize import linprog
    W, sig = model['W'], model['sig']; M = P.mu_matrix(model, scen); nA = len(PROBE_ACTS); N = np.zeros(len(scen))
    for a in ACTS:
        d = W[ACTS.index(a)] / sig; nd = np.linalg.norm(d) + 1e-12
        for si, s in enumerate(scen): N[si] += model['nev'][a] * (d[s['K']] ** 2).sum() / nd / model['Ts2'][(a, 'n')]
    sc = max(M.max() * B, N.max(), 1e-9); c = np.zeros(nA + 1); c[-1] = -1
    A_ub = np.hstack([-(B * M.T) / sc, np.ones((len(scen), 1))]); b_ub = N / sc
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=np.hstack([np.ones((1, nA)), np.zeros((1, 1))]), b_eq=[1.0], bounds=[(0, 1)] * nA + [(None, None)], method='highs')
    pi = np.clip(res.x[:nA], 0, None); return pi / pi.sum()

def run_seed(seed):
    fn = f'pilot15_seed{seed}.json'; pf = f'partial15_seed{seed}.json'
    if os.path.exists(fn): return json.load(open(fn))
    part = json.load(open(pf)) if os.path.exists(pf) else {}
    t0 = time.time(); cfg = dict(P.CFG); cfg['ep'] = EP
    plant = P.Plant(P.prepare_inp(f'real{seed}', seed=seed), f'p{seed}'); twin = P.Plant(P.prepare_inp(f'twin{seed}', seed=seed + 500), f't{seed}')
    out = dict(seed=seed, res={}); models = {}; libs = {}; scen = None; pis = {}
    for name in ARMS:
        base, _, alloc = name.partition('+'); frac = float(base[4:]) if base.startswith('hyst') else 0.0
        if base.startswith('tog-'): alloc = base[4:]
        if frac not in models: models[frac] = fit_model(plant, 1000 + seed, cfg, frac); libs[frac] = replay_library(plant, seed, frac)
        model = models[frac]
        if scen is None: scen = P.scenarios(models[frac])
        nA = len(PROBE_ACTS); pi = np.ones(nA) / nA; B = 0
        if alloc == 'rival': pi = P.best_single(model, scen); B = BUD
        if alloc == 'game': pi = P.game_pi(model, scen)[0]; B = BUD
        if alloc == 'unif': B = BUD
        if alloc == 'ogame': pi = offset_game(model, scen, BUD); B = BUD
        arm = dict(frac=frac, pi=pi, B=B, events=(name != 'passive')); pis[name] = [float(x) for x in pi]
        if all(f'{name}@{al}' in part for al in ALPHAS):
            for al in ALPHAS: out['res'][f'{name}@{al}'] = part[f'{name}@{al}']
            continue
        det = Det(model)
        cal, _, _ = run_normal(plant, det, arm, np.random.default_rng(50_000 + 10 * seed), np.random.default_rng(60_000 + 10 * seed), CAL)
        for alpha in ALPHAS:
            calibrate(det, cal[12:], alpha)
            _, nsw, al = run_normal(plant, det, arm, np.random.default_rng(70_000 + seed), np.random.default_rng(71_000 + seed), CAL)
            o = dict(fa_per_week=float(al.sum() / CAL * 7), switches_per_day=float(nsw), hp=det.hp, h=det.h, det={})
            for si, sc in enumerate(scen):
                for kind in KINDS:
                    o['det'][f"{sc['force']}|{kind}"] = [P.timeliness(safe_episode(plant, twin, det, arm, sc, kind, 10_000 + 100 * seed + 10 * si + e, 20_000 + 100 * seed + 10 * si + e, cfg, libs[frac])) for e in range(EP)]
            out['res'][f'{name}@{alpha}'] = o
        part.update({k: v for k, v in out['res'].items() if k.startswith(name + '@')}); json.dump(part, open(pf, 'w'), default=float)
        print('  seed', seed, name, 'done %.1f min' % ((time.time() - t0) / 60), flush=True)
    out['scen'] = [dict(force=s['force'], K=[TANKS[i] for i in s['K']]) for s in scen]; out['minutes'] = (time.time() - t0) / 60
    out['nev'] = {str(f): m['nev'] for f, m in models.items()}; out['pi'] = pis
    json.dump(out, open(fn, 'w'), default=float); print('seed %d done in %.1f min' % (seed, out['minutes']), flush=True); return out

def report(runs):
    print('\n%s  seeds %s  EP %d  calibration %d days' % (net, [r['seed'] for r in runs], EP, CAL))
    for alpha in ALPHAS:
        print('--- false-alarm target %.4f per step (= %.1f per week)' % (alpha, alpha * 2016))
        print('%-10s %-8s %-8s %-6s| raw timeliness %-6s %-6s %-6s %-6s %-6s %-6s| EXCESS over placebo: mean(4 forgers)  min_s,f   | P(detect)-P(FA): min_s,f' % ('arm', 'FA/week', 'switch/d', 'hp', 'none', 'twin', 'replay', 'lag1', 'zero', 'rt*'))
        for name in ARMS:
            key = f'{name}@{alpha}'; R = [r['res'][key] for r in runs]
            def cell(kind): return np.mean([np.mean([np.mean(v) for k, v in x['det'].items() if k.endswith('|' + kind)]) for x in R])
            exm, exmin, pd = [], [], []
            for x in R:
                sc = sorted(set(k.split('|')[0] for k in x['det']))
                e = {(f, kd): np.mean(x['det'][f'{f}|{kd}']) - np.mean(x['det'][f'{f}|none']) for f in sc for kd in INM}
                p = {(f, kd): np.mean(np.array(x['det'][f'{f}|{kd}']) > 0) - np.mean(np.array(x['det'][f'{f}|none']) > 0) for f in sc for kd in INM}
                exm.append(np.mean(list(e.values()))); exmin.append(min(e.values())); pd.append(min(p.values()))
            print('%-10s %-8.2f %-8.1f %-6.2f|                %.3f  %.3f  %.3f  %.3f  %.3f  %.3f |                      %.3f             %.3f     |          %.3f' % (
                name, np.mean([x['fa_per_week'] for x in R]), np.mean([x['switches_per_day'] for x in R]), np.mean([x['hp'] or 0 for x in R]),
                cell('none'), cell('twin'), cell('replay'), cell('observer-lag'), cell('zero-residual'), cell('observer-rt'), np.mean(exm), np.mean(exmin), np.mean(pd)))

if __name__ == '__main__':
    from multiprocessing import Pool
    with Pool(min(2, len(seeds))) as pool: runs = pool.map(run_seed, seeds)
    report(runs)
