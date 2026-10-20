import json,math,re,collections
from pathlib import Path
d=json.loads(Path('artifacts/dezignlink/design-parameters-is800-response.json').read_text());M={int(k):tuple(v) for k,v in d[0][0].items()};N={int(k):v for k,v in d[0][1].items()};G=json.loads(Path('artifacts/dezignlink/cached-disposable-engineering.json').read_text())['selection']['mem_groups'];cols=set(G['-COL-']);beta=set(d[0][3]['90'])
def parse(txt):
 out=collections.defaultdict(dict)
 for line in txt.replace('-\n','').splitlines():
  m=re.match(r'(LY|LZ|UNL|DJ1|DJ2) ([\d.]+) MEMB (.*)',line)
  if m:
   for mid in map(int,m[3].split()):out[m[1]][mid]=float(m[2])
 return out
P=parse(d[1]); A=collections.defaultdict(list)
for mid,(a,b) in M.items():A[a].append((mid,b));A[b].append((mid,a))
vertical={mid for mid,(a,b) in M.items() if abs(N[a][0]-N[b][0])<1e-5 and abs(N[a][2]-N[b][2])<1e-5}
def span(mid,axis,diagonal=True,primary=False):
 a,b=M[mid]; lo,hi=sorted((a,b),key=lambda n:N[n][1]); ends=[]
 for seed,direction in [(lo,-1),(hi,1)]:
  n=seed;seen=set()
  while True:
   rest=[]
   for k,o in A[n]:
    if k in vertical:continue
    delta=[abs(y-x) for x,y in zip(N[n],N[o])]
    if delta[axis]>1e-5 and (diagonal or delta[1]<1e-5) and (not primary or k in set(G['-PBM-'])):rest.append(k)
   if rest:break
   options=[o for k,o in A[n] if k in vertical and (N[o][1]-N[n][1])*direction>1e-5 and o not in seen]
   if len(options)!=1:break
   seen.add(n);n=options[0]
  ends.append(N[n][1])
 return round(ends[1]-ends[0],3)
for diag in [False,True]:
 for prim in [False,True]:
  for swap in [False,True]:
   counts=[]
   for key,axis in [('LY',0 if swap else 2),('LZ',2 if swap else 0)]:
    good=[];bad=[]
    for mid,v in P[key].items():
     ax=2-axis if mid in beta else axis
     pred=span(mid,ax,diag,prim)
     (good if abs(pred-v)<.002 else bad).append((mid,v,pred))
    counts.append((key,len(good),len(bad),bad[:3]))
   print(diag,prim,swap,counts)
Path('artifacts/dezignlink/parameter-span-analysis.json').write_text(json.dumps({'column_count':len(cols),'parameters':{k:len(v) for k,v in P.items()}}))
