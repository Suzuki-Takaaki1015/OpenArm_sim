"""Edit one tabletop at a useful scale, in the table's local frame."""
from tkinter import Toplevel, Canvas, StringVar, ttk
from tabletop import PROPS, footprint, rotate, validate_objects


class TabletopEditor(Toplevel):
    def __init__(self, parent, table, commit):
        super().__init__(parent)
        self.title('机の上を編集')
        self.geometry('720x470')
        self.minsize(550,350)
        self.transient(parent)
        self.table = table
        self.commit = commit
        self.objects = [dict(o) for o in table.get('objects', [])]
        self.selected = None
        self.drag = None
        self.tool = StringVar(value='select')
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill='x')
        for key, label in [('select','選択・移動')] + [(k,v['label']) for k,v in PROPS.items()]:
            ttk.Radiobutton(bar, text=label, value=key, variable=self.tool).pack(side='left')
        self.canvas = Canvas(self, background='#f6f7f3', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>',lambda _:self.draw())
        self.canvas.bind('<Button-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.move)
        self.canvas.bind('<ButtonRelease-1>',lambda _:setattr(self,'drag',None))
        self.canvas.bind('<Delete>',lambda _:self.remove())
        controls = ttk.Frame(self,padding=6)
        controls.pack(fill='x')
        self.fields = {}
        for key,label in [('x','X (m)'),('y','Y (m)'),('yaw','向き (°)')]:
            ttk.Label(controls,text=label).pack(side='left')
            var = StringVar()
            self.fields[key] = var
            field = ttk.Entry(controls,textvariable=var,width=8)
            field.pack(side='left',padx=(2,6))
            field.bind('<Return>',lambda _:self.apply_fields())
        ttk.Button(controls,text='数値を反映',command=self.apply_fields).pack(side='left')
        ttk.Button(controls,text='削除',command=self.remove).pack(side='left')
        footer = ttk.Frame(self,padding=6)
        footer.pack(fill='x')
        self.message = StringVar(value='種類を選び天板をクリック。机の中心が原点、右が +X、上が +Y です。')
        ttk.Label(footer,textvariable=self.message,wraplength=430).pack(side='left')
        ttk.Button(footer,text='机に反映',command=self.finish).pack(side='right')
        ttk.Button(footer,text='キャンセル',command=self.destroy).pack(side='right')
        self.grab_set()

    def scale(self):
        return max(.01,min((self.canvas.winfo_width()-36)/self.table['length'],
                           (self.canvas.winfo_height()-36)/self.table['depth']))

    def screen(self,x,y):
        scale = self.scale()
        return self.canvas.winfo_width()/2+x*scale,self.canvas.winfo_height()/2-y*scale

    def point(self,event):
        cx,cy = self.screen(0,0)
        return (event.x-cx)/self.scale(), (cy-event.y)/self.scale()

    def draw(self):
        c = self.canvas
        c.delete('all')
        w,h = self.table['length']/2,self.table['depth']/2
        c.create_rectangle(*self.screen(-w,h),*self.screen(w,-h),fill='#dec5a7',outline='#7c6045')
        cx,cy = self.screen(0,0)
        c.create_line(cx-5,cy,cx+5,cy,fill='#7c6045')
        c.create_line(cx,cy-5,cx,cy+5,fill='#7c6045')
        for i,obj in enumerate(self.objects):
            x,y = obj['x'],obj['y']
            hx,hy = footprint(obj)
            rgba = PROPS[obj['kind']]['geoms'][0]['rgba']
            opts = dict(fill='#%02x%02x%02x'%tuple(round(v*255) for v in rgba[:3]),
                        outline='#123c63' if i==self.selected else '#494642',
                        width=3 if i==self.selected else 1,tags=(f'prop{i}',))
            if obj['kind'] == 'box':
                corners = [rotate(sx*hx,sy*hy,obj['yaw']) for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
                c.create_polygon([v for dx,dy in corners for v in self.screen(x+dx,y+dy)],**opts)
            else:
                c.create_oval(*self.screen(x-hx,y+hy),*self.screen(x+hx,y-hy),**opts)

    def select(self,i):
        self.selected = i
        for key,var in self.fields.items():
            var.set('' if i is None else str(self.objects[i][key]))
        self.draw()

    def change(self, obj, index):
        updated = self.objects.copy()
        if index is None:
            index = len(updated)
            updated.append(obj)
        else:
            updated[index] = obj
        try:
            validate_objects(dict(self.table,objects=updated))
        except ValueError as exc:
            self.message.set(str(exc))
            return False
        self.objects = updated
        self.select(index)
        self.message.set('机の中心を基準に位置・向きを指定できます。')
        return True

    def press(self,event):
        self.canvas.focus_set()
        x,y = self.point(event)
        tool = self.tool.get()
        if tool != 'select':
            if self.change(dict(kind=tool,x=round(x,3),y=round(y,3),yaw=0.),None):
                self.tool.set('select')
            return
        self.drag = None
        hits = self.canvas.find_overlapping(event.x-2,event.y-2,event.x+2,event.y+2)
        for hit in reversed(hits):
            tag = next((t for t in self.canvas.gettags(hit) if t.startswith('prop')),None)
            if tag:
                self.select(int(tag[4:]))
                obj = self.objects[self.selected]
                self.drag = x-obj['x'], y-obj['y']
                return
        self.select(None)

    def move(self,event):
        if self.drag is not None:
            x,y = self.point(event)
            self.change(dict(self.objects[self.selected],x=round(x-self.drag[0],3),
                             y=round(y-self.drag[1],3)),self.selected)

    def remove(self):
        if self.selected is not None:
            self.objects.pop(self.selected)
            self.drag = None
            self.select(None)

    def apply_fields(self):
        if self.selected is None:
            return True
        try:
            values = {k:float(v.get()) for k,v in self.fields.items()}
        except ValueError:
            self.message.set('位置と向きに数値を入力してください。')
            return False
        return self.change(dict(self.objects[self.selected],**values),self.selected)

    def finish(self):
        if self.apply_fields():
            self.commit(self.objects)
            self.destroy()
