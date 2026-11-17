import json,glob,sys,numpy as np
from scipy.stats import wilcoxon
net=sys.argv[1]; INM=['twin','replay','observer-lag','zero-residual']
runs=[json.load(open(f)) for f in sorted(glob.glob(f'{net}/pilot15_seed*.json'))]
print(net,'seeds',[r['seed'] for r in runs])
ARMS=['passive','tog-rival','tog-game','hyst0.3','hyst0.3+ogame']
def out(x):
    sc=sorted(set(k.split('|')[0] for k in x['det']))
    e={(f,kd):np.mean(x['det'][f'{f}|{kd}'])-np.mean(x['det'][f'{f}|none']) for f in sc for kd in INM}
    rt=np.mean([np.mean(x['det'][f'{f}|observer-rt'])-np.mean(x['det'][f'{f}|none']) for f in sc])
    return np.mean(list(e.values())),min(e.values()),rt
def boot(d,n=10000):
    rng=np.random.default_rng(0); m=[np.mean(rng.choice(d,len(d))) for _ in range(n)]; return np.percentile(m,[2.5,97.5])
for a in ['0.0005','0.01']:
    print('--- alpha',a)
    P={};W={}
    for arm in ARMS:
        R=[r['res'][f'{arm}@{a}'] for r in runs]; o=[out(x) for x in R]
        P[arm]=np.array([v[0] for v in o]); W[arm]=np.array([v[1] for v in o])
        fa=[x['fa_per_week'] for x in R]
        print('%-14s primary %.3f (sd %.3f)  worst %.3f [max seed %.3f]  rt* %.3f  FA/wk mean %.2f max %.2f  sw/d %.1f'%(arm,P[arm].mean(),P[arm].std(ddof=1),W[arm].mean(),W[arm].max(),np.mean([v[2] for v in o]),np.mean(fa),np.max(fa),np.mean([x['switches_per_day'] for x in R])))
    def cmp(x,y):
        d=P[x]-P[y]; p=wilcoxon(d).pvalue if np.any(d!=0) else 1.0; ci=boot(d)
        print('  %s - %s: mean diff %+.3f CI[%+.3f,%+.3f] wins %d/%d p=%.4f'%(x,y,d.mean(),ci[0],ci[1],(d>0).sum(),len(d),p)); return p
    p1=cmp('hyst0.3+ogame','tog-rival'); p2=cmp('hyst0.3+ogame','tog-game')
    ps=sorted([p1,p2]); print('  H1 Holm p:',min(1,2*ps[0]),max(min(1,2*ps[0]),ps[1]))
    best='tog-rival' if P['tog-rival'].mean()>=P['tog-game'].mean() else 'tog-game'
    cmp('hyst0.3',best); cmp('tog-rival','tog-game'); cmp('hyst0.3+ogame','hyst0.3')
