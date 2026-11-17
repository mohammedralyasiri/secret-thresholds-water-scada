# Figure: comparison charts across networks (Study 4) and the Study 5 channel effect.
import numpy as np, matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
C_sec='#16a085'; C_del='#d68910'; C_pars='#8e44ad'; C_tog='#95a5a6'; C_pas='#bdc3c7'; C_ae='#d5dbdb'
fig=plt.figure(figsize=(13,8.6)); gs=fig.add_gridspec(2,2,height_ratios=[1,0.95],hspace=0.42,wspace=0.26)

# ---- Panel A: Study 4 primary outcome, grouped by network
ax=fig.add_subplot(gs[0,:])
arms=['passive','autoencoder','toggles','parsim.\nprobing','random\ndelay','secret\nthresholds']
cols=[C_pas,C_ae,C_tog,C_pars,C_del,C_sec]
ct=[0.011,0.004,0.238,0.261,0.186,0.466]
ri=[0.004,0.010,0.087,0.112,0.106,0.448]
n6=[0.005,0.007,0.074,0.186,0.029,0.115]
x=np.arange(len(arms)); w=0.26
for off,data,lab,hatch in [(-w,ct,'C-Town',''),(0,ri,'Richmond','//'),(w,n6,'Net6 (61 actuators)','..')]:
    bars=ax.bar(x+off,data,w,color=cols,ec='#333',lw=0.5,hatch=hatch)
for xi,v in zip(x-w,ct): ax.text(xi,v+0.008,f'{v:.2f}',ha='center',fontsize=6.8)
for xi,v in zip(x,ri): ax.text(xi,v+0.008,f'{v:.2f}',ha='center',fontsize=6.8)
for xi,v in zip(x+w,n6): ax.text(xi,v+0.008,f'{v:.2f}',ha='center',fontsize=6.8)
# flag Net6 secret-thresholds over budget
ax.annotate('Net6: over FA\nbudget (2.0/wk)',xy=(x[-1]+w,0.125),xytext=(x[-1]-0.52,0.33),fontsize=7.3,color='#c0392b',ha='center',arrowprops=dict(arrowstyle='->',color='#c0392b',lw=1))
ax.set_xticks(x); ax.set_xticklabels(arms,fontsize=9); ax.set_ylim(0,0.54)
ax.set_ylabel('excess timely detection\n(placebo-corrected, FA = 1/week)')
ax.set_title('A  Detection against model-aware forgers — Study 4 (10 seeds per network)',loc='left',fontweight='bold')
ax.legend(handles=[Patch(fc='white',ec='#333',label='C-Town'),Patch(fc='white',ec='#333',hatch='//',label='Richmond'),Patch(fc='white',ec='#333',hatch='..',label='Net6')],loc='upper left',fontsize=8.8,ncol=3)
for s in ['top','right']: ax.spines[s].set_visible(False)

# ---- Panel B: operational cost
ax=fig.add_subplot(gs[1,0])
nets=['C-Town','Richmond']; pas=[5.8,2.8]; hy=[2.7,0.2]; de=[32.1,56.5]
x=np.arange(2); w=0.26
ax.bar(x-w,pas,w,color=C_pas,ec='#333',lw=0.5,label='passive (baseline)')
ax.bar(x,hy,w,color=C_sec,ec='#333',lw=0.5,label='secret thresholds (ours)')
ax.bar(x+w,de,w,color=C_del,ec='#333',lw=0.5,label='random delay (Ahmed et al. 2024)')
for xi,v in zip(x-w,pas): ax.text(xi,v+1,f'{v:.1f}',ha='center',fontsize=8)
for xi,v in zip(x,hy): ax.text(xi,v+1,f'{v:.1f}',ha='center',fontsize=8)
for xi,v in zip(x+w,de): ax.text(xi,v+1,f'{v:.1f}',ha='center',fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(nets); ax.set_ylim(0,64)
ax.set_ylabel('% of time tank level outside\nsafe envelope')
ax.set_title('B  Operational cost of the watermark',loc='left',fontweight='bold')
ax.legend(loc='upper left',fontsize=8); ax.text(0.5,42,'Net6 excluded: the\nenvelope metric is\ndegenerate there.',ha='center',fontsize=7.6,style='italic',color='#777')
for s in ['top','right']: ax.spines[s].set_visible(False)

# ---- Panel C: Study 5 channel effect
ax=fig.add_subplot(gs[1,1])
arms2=['passive','secret\nthresholds','random\ndelay']; col2=[C_pas,C_sec,C_del]
noch=[0.011,0.466,0.186]; ch=[0.001,0.112,0.021]
x=np.arange(3); w=0.36
ax.bar(x-w/2,noch,w,color=col2,ec='#333',lw=0.5,label='Study 4 (clean)')
ax.bar(x+w/2,ch,w,color=col2,ec='#333',lw=0.5,hatch='xx',alpha=0.9,label='Study 5b (measured channel)')
for xi,v in zip(x-w/2,noch): ax.text(xi,v+0.008,f'{v:.2f}',ha='center',fontsize=7.6)
for xi,v in zip(x+w/2,ch): ax.text(xi,v+0.008,f'{v:.2f}',ha='center',fontsize=7.6)
ax.set_xticks(x); ax.set_xticklabels(arms2); ax.set_ylim(0,0.54)
ax.set_ylabel('excess timely detection\n(C-Town, FA = 1/week)')
ax.set_title('C  Effect of SCADA polling staleness — Study 5b',loc='left',fontweight='bold')
ax.legend(handles=[Patch(fc='#999',ec='#333',label='clean (Study 4)'),Patch(fc='#999',ec='#333',hatch='xx',label='measured channel (5b)')],loc='upper right',fontsize=8)
ax.text(-0.42,0.52,'secret thresholds\nstill win 10/10 seeds\n(p=0.002); both lose\nmost of absolute\nscore',ha='left',va='top',fontsize=7.0,style='italic',color=C_sec)
for s in ['top','right']: ax.spines[s].set_visible(False)

fig.suptitle('Secret-threshold watermark — comparison across networks and under a measured SCADA channel',fontsize=12.5,fontweight='bold',y=0.98)
fig.savefig('fig_compare.png',dpi=200,bbox_inches='tight'); fig.savefig('fig_compare.pdf',bbox_inches='tight')
print('comparison figure saved')
