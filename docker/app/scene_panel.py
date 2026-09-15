"""Desktop scene controls; runtime only, no embedded test runner."""
import json,queue,subprocess,sys,threading,socket
from pathlib import Path
import tkinter as tk
from tkinter import ttk

class ScenePanel:
    def __init__(self,root):
        self.root=root;self.queue=queue.Queue();self.busy=False;self.buttons=[]
        root.title('OpenArm - シーン・カメラ');root.geometry('610x760');root.minsize(610,760)
        style=ttk.Style();style.configure('TLabel',font=('Noto Sans CJK JP',10));style.configure('TButton',font=('Noto Sans CJK JP',10),padding=7)
        frame=ttk.Frame(root,padding=18);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='シーンとD435カメラ',font=('Noto Sans CJK JP',17,'bold')).pack(anchor='w')
        self.group(frame,'作業台',[('表示','on'),('非表示','off')])
        self.group(frame,'把持対象：直方体（100 g）',[('配置','box-on'),('削除','box-off'),('ランダム再配置','box-reposition')])
        self.group(frame,'把持対象：500 mLボトル（満水相当・近似剛体）',[('配置','bottle-on'),('削除','bottle-off'),('ランダム再配置','bottle-reposition')])
        self.group(frame,'胸部D435：RGB・深度・CameraInfo・TF',[('配信開始','camera-on'),('配信停止','camera-off')])
        ttk.Label(frame,text='カメラは初期OFF・2 fps。公式マウント／M6固定高さ740 mm（本環境の基準）。',wraplength=570).pack(anchor='w',pady=(4,8))
        recovery=ttk.LabelFrame(frame,text='復旧',padding=8);recovery.pack(fill='x',pady=(10,8))
        self.restart_button=ttk.Button(recovery,text='シミュレーションを再起動',command=self.restart)
        self.restart_button.pack(anchor='w')
        ttk.Label(recovery,text='腕・物体・カメラを初期状態へ戻し、MoveItと制御も再起動します。',wraplength=560).pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x')
        self.button(row,'状態を更新','status')
        self.state=tk.StringVar(value='ROSへ接続中…')
        ttk.Label(frame,textvariable=self.state,wraplength=560).pack(anchor='w',pady=(10,3))
        self.detail=tk.StringVar(value='')
        ttk.Label(frame,textvariable=self.detail,wraplength=560,font=('Noto Sans CJK JP',9)).pack(anchor='w')
        ttk.Label(frame,text='配置・削除は腕を止めてから。配置時は机も自動で有効になります。\n物体を削除してから机を非表示にしてください。\n認識・自動把持プログラムは含みません。',wraplength=560).pack(anchor='w',pady=(12,0))
        root.after(100,self.poll);root.after(300,lambda:self.request('status'))
    def restart(self):
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
    def request(self,action):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.state(['disabled'])
        self.state.set('処理中…');self.detail.set('初期化中は応答まで時間がかかる場合があります。')
        def worker():
            try:
                r=subprocess.run([sys.executable,str(Path(__file__).with_name('scene_cli.py')),action],capture_output=True,text=True,timeout=180)
                self.queue.put((action,r.returncode==0,(r.stdout+r.stderr).strip()))
            except Exception as exc:self.queue.put((action,False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:action,ok,text=self.queue.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False
            for b in self.buttons:b.state(['!disabled'])
            if not ok:self.state.set('操作できませんでした');self.detail.set(text[-300:])
            elif action=='status':
                try:
                    d=json.loads(text);s=d['scene'];c=d['camera'];mark=lambda v:'ON' if v else 'OFF'
                    self.state.set(f'机 {mark(s["obstacles"])} ／ 直方体 {mark(s["objects"]["box"])} ／ ボトル {mark(s["objects"]["bottle"])} ／ カメラ {mark(c["enabled"])}')
                    self.detail.set(c.get('error','') or f'シミュレーション速度: {s.get("performance",{}).get("real_time_factor",0):.2f} 倍（1.00が実時間）')
                except Exception:self.state.set('状態取得に失敗');self.detail.set(text[-300:])
            else:
                self.state.set('操作完了');self.detail.set(text)
                self.root.after(100,lambda:self.request('status'))
        self.root.after(100,self.poll)

if __name__=='__main__':
    root=tk.Tk();ScenePanel(root);root.mainloop()
