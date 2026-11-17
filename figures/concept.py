import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
C_def='#1f6f8b'; C_att='#c0392b'; C_pub='#7f8c8d'; C_sec='#16a085'; C_del='#d68910'
fig=plt.figure(figsize=(14,9.6))
gs=fig.add_gridspec(2,2,height_ratios=[1,1],hspace=0.38,wspace=0.22)

# ---------- A: architecture
ax=fig.add_subplot(gs[0,0]); ax.set_xlim(0,10); ax.set_ylim(0,6.2); ax.axis('off')
ax.set_title('A  Threat model and defence', loc='left', fontweight='bold')
def box(x,y,w,h,t,c,fc='white',fs=9.5):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.05,rounding_size=0.15',ec=c,fc=fc,lw=1.6))
    ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=fs,color='#222')
def arr(a,b,c='#333',ls='-',txt=None,off=(0,0.18)):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=14,color=c,lw=1.5,ls=ls))
    if txt: ax.text((a[0]+b[0])/2+off[0],(a[1]+b[1])/2+off[1],txt,ha='center',fontsize=8.3,color=c)
# tank
ax.add_patch(Rectangle((0.3,0.5),1.4,2.2,ec='#34495e',fc='none',lw=1.8))
ax.add_patch(Rectangle((0.3,0.5),1.4,1.3,ec='none',fc='#aed6f1'))
ax.text(1.0,0.2,'Tank',ha='center',fontsize=9.5)
box(0.25,4.3,1.5,0.9,'Pump /\nvalve','#34495e')
arr((1.0,4.3),(1.0,2.75),'#34495e')
box(2.75,0.8,2.6,1.7,'PLC\nsecret thresholds\n(dithered inward,\nredrawn each switch)',C_sec,'#e8f8f5',8.2)
arr((1.7,1.3),(3.0,1.3),'#34495e',txt='level',off=(0,0.15))
arr((4.15,2.4),(1.75,4.6),C_sec,txt='switch',off=(0.35,0.1))
box(6.8,4.3,2.9,1.2,'SCADA / HMI\n+ matched-event\nCUSUM detector',C_def,'#eaf2f8',8.8)
box(6.8,0.9,2.9,1.3,'Attacker\nforges level readings\n(twin, replay, lag,\nzero-residual)',C_att,'#fdedec',8.8)
arr((5.3,1.7),(6.8,1.7),'#333',txt='true level',off=(0,0.15))
arr((8.25,2.2),(8.25,4.3),C_att,txt='forged level',off=(-0.75,0))
arr((5.3,2.2),(6.9,4.4),C_def,ls='--',txt='switch events\n(authentic)',off=(-0.6,0.15))
ax.text(5.0,5.85,'Defender knows the secret thresholds; the forger does not.\nAt every natural switch the reported level must sit at the secret threshold.',ha='center',fontsize=8.6,style='italic',color='#333')

# ---------- B: secret thresholds timeline
ax=fig.add_subplot(gs[0,1]); rng=np.random.default_rng(3)
lo,hi=1.0,3.0; t=[0]; L=[1.6]; up=True; T=0; sw=[]; th_lo=[];th_hi=[]
cur_hi=hi-rng.uniform(0,0.3)*(hi-lo); cur_lo=lo+rng.uniform(0,0.3)*(hi-lo)
dt=0.05
while T<24:
    T+=dt; x=L[-1]+(0.11 if up else -0.08)*dt*10
    if up and x>=cur_hi: up=False; sw.append((T,x)); cur_lo=lo+rng.uniform(0,0.3)*(hi-lo)
    elif (not up) and x<=cur_lo: up=True; sw.append((T,x)); cur_hi=hi-rng.uniform(0,0.3)*(hi-lo)
    t.append(T); L.append(x)
t=np.array(t);L=np.array(L)
ax.axhspan(lo,hi,color='#f2f3f4'); 
ax.axhline(hi,color=C_pub,ls=':',lw=1.2); ax.axhline(lo,color=C_pub,ls=':',lw=1.2)
ax.axhspan(hi-0.3*(hi-lo),hi,color=C_sec,alpha=0.10); ax.axhspan(lo,lo+0.3*(hi-lo),color=C_sec,alpha=0.10)
ax.plot(t,L,color='#2471a3',lw=1.8,label='true level')
for T0,x in sw: ax.plot([T0-0.5,T0+0.5],[x,x],color=C_sec,lw=2.2)
ax.scatter([s[0] for s in sw],[s[1] for s in sw],color=C_sec,zorder=5,s=28,label='switch at secret threshold')
# forged trace: twin assuming public thresholds -> deviates
fx=np.clip(L+0.0,0,4); 
ax.plot(t[t>12],np.interp(t[t>12],t,np.convolve(L,np.ones(1),'same'))[:]*0+np.interp(t[t>12]-0.8,t,L)*0.93+0.1,color=C_att,lw=1.4,ls='--',label='forged level (from t=12 h)')
for T0,x in sw:
    if T0>12:
        fv=np.interp(T0-0.8,t,L)*0.93+0.1
        ax.annotate('',xy=(T0,fv),xytext=(T0,x),arrowprops=dict(arrowstyle='<->',color=C_att,lw=1))
ax.axvline(12,color=C_att,lw=0.8,alpha=0.5); ax.text(12.2,3.32,'attack starts',color=C_att,fontsize=8.5)
ax.text(0.2,hi+0.05,'public upper threshold',fontsize=8,color=C_pub); ax.text(0.2,lo-0.17,'public lower threshold',fontsize=8,color=C_pub)
ax.text(0.2,hi-0.3,'inward dither zone',fontsize=8,color=C_sec,ha='left',va='center')
ax.set_ylim(0.6,3.55); ax.set_xlabel('time (h)',labelpad=1); ax.set_ylabel('tank level (m)')
ax.set_title('B  Secret thresholds turn every natural switch into a probe',loc='left',fontweight='bold')
ax.legend(loc='upper center',bbox_to_anchor=(0.5,-0.13),fontsize=8,frameon=False,ncol=3)
for s in ['top','right']: ax.spines[s].set_visible(False)

# ---------- C: detection results
ax=fig.add_subplot(gs[1,0])
arms=['passive','autoencoder','toggles','parsim.\nprobing','random\ndelay','secret\nthresholds']
ct=[0.011,0.004,0.238,0.261,0.186,0.466]; ri=[0.004,0.010,0.087,0.112,0.106,0.448]
x=np.arange(len(arms)); w=0.38
cols=['#bdc3c7','#bdc3c7','#95a5a6','#95a5a6',C_del,C_sec]
b1=ax.bar(x-w/2,ct,w,color=cols,ec='#333',lw=0.6)
b2=ax.bar(x+w/2,ri,w,color=cols,ec='#333',lw=0.6,hatch='//',alpha=0.85)
for xi,v in zip(x-w/2,ct): ax.text(xi,v+0.01,f'{v:.2f}',ha='center',fontsize=7.8)
for xi,v in zip(x+w/2,ri): ax.text(xi,v+0.01,f'{v:.2f}',ha='center',fontsize=7.8)
ax.set_xticks(x); ax.set_xticklabels(arms,fontsize=8.5); ax.set_ylim(0,0.56)
ax.set_ylabel('excess timely detection\n(placebo-corrected, FA = 1/week)')
from matplotlib.patches import Patch
ax.legend(handles=[Patch(fc='white',ec='#333',label='C-Town'),Patch(fc='white',ec='#333',hatch='//',label='Richmond')],loc='upper left',fontsize=8.5)
ax.set_title('C  Detection against model-aware forgers (10 seeds each)',loc='left',fontweight='bold')
ax.text(5,0.53,'p = 0.002 vs delay\n(10/10 seeds, both nets)',ha='center',fontsize=8,color=C_sec)
for s in ['top','right']: ax.spines[s].set_visible(False)

# ---------- D: safety
ax=fig.add_subplot(gs[1,1])
nets=['C-Town','Richmond']; base=[None,2.8]; hy=[2.7,0.2]; de=[32.1,56.5]
x=np.arange(2); w=0.32
ax.bar(x-w/2,hy,w,color=C_sec,ec='#333',lw=0.6,label='secret thresholds (ours)')
ax.bar(x+w/2,de,w,color=C_del,ec='#333',lw=0.6,label='random delay (Ahmed 2024)')
for xi,v in zip(x-w/2,hy): ax.text(xi,v+1,f'{v:.1f}%',ha='center',fontsize=9)
for xi,v in zip(x+w/2,de): ax.text(xi,v+1,f'{v:.1f}%',ha='center',fontsize=9)
ax.set_xticks(x); ax.set_xticklabels(nets); ax.set_ylim(0,66)
ax.set_ylabel('time with tank level outside\nsafe envelope (> 5% of band)')
ax.legend(loc='upper left',fontsize=8.5)
ax.set_title('D  Operational cost of the watermark',loc='left',fontweight='bold')
ax.text(0.5,44,'Inward thresholds keep the level inside\nits normal envelope; delaying a\nswitch pushes it outside.',ha='center',fontsize=8.6,style='italic',color='#333')
for s in ['top','right']: ax.spines[s].set_visible(False)

fig.suptitle('Secret-threshold watermarking for on/off control in water SCADA — concept and Study 4 results',fontsize=12.5,fontweight='bold',y=0.985)
fig.savefig('concept_overview.png',dpi=200,bbox_inches='tight'); fig.savefig('concept_overview.pdf',bbox_inches='tight')
