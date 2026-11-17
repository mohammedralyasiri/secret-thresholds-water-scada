# Figure 1: DHALSIM emulated SCADA testbed used in Study 5.
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
C_plant='#2471a3'; C_plc='#16a085'; C_net='#7f8c8d'; C_sca='#1f6f8b'; C_att='#c0392b'
fig,ax=plt.subplots(figsize=(11,6.8)); ax.set_xlim(0,12); ax.set_ylim(0,8.7); ax.axis('off')
def box(x,y,w,h,t,ec,fc='white',fs=9.5,tc='#222'):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.04,rounding_size=0.12',ec=ec,fc=fc,lw=1.7))
    ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=fs,color=tc)
def arr(a,b,c='#333',ls='-',lw=1.6,txt=None,off=(0,0.2),fs=8.3,bidir=False):
    st='<|-|>' if bidir else '-|>'
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle=st,mutation_scale=13,color=c,lw=lw,ls=ls))
    if txt: ax.text((a[0]+b[0])/2+off[0],(a[1]+b[1])/2+off[1],txt,ha='center',fontsize=fs,color=c)

# --- Physical plant (EPANET/WNTR)
ax.add_patch(Rectangle((0.3,0.4),3.1,6.9,ec=C_plant,fc='#eef5fb',lw=1.5,ls='--'))
ax.text(1.85,6.62,'Physical plant\n(EPANET / WNTR)',ha='center',fontsize=8.6,color=C_plant,fontweight='bold')
# tanks and pumps
ax.add_patch(Rectangle((0.7,4.9),0.9,1.4,ec='#34495e',fc='none',lw=1.6)); ax.add_patch(Rectangle((0.7,4.9),0.9,0.8,ec='none',fc='#aed6f1')); ax.text(1.15,4.6,'tanks',ha='center',fontsize=8)
box(2.0,5.0,1.1,1.1,'pumps\n/ valves','#34495e',fs=8)
box(0.7,2.2,2.5,1.3,'on/off control rules\nwith SECRET THRESHOLDS\n(dithered inward,\nredrawn each switch)',C_plc,'#e8f8f5',7.8,tc='#145a4c')
arr((1.9,4.9),(1.9,3.5),C_plc,lw=1.4)
arr((1.9,2.2),(1.9,0.9),'#34495e',lw=1.4,txt='actuation',off=(0.75,0),fs=7.5)
ax.text(1.9,0.65,'water network',ha='center',fontsize=8,color=C_plant)

# --- PLC layer
for i,xx in enumerate([4.2,5.25,6.3]):
    box(xx,5.3,0.95,1.0,f'PLC{i+1}',C_plc,'#e8f8f5',8)
ax.text(5.75,6.5,'9 PLCs (epynet)',ha='center',fontsize=8.5,color=C_plc)
ax.text(5.75,5.05,'...',ha='center',fontsize=12,color=C_plc)
arr((3.4,5.9),(4.2,5.9),C_plant,lw=1.4,txt='sensors',off=(0,0.22),fs=7.5)

# --- Mininet network
box(4.2,3.2,3.0,1.1,'Emulated Ethernet (Mininet)\nEtherNet/IP  •  Linux-bridge switches',C_net,'#f4f6f6',8.3)
for xx in [4.6,5.7,6.8]:
    arr((xx,5.3),(xx,4.3),C_net,lw=1.3)

# --- SCADA / detector
box(8.3,5.1,3.3,1.5,'SCADA / HMI\n+ matched-event CUSUM\ndetector (defender knows\nthe secret thresholds)',C_sca,'#eaf2f8',8.5)
arr((7.2,3.9),(8.3,5.3),C_sca,lw=1.5,txt='polled levels\n& statuses',off=(0.55,-0.15),fs=7.5)

# --- Attacker (5c)
box(8.3,2.2,3.3,1.3,'Attacker (Study 5c)\nman-in-the-middle\nreplays captured levels',C_att,'#fdedec',8.3)
arr((7.0,3.5),(8.3,2.9),C_att,ls='--',lw=1.4)
arr((9.95,3.5),(9.95,5.1),C_att,ls='--',lw=1.4,txt='forged\nlevels',off=(0.6,0),fs=7.5)

ax.text(6,8.45,'Figure 1.  DHALSIM emulated SCADA testbed: the secret thresholds live inside the PLCs and act on the true level;',ha='center',fontsize=9,style='italic',color='#333')
ax.text(6,8.2,'the detector sees only what reaches SCADA across the emulated network.',ha='center',fontsize=9,style='italic',color='#333')
fig.savefig('fig_network.png',dpi=200,bbox_inches='tight'); fig.savefig('fig_network.pdf',bbox_inches='tight')
print('network figure saved')
