# Study 5c: descriptive concealment demonstration on DHALSIM.
# Payload-replay MITM on tank T1 (target PLC2): during the attack SCADA is fed
# previously captured real levels, while the true level evolves away from them.
import sys, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
d=sys.argv[1] if len(sys.argv)>1 else '/home/claude/dh_out/s5c'
TAG=sys.argv[2] if len(sys.argv)>2 else 'T1'
ATK=(100,290)
s=pd.read_csv(f'{d}/scada_values.csv'); g=pd.read_csv(f'{d}/ground_truth.csv')
n=min(len(s),len(g)); sv=s[TAG].values[:n]; gv=g[f'{TAG}_LEVEL'].values[:n]; t=np.arange(n)
div=np.abs(sv-gv)>0.3
C_true='#2471a3'; C_sca='#c0392b'; C_sec='#16a085'
fig,ax=plt.subplots(figsize=(9,4.6))
a0,a1=ATK[0],min(ATK[1],n-1)
ax.axvspan(a0,a1,color='#fdedec',alpha=0.6)
ax.plot(t,gv,color=C_true,lw=2.0,label=f'true {TAG} level (plant)')
ax.plot(t,sv,color=C_sca,lw=1.7,ls='--',label=f'{TAG} level reported to SCADA')
# shade divergence
for k in np.where(div)[0]:
    ax.plot([k,k],[min(sv[k],gv[k]),max(sv[k],gv[k])],color='#c0392b',lw=0.4,alpha=0.25)
rep=142
ax.axvline(a0,color='#888',lw=0.8,alpha=0.6,ls=':'); ax.text(a0+1,ax.get_ylim()[1],'MITM active\n(capturing)',color='#888',fontsize=8,va='top')
ax.axvline(rep,color=C_sca,lw=0.9,alpha=0.7); ax.text(rep+1,ax.get_ylim()[1],'replay starts',color=C_sca,fontsize=8.5,va='top')
mae=np.abs(sv[div]-gv[div]).mean() if div.any() else 0
ax.set_xlabel('simulation step (5-min)'); ax.set_ylabel(f'{TAG} level (m)')
ax.set_title(f'Study 5c  Payload-replay concealment on DHALSIM: SCADA is blind to the true level',loc='left',fontweight='bold',fontsize=11)
ax.legend(loc='best',fontsize=9,frameon=False)
ax.text(0.99,0.02,f'during attack: mean gap true vs reported = {mae:.2f} m over {int(div.sum())} steps',
        transform=ax.transAxes,ha='right',fontsize=8.3,style='italic',color='#555')
for sp in ['top','right']: ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig('fig_5c_concealment.png',dpi=200,bbox_inches='tight'); fig.savefig('fig_5c_concealment.pdf',bbox_inches='tight')
print('saved; steps',n,'diverge',int(div.sum()),'mae',round(float(mae),3))
