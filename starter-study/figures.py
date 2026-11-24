"""Generate the three figures from the official starter and published dev table."""
import json
from pathlib import Path
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FormatStrFormatter

ROOT = Path(__file__).parent
rows = json.loads((ROOT / "tasks.json").read_text())
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"axes.titleweight":"bold",
                     "axes.titlelocation":"left","axes.spines.top":False,"axes.spines.right":False,
                     "savefig.facecolor":"white"})
def save(fig, name):
    fig.savefig(ROOT / name, dpi=145, bbox_inches="tight", pad_inches=.25)
    plt.close(fig)

fig,ax=plt.subplots(figsize=(8.8,4.1))
domains=["Civil","Electrical","Mechanical","Structural"]
colors=["#a63732","#d5833d","#799bb3","#24634f"]
categories=["Zero, no file","Zero, file exported","Partial credit","Full credit"]
for i,d in enumerate(domains):
    values=[r for r in rows if r["discipline"]==d]
    counts=Counter(3 if r["reward"]==1 else 2 if r["reward"] else 1 if r["files"] else 0 for r in values)
    left=0
    for k,name in enumerate(categories):
        n=counts[k]
        ax.barh(i,n,left=left,height=.52,color=colors[k],label=name if i==0 else None)
        if n: ax.text(left+n/2,i,str(n),ha="center",va="center",weight="bold",color="white" if k!=2 else "#152f3d")
        left+=n
ax.set_yticks(range(4),domains); ax.invert_yaxis(); ax.set_xlim(0,9.3); ax.set_xticks(range(10))
ax.set_xlabel("Dev tasks in the supplied run"); ax.set_title("Two kinds of zero credit across four disciplines",pad=16)
ax.legend(ncol=2,loc="upper left",bbox_to_anchor=(0,-.23),frameon=False)
save(fig,"failure-breakdown.png")

fig,ax=plt.subplots(figsize=(8.8,4.7))
points=[("Gemini 3.8 Flash",2.24,.270,(7,8)),("Gemini 4 Hydrogen",3.82,.502,(8,8)),
        ("Gemini 4 Argon",5.29,.471,(-25,-23)),("Gemini 4 Neon",8.78,.563,(8,-1)),
        ("Claude Opus 5.5",13.29,.474,(8,6)),("GLM 5.2",16.25,.213,(-65,10))]
for name,cost,score,offset in points:
    selected=name=="Claude Opus 5.5"
    ax.scatter(cost,score,s=100 if selected else 54,c="#bd5a28" if selected else "#345f75",zorder=3)
    ax.annotate(name+(" *" if "Neon" in name else ""), (cost,score),xytext=offset,textcoords="offset points",fontsize=10,weight="bold" if selected else "normal")
ax.set(xlim=(0,20),ylim=(.15,.62),xlabel="Published mean model cost per dev task (USD)",ylabel="Mean dev reward")
ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f")); ax.grid(axis="y",alpha=.19)
ax.set_title("Six models using Pi on the same 29 tasks",pad=13)
fig.text(.12,-.015,"Organizer measurements, three runs per pair.  * Gemini 4 Neon cost is approximate.",fontsize=10)
save(fig,"score-cost.png")

fig,ax=plt.subplots(figsize=(9,4));ax.set_xlim(0,10);ax.set_ylim(0,5);ax.axis("off")
ax.set_title("How the unmodified Pi starter handles one task",pad=8)
def box(x,y,w,h,t,color):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=.06,rounding_size=.12",fc=color,ec="#64798a",lw=1.1))
    ax.text(x+w/2,y+h/2,t,ha="center",va="center",fontsize=10)
def arrow(a,b,both=False):
    ax.annotate("",xy=b,xytext=a,arrowprops={"arrowstyle":"<->" if both else "->","color":"#324c5b","lw":1.45})
box(.22,2.15,2.05,.9,"Evaluator\nWebSocket session","#e6f0f6")
box(3.42,2.15,2.8,.9,"Pi CLI + taskbridge\nper-task workspace","#edf5ee")
box(7.25,3.42,2.4,.9,"Claude Opus 5.5\nmodel proxy","#fff0df")
box(7.25,.65,2.4,.9,"Isolated task project\nshell, files and MCP","#e6f0f6")
arrow((2.34,2.6),(3.33,2.6),True)
arrow((6.28,2.78),(7.18,3.75),True);arrow((6.28,2.4),(7.18,1.18),True)
ax.text(2.78,1.95,"task / done",ha="center",fontsize=9)
ax.text(4.95,.18,"The evaluator exports declared paths after the session ends.",ha="center",fontsize=10)
save(fig,"architecture.png")
