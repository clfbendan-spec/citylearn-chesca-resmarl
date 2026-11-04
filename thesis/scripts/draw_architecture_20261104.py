"""Editable vector diagrams; layout units are independent of manuscript size."""
from pathlib import Path
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from matplotlib.font_manager import FontProperties

T=Path(__file__).resolve().parents[1]
OUT=T/'images'/'architecture_20261104'
OUT.mkdir(parents=True,exist_ok=True)
matplotlib.rcParams.update({'font.family':'SimSun','font.size':11,'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
C={'blue':'#e7eff7','green':'#e6f1e9','orange':'#fbefdf','gray':'#f1f3f5','ink':'#344553'}

def canvas(h):
    fig,ax=plt.subplots(figsize=(7.0,h/13*7.0))
    ax.set(xlim=(0,13),ylim=(0,h)); ax.axis('off')
    fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
    return fig,ax
def box(ax,x,y,w,h,title,sub='',color='blue'):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.02,rounding_size=0.10',facecolor=C[color],edgecolor=C['ink'],lw=.9))
    if sub:
        ax.text(x+w/2,y+h*.65,title,ha='center',va='center',size=11)
        ax.text(x+w/2,y+h*.28,sub,ha='center',va='center',size=9,color=C['ink'],linespacing=1.4)
    else: ax.text(x+w/2,y+h/2,title,ha='center',va='center',size=11,linespacing=1.5)
def arr(ax,pts,both=False,dashed=False):
    for p,q in zip(pts[:-2],pts[1:-1]): ax.plot([p[0],q[0]],[p[1],q[1]],color=C['ink'],lw=.9,ls='--' if dashed else '-')
    ax.add_patch(FancyArrowPatch(pts[-2],pts[-1],arrowstyle='<->' if both else '-|>',mutation_scale=10,lw=.9,color=C['ink'],linestyle='--' if dashed else '-',shrinkA=0,shrinkB=2))
def label(ax,x,y,t): ax.text(x,y,t,ha='center',va='center',size=9,color=C['ink'],bbox=dict(facecolor='white',edgecolor='none',pad=1))
def save(fig,name):
    for ext in ['svg','pdf','png']: fig.savefig(OUT/f'{name}.{ext}',dpi=200,facecolor='white')
    plt.close(fig)

fig,ax=canvas(6.6)
box(ax,.25,4.45,2.25,1.1,'环境包装器观测','当前状态与历史信息','gray')
box(ax,3.3,4.45,2.8,1.1,'CHESCA基线','预测 · 温控 · 储能','blue')
box(ax,3.3,1.85,2.8,1.1,'逐楼IPPO策略','演员输出修正向量','green')
box(ax,6.7,1.85,2.65,1.1,'受限残差','掩码 · 幅度 · 门控','green')
ax.add_patch(Circle((8.9,5.0),.30,edgecolor=C['ink'],facecolor=C['orange'],lw=.9));ax.text(8.9,5.0,'+',ha='center',va='center',size=17)
box(ax,10.15,4.45,2.6,1.1,'动作约束处理','可选投影与范围裁剪','orange')
box(ax,10.15,1.85,2.6,1.1,'CityLearn执行','状态转移与奖励','gray')
arr(ax,[(2.5,5),(3.3,5)])
arr(ax,[(1.4,4.45),(1.4,2.4),(3.3,2.4)])
arr(ax,[(6.1,5),(8.59,5)]);label(ax,7.35,5.35,'基线动作')
arr(ax,[(6.1,2.4),(6.7,2.4)])
arr(ax,[(8.9,2.95),(8.9,4.68)]);label(ax,8.9,3.8,'请求修正')
arr(ax,[(9.2,5),(10.15,5)])
arr(ax,[(11.45,4.45),(11.45,2.95)]);label(ax,11.45,3.7,'执行动作')
ax.text(6.5,.65,'动作记录：基线动作 / 请求修正 / 实际修正 / 跳过原因',ha='center',va='center',size=10,color=C['ink'])
save(fig,'residual_control')

fig,ax=canvas(7.4)
box(ax,3.6,5.85,5.8,1.1,'浏览器与Vue前端','实验配置 · 任务列表 · ECharts交互分析','blue')
box(ax,1.0,3.7,11,1.2,'Spring Boot业务服务','权限校验 · 任务编排 · 进程管理 · 结果读取','green')
arr(ax,[(6.5,5.85),(6.5,4.9)],both=True);label(ax,8.05,5.4,'HTTP请求 / 状态与结果')
box(ax,.3,.65,3.7,1.45,'MySQL','用户、脚本、配置、任务\n脚本级KPI摘要','gray')
box(ax,4.65,.65,3.7,1.45,'任务文件目录','配置、日志、模型\nKPI与逐时轨迹','gray')
box(ax,9,.65,3.7,1.45,'Python / CityLearn','规则控制 · 残差学习\n训练与官方评估','orange')
arr(ax,[(2.15,3.7),(2.15,2.1)],both=True);label(ax,2.15,2.9,'元数据读写')
arr(ax,[(6.5,2.1),(6.5,3.7)]);label(ax,6.5,2.9,'读取任务产物')
arr(ax,[(10.85,3.7),(10.85,2.1)]);label(ax,10.85,2.9,'启动独立进程')
arr(ax,[(9,1.35),(8.35,1.35)])
label(ax,8.68,.3,'导出')
save(fig,'platform_architecture')

fig,ax=canvas(3.6)
names=[('观测与预测','当前与历史信息'),('单楼设备控制','热水与温控动作'),('社区储能规划','净负荷与电池状态'),('动作回写执行','设备动作与状态转移')]
for i,(a,b) in enumerate(names):
    x=.25+i*3.25;box(ax,x,1.1,2.75,1.35,a,b,'blue' if i<3 else 'orange')
    if i<3:arr(ax,[(x+2.75,1.77),(x+3.25,1.77)])
save(fig,'chesca_flow')

fig,ax=canvas(7.2)
box(ax,.4,5.6,2.8,1,'用户',color='blue');box(ax,5,5.6,3,1,'用户权限关联',color='blue');box(ax,9.8,5.6,2.8,1,'权限',color='blue')
arr(ax,[(3.2,6.1),(5,6.1)],both=True);arr(ax,[(8,6.1),(9.8,6.1)],both=True)
box(ax,.4,3.55,2.8,1.1,'算法脚本',color='green');box(ax,5,3.55,3,1.1,'任务与配置','训练、评估及子任务','green');box(ax,9.8,3.55,2.8,1.1,'任务目录','日志、模型与轨迹','gray')
arr(ax,[(3.2,4.1),(5,4.1)]);label(ax,4.1,4.47,'脚本标识')
arr(ax,[(8,4.1),(9.8,4.1)],dashed=True);label(ax,8.9,4.47,'任务标识')
box(ax,.4,1.35,2.8,1.1,'脚本级KPI摘要',color='gray');arr(ax,[(1.8,3.55),(1.8,2.45)]);label(ax,1.8,3,'脚本标识')
box(ax,5,1.35,3,1.1,'参数定义与配置组',color='orange');arr(ax,[(6.5,2.45),(6.5,3.55)],dashed=True)
box(ax,9.8,1.35,2.8,1.1,'数据集目录',color='orange');arr(ax,[(9.8,1.9),(8.8,1.9),(8.8,3.0),(7.5,3.0),(7.5,3.55)],dashed=True)
ax.text(6.5,.55,'实线：标识关联；虚线：配置或目录引用。图示为业务关系。',ha='center',size=9,color=C['ink'])
save(fig,'storage_relations')

fig,ax=canvas(5.9)
box(ax,.4,2.4,2.4,1.1,'Python执行',color='orange')
box(ax,3.7,4.0,3.2,1.1,'控制台与运行日志',color='gray');box(ax,3.7,.8,3.2,1.1,'CSV / JSON / 模型',color='gray')
arr(ax,[(2.8,3.2),(3.2,3.2),(3.2,4.55),(3.7,4.55)])
arr(ax,[(2.8,2.7),(3.2,2.7),(3.2,1.35),(3.7,1.35)])
box(ax,8,2.4,4.55,1.1,'后端读取与解析','任务目录保存历史产物','green')
arr(ax,[(6.9,4.55),(10.3,4.55),(10.3,3.5)])
arr(ax,[(6.9,1.35),(7.4,1.35),(7.4,2.95),(8,2.95)])
box(ax,8,.5,4.55,1.0,'Vue指标与轨迹视图',color='blue');arr(ax,[(10.3,2.4),(10.3,1.5)])
save(fig,'artifact_flow')

fig,ax=canvas(6.5)
for x,t,col in [(2,'Vue前端','blue'),(6.5,'Java任务编排','green'),(11,'Python执行','orange')]:
    box(ax,x-1.7,5.35,3.4,.8,t,color=col)
    ax.plot([x,x],[.45,5.3],color='#a3aeb7',lw=.8,ls='--')
for y,start,end,t in [(4.8,2,6.5,'创建待执行任务'),(4.0,2,6.5,'执行编排任务'),(3.2,6.5,11,'启动训练子任务'),(2.45,11,6.5,'返回退出状态与模型'),(1.7,6.5,11,'训练成功后启动评估'),(.9,11,6.5,'返回评估状态与产物')]:
    arr(ax,[(start,y),(end,y)]);label(ax,(start+end)/2,y+.22,t)
save(fig,'task_sequence')

def replace_figure(file,label,name):
    p=T/'contents'/file;s=p.read_text(encoding='utf-8')
    pat=r'\\begin\{figure\}\[!htbp\].*?\\end\{figure\}'
    def f(m):
        old=m.group()
        if '\\label{'+label+'}' not in old:return old
        cap=old[old.index('\\bicaption'):]
        return '\\begin{figure}[!htbp]\n\\centering\n\\includegraphics[width=0.98\\textwidth]{images/architecture_20261104/'+name+'.pdf}\n'+cap
    new=re.sub(pat,f,s,flags=re.S)
    if new==s and ('architecture_20261104/'+name+'.pdf') not in s:raise ValueError('Figure not replaced: '+label)
    p.write_text(new,encoding='utf-8')
for args in [('chap2.tex','CHESCA单步流程图','chesca_flow'),('chap2.tex','CHESCA-ResMARL框架','residual_control'),('chap3.tex','系统架构图','platform_architecture'),('chap3.tex','数据库E-R图','storage_relations'),('chap4.tex','日志归档流程图','artifact_flow'),('chap4.tex','异步调度时序图','task_sequence')]:replace_figure(*args)
print('Exported and embedded six diagrams (SVG, PDF, PNG):',OUT)
