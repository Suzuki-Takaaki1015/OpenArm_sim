"""Searchable catalog with the same placement services as the built-in objects."""
import math
import tkinter as tk
from tkinter import ttk
from ycb_assets import CATALOG

class YcbPanel:
    def __init__(self,parent):
        self.parent=parent;self.active={}
        self.root=tk.Toplevel(parent.root);self.root.title('YCB オブジェクトライブラリ');self.root.geometry('850x650')
        frame=ttk.Frame(self.root,padding=12);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='YCB オブジェクト — OpenArm 1.0 / 2.0 共通',font=('Noto Sans CJK JP',15,'bold')).pack(anchor='w')
        self.query=tk.StringVar();row=ttk.Frame(frame);row.pack(fill='x',pady=8)
        ttk.Label(row,text='検索（英語名・日本語・番号）').pack(side='left')
        ttk.Entry(row,textvariable=self.query).pack(side='left',fill='x',expand=True)
        self.query.trace_add('write',lambda *_:self.refresh())
        container=ttk.Frame(frame);container.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(container,columns=('name','mass','kind','active'),show='headings',selectmode='browse')
        for key,label,width in [('name','名称',355),('mass','質量 g',75),('kind','形状の由来',150),('active','配置',60)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width,stretch=key=='name')
        scroll=ttk.Scrollbar(container,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.describe)
        self.info=tk.StringVar(value='物体を選択してください。各種類を1個ずつ、複数種類を同時に配置できます。')
        ttk.Label(frame,textvariable=self.info,wraplength=800).pack(anchor='w',pady=8)
        row=ttk.Frame(frame);row.pack(fill='x');self.values={}
        for key,label,value in [('x','X m',.43),('y','Y m',-.18),('yaw','向き °',0)]:
            ttk.Label(row,text=label).pack(side='left',padx=(0,4));v=tk.StringVar(value=str(value));self.values[key]=v
            ttk.Entry(row,textvariable=v,width=9).pack(side='left',padx=(0,12))
        row=ttk.Frame(frame);row.pack(fill='x',pady=8)
        for label,action in [('指定位置へ配置','place'),('ランダム配置','reposition'),('削除','off')]:
            ttk.Button(row,text=label,command=lambda action=action:self.run(action)).pack(side='left',padx=(0,8))
        ttk.Button(row,text='状態を更新',command=lambda:parent.request('status')).pack(side='left')
        ttk.Label(frame,textvariable=parent.state,wraplength=800).pack(anchor='w')
        ttk.Label(frame,textvariable=parent.detail,wraplength=800).pack(anchor='w')
        ttk.Label(frame,text='腕を停止してから配置してください。高さは自動調整。大きすぎる物体や衝突する位置は拒否します。\n質量の「推定」、代替形状は選択時に明示します。全物体は剛体です。',wraplength=800).pack(anchor='w',pady=8)
        self.refresh();self.query.set('mug')
    def selected(self):
        selected=self.tree.selection()
        return next((e for e in CATALOG if e['key']==selected[0]),None) if selected else None
    def refresh(self):
        selected=self.tree.selection();q=self.query.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for e in CATALOG:
            if q and q not in (e['label']+' '+e['name']).lower():continue
            self.tree.insert('', 'end', iid=e['key'],values=(e['label'],f"{e['mass_kg']*1000:g}"+(' 推定' if e['mass_estimated'] else ''),e['quality'],'ON' if self.active.get(e['key']) else 'OFF'))
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected)
        elif self.tree.get_children():self.tree.selection_set(self.tree.get_children()[0])
    def describe(self,*_):
        e=self.selected()
        if not e:return
        size=' × '.join(f'{v*1000:.1f}' for v in e.get('size',[]))
        self.info.set(f"{e['name']} — {size} mm\n{e.get('note','')} 質量: {e['mass_source']}")
    def run(self,action):
        e=self.selected()
        if not e:return
        if not e['available']:
            self.parent.state.set('この物体のモデルは利用できません');return
        extra=[]
        if action=='place':
            try:
                values={k:float(v.get()) for k,v in self.values.items()}
                if not all(math.isfinite(v) for v in values.values()):raise ValueError()
            except ValueError:self.parent.state.set('X・Y・向きには有限の数値を入力してください');return
            extra=[s for k,v in values.items() for s in ['--'+k,str(v)]]
        self.parent.request(e['key']+'-'+action,extra)
    def update(self,active):
        self.active=active;self.refresh()
