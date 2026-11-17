import json,glob,sys,numpy as np
from scipy.stats import wilcoxon
net=sys.argv[1]; INM=['twin','replay','observer-lag','zero-residual']
runs=[json.load(open(f)) for f in sorted(glob.glob(f'{net}/pilot16_seed*.json'))]
print(net,'seeds',[r['seed'] for r in runs])
ARMS=['passive','ae','tog-rival','pars-rival','hyst0.3','delay0.3']
def out(x):
    sc=sorted(set(k.split('|')[0] for k in x['det']))
    e={(f,kd):np.mean(x['det'][f'{f}|{kd}'])-np.mean(x['det'][f'{f}|none']) for f in sc for kd in INM}
    rt=np.mean([np.mean(x['det'][f'{f}|observer-rt'])-np.mean(x['det'][f'{f}|none']) for f in sc])
    return np.mean(list(e.values())),min(e.values()),rt
def boot(d,n=10000):
    rng=np.random.default_rng(0); return np.percentile([np.mean(rng.choice(d,len(d))) for _ in range(n)],[2.5,97.5])
for a in ['0.0005','0.01']:
    print('--- alpha',a); P={};E={};S={}
    for arm in ARMS:
        R=[r['res'][f'{arm}@{a}'] for r in runs]; o=[out(x) for x in R]
        P[arm]=np.array([v[0] for v in o]); E[arm]=np.array([x['exc_p99'] for x in R]); S[arm]=np.array([x['switches_per_day'] for x in R])
        fa=np.array([x['fa_per_week'] for x in R])
        print('%-11s primary %.3f (sd %.3f) worst %.3f rt* %.3f | FA/wk %.2f (seeds>2: %d) | sw/d %.1f | exc_p99 %.3f exc_frac %.3f exc_max %.3f'%(arm,P[arm].mean(),P[arm].std(ddof=1),np.mean([v[1] for v in o]),np.mean([v[2] for v in o]),fa.mean(),(fa>2).sum(),S[arm].mean(),E[arm].mean(),np.mean([x['exc_frac'] for x in R]),np.mean([x['exc_max'] for x in R])))
    def cmp(lbl,x,y,D=P):
        d=D[x]-D[y]; p=wilcoxon(d).pvalue if np.any(d!=0) else 1.0; ci=boot(d)
        print('  %-5s %s - %s: %+.3f CI[%+.3f,%+.3f] pos %d/%d p=%.4f'%(lbl,x,y,d.mean(),ci[0],ci[1],(d>0).sum(),len(d),p))
    cmp('H4-1','hyst0.3','delay0.3'); cmp('H4-2','delay0.3','hyst0.3',E)
    cmp('P4-1','hyst0.3','pars-rival'); cmp('P4-2','pars-rival','tog-rival')
    print('  cost pars/tog switches: %.2f'%(S['pars-rival'].mean()/S['tog-rival'].mean()))
