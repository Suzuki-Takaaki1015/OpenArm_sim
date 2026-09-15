"""Desktop scene controls; runtime only, no embedded test runner."""
import os,json,queue,subprocess,sys,threading,socket,math
from pathlib import Path
import tkinter as tk
from tkinter import ttk
class ScenePanel:
    def __init__(self,root):
        self.root=root;self.queue=queue.Queue();self.busy=False;self.buttons=[];self.demo_proc=None;self.demo_stopping=False
        root.title(f"OpenArm {os.environ.get('OPENARM_VERSION','1')}.0 - シーン・カメラ");root.geometry('700x930');root.minsize(650,900)
        style=ttk.Style();style.configure('TLabel',font=('Noto Sans CJK JP',10));style.configure('TButton',font=('Noto Sans CJK JP',10),padding=7)
        frame=ttk.Frame(root,padding=18);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='シーンとD435カメラ',font=('Noto Sans CJK JP',17,'bold')).pack(anchor='w')
        self.group(frame,'作業台',[('表示','on'),('非表示','off')])
        self.group(frame,'把持対象：直方体（100 g）',[('配置','box-on'),('削除','box-off'),('ランダム再配置','box-reposition'),('左箱を削除','box_left-off')])
        self.group(frame,'把持対象：500 mLボトル（満水相当・近似剛体）',[('配置','bottle-on'),('削除','bottle-off'),('ランダム再配置','bottle-reposition')])
        self.ycb_panel=None
        ttk.Button(frame,text='YCB オブジェクトライブラリを開く',command=self.open_ycb).pack(fill='x',pady=(8,0))
        manual=ttk.LabelFrame(frame,text='位置を指定して配置（world座標）',padding=8);manual.pack(fill='x',pady=(10,0))
        row=ttk.Frame(manual);row.pack(fill='x')
        self.place_kind=tk.StringVar(value='直方体')
        ttk.Combobox(row,textvariable=self.place_kind,values=['直方体','左直方体','ボトル'],state='readonly',width=8).pack(side='left')
        self.place_values={}
        for label,key,value,lo,hi,inc in [('X m','x',.36,.29,.71,.01),('Y m','y',-.20,-.31,.31,.01),('向き °','yaw',0,-180,180,5)]:
            ttk.Label(row,text=label).pack(side='left',padx=(6,2))
            variable=tk.StringVar(value=str(value));self.place_values[key]=variable
            ttk.Spinbox(row,textvariable=variable,from_=lo,to=hi,increment=inc,width=6).pack(side='left')
        row=ttk.Frame(manual);row.pack(fill='x',pady=(5,0))
        b=ttk.Button(row,text='指定位置へ配置',command=self.place);b.pack(side='left');self.buttons.append(b)
        for label,y in [('手前・左',.20),('手前・右',-.20)]:
            ttk.Button(row,text=label,command=lambda y=y:self.preset(y)).pack(side='left',padx=4)
        ttk.Label(manual,text='Xは前方、Yは左方向。高さは机上へ自動調整。衝突・机外への配置は拒否します。',wraplength=620).pack(anchor='w')
        self.group(frame,'胸部D435：RGB・深度・CameraInfo・TF',[('配信開始','camera-on'),('配信停止','camera-off')])
        ttk.Label(frame,text='カメラは初期OFF・2 fps。公式マウント／M6固定高さ740 mm（本環境の基準）。',wraplength=570).pack(anchor='w',pady=(4,8))
        recovery=ttk.LabelFrame(frame,text='復旧',padding=8);recovery.pack(fill='x',pady=(10,8))
        self.restart_button=ttk.Button(recovery,text='シミュレーションを再起動',command=self.restart)
        self.restart_button.pack(anchor='w')
        ttk.Label(recovery,text='腕・物体・カメラを初期状態へ戻し、MoveItと制御も再起動します。',wraplength=560).pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x')
        self.button(row,'状態を更新','status')
        self.button(row,'右手把持デモ','grasp-demo')
        self.button(row,'両腕把持デモ','bimanual-demo')
        self.demo_stop=ttk.Button(row,text='デモ停止',command=self.stop_demo);self.demo_stop.pack(side='left');self.demo_stop.state(['disabled'])
        self.state=tk.StringVar(value='ROSへ接続中…')
        ttk.Label(frame,textvariable=self.state,wraplength=560).pack(anchor='w',pady=(10,3))
        self.detail=tk.StringVar(value='')
        ttk.Label(frame,textvariable=self.detail,wraplength=560,font=('Noto Sans CJK JP',9)).pack(anchor='w')
        ttk.Label(frame,text='配置・削除は腕を止めてから。配置時は机も自動で有効になります。\n物体を削除してから机を非表示にしてください。\n把持デモは初期姿勢から実行。机と直方体を準備し、他の配置物体を削除します。',wraplength=560).pack(anchor='w',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll);root.after(300,lambda:self.request('status'))
    def open_ycb(self):
        from ycb_panel import YcbPanel
        if self.ycb_panel is not None and self.ycb_panel.root.winfo_exists():self.ycb_panel.root.lift();return
        self.ycb_panel=YcbPanel(self)
        self.request('status')
    def preset(self,y):
        for key,value in [('x',.36),('y',y),('yaw',0)]:self.place_values[key].set(str(value))
    def place(self):
        try:
            values={k:float(v.get()) for k,v in self.place_values.items()}
            if not all(math.isfinite(v) for v in values.values()):raise ValueError()
        except ValueError:
            self.state.set('X・Y・向きに有限の数値を入力してください');return
        key={'直方体':'box','左直方体':'box_left','ボトル':'bottle'}[self.place_kind.get()]
        extra=[part for k,v in values.items() for part in ['--'+k,str(v)]]
        self.request(key+'-place',extra)
    def close(self):
        self.stop_demo();self.root.destroy()
    def stop_demo(self):
        if self.demo_proc is not None and self.demo_proc.poll() is None and not self.demo_stopping:
            self.demo_stopping=True
            self.demo_proc.terminate();self.state.set("デモを停止中…")
    def restart(self):
        if self.demo_proc is not None and self.demo_proc.poll() is None:
            self.stop_demo();self.root.after(1000,self.restart);return
        # This control does not depend on ROS responding and stays available
        # while scene service calls are waiting.
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect('/tmp/openarm-supervisor.sock')
                client.sendall(b'restart\n')
                reply=client.recv(64)
            if reply.strip()!=b'restarting':raise RuntimeError(reply.decode())
            self.state.set('再起動中… RVizとMuJoCoが開き直します。')
            self.detail.set('初期姿勢に戻ります。起動完了後に状態を更新してください。')
            self.restart_button.state(['disabled'])
            self.root.after(15000,lambda:self.restart_button.state(['!disabled']))
        except Exception as exc:
            self.state.set('再起動を開始できませんでした');self.detail.set(str(exc))
    def button(self,parent,label,action):
        b=ttk.Button(parent,text=label,command=lambda:self.request(action));b.pack(side='left',padx=(0,8));self.buttons.append(b)
    def group(self,parent,title,actions):
        group=ttk.LabelFrame(parent,text=title,padding=8);group.pack(fill='x',pady=(10,0))
        for label,action in actions:self.button(group,label,action)
    def request(self,action,extra=None):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.state(['disabled'])
        if action in ('grasp-demo','bimanual-demo'):
            self.demo_stopping=False;self.demo_stop.state(['!disabled'])
        self.state.set('処理中…');self.detail.set('初期化中は応答まで時間がかかる場合があります。')
        def worker():
            try:
                if action in ('grasp-demo','bimanual-demo'):
                    lines=[]
                    with subprocess.Popen(['/opt/openarm/scripts/entrypoint.sh','python','-u','-m','openarm_demos.grasp_demo' if action=='grasp-demo' else 'openarm_demos.bimanual_demo'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True) as proc:
                        self.demo_proc=proc
                        for line in proc.stdout:
                            lines.append(line.strip());self.queue.put(('demo-progress',True,line.strip()))
                        code=proc.wait()
                    self.queue.put(('demo-stopped' if code==130 else action,code in (0,130),'\n'.join(lines[-3:])));return
                r=subprocess.run([sys.executable,str(Path(__file__).with_name('scene_cli.py')),action,*(extra or [])],capture_output=True,text=True,timeout=180)
                self.queue.put((action,r.returncode==0,(r.stdout+r.stderr).strip()))
            except Exception as exc:self.queue.put((action,False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:action,ok,text=self.queue.get_nowait()
        except queue.Empty:pass
        else:
            if action=='demo-progress':
                self.state.set('把持デモを実行中…');self.detail.set(text)
                self.root.after(100,self.poll);return
            self.demo_stop.state(['disabled'])
            self.busy=False
            for b in self.buttons:b.state(['!disabled'])
            if not ok:self.state.set('操作できませんでした');self.detail.set(text[-300:])
            elif action=='demo-stopped':
                self.state.set('デモを停止しました');self.detail.set('再実行する場合はシミュレーションを再起動してください。')
            elif action in ('grasp-demo','bimanual-demo'):
                self.state.set('把持デモ完了');self.detail.set(text)
            elif action=='status':
                try:
                    d=json.loads(text);s=d['scene'];c=d['camera'];mark=lambda v:'ON' if v else 'OFF'
                    self.state.set(f'机 {mark(s["obstacles"])} ／ 直方体 {mark(s["objects"]["box"])} ／ ボトル {mark(s["objects"]["bottle"])} ／ カメラ {mark(c["enabled"])}')
                    if self.ycb_panel is not None and self.ycb_panel.root.winfo_exists():self.ycb_panel.update(s['objects'])
                    self.detail.set(c.get('error','') or f'シミュレーション速度: {s.get("performance",{}).get("real_time_factor",0):.2f} 倍（1.00が実時間）')
                except Exception:self.state.set('状態取得に失敗');self.detail.set(text[-300:])
            else:
                self.state.set('操作完了');self.detail.set(text)
                self.root.after(100,lambda:self.request('status'))
        self.root.after(100,self.poll)
if __name__=='__main__':
    root=tk.Tk();ScenePanel(root);root.mainloop()
