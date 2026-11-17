# STUDY 5b (pilot16 + SCADA polling channel). Formerly: EXPLORATORY (development seeds only). Unified test bench:
#   arms = passive | toggle probes (v13-style, single-best or game) | secret hysteresis (dithered thresholds, no toggles)
#   strict false-alarm budgets, placebo episodes (no attack, same seeds) so that false alarms are not counted as detections.
import sys, os, importlib, json, time, numpy as np
net = sys.argv[1]; seeds = [int(x) for x in sys.argv[2].split(',')]; EP = int(os.environ.get('EP', 4))
ALPHAS = [float(x) for x in os.environ.get('ALPHAS', '0.0005,0.01').split(',')]      # total per-step false-alarm targets
CAL = int(os.environ.get('CAL', 28)); TAG = os.environ.get('TAG', 'd')
ARMS = os.environ.get('ARMS', 'passive,tog-rival,tog-game,hyst0.08,hyst0.08+ogame,hyst0.08+unif').split(',')
root = '/home/claude/pilot'; wd = f'{root}/run17/{net}'; os.makedirs(wd, exist_ok=True); os.chdir(wd)
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

class DelayPLC:
    """Nominal thresholds; when a switching condition becomes true the switch is executed after a secret random delay of 0..K[a] steps
    (time-domain watermark in the style of Ahmed et al., 2024)."""
    def __init__(self, rng, K, frac):
        self.rng, self.K, self.frac = rng, K, frac; self.wait = {a: None for a in RULES}; self.started = []
    def __call__(self, levels_shown, state):
        lv = dict(zip(TANKS, levels_shown))
        for a, (t, lo, hi) in RULES.items():
            want = 1 if lv[t] < lo else (0 if lv[t] > hi else state[a])
            if self.wait[a] is None:
                if want != state[a]:
                    self.wait[a] = [want, int(self.rng.integers(0, self.K[a] + 1))]
                    if self.wait[a][1] > 0: self.started.append((a, want, 'd'))      # condition true but switch withheld: a "no response expected" event
            if self.wait[a] is not None:
                w = self.frac * (hi - lo)
                if self.wait[a][1] <= 0 or lv[t] < lo - w or lv[t] > hi + w: state[a] = self.wait[a][0]; self.wait[a] = None   # safety cap: never further out than the dither is in
                else: self.wait[a][1] -= 1
        return state

def make_plc(rng, mode):
    return DelayPLC(rng, mode[1], mode[2]) if isinstance(mode, tuple) else SecretPLC(rng, mode)
def mfrac(mode): return 0.0 if isinstance(mode, tuple) else mode
EXC = []
def excursion(lv):
    """largest distance of a controlled tank level outside its operating envelope (lowest on-threshold to highest off-threshold), as a fraction of the envelope"""
    l = dict(zip(TANKS, lv)); return max(max(lo - l[t], l[t] - hi, 0.0) / (hi - lo) for t, (lo, hi) in ENV.items())
ENV = {}
for _a, (_t, _lo, _hi) in RULES.items(): ENV[_t] = (min(_lo, ENV.get(_t, (_lo, _hi))[0]), max(_hi, ENV.get(_t, (_lo, _hi))[1]))

def nat_events(st, prev): return [(a, st[a], 'n') for a in ACTS if st[a] != prev[a]]
def held(sp):
    ev = getattr(sp, 'started', []);
    if ev: sp.started = []
    return list(ev)
SGN = {'n': -1.0, 't': -1.0, 'd': 1.0}


# ---- Study 5b: SCADA polling channel (registered in REGISTRATION5.txt) ----
# Each tank level and each actuator status reaches SCADA through a two-state Markov channel fitted to the
# DHALSIM measurement (Study 5a): fresh -> stale with prob a, stale -> stale with prob b; a stale tag repeats the
# last value SCADA received. Natural-switch events are only seen when SCADA receives the new status; toggle ('t')
# and withheld-switch ('d') events are defender-originated and are not delayed. The PLC itself is unaffected.
CHP = json.load(open(os.environ['CHAN']))
class Chan:
    def __init__(self, rng, lv, cmd):
        self.rng = rng; self.lv = np.array(lv, float).copy(); self.cmd = dict(cmd); self.pend = {}
        self.sl = np.zeros(NT, bool); self.sa = {a: False for a in ACTS}
    def _next(self, stale, ab):
        a, b = ab; return bool(self.rng.random() < (b if stale else a))
    def see(self, lv, cmd, ev):
        out_ev = [e for e in ev if e[2] != 'n']
        for e in ev:
            if e[2] == 'n': self.pend[e[0]] = e
        for i, t in enumerate(TANKS):
            if t in CHP['levels']: self.sl[i] = self._next(self.sl[i], CHP['levels'][t])
        rl = np.where(self.sl, self.lv, lv); self.lv = rl.copy()
        rc = dict(self.cmd)
        for a in ACTS:
            if a in CHP['acts']: self.sa[a] = self._next(self.sa[a], CHP['acts'][a])
            if not self.sa[a]:
                rc[a] = cmd[a]
                if a in self.pend: out_ev.append(self.pend.pop(a))
        self.cmd = dict(rc)
        return rl, rc, out_ev
CHS = {'base': 0, 'n': 0}
def _chan_rng():
    CHS['n'] += 1; return np.random.default_rng([777, CHS['base'], CHS['n']])

def fit_model(plant, seed, cfg, mode):
    rng = np.random.default_rng(seed); X, Y, EV = [], [], []
    for d in range(cfg['fit_days']):
        plant.reset(rng, start=0); st = P.init_state(); sp = make_plc(np.random.default_rng(900_000 + 10 * seed + d), mode)
        lv = plant.levels() + rng.normal(0, NOISE, NT); prev = dict(st); ch = Chan(np.random.default_rng([778, seed, d]), lv, st); rlv = lv.copy()
        for k in range(288):
            st = sp(lv, st); ev = nat_events(st, prev) + held(sp); stx = dict(st)
            if rng.random() < 0.05: j = PROBE_ACTS[rng.integers(len(PROBE_ACTS))]; stx[j] = 1 - stx[j]; ev = [(j, stx[j], 't')]
            nl = plant.step(stx) + rng.normal(0, NOISE, NT)
            rnl, rc, rev = ch.see(nl, stx, ev)
            X.append(P.features(rlv, rc, k)); Y.append(rnl - rlv); EV.append(rev); lv = nl; rlv = rnl; prev = dict(st)
    X, Y = np.array(X), np.array(Y); W = np.linalg.lstsq(X, Y, rcond=None)[0]; R = Y - X @ W
    Rh = np.zeros_like(R); m = np.zeros(R.shape[1])
    for t in range(len(R)): Rh[t] = R[t] - m; m = 0.9 * m + 0.1 * R[t]
    sig = Rh.std(0) + 1e-6; J = np.abs(W[:len(ACTS)]); Tv = {(a, c): [] for a in ACTS for c in 'ntd'}
    for t, ev in enumerate(EV):
        for a, s, c in ev:
            d = (2 * s - 1) * W[ACTS.index(a)] / sig
            Tv[(a, c)].append(SGN[c] * (np.clip(Rh[t] / sig, -ZCLIP, ZCLIP) @ d) / (np.linalg.norm(d) + 1e-12))
    Tm = {k: (np.sum(v) / (len(v) + 5.0) if len(v) else 0.0) for k, v in Tv.items()}
    Ts = {k: max(1.0, float(np.std(v)) if len(v) > 2 else 1.0) for k, v in Tv.items()}
    return dict(W=W, sig=sig, J=J, Tm2=Tm, Ts2=Ts, Tm={a: Tm[(a, 't')] for a in PROBE_ACTS}, Ts={a: Ts[(a, 't')] for a in PROBE_ACTS},
                nev={a: len(Tv[(a, 'n')]) / cfg['fit_days'] for a in ACTS}, ndl={a: len(Tv[(a, 'd')]) / cfg['fit_days'] for a in ACTS})

class Det:
    def __init__(self, model):
        self.W, self.sig, self.Tm, self.Ts = model['W'], model['sig'], model['Tm2'], model['Ts2']
        self.k = self.h = self.hp = self.hd = None; self.reset()
    def reset(self): self.S = 0.0; self.Sp = 0.0; self.Sd = 0.0; self.m = np.zeros(NT)
    def stat(self, prev_lv, lv, status, step_idx, ev):
        r = (lv - prev_lv) - P.features(prev_lv, status, step_idx) @ self.W
        rh = r - self.m; self.m = 0.9 * self.m + 0.1 * r; z = rh / self.sig; s = np.minimum(z ** 2, 50.0).mean(); T = []; Td = []
        for a, snew, c in ev:
            d = (2 * snew - 1) * self.W[ACTS.index(a)] / self.sig
            (Td if c == 'd' else T).append((SGN[c] * (np.clip(z, -ZCLIP, ZCLIP) @ d) / (np.linalg.norm(d) + 1e-12) - self.Tm[(a, c)]) / self.Ts[(a, c)])
        return (s, T, Td)
    def update(self, st):
        s, T, Td = st; al = False
        self.S = max(0.0, self.S + s - self.k)
        if self.S > self.h: self.S = 0.0; al = True
        if self.hp is not None:
            for t in T:
                self.Sp = max(0.0, self.Sp + t - KAPPA)
                if self.Sp > self.hp: self.Sp = 0.0; al = True
        if self.hd is not None:                      # separate CUSUM for "switch withheld" events (delay arm only), so that null events of one kind do not dilute the other
            for t in Td:
                self.Sd = max(0.0, self.Sd + t - KAPPA)
                if self.Sd > self.hd: self.Sd = 0.0; al = True
        return al

_stat0 = Det.stat; _reset0 = Det.reset
def _reset(self): _reset0(self); self.ch = None; self.chprev = None
def _stat(self, prev_lv, lv, status, step_idx, ev):
    if self.ch is None: self.ch = Chan(_chan_rng(), prev_lv, status); self.chprev = np.array(prev_lv, float).copy()
    rl, rc, rev = self.ch.see(lv, status, ev); out = _stat0(self, self.chprev, rl, rc, step_idx, rev); self.chprev = rl; return out
Det.reset = _reset; Det.stat = _stat

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

PLO, PHI, CQ = float(os.environ.get('PLO', 4)), float(os.environ.get('PHI', 48)), float(os.environ.get('CQ', 1.5))
class ParsSched(Sched2):
    """Parsimonious probing in the spirit of Naha et al. (2023): a low base rate of toggles, raised while the probe statistic is suspicious."""
    def __init__(self, pi, rng, frac):
        super().__init__(pi, PLO, rng, frac); self.lo = (self.p, self.gmin, self.p_eff)
        t = P.Scheduler(pi, PHI, rng, 0.5); self.hi = (t.p, t.gmin, t.p_eff); self.Q = 0.0
    def feed(self, T):
        for t in T: self.Q = max(0.0, self.Q + t - KAPPA)
        self.p, self.gmin, self.p_eff = self.hi if self.Q > CQ else self.lo
def make_sch(arm, rng):
    if arm['B'] <= 0: return None
    return ParsSched(arm['pi'], rng, mfrac(arm['mode'])) if arm.get('pars') else Sched2(arm['pi'], arm['B'], rng, mfrac(arm['mode']))
def _fb(sch, s):
    if hasattr(sch, 'feed'): sch.feed(s[1])
    return s

AEL = 6
class DetAE(Det):
    """Passive data-driven baseline: reconstruction autoencoder on a sliding window of levels and actuator states
    (in the spirit of the BATADAL autoencoder detectors, e.g. Raza et al., 2025), followed by the same calibrated CUSUM."""
    def __init__(self, model, plant, seed):
        from sklearn.neural_network import MLPRegressor
        super().__init__(model); rng = np.random.default_rng(910_000 + seed); plant.reset(rng, start=0); st = P.init_state()
        lv = plant.levels() + rng.normal(0, NOISE, NT); L = [lv]; S = [dict(st)]
        for k in range(288 * 14):
            st = P.plc(lv, st); lv = plant.step(st) + rng.normal(0, NOISE, NT); L.append(lv); S.append(dict(st))
        L = np.array(L); self.mu, self.sd = L.mean(0), L.std(0) + 1e-6; Z = (L - self.mu) / self.sd
        X = np.array([np.concatenate([Z[t - AEL + 1:t + 1].ravel(), [S[t][a] for a in ACTS]]) for t in range(AEL - 1, len(Z))])
        self.ae = MLPRegressor(hidden_layer_sizes=(32, 8, 32), max_iter=600, random_state=seed).fit(X, X)
    def reset(self): super().reset(); self.buf = []
    def stat(self, prev_lv, lv, status, step_idx, ev):
        if not self.buf: self.buf = [(prev_lv - self.mu) / self.sd] * AEL
        self.buf = self.buf[1:] + [(lv - self.mu) / self.sd]
        x = np.concatenate([np.array(self.buf).ravel(), [status[a] for a in ACTS]])
        e = self.ae.predict(x[None])[0] - x; return (float(min((e[:NT * AEL] ** 2).mean(), 50.0)), [], [])

def one_step(sp, sch, lv_seen, st, prev_st):
    """Defender's command for this step: secret-threshold PLC state, plus an optional one-step toggle probe."""
    st = sp(lv_seen, st); ev = nat_events(st, prev_st) + held(sp); cmd = dict(st); j = sch.draw(lv_seen) if sch is not None else None
    if j: cmd[j] = 1 - cmd[j]; ev = ev + [(j, cmd[j], 't')]
    return st, cmd, ev, j

def run_normal(plant, det, arm, rng_env, rng_sec, days):
    plant.reset(rng_env, start=0); st = P.init_state(); sp = make_plc(rng_sec, arm['mode'])
    sch = make_sch(arm, rng_sec)
    lv = plant.levels() + rng_env.normal(0, NOISE, NT); stats, nsw, alarms = [], 0, []; det.reset(); prev = dict(st)
    for k in range(288 * days):
        st, cmd, ev, j = one_step(sp, sch, lv, st, prev); nsw += sum(1 for e in ev if e[2] != 'd') + (1 if j else 0)
        nl = plant.step(cmd) + rng_env.normal(0, NOISE, NT)
        s = _fb(sch, det.stat(lv, nl, cmd, k, ev if arm['events'] else [])); stats.append(s)
        if det.k is not None: alarms.append(det.update(s)); EXC.append(excursion(nl))
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
    sv = np.array([x[0] for x in stats], float); Tv = [t for x in stats for t in x[1]]; Dv = [t for x in stats for t in x[2]]; probing = len(Tv) > 0
    ap = alpha / 2 if probing else 0.0; ad = ap / 2 if len(Dv) > 0 else 0.0; ap = ap - ad
    det.k = sv.mean() + 0.5 * sv.std()
    det.h = P._first_h(sv, det.k, alpha - ap, len(sv), np.linspace(0.5, 400, 800))
    det.hp = P._first_h(Tv, KAPPA, ap, len(sv), np.linspace(0.25, 40, 160)) if probing else None
    det.hd = P._first_h(Dv, KAPPA, ad, len(sv), np.linspace(0.25, 40, 160)) if len(Dv) > 0 else None
    det.reset()

def replay_library(plant, seed, mode):
    rng = np.random.default_rng(424_242 + seed); plant.reset(rng, start=0); st = P.init_state(); sp = make_plc(np.random.default_rng(31_337 + seed), mode)
    lv = plant.levels() + rng.normal(0, NOISE, NT); out = [lv]
    for k in range(288 * 3):
        st = sp(lv, st); lv = plant.step(st) + rng.normal(0, NOISE, NT); out.append(lv)
    return np.array(out)

def attack_episode(plant, twin, det, arm, scen, kind, env_seed, sec_seed, cfg, lib):
    rng = np.random.default_rng(env_seed); rs = np.random.default_rng(sec_seed); sp = make_plc(rs, arm['mode'])
    sch = make_sch(arm, rs)
    plant.reset(rng, start=0); st = P.init_state(); lv = plant.levels() + rng.normal(0, NOISE, NT); det.reset(); prev = dict(st)
    for k in range(cfg['warm']):
        st, cmd, ev, j = one_step(sp, sch, lv, st, prev)
        nl = plant.step(cmd) + rng.normal(0, NOISE, NT); det.update(_fb(sch, det.stat(lv, nl, cmd, k, ev if arm['events'] else []))); lv = nl; prev = dict(st)
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
            if isinstance(arm['mode'], tuple):                              # secret delays: forger knows the scheme, cannot predict the delay, mirrors natural switches one step late
                for a_ in ACTS:
                    if prev_cmd[a_] != est[a_] and a_ in RULES:
                        t_, lo_, hi_ = RULES[a_]; l_ = prev_shown[TANKS.index(t_)]
                        if (prev_cmd[a_] == 1 and l_ < lo_) or (prev_cmd[a_] == 0 and l_ > hi_): est[a_] = prev_cmd[a_]
                bel = dict(est)
            elif arm['frac'] > 0:                                           # secret thresholds: forger tracks the PLC state from commands seen one step late
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
        alarms.append(det.update(_fb(sch, det.stat(shown, new_shown, cmd, k, ev if arm['events'] else [])))); prev_shown = shown; shown = new_shown; prev_j = j; prev_cmd = dict(cmd)
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

_DK = {}
def delay_K(plant, seed, frac):
    """Delay range matched to a dither of width frac: K[a] = round(frac * band / level speed just before a natural switch), clipped to 1..12,
    so that the delay moves the switching level outward by about as much as the dither moves it inward.
    Measured on a 3-day attack-free run with public thresholds (set-up measurement, no outcome involved)."""
    if (seed, frac) in _DK: return _DK[(seed, frac)]
    rng = np.random.default_rng(80_000 + seed); plant.reset(rng, start=0); st = P.init_state(); lv = plant.levels(); R = {t: [] for t in TANKS}; dl = np.zeros(NT)
    for k in range(288 * 3):
        prev = dict(st); st = P.plc(lv, st)
        for a, (t, lo, hi) in RULES.items():
            if st[a] != prev[a] and k > 0: R[t].append(abs(dl[TANKS.index(t)]) / (hi - lo))        # level speed in the step before a natural switch
        nl = plant.step(st); dl = nl - lv; lv = nl
    allr = [x for v in R.values() for x in v]; glob = float(np.median(allr)) if allr else 0.03      # speeds as a fraction of the band per step
    K = {}
    for a, (t, lo, hi) in RULES.items():
        r = float(np.median(R[t])) if len(R[t]) >= 3 else glob
        K[a] = int(np.clip(round(frac / max(r, 1e-6)), 1, 12))
    _DK[(seed, frac)] = K; return K

def run_seed(seed):
    fn = f'pilot17_seed{seed}.json'; pf = f'partial17_seed{seed}.json'
    if os.path.exists(fn): return json.load(open(fn))
    part = json.load(open(pf)) if os.path.exists(pf) else {}
    t0 = time.time(); cfg = dict(P.CFG); cfg['ep'] = EP
    plant = P.Plant(P.prepare_inp(f'real{seed}', seed=seed), f'p{seed}'); twin = P.Plant(P.prepare_inp(f'twin{seed}', seed=seed + 500), f't{seed}')
    out = dict(seed=seed, res={}); models = {}; libs = {}; scen = None; pis = {}
    for name in ARMS:
        base, _, alloc = name.partition('+'); frac = float(base[4:]) if base.startswith('hyst') else 0.0
        mode = ('delay', delay_K(plant, seed, float(base[5:])), float(base[5:])) if base.startswith('delay') else frac
        mk = base if base.startswith('delay') else frac
        if base.startswith('tog-'): alloc = base[4:]
        pars = base.startswith('pars-')
        if pars: alloc = base[5:]
        if mk not in models: models[mk] = fit_model(plant, 1000 + seed, cfg, mode); libs[mk] = replay_library(plant, seed, mode)
        model = models[mk]
        if scen is None: scen = P.scenarios(models[mk])
        nA = len(PROBE_ACTS); pi = np.ones(nA) / nA; B = 0
        if alloc == 'rival': pi = P.best_single(model, scen); B = BUD
        if alloc == 'game': pi = P.game_pi(model, scen)[0]; B = BUD
        if alloc == 'unif': B = BUD
        if alloc == 'ogame': pi = offset_game(model, scen, BUD); B = BUD
        arm = dict(frac=frac, mode=mode, pi=pi, B=B, events=(name not in ('passive', 'ae')), pars=pars); pis[name] = [float(x) for x in pi]
        if all(f'{name}@{al}' in part for al in ALPHAS):
            for al in ALPHAS: out['res'][f'{name}@{al}'] = part[f'{name}@{al}']
            continue
        CHS['base'] = seed; CHS['n'] = 0
        det = DetAE(model, plant, seed) if base == 'ae' else Det(model)
        cal, _, _ = run_normal(plant, det, arm, np.random.default_rng(50_000 + 10 * seed), np.random.default_rng(60_000 + 10 * seed), CAL)
        for alpha in ALPHAS:
            calibrate(det, cal[12:], alpha)
            EXC.clear(); _, nsw, al = run_normal(plant, det, arm, np.random.default_rng(70_000 + seed), np.random.default_rng(71_000 + seed), CAL); ex = np.array(EXC)
            o = dict(fa_per_week=float(al.sum() / CAL * 7), switches_per_day=float(nsw), hp=det.hp, h=det.h, det={},
                     exc_frac=float((ex > 0.05).mean()), exc_p99=float(np.percentile(ex, 99)), exc_max=float(ex.max()), K=(mode[1] if isinstance(mode, tuple) else None))
            for si, sc in enumerate(scen):
                for kind in KINDS:
                    o['det'][f"{sc['force']}|{kind}"] = [P.timeliness(safe_episode(plant, twin, det, arm, sc, kind, 10_000 + 100 * seed + 10 * si + e, 20_000 + 100 * seed + 10 * si + e, cfg, libs[mk])) for e in range(EP)]
            out['res'][f'{name}@{alpha}'] = o
        part.update({k: v for k, v in out['res'].items() if k.startswith(name + '@')}); json.dump(part, open(pf, 'w'), default=float)
        print('  seed', seed, name, 'done %.1f min' % ((time.time() - t0) / 60), flush=True)
    out['scen'] = [dict(force=s['force'], K=[TANKS[i] for i in s['K']]) for s in scen]; out['minutes'] = (time.time() - t0) / 60
    out['nev'] = {str(f): m['nev'] for f, m in models.items()}; out['delayK'] = {str(k): v for k, v in _DK.items()}; out['pi'] = pis
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
