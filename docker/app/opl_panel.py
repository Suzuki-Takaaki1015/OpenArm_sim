"""OPL source-labelled catalog; delegates operations to the existing serial GUI worker."""
import math
import tkinter as tk
from tkinter import ttk
from opl_assets import CATALOG,FURNITURE,PROXIES,SURFACE_IDS
from environment_assets import ITEMS

class OplPanel:
    def __init__(self,parent):
        self.parent=parent;self.active={}
        self.root=tk.Toplevel(parent.root);self.root.title('OPL 2026 — 物体と家具（近似）');self.root.geometry('980x740')
        frame=ttk.Frame(self.root,padding=12);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='OPL Category A 34項目 / 公開家具14種',font=('Noto Sans CJK JP',15,'bold')).pack(anchor='w')
        ttk.Label(frame,text='公式名に対応する練習用モデル。近似寸法・質量は大会仕様ではありません。家具は床に固定。').pack(anchor='w')
        self.rows=[dict(e) for e in CATALOG]
        self.rows += [dict(row='41',key='opl_clothes_'+str(i),label='Clothes '+str(i)+'/12',kind='剛体近似') for i in range(2,13)]
        self.rows += [dict(row='家具',key=k,label=o['label'],kind='家具近似・寸法は既定値') for k,o in FURNITURE.items()]
        self.query=tk.StringVar();ttk.Entry(frame,textvariable=self.query).pack(fill='x',pady=8)
        self.query.trace_add('write',lambda *_:self.refresh())
        wrap=ttk.Frame(frame);wrap.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(wrap,columns=('row','name','kind','active'),show='headings',selectmode='browse')
        for key,title,width in [('row','公式ID',60),('name','名称',370),('kind','モデル',280),('active','表示',60)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(wrap,orient='vertical',command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.config(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.describe)
        self.info=tk.StringVar();ttk.Label(frame,textvariable=self.info,wraplength=930).pack(anchor='w',pady=8)
        row=ttk.Frame(frame);row.pack(fill='x')
        ttk.Label(row,text='物体の支持面').pack(side='left')
        self.support=tk.StringVar(value='worktable')
        ttk.Combobox(row,textvariable=self.support,values=SURFACE_IDS,state='readonly',width=42).pack(side='left')
        ttk.Label(row,text='家具は床配置（支持面選択は無視）').pack(side='left')
        row=ttk.Frame(frame);row.pack(fill='x',pady=8);self.values={}
        for key,label,value in [('x','world X m',.5),('y','world Y m',0),('yaw','向き °',0)]:
            ttk.Label(row,text=label).pack(side='left')
            v=tk.StringVar(value=str(value));self.values[key]=v;ttk.Entry(row,textvariable=v,width=10).pack(side='left',padx=8)
        row=ttk.Frame(frame);row.pack(fill='x')
        for label,action in [('指定位置へ配置 / 移動','place'),('物体を支持面内でランダム配置','reposition'),('非表示 / 削除','off')]:
            ttk.Button(row,text=label,command=lambda a=action:self.run(a)).pack(side='left',padx=4)
        ttk.Button(row,text='状態更新',command=lambda:parent.request('status')).pack(side='left')
        ttk.Label(frame,text='先に家具を配置し、支持面を選んで物体を置きます。棚は shelf1 が最下段。\nX/Y は ±5 m、向きは ±360°。腕を停止して操作。衝突・支持面外・占有中の家具移動は拒否。\n衣類は12個の剛体。布変形・液体・家電動作・移動台車は再現しません。',wraplength=930).pack(anchor='w',pady=8)
        ttk.Label(frame,textvariable=parent.state,wraplength=930).pack(anchor='w')
        ttk.Label(frame,textvariable=parent.detail,wraplength=930).pack(anchor='w')
        self.refresh()

    def refresh(self):
        selected=self.tree.selection();query=self.query.get().lower().strip()
        self.tree.delete(*self.tree.get_children())
        for e in self.rows:
            if query and query not in (str(e['row'])+' '+e['label']+' '+e['key']).lower():continue
            self.tree.insert('','end',iid=e['key'],values=(e['row'],e['label'],e['kind'],'ON' if self.active.get(e['key']) else 'OFF'))
        keys=self.tree.get_children()
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected)
        elif keys:self.tree.selection_set(keys[0])
    def describe(self,*_):
        keys=self.tree.selection()
        if not keys:return
        obj=ITEMS.get(keys[0])
        if not obj:self.info.set('モデルがありません。イメージを再ビルドしてください。');return
        dimensions=' × '.join(f'{v:.3f}' for v in obj['size'])
        self.info.set(obj['label']+' / '+dimensions+' m / '+str(obj['mass'])+' kg'+
                      (' — 近似の既定値' if not obj.get('ycb') else ' — 既存YCB形状・質量（YCB文書参照）'))
    def run(self,action):
        keys=self.tree.selection()
        if not keys:return
        key=keys[0];extra=[]
        if key in FURNITURE and action=='reposition':
            self.parent.state.set('家具は指定位置へ配置してください');return
        if action=='place':
            try:
                values={k:float(v.get()) for k,v in self.values.items()}
                if not all(math.isfinite(v) for v in values.values()):raise ValueError()
            except ValueError:self.parent.state.set('有限の数値を入力してください');return
            extra=[s for k,v in values.items() for s in ['--'+k,str(v)]]
        if key not in FURNITURE and action!='off':extra += ['--support',self.support.get()]
        self.parent.request(key+'-'+action,extra)
    def update(self,active):
        self.active=active;self.refresh()
