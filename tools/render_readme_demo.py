"""Render a clearly-labelled illustrative animation from verified fictional results."""
from pathlib import Path
import json,functools,hashlib
from PIL import Image,ImageDraw,ImageFont
W,H=1280,800
BG='#F5F8FA';INK='#173C4B';MUTED='#667E8B';TEAL='#078592';PALE='#E8F4F5';LINE='#D9E4E9';WHITE='#FFFFFF';GREEN='#23765C';GP='#E7F3ED';AMBER='#9B6427';AP='#FCF1DF'
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
@functools.lru_cache(None)
def font(n):return ImageFont.truetype(FONT,n)
def txt(d,xy,s,n=24,color=INK):d.text(xy,str(s),font=font(n),fill=color)
def rr(d,box,fill=WHITE,outline=LINE,r=16,width=1):d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)
def ease(v):v=max(0,min(1,v));return v*v*(3-2*v)
def wrap(d,text,width,n):
 lines=[];line=''
 for ch in str(text):
  if ch=='\n':lines.append(line);line='';continue
  if line and d.textlength(line+ch,font=font(n))>width:lines.append(line);line=ch
  else:line+=ch
 if line:lines.append(line)
 return lines

def paragraph(d,xy,text,width,n=24,color=INK,leading=None,maxlines=None):
 lines=wrap(d,text,width,n);leading=leading or n+10
 if maxlines and len(lines)>maxlines:
  lines=lines[:maxlines]
  while lines[-1] and d.textlength(lines[-1]+'…',font=font(n))>width:lines[-1]=lines[-1][:-1]
  lines[-1]+='…'
 for i,s in enumerate(lines):txt(d,(xy[0],xy[1]+i*leading),s,n,color)
 return len(lines)*leading

def pill(d,xy,label,color=TEAL,fill=PALE,n=19):
 width=d.textlength(label,font=font(n))+26;x,y=xy;rr(d,(x,y,x+width,y+34),fill,None,10);txt(d,(x+13,y+5),label,n,color);return width

def tick(d,x,y,r=12,color=TEAL):
 d.ellipse((x-r,y-r,x+r,y+r),fill=color)
 d.line([(x-5,y),(x-1,y+4),(x+6,y-5)],fill=WHITE,width=3)

def base(title,subtitle,chapter):
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 txt(d,(48,26),'Privacy Protector · 隐私保护Skill  /  0.10.0',21,TEAL)
 pill(d,(984,24),'示意动画',AMBER,AP);pill(d,(1110,24),'虚构材料',MUTED,'#E9EFF2')
 txt(d,(48,86),title,40)
 txt(d,(48,151),subtitle,22,MUTED)
 for i,label in enumerate(['01  自动自检','02  表格处理','03  文档摘录']):
  x=48+i*400;active=chapter==i
  rr(d,(x,205,x+384,250),TEAL if active else WHITE,None if active else LINE,12)
  txt(d,(x+22,215),label,22,WHITE if active else MUTED)
 d.line((48,720,1232,720),fill=LINE,width=1)
 txt(d,(48,737),'流程动效为示意 · 数字与摘录来自本机实测 · 非软件界面录屏',18,MUTED)
 txt(d,(48,768),'实测：Apple M5 / 24GiB  ｜  8GB、Windows / WorkBuddy、Intel Mac 尚未实机验收',17,MUTED)
 return im,d

def intro(t,R):
 im,d=base('隐私材料，留在本地完成处理','表格计算、文档摘录和自动自检，按同一条本地流程运行。',-1)
 cards=[('01','先检查，再处理','自动试跑虚构材料，核验资源、保护与输出。'),('02','台账，筛出重点','筛选、排序、统计，保留原值并回填身份。'),('03','纪要，摘出待办','由本地模型选取原文，结果交由本人核对。')]
 for i,(num,title,body) in enumerate(cards):
  k=ease((t-i*.18)/.65);y=295+int(18*(1-k));x=48+i*400
  rr(d,(x,y,x+384,y+255));txt(d,(x+26,y+26),num,24,TEAL);txt(d,(x+26,y+82),title,30)
  paragraph(d,(x+26,y+139),body,330,24,MUTED,36)
 rr(d,(48,603,1232,683),PALE,None,14)
 txt(d,(76,628),'你负责：说任务、选文件、核对结果。支持的处理由程序在后台完成。',25,INK)
 return im

def selfcheck(t,R):
 im,d=base('首次安装后，先用虚构材料检查','安装后自动检查环境并试跑；右侧为 Mac 样例的实测结果。',0)
 rr(d,(48,275,745,693));pill(d,(72,296),'流程示意',AMBER,AP)
 labels=['检查电脑资源','确认处理进程断网','试跑虚构表格与文档','核验结果后启用']
 for i,label in enumerate(labels):
  y=370+i*57;done=t>0.45+i*.70
  if done:tick(d,90,y+15)
  else:d.ellipse((78,y+3,102,y+27),outline=LINE,width=2)
  txt(d,(122,y),label,26,INK if done else MUTED)
 rr(d,(72,618,721,674),AP,None,10)
 txt(d,(88,628),'规则示意：可用内存不足时停止，不自动转云端。',21,AMBER)
 rr(d,(768,275,1232,693));pill(d,(792,296),'样例实测',GREEN,GP)
 receipt=R['first_self_check'];num=len(receipt['checks']);secs=receipt['elapsed_seconds']
 txt(d,(800,350),f'{num} / {num}',54,TEAL);txt(d,(802,414),'核验项目通过',24)
 txt(d,(800,470),f'{secs:.2f} 秒',40);txt(d,(802,522),'自检耗时，不含首次下载',21,MUTED)
 txt(d,(802,585),f"{receipt['local_model_calls']} 次真实本地模型调用",25,INK)
 txt(d,(802,637),'已复用校验通过的模型缓存',19,MUTED)
 return im

def table(t,R):
 im,d=base('表格：8 条记录，筛出 5 条跟进','虚构任务：待补材料数 ≥ 3，按数量降序，新增统一跟进标记与优先级。',1)
 rr(d,(48,275,606,693));txt(d,(70,293),'原表 · 8 条虚构记录',25);txt(d,(72,332),'编号          姓名          待补 / 份    已核对 / 份',18,MUTED)
 rows=R['table']['input_rows'][1:]
 for i,row in enumerate(rows):
  y=365+i*36;chosen=row[2]>=3 and t>.55+i*.12
  if chosen:rr(d,(64,y-2,590,y+32),PALE,None,6)
  for x,v in zip([76,193,330,464],row):txt(d,(x,y),v,22,TEAL if chosen else MUTED)
 txt(d,(72,661),'原文件未改动',19,MUTED)
 rr(d,(630,275,1232,693));txt(d,(654,293),'结果 · 保留身份与原值',25);pill(d,(1078,291),'实测',GREEN,GP,18)
 heads=['姓名','待补 / 份','是否跟进','优先级'];xs=[656,790,915,1110]
 for x,v in zip(xs,heads):txt(d,(x,337),v,19,MUTED)
 for i,row in enumerate(R['table']['output_rows'][1:]):
  progress=ease((t-1.6-i*.27)/.6)
  if progress<=0:continue
  y=379+i*43;dx=int((1-progress)*28)
  if i%2==0:rr(d,(646,y-5,1216,y+36),'#F0F6F7',None,6)
  for x,v in zip(xs,[row[1],row[2],row[-2],row[-1]]):txt(d,(x+dx,y),v,23,INK)
 if t>3.5:
  rr(d,(650,605,1212,645),GP,None,9);txt(d,(668,613),f"实测：{R['table']['selected_count']} 条，待补材料合计 {R['table']['selected_sum']} 份",24,GREEN)
 txt(d,(654,662),'本地程序计算 · 未调用模型 · 结果展示部分列',18,MUTED)
 return im

def document(t,R):
 im,d=base('文档：6 段纪要，摘出 3 项待办','由本地模型选段，程序按原文生成结果；以下人物与情境均为虚构。',2)
 rr(d,(48,275,618,693));txt(d,(70,294),'原纪要 · 节选展示',25)
 ids=R['document']['selected_ids']
 for i,p in enumerate(R['document']['input_paragraphs'],1):
  y=341+(i-1)*55;chosen=i in ids and t>.5+(i-1)*.22
  if chosen:rr(d,(65,y-3,601,y+49),PALE,None,6)
  txt(d,(77,y+6),f'{i:02d}',20,TEAL if chosen else MUTED)
  paragraph(d,(119,y),p,466,18,INK if chosen else MUTED,25,2)
 txt(d,(72,671),'完整正文已在本机核验',17,MUTED)
 rr(d,(640,275,1232,693));txt(d,(662,294),'导出 Word · 原文摘录',25);pill(d,(1112,291),'实测',GREEN,GP,18)
 for k,(num,p) in enumerate(zip(ids,R['document']['output_paragraphs'])):
  progress=ease((t-2-k*.48)/.6)
  if progress<=0:continue
  y=343+k*101;dx=int((1-progress)*22)
  rr(d,(658+dx,y,1214,y+91),PALE,None,10)
  txt(d,(675+dx,y+15),f'{num:02d}',21,TEAL)
  paragraph(d,(722+dx,y+10),p,470-dx,20,INK,29,3)
 txt(d,(666,661),f"真实调用本地模型 {R['document']['local_model_calls']} 次 · 摘录逐字比对通过",19,MUTED)
 return im

def ending(t,R):
 im,d=base('样例结果与设备要求','虚构材料的实测结果；画面为流程示意，播放速度不代表处理耗时。',-1)
 cards=[('9 / 9','首次自检核验通过'),('5 条 · 21 份','表格筛选与合计'),('第 2、3、6 段','未完成待办摘录')]
 for i,(number,label) in enumerate(cards):
  x=48+i*400;rr(d,(x,287,x+384,460));txt(d,(x+25,320),number,36,TEAL);txt(d,(x+25,393),label,23)
 rr(d,(48,492,1232,692),WHITE,LINE,14)
 pill(d,(72,512),'适用边界',AMBER,AP)
 txt(d,(72,564),'8GB、Windows / WorkBuddy、Intel Mac 尚未实机验收。',28)
 txt(d,(72,613),'短样例通过不保证任意材料都能完成；文档结果仍需本人核对。',23,MUTED)
 txt(d,(72,653),'保护只覆盖本 Skill 的处理流程，不撤销原 Agent 已有文件权限。',21,MUTED)
 return im

SCENES=[('开场',4,intro),('自动自检',8,selfcheck),('表格处理',12,table),('文档摘录',13,document),('验证边界',8,ending)]
def run(report_path,out):
 R=json.loads(Path(report_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
 assert R['version']=='0.10.0' and R['table']['selected_count']==5 and R['document']['selected_ids']==[2,3,6]
 assert R['presentation']=='redrawn_animation_not_screen_recording' and not R['real_private_data_read']
 keyframes=[fn(dur-.2,R) for _,dur,fn in SCENES]
 sheet=Image.new('RGB',(W*len(keyframes),H),WHITE)
 for i,im in enumerate(keyframes):sheet.paste(im,(W*i,0))
 palette=sheet.quantize(colors=128,method=Image.Quantize.MEDIANCUT)
 frames=[];durations=[];fps=6;timecodes=[];elapsed=0
 for name,dur,fn in SCENES:
  timecodes.append({'chapter':name,'start_seconds':elapsed,'duration_seconds':dur})
  for i in range(dur*fps):
   im=fn(i/fps,R).quantize(palette=palette,dither=Image.Dither.NONE)
   frames.append(im);durations.append(160 if i%3 else 180)
  elapsed+=dur
 path=out/'privacy-workflow.gif'
 frames[0].save(path,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=True,disposal=1)
 ending(6,R).save(out/'demo-summary.png',optimize=True)
 for i,im in enumerate(keyframes):im.save(out/f'qa-{i+1}.png',optimize=True)
 # Contact sheet is QA-only; no learner/private artifacts are included.
 thumbs=Image.new('RGB',(1280,3*400),BG)
 for i,im in enumerate(keyframes):thumbs.paste(im.resize((640,400)),((i%2)*640,(i//2)*400))
 thumbs.save(out/'qa-contact.png')
 R['animation']={'format':'GIF','width':W,'height':H,'duration_seconds':45,'frame_rate':fps,'chapters':timecodes,'all_frames_are_redrawn':True,'progress_and_low_memory_branch':'illustrative_not_a_hardware_run','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 (out/'demo-verification.json').write_text(json.dumps(R,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'gif':str(path),'size_bytes':path.stat().st_size,'source_frames':len(frames),'seconds':sum(durations)/1000,'report':str(out/'demo-verification.json')},ensure_ascii=False))

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.report,a.output)
