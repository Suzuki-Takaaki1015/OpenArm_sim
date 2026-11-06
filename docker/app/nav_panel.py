"""Map controls for the mobile scene panel."""
import queue
import threading
import tkinter as tk
from tkinter import messagebox,ttk
import happy_navigation as nav

class NavPanel:
    def __init__(self,parent,panel):
        self.panel=panel
        nav.setup()
        box=ttk.LabelFrame(parent,text='地図作成・Nav2',padding=6)
        box.pack(fill='x',pady=4)
        self.name=tk.StringVar(value='room_01')
        self.choices=ttk.Combobox(box,textvariable=self.name,width=17,postcommand=self.refresh)
        self.choices.pack(side='left')
        self.saving=False
        self.result=queue.Queue()
        for text,cmd in [('地図を保存',self.save),('保存地図で起動',lambda:self.switch(True)),('新規マッピング',lambda:self.switch(False))]:
            ttk.Button(box,text=text,command=cmd).pack(side='left')
        self.label=tk.StringVar()
        ttk.Label(parent,textvariable=self.label,wraplength=610).pack(anchor='w')
        self.mode_label();box.after(250,self.poll)
        self.box=box
    def mode_label(self):
        path=nav.selected()
        self.name.set(path.parent.name if path else 'room_01')
        self.refresh()
        self.label.set('自己位置推定: '+path.parent.name if path else 'マッピング: 手動運転で走行し、地図を保存してください。')
    def refresh(self):
        self.choices.configure(values=sorted(nav.map_paths(nav.room_id())))
    def save(self):
        if self.saving:return
        name=self.name.get().strip()
        self.saving=True;self.label.set('地図を保存しています…')
        def worker():
            try:nav.save(name);msg='地図を保存しました: '+name
            except Exception as exc:msg='保存失敗: '+str(exc)
            self.result.put(msg)
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:self.label.set(self.result.get_nowait());self.saving=False
        except queue.Empty:pass
        self.box.after(250,self.poll)
    def switch(self,localize):
        if self.saving:return
        if not messagebox.askokcancel('Nav2','機体とROSを初期位置から再起動します。未保存の地図は破棄されます。',parent=self.box):return
        try:
            nav.choose(self.name.get().strip() if localize else None)
            self.panel.restart()
            self.mode_label()
        except (ValueError,OSError) as exc:self.label.set(str(exc))
