"""Top-down room designer, opened as an independent window in mobile mode."""
import copy
import math
import os
import stat
from pathlib import Path
import socket
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import uuid

from room_layout import ACTIVE, FIELDS, KINDS, ROOMS, item, read, validate, write

from tabletop import PROPS, world_xy

class RoomEditor(tk.Toplevel):
    def __init__(self, parent, on_switch=None):
        super().__init__(parent)
        self.title('Happy mignon | 生活環境エディター')
        self.geometry('980x670')
        self.minsize(730, 480)
        self.items = []
        self.selection = None
        self.history = []
        self.drag = None
        self.scale = 70.
        self.pan = (0., 0.)
        self.tool = tk.StringVar(value='select')
        self.snap = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='家具を選び、平面図をクリックして配置します。')
        self.on_switch = on_switch
        self.editing_name = ''
        self.baseline = []
        self.library_name = tk.StringVar()
        self.active_label = tk.StringVar(value='使用中：名前なし')
        library = ttk.LabelFrame(self, text='環境ライブラリ', padding=6)
        library.pack(fill='x', padx=8, pady=4)
        controls = ttk.Frame(library)
        controls.pack(fill='x')
        self.library = ttk.Combobox(controls, state='readonly', width=24, textvariable=self.library_name,
                                    postcommand=self.refresh_library)
        self.library.pack(side='left')
        self.library.bind('<<ComboboxSelected>>', lambda _: self.refresh_library())
        for label, command in [('編集用に開く', self.open_saved), ('この環境に切替', self.switch_saved),
                               ('環境を保存', self.save_named)]:
            ttk.Button(controls,text=label,command=command).pack(side='left',padx=2)
        self.delete_room_button = ttk.Button(controls, text='環境を削除…', command=self.delete_saved)
        self.delete_room_button.pack(side='left', padx=2)
        ttk.Label(library,textvariable=self.active_label).pack(anchor='w',pady=(3,0))
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        for label, callback in [('新規', self.clear), ('ファイル取込', self.load), ('書き出し', self.save),
                                ('元に戻す', self.undo), ('全体表示', self.fit)]:
            ttk.Button(bar, text=label, command=callback).pack(side='left', padx=2)
        ttk.Button(bar, text='部屋を適用して再起動', command=self.apply).pack(side='right')
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True)
        side = ttk.Frame(body, padding=10)
        side.pack(side='right', fill='y')
        ttk.Label(side, text='配置ツール').pack(anchor='w')
        for k, label in [('select','選択・移動')]+[(k,v[0]) for k,v in KINDS.items()]:
            ttk.Radiobutton(side, text=label, variable=self.tool, value=k).pack(anchor='w')
        ttk.Checkbutton(side, text='10 cmグリッドに吸着', variable=self.snap).pack(anchor='w', pady=5)
        props = ttk.LabelFrame(side, text='選択中の家具', padding=5)
        props.pack(fill='x')
        self.inputs = {}
        for row,(k,label) in enumerate(zip(FIELDS, ('中心 X (m)','中心 Y (m)','向き (度)','長さ X (m)','奥行 Y (m)','高さ (m)'))):
            ttk.Label(props,text=label).grid(row=row,column=0,sticky='w')
            var=tk.StringVar()
            field=ttk.Entry(props,textvariable=var,width=9)
            field.grid(row=row,column=1,pady=2)
            field.bind('<Return>',lambda _:self.update_values())
            self.inputs[k]=var
        ttk.Button(props,text='数値を反映',command=self.update_values).grid(row=6,columnspan=2,sticky='ew')
        self.table_button = ttk.Button(side,text='机の上を編集…',command=self.edit_table)
        self.table_button.pack(fill='x',pady=3)
        self.table_button.state(['disabled'])
        ttk.Button(side,text='選択した家具を削除',command=self.delete).pack(fill='x',pady=6)
        ttk.Label(side,text='右方向が +X、上方向が +Y\n破線円は機体の初期位置\nホイールで拡大・縮小\n中ドラッグで平行移動').pack(anchor='w',pady=8)
        self.canvas=tk.Canvas(body,background='#f6f7f3',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.initial_fit = True
        self.canvas.bind('<Configure>',self.resize_canvas)
        self.canvas.bind('<Button-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.move)
        self.canvas.bind('<ButtonRelease-1>',lambda _:setattr(self,'drag',None))
        self.canvas.bind('<Delete>',lambda _:self.delete())
        self.canvas.bind('<Button-2>',lambda e:setattr(self,'pan_anchor',(e.x,e.y,*self.pan)))
        self.canvas.bind('<B2-Motion>',self.pan_view)
        for event,mult in [('<Button-4>',1.25),('<Button-5>',.8)]:
            self.canvas.bind(event,lambda _,v=mult:self.zoom(v))
        ttk.Label(self,textvariable=self.status,padding=7).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW',self.hide)
        if ACTIVE.exists():
            try:
                current=read(ACTIVE)
                self.items=current['items']
                self.editing_name=current.get('library_name','')
                self.library_name.set(self.editing_name)
            except (ValueError,OSError) as exc:self.status.set(str(exc))

        self.baseline=copy.deepcopy(self.items)
        self.refresh_library()

    def refresh_library(self):
        names = sorted(p.stem for p in ROOMS.glob('*.json')
                       if not p.name.startswith('.') and not p.is_symlink() and p.is_file())
        self.library.configure(values=names)
        if self.editing_name not in names:
            self.editing_name = ''
        if self.library_name.get() not in names:
            self.library_name.set('')
        self.delete_room_button.state(['!disabled' if self.library_name.get() else 'disabled'])

        # The supervisor keeps an independent snapshot of the running layout.
        try:
            active = read(ACTIVE) if ACTIVE.exists() else {}
            name = active.get('library_name', '')
            label = name or '名前なし'
            if name and name not in names:
                label += '（ライブラリ保存なし）'
            elif name and read(self.library_path(name))['items'] != active['items']:
                label += '（保存版と配置が異なります）'
        except (OSError, ValueError):
            label = '確認できません'
        self.active_label.set('使用中：'+label)

    def library_path(self,name):
        if not name or name.startswith('.') or any(c in name for c in ('/',chr(92))) or not name.isprintable() or len((name+'.json').encode())>255:
            raise ValueError('環境名を選択するか、ファイル名に使える名前を入力してください。')
        path=ROOMS/(name+'.json')
        if path.is_symlink():raise ValueError('シンボリックリンクは環境として操作できません。')
        return path

    def save_named(self):
        try:
            doc=self.document()
            name=simpledialog.askstring('環境を保存','大会名・会場名など',initialvalue=self.editing_name,parent=self)
            if name is None:return
            name=name.strip()
            path=self.library_path(name)
            if path.exists() and not messagebox.askyesno('環境を更新',name+' を上書きしますか？',parent=self):return
            write(path,doc)
            self.editing_name=name
            self.library_name.set(name)
            self.baseline=copy.deepcopy(doc['items'])
            self.refresh_library()
            self.status.set(name+' をライブラリに保存しました。')
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def delete_saved(self):
        name = self.library_name.get()
        try:
            path = self.library_path(name)
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('保存した環境ファイルを選んでください。')
            if not messagebox.askyesno('環境を削除', f'「{name}」を環境ライブラリから削除しますか？',
                                       detail='使用中の部屋・編集中の配置・保存済みの地図は保持されます。',
                                       default=messagebox.NO, parent=self):
                return
            # Another editor may have replaced the saved room while the dialog was open.
            after = path.lstat()
            if not os.path.samestat(before, after) or before.st_mtime_ns != after.st_mtime_ns:
                raise ValueError('確認中に保存版が変更されました。内容を確認してから削除してください。')
            path.unlink()
            self.status.set(f'「{name}」を環境ライブラリから削除しました。')
        except FileNotFoundError:
            self.status.set('選択した環境はすでにライブラリにありません。')
        except (OSError, ValueError) as exc:
            self.status.set(str(exc))
        self.refresh_library()

    def replace_draft(self,doc,name):
        self.items=doc['items']
        self.editing_name=name
        self.library_name.set(name)
        self.refresh_library()
        self.baseline=copy.deepcopy(self.items)
        self.history.clear()
        self.select(None)
        self.fit()

    def unsaved(self):
        return not self.update_values() or self.items!=self.baseline

    def open_saved(self):
        try:
            name=self.library_name.get()
            doc=read(self.library_path(name))
            if self.unsaved() and not messagebox.askokcancel('編集内容','未保存の編集を破棄して開きますか？',parent=self):return
            self.replace_draft(doc,name)
            self.status.set(name+' を編集中です。走行環境は「この環境に切替」で変更します。')
        except (ValueError,OSError) as exc:self.status.set(str(exc))

    def switch_saved(self):
        try:
            name=self.library_name.get()
            doc=read(self.library_path(name))
            note='未保存の編集は破棄されます。' if self.unsaved() else ''
            if not messagebox.askokcancel('環境を切替',f'{name} で機体を初期位置から再起動します。'+note,parent=self):return
            self.activate(doc,name)
            self.replace_draft(doc,name)
        except (ValueError,OSError) as exc:self.status.set(str(exc))

    def resize_canvas(self,event):
        if self.initial_fit and event.width > 100 and event.height > 100:
            self.initial_fit = False
            self.fit()
        else:
            self.draw()

    def hide(self):
        self.withdraw()  # Keep the draft available when the window reopens.

    def screen(self,x,y):
        return (self.canvas.winfo_width()/2+(x-self.pan[0])*self.scale,
                self.canvas.winfo_height()/2-(y-self.pan[1])*self.scale)

    def world(self,e):
        ox,oy=self.screen(0,0)
        return (e.x-ox)/self.scale,(oy-e.y)/self.scale

    def rounded(self,v):
        return round(v,1 if self.snap.get() else 3)

    def zoom(self,m):
        self.scale=max(6.,min(300.,self.scale*m))
        self.draw()

    def pan_view(self,e):
        x,y,px,py=self.pan_anchor
        self.pan=(px+(x-e.x)/self.scale,py+(e.y-y)/self.scale)
        self.draw()

    def fit(self):
        xs=[-.6,.6];ys=[-.6,.6]
        for obj in self.items:
            for x,y in self.corners(obj):
                xs.append(x);ys.append(y)
        self.pan=((min(xs)+max(xs))/2,(min(ys)+max(ys))/2)
        self.scale=min(85.,max(5.,min(self.canvas.winfo_width()/(max(xs)-min(xs)+1),
                                      self.canvas.winfo_height()/(max(ys)-min(ys)+1))))
        self.draw()

    def corners(self,o):
        a=math.radians(o['yaw'])
        for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]:
            x,y=sx*o['length']/2,sy*o['depth']/2
            yield (o['x']+x*math.cos(a)-y*math.sin(a),o['y']+x*math.sin(a)+y*math.cos(a))

    def draw(self):
        c=self.canvas;c.delete('all')
        w,h=c.winfo_width(),c.winfo_height()
        ox,oy=self.screen(0,0)
        spacing=self.scale if self.scale>22 else self.scale*5
        for start,end,vertical in [(ox,w,True),(oy,h,False)]:
            v=start%spacing
            while v<end:
                c.create_line(*( (v,0,v,h) if vertical else (0,v,w,v)),fill='#d8ded9')
                v+=spacing
        r=.45*self.scale
        c.create_oval(ox-r,oy-r,ox+r,oy+r,outline='#12746d',dash=(4,2),width=2)
        c.create_line(ox,oy,ox+r,oy,arrow='last',fill='#12746d')
        for i,o in enumerate(self.items):
            coords=[v for xy in self.corners(o) for v in self.screen(*xy)]
            label,_,rgba=KINDS[o['kind']]
            color='#%02x%02x%02x'%tuple(round(255*n) for n in rgba[:3])
            tag=f'item{i}'
            c.create_polygon(coords,fill=color,outline='#00658b' if i==self.selection else '#434944',
                             width=3 if i==self.selection else 1,tags=tag)
            if min(o['length'],o['depth'])*self.scale>19:
                c.create_text(*self.screen(o['x'],o['y']),text=label,tags=tag)

            for prop in o.get('objects', []):
                x,y = self.screen(*world_xy(o,prop['x'],prop['y']))
                rgba = PROPS[prop['kind']]['geoms'][0]['rgba']
                color = '#%02x%02x%02x'%tuple(round(255*n) for n in rgba[:3])
                size = max(2., .028*self.scale)
                c.create_oval(x-size,y-size,x+size,y+size,fill=color,outline='#333333',tags=tag)

    def edit_table(self):
        if self.selection is None or not self.update_values():
            return
        table = self.items[self.selection]
        if table['kind'] != 'table':
            return
        from tabletop_editor import TabletopEditor
        def commit(objects):
            if table.get('objects', []) != objects:
                self.remember()
                if objects:
                    table['objects'] = objects
                else:
                    table.pop('objects', None)
                self.draw()
                self.status.set('机上の配置を更新しました。部屋を保存、または適用してください。')
        TabletopEditor(self,table,commit)

    def remember(self):
        self.history=(self.history+[copy.deepcopy(self.items)])[-40:]

    def select(self,i):
        self.selection=i
        table = i is not None and self.items[i]['kind']=='table'
        self.table_button.state(['!disabled' if table else 'disabled'])
        for k,var in self.inputs.items():
            var.set(str(self.items[i][k]) if i is not None else '')
        self.draw()

    def press(self,e):
        self.canvas.focus_set()
        x,y=self.world(e)
        if self.tool.get()!='select':
            if len(self.items)>=100:
                self.status.set('家具は100個までです。');return
            self.remember()
            self.items.append(item(self.tool.get(),self.rounded(x),self.rounded(y)))
            self.tool.set('select')
            self.select(len(self.items)-1)
        else:
            i=None
            for hit in reversed(self.canvas.find_overlapping(e.x,e.y,e.x,e.y)):
                tags=self.canvas.gettags(hit)
                if tags and tags[0].startswith('item'):
                    i=int(tags[0][4:]);break
            self.select(i)
            if i is not None:
                self.drag=(x-self.items[i]['x'],y-self.items[i]['y'],False)

    def move(self,e):
        if self.drag is None:return
        dx,dy,started=self.drag
        if not started:
            self.remember();self.drag=(dx,dy,True)
        x,y=self.world(e)
        obj=self.items[self.selection]
        obj.update(x=self.rounded(x-dx),y=self.rounded(y-dy))
        self.select(self.selection)

    def update_values(self):
        if self.selection is None:return True
        try:
            obj=dict(self.items[self.selection],**{k:float(v.get()) for k,v in self.inputs.items()})
            validate(dict(version=1,items=[obj]),check_spawn=False)
        except ValueError as exc:
            self.status.set(str(exc));return False
        if obj!=self.items[self.selection]:
            self.remember();self.items[self.selection]=obj;self.select(self.selection)
        return True

    def delete(self):
        if self.selection is not None:
            self.remember();self.items.pop(self.selection);self.select(None)

    def clear(self):
        self.editing_name=''
        self.library_name.set('')
        self.refresh_library()
        if self.items:
            self.remember()
            self.items=[]
            self.select(None)
        self.fit()
        self.status.set('空の部屋を編集中。元に戻すこともできます。')

    def undo(self):
        if self.history:self.items=self.history.pop();self.select(None)

    def document(self):
        if not self.update_values():raise ValueError('家具の数値を確認してください。')
        return validate(dict(version=1,items=self.items))

    def save(self):
        try:
            doc=self.document()
            ROOMS.mkdir(parents=True,exist_ok=True)
            path=filedialog.asksaveasfilename(parent=self,initialdir=ROOMS,defaultextension='.json',filetypes=[('部屋','*.json')])
            if path:
                if Path(path).resolve()==ACTIVE.resolve():raise ValueError('別のファイル名を選んでください。')
                write(Path(path),doc);self.status.set('保存しました。 '+Path(path).name)
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def load(self):
        try:
            ROOMS.mkdir(parents=True,exist_ok=True)
            path=filedialog.askopenfilename(parent=self,initialdir=ROOMS,filetypes=[('部屋','*.json')])
            if path:
                doc=read(Path(path))
                if self.unsaved() and not messagebox.askokcancel('編集内容','未保存の編集を破棄して取り込みますか？',parent=self):return
                self.replace_draft(doc,'')
                self.baseline=[]
                self.status.set('読み込みました。「部屋を適用して再起動」で反映します。')
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def apply(self):
        try:
            doc=self.document()
            if not messagebox.askokcancel('部屋を適用','現在の走行・腕の動作を終了し、機体を初期位置から再起動します。',parent=self):return
            name=self.editing_name
            if name:
                path=self.library_path(name)
                if not path.exists() or read(path)['items']!=doc['items']:name=''
            self.activate(doc,name)
        except (OSError,ValueError) as exc:self.status.set(str(exc))

    def activate(self,doc,name):
        doc=dict(version=1,items=doc['items'])
        if name:doc['library_name']=name
        token=uuid.uuid4().hex[:16]
        path=Path('/tmp')/('happy-room-'+token+'.json')
        write(path,doc)
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
                conn.settimeout(4)
                conn.connect('/tmp/openarm-supervisor.sock')
                conn.sendall(('room-'+token).encode());conn.shutdown(socket.SHUT_WR)
                reply=conn.recv(1024).decode().strip()
                if reply!='restarting':raise ValueError(reply or '応答がありません。')
        finally:path.unlink(missing_ok=True)
        self.status.set('部屋を適用しました。機体を再起動しています。')
        self.active_label.set('使用中：'+(name or '名前なし'))
        if self.on_switch:self.on_switch()
