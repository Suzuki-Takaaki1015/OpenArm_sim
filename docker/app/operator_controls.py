"""Existing scene panel controls for joint-space postures and mobile teleoperation."""
import json
import math
import os
import signal
import subprocess
from tkinter import ttk
import tkinter as tk

from ament_index_python.packages import get_package_prefix
from mobile_speeds import MANUAL_SPEEDS


class PosturePanel:
    def __init__(self, parent):
        self.proc = None
        box = ttk.LabelFrame(parent, text='アーム姿勢（MoveIt 2・関節角度）',padding=6)
        box.pack(fill='x',pady=4)
        row=ttk.Frame(box);row.pack(fill='x')
        self.side=tk.StringVar(value='right')
        self.chooser=ttk.Combobox(row,values=['right','left'],textvariable=self.side,state='readonly',width=6)
        self.chooser.pack(side='left')
        self.buttons=[]
        for text,command in [('現在角を取得',lambda:self.run(True)),('初期姿勢を入力',self.home),('計画して実行',lambda:self.run(False))]:
            button=ttk.Button(row,text=text,command=command)
            button.pack(side='left',padx=2);self.buttons.append(button)
        ttk.Button(row,text='中止',command=self.cancel).pack(side='left')
        joints=ttk.Frame(box);joints.pack(fill='x')
        self.fields=[]
        for i in range(7):
            ttk.Label(joints,text=f'J{i+1} °').grid(row=0,column=i)
            var=tk.StringVar()
            ttk.Entry(joints,width=7,textvariable=var).grid(row=1,column=i,padx=2)
            self.fields.append(var)
        self.chooser.bind('<<ComboboxSelected>>',lambda _:self.clear())
        self.status=tk.StringVar(value='左右の腕を選び、現在角を読み込んで編集します。')
        ttk.Label(box,textvariable=self.status,wraplength=620).pack(anchor='w')
        self.box=box

    def clear(self):
        for var in self.fields:var.set('')

    def home(self):
        for var in self.fields:var.set('0')

    def run(self, reading):
        if self.proc:return
        try:
            args=['--read']
            if not reading:
                angles=[float(v.get()) for v in self.fields]
                if not all(map(math.isfinite,angles)):raise ValueError()
                args=['--degrees',*map(str,angles)]
            exe=get_package_prefix('happy_posture')+'/lib/happy_posture/posture'
            self.proc=subprocess.Popen([exe,self.side.get(),*args],stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,text=True,start_new_session=True)
        except ValueError:
            self.status.set('7関節すべてに角度（度）を入力してください。');return
        except (OSError,LookupError) as exc:
            self.status.set(str(exc));return
        self.status.set('取得中…' if reading else '経路計画・実行中…')
        self.chooser.configure(state='disabled')
        for button in self.buttons:button.state(['disabled'])
        self.box.after(80,lambda:self.poll(reading))

    def poll(self, reading):
        if self.proc.poll() is None:
            self.box.after(80,lambda:self.poll(reading));return
        output=self.proc.communicate()[0].strip().splitlines()
        code=self.proc.returncode;self.proc=None
        self.chooser.configure(state='readonly')
        for button in self.buttons:button.state(['!disabled'])
        if reading and code==0:
            for var,n in zip(self.fields,json.loads(output[-1])):var.set(str(n))
            self.status.set('現在角を取得しました。')
        else:self.status.set(output[-1] if output else f'終了コード {code}')

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)


class KeyboardDrive:
    axes={'w':(1,0,0),'s':(-1,0,0),'a':(0,1,0),'d':(0,-1,0),'q':(0,0,1),'e':(0,0,-1)}
    def __init__(self,parent):
        import rclpy
        from geometry_msgs.msg import Twist
        self.msg=Twist
        self.context=rclpy.Context()
        rclpy.init(context=self.context)
        self.node=rclpy.create_node('happy_keyboard_drive',context=self.context)
        self.publisher=self.node.create_publisher(Twist,'/happy/manual_cmd_vel',1)
        self.enabled=tk.BooleanVar(value=False)
        self.keys=set()
        self.release_jobs={}
        self.closed=False
        box=ttk.LabelFrame(parent,text='台車の手動運転',padding=6);box.pack(fill='x',pady=4)
        self.speed = tk.StringVar(value='標準')
        speeds = ttk.Frame(box)
        speeds.pack(fill='x')
        ttk.Label(speeds,text='走行速度').pack(side='left')
        for name,(linear,_) in MANUAL_SPEEDS.items():
            ttk.Radiobutton(speeds,text=f'{name} {linear:.2f} m/s',variable=self.speed,
                            value=name).pack(side='left',padx=3)
        ttk.Checkbutton(box,text='ユーザー移動制御モード',variable=self.enabled,command=self.toggle).pack(anchor='w')
        self.pad=tk.Label(box,text='W 前進　S 後退　A 左　D 右　Q 左旋回　E 右旋回　Esc 解除',
                          padx=6,pady=10,bg='#e0e4e5',takefocus=True)
        self.pad.pack(fill='x')
        self.pad.bind('<KeyPress>',self.press)
        self.pad.bind('<KeyRelease>',self.release)
        self.pad.bind('<FocusOut>',lambda _:self.off())
        self.pad.bind('<Unmap>',lambda _:self.off())
        self.pad.after(50,self.tick)

    def toggle(self):
        if self.enabled.get():
            self.keys.clear()
            self.pad.focus_set()
            self.pad.configure(bg='#a6ddc1')
            self.send()
        else:self.off(force=True)

    def press(self,event):
        key=event.keysym.lower()
        if key=='escape':self.off();return 'break'
        if self.enabled.get() and key in self.axes:
            job=self.release_jobs.pop(key,None)
            if job:self.pad.after_cancel(job)
            self.keys.add(key);return 'break'

    def release(self,event):
        key=event.keysym.lower()
        if key in self.keys and key not in self.release_jobs:
            # X11 autorepeat can send Release then Press with the same keysym.
            self.release_jobs[key]=self.pad.after_idle(lambda:self.finish_release(key))
            return 'break'

    def finish_release(self,key):
        self.release_jobs.pop(key,None);self.keys.discard(key)
        if self.enabled.get():self.send()

    def send(self):
        x,y,w=(sum(self.axes[k][i] for k in self.keys) for i in range(3))
        linear, yaw = MANUAL_SPEEDS[self.speed.get()]
        scale = linear / max(1., math.hypot(x,y))
        msg=self.msg()
        msg.linear.x=x*scale;msg.linear.y=y*scale;msg.angular.z=yaw*w
        self.publisher.publish(msg)

    def tick(self):
        if self.closed:return
        if self.enabled.get():
            if self.pad.focus_get()==self.pad:self.send()
            else:self.off()
        self.pad.after(50,self.tick)

    def off(self,force=False):
        if self.closed:return
        active=self.enabled.get()
        self.enabled.set(False);self.keys.clear()
        for job in self.release_jobs.values():self.pad.after_cancel(job)
        self.release_jobs.clear()
        if active or force:self.send()
        self.pad.configure(bg='#e0e4e5')

    def close(self):
        self.off();self.closed=True
        self.node.destroy_node();self.context.shutdown()
