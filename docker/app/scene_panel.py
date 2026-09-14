"""Small non-blocking desktop control panel for the built-in obstacle scene."""
import argparse
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

class ScenePanel:
    def __init__(self, root):
        self.root=root;self.results=queue.Queue();self.busy=False;self.last_mode=None;self.last_ok=False
        root.title('OpenArm - シーン操作');root.geometry('480x370');root.minsize(440,350)
        style=ttk.Style();style.configure('TLabel',font=('Noto Sans CJK JP',11));style.configure('TButton',font=('Noto Sans CJK JP',11),padding=8)
        frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='シミュレーションのシーン',font=('Noto Sans CJK JP',16,'bold')).pack(anchor='w')
        ttk.Label(frame,text='標準シーン：作業台 ＋ 固定障害物').pack(anchor='w',pady=(16,5))
        ttk.Label(frame,text='表示すると、MoveItの衝突判定と\nMuJoCoの物理接触も有効になります。').pack(anchor='w')
        self.state=tk.StringVar(value='ROSへの接続を確認しています…')
        ttk.Label(frame,textvariable=self.state,wraplength=420).pack(anchor='w',pady=16)
        row=ttk.Frame(frame);row.pack(fill='x')
        self.buttons=[]
        for text,mode in [('表示する','on'),('非表示にする','off'),('状態を確認','status')]:
            button=ttk.Button(row,text=text,command=lambda mode=mode:self.request(mode));button.pack(side='left',padx=(0,8));self.buttons.append(button)
        ttk.Label(frame,text='切り替えは腕を停止させてから行ってください。\n固定物体です。持ち上げる把持対象ではありません。',wraplength=420).pack(anchor='w',pady=(16,0))
        self.detail=tk.StringVar(value='このパネルを閉じてもシミュレーションは継続します。')
        ttk.Label(frame,textvariable=self.detail,wraplength=420,font=('Noto Sans CJK JP',9)).pack(anchor='w',pady=(8,0))
        root.after(100,self.poll);root.after(200,lambda:self.request('status'))

    def request(self, mode):
        if self.busy:return
        self.busy=True;self.last_mode=None
        for button in self.buttons:button.state(['disabled'])
        self.state.set('状態を確認中…' if mode=='status' else 'シーンを更新中…')
        self.detail.set('応答を待っています。初期化中は少し時間がかかります。')
        def work():
            try:
                result=subprocess.run([sys.executable,str(Path(__file__).with_name('scene_cli.py')),mode],capture_output=True,text=True,timeout=100)
                self.results.put((mode,result.returncode==0,(result.stdout+result.stderr).strip()))
            except Exception as exc:self.results.put((mode,False,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            mode,ok,text=self.results.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False;self.last_mode=mode;self.last_ok=ok
            for button in self.buttons:button.state(['!disabled'])
            if ok:
                if mode=='status':
                    state='非表示' if text.endswith('off') else '表示中' if 'openarm_demo_table' in text and 'openarm_demo_obstacle' in text else '一部のみ登録'
                    self.state.set('MoveIt登録状態：'+state)
                else:self.state.set('表示中：表示・接触・衝突判定が有効' if mode=='on' else '非表示：接触・衝突判定は無効')
                self.detail.set('操作完了。最新状態は「状態を確認」で再取得できます。')
            else:
                self.state.set('操作できませんでした。状態を確認して再試行してください。')
                self.detail.set(text[-220:])
                print(text,file=sys.stderr,flush=True)
        self.root.after(100,self.poll)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    root=tk.Tk();panel=ScenePanel(root)
    if args.self_test:
        stages=iter(['on','off']); outcome=[False]
        def advance():
            if panel.last_mode and not panel.busy:
                if not panel.last_ok:root.destroy();return
                try:panel.request(next(stages))
                except StopIteration:outcome[0]=True;root.destroy();return
            root.after(200,advance)
        root.after(300,advance);root.after(180000,root.destroy)
        root.mainloop()
        if not outcome[0]:raise SystemExit('Panel integration test failed')
        print('PASS: GUI status, enable, disable via live ROS services')
    else:root.mainloop()

if __name__=='__main__':main()
