#!/usr/bin/env python3
"""Regenerate embeddable FinCoach mini-games under web/static/games/. Run: python3 scripts/generate_embed_games.py"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "web" / "static" / "games"
LINK = '<link rel="stylesheet" href="/static/games/shared/game-shell.css">'


def page(title: str, body: str, script: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{LINK}
</head>
<body>
{body}
<script>
{script}

function reportHeight() {{
  const h = Math.max(
    document.body ? document.body.scrollHeight : 0,
    document.documentElement ? document.documentElement.scrollHeight : 0
  );
  if (window.parent && window.parent !== window) {{
    window.parent.postMessage({{ type: 'fincoach-game-height', height: h }}, window.location.origin);
  }}
}}

window.addEventListener('load', reportHeight);
window.addEventListener('resize', reportHeight);
new MutationObserver(() => reportHeight()).observe(document.body, {{ childList: true, subtree: true, attributes: true }});
setTimeout(reportHeight, 0);
</script>
</body>
</html>
"""


def main() -> None:
    games: dict[str, str] = {}

    games["budget-blaster"] = page(
        "Sort the chips",
        """<h1>Drag chips to bins</h1><p class="sub">Needs 🏠 vs wants ✨ — drop each chip in the right zone.</p>
<div class="score" id="sc"></div>
<div class="chip-tray" id="tray"></div>
<div class="bins-row">
<div class="drop-bin" data-cat="need" id="bn"><h3>Needs</h3></div>
<div class="drop-bin" data-cat="want" id="bw"><h3>Wants</h3></div>
</div>
<div class="feedback hidden" id="fb"></div>""",
        """const items=[{t:"🍞 Groceries",c:"need",p:0},{t:"🎮 New console",c:"want",p:0},{t:"🏠 Rent",c:"need",p:0},{t:"🎤 Concert (optional)",c:"want",p:0},{t:"🚌 Bus pass",c:"need",p:0},{t:"👟 Extra sneakers",c:"want",p:0}];
let placed=0,good=0;
function tray(){const tr=document.getElementById('tray');tr.innerHTML='';
items.forEach((it,i)=>{if(it.p)return;const d=document.createElement('div');d.className='drag-chip';d.draggable=true;d.textContent=it.t;d.dataset.i=i;
d.ondragstart=e=>e.dataTransfer.setData('text/plain',i);tr.appendChild(d);});
document.getElementById('sc').textContent='Placed '+placed+' / '+items.length;}
function wire(id){const el=document.getElementById(id);
el.ondragover=e=>{e.preventDefault();el.classList.add('drag-over');};
el.ondragleave=()=>el.classList.remove('drag-over');
el.ondrop=e=>{e.preventDefault();el.classList.remove('drag-over');
const i=+e.dataTransfer.getData('text/plain');const it=items[i];if(it.p)return;
it.p=1;placed++;if(it.c===el.dataset.cat)good++;
const s=document.createElement('span');s.className='drag-chip in-bin';s.style.fontSize='0.95rem';s.textContent=it.t;el.appendChild(s);tray();
if(placed===items.length){const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add(good===items.length?'good':'bad');
fb.textContent=good===items.length?'Perfect!':'Score '+good+'/'+items.length+' — needs are essentials; wants are extras.';}};}
wire('bn');wire('bw');tray();""",
    )

    games["savings-simulator"] = page(
        "Fill the jar",
        """<h1>Coin drop</h1><p class="sub">Tap coins to fill the jar toward $120. Skip a week with Spend week.</p>
<div class="score" id="wk">Week 1 of 8</div>
<div class="jar-wrap"><div class="jar"><div class="jar-fill" id="jf"></div></div>
<p>$<span id="bal">0</span> / $120</p>
<div class="coin-pad"><button type="button" class="coin-btn" id="coin" title="Save $15">🪙</button>
<button class="btn btn-outline" id="sp">Spend week</button></div></div>
<div class="feedback hidden" id="fb"></div>""",
        """let week=1,bal=0;const goal=120,add=15,weeks=8;
function paint(){document.getElementById('wk').textContent='Week '+week+' of '+weeks;
document.getElementById('bal').textContent=bal;
document.getElementById('jf').style.height=Math.min(100,(bal/goal)*100)+'%';
if(week>weeks){const fb=document.getElementById('fb');fb.classList.remove('hidden');
fb.textContent=bal>=goal?'Jar filled — nice emergency starter!':'Jar at $'+bal+' — try more 🪙 taps next run.';
fb.classList.add(bal>=goal?'good':'bad');}}
document.getElementById('coin').onclick=()=>{if(week<=weeks){bal+=add;week++;paint();}};
document.getElementById('sp').onclick=()=>{if(week<=weeks){week++;paint();}};
paint();""",
    )

    games["market-maker"] = page(
        "Chart trader",
        """<h1>Live chart</h1><p class="sub">Bars = price each round. Trade $100 cash, 0 shares — 5 rounds.</p>
<div class="ticker" id="tk">FCX $10 · Cash $100 · Shares 0</div>
<div class="chart" id="ch"></div>
<div class="row"><button class="btn btn-primary" id="buy">Buy 1 📈</button>
<button class="btn btn-secondary" id="sell">Sell 1 📉</button>
<button class="btn btn-outline" id="hold">Hold ⏸</button></div>
<div class="feedback hidden" id="fb"></div>""",
        """let price=10,cash=100,sh=0,r=0;const hist=[10];
function rnd(){return Math.floor(Math.random()*5)-2;}
function bars(){const ch=document.getElementById('ch');ch.innerHTML='';
const mx=Math.max(...hist,12);hist.forEach(p=>{const b=document.createElement('div');b.className='chart-bar';b.style.height=(p/mx*100)+'%';ch.appendChild(b);});}
function render(){document.getElementById('tk').textContent='FCX $'+price+' · Cash $'+cash+' · Shares '+sh+' · R '+(r+1)+'/5';bars();}
function end(){const v=cash+sh*price;const fb=document.getElementById('fb');fb.classList.remove('hidden');
fb.textContent='Portfolio ≈ $'+v.toFixed(0)+(v>=100?' — steady hands!':' — bumpy tape');fb.classList.toggle('good',v>=100);r=99;}
function step(a){if(r>=5)return;if(a==='buy'&&cash>=price){cash-=price;sh++;}
else if(a==='sell'&&sh>0){cash+=price;sh--;}
price=Math.max(3,price+rnd());hist.push(price);r++;render();if(r>=5)end();}
document.getElementById('buy').onclick=()=>step('buy');
document.getElementById('sell').onclick=()=>step('sell');
document.getElementById('hold').onclick=()=>step('hold');
render();""",
    )

    games["credit-challenge"] = page(
        "Credit gauge",
        """<h1>Credit gauge</h1><p class="sub">Smart moves fill the bar. Start 680.</p>
<div class="score">Score <span id="score">680</span></div>
<div class="gauge-track"><div class="gauge-fill" id="gf"></div></div>
<div class="card" id="card"></div>""",
        """const qs=[{t:"Pay at least the minimum on time?",good:15,bad:-25},{t:"Open 3 new cards same week?",good:-35,bad:5},{t:"Keep card use under ~30% of limit?",good:20,bad:-15},{t:"Close your oldest card?",good:-30,bad:8},{t:"Check free credit report yearly?",good:10,bad:-5}];
let sc=680,i=0;
function bar(){document.getElementById('score').textContent=sc;
const w=Math.min(100,Math.max(6,(sc-300)/5.5));document.getElementById('gf').style.width=w+'%';}
function show(){if(i>=qs.length){document.getElementById('card').innerHTML='<p><strong>Final: '+sc+'</strong></p>';return;}
const q=qs[i];
document.getElementById('card').innerHTML='<p>'+q.t+'</p><div class="hero-pick"><button type="button" class="hero-tile" id="g">👍<small>Good move</small></button><button type="button" class="hero-tile" id="b">👎<small>Risky</small></button></div>';
document.getElementById('g').onclick=()=>{sc+=q.good;i++;bar();show();};
document.getElementById('b').onclick=()=>{sc+=q.bad;i++;bar();show();};}
bar();show();""",
    )

    games["compound-explorer"] = page(
        "Growth tower",
        """<h1>Stack the years</h1><p class="sub">Dial inputs, then grow a bar for each year of compounding.</p>
<label>Start $</label><input type="number" id="p" value="1000">
<label>Rate % / yr</label><input type="number" id="r" value="6">
<label>Years (max 12)</label><input type="number" id="t" value="8">
<label>Monthly add $</label><input type="number" id="m" value="40">
<button class="btn btn-primary" id="go" style="margin-top:8px">Grow tower</button>
<div class="tower" id="tw"></div>
<div class="feedback" id="out"></div>""",
        """document.getElementById('go').onclick=()=>{
let P=+document.getElementById('p').value||0;const yr=+document.getElementById('r').value/100||0;
const Y=Math.min(12,Math.max(1,+document.getElementById('t').value||1));const M=+document.getElementById('m').value||0;
const rm=yr/12;const tw=document.getElementById('tw');tw.innerHTML='';const vals=[];
for(let y=0;y<Y;y++){for(let k=0;k<12;k++)P=(P+M)*(1+rm);vals.push(P);}
const mx=Math.max(...vals,1);
vals.forEach(v=>{const layer=document.createElement('div');layer.className='tower-layer';layer.style.width=(28+72*(v/mx))+'%';tw.appendChild(layer);});
document.getElementById('out').textContent='After '+Y+' yrs ≈ $'+P.toFixed(0)+' — each block is a year-end balance (illustration).';};""",
    )

    games["portfolio-puzzle"] = page(
        "Pie shock",
        """<h1>Spin the mix</h1><p class="sub">Tap slices to tilt stocks vs bonds, then shock the market.</p>
<div class="pie-visual" id="pie"></div>
<div class="score" id="mixl">Stocks 60% · Bonds 40%</div>
<div class="match-grid-2">
<button type="button" class="pick-tile" id="st">📈 Stocks +10</button>
<button type="button" class="pick-tile" id="bd">📜 Bonds +10</button>
</div>
<button class="btn btn-primary" id="go" style="margin-top:8px">Random shock year</button>
<div class="feedback" id="out"></div>""",
        """let s=60,b=40;
function paint(){s=Math.min(90,Math.max(10,s));b=100-s;document.getElementById('mixl').textContent='Stocks '+s+'% · Bonds '+b+'%';
document.getElementById('pie').style.background='conic-gradient(#22c55e 0deg '+(s*3.6)+'deg, #64748b '+(s*3.6)+'deg 360deg)';}
document.getElementById('st').onclick=()=>{s+=10;b-=10;paint();};
document.getElementById('bd').onclick=()=>{b+=10;s-=10;paint();};
document.getElementById('go').onclick=()=>{
const sm=(Math.random()>.5?1:-1)*(8+Math.random()*14),bm=(Math.random()>.5?1:-1)*(1+Math.random()*2);
const ret=(s/100)*sm+(b/100)*bm;
document.getElementById('out').textContent='Stocks ~'+sm.toFixed(1)+'%, bonds ~'+bm.toFixed(1)+'%. Your pie returned about '+ret.toFixed(1)+'% this simulated year.';};
paint();""",
    )

    games["tax-type-match"] = page(
        "Tax memory",
        """<h1>Flip & match</h1><p class="sub">Find pairs: clue ↔ tax type (8 cards).</p>
<div class="score" id="sc">Matches: 0 / 4</div>
<div class="memory-grid" id="grid"></div>
<div class="feedback hidden" id="fb"></div>""",
        """const pairs=[["Soda receipt","Sales tax"],["Paystub withhold","Income tax"],["Home value bill","Property tax"],["FICA line","Payroll tax"]];
let cards=[],first=null,lock=false,matches=0;
function build(){cards=[];pairs.forEach(([a,b],i)=>{cards.push({id:i,t:a,side:'a'});cards.push({id:i,t:b,side:'b'});});
cards.sort(()=>Math.random()-.5);const g=document.getElementById('grid');g.innerHTML='';
cards.forEach((c,idx)=>{const w=document.createElement('div');w.className='flip-wrap perspective';w.dataset.idx=idx;
w.innerHTML='<div class="flip-inner"><div class="flip-face flip-front">?</div><div class="flip-face flip-back">'+c.t+'</div></div>';
w.onclick=()=>flip(w);g.appendChild(w);});}
function flip(w){if(lock||w.classList.contains('matched')||w.classList.contains('flipped'))return;
w.classList.add('flipped');const idx=+w.dataset.idx,c=cards[idx];
if(!first){first={w,c};return;}
lock=true;const a=first.c,b=c;if(a.id===b.id&&a.side!==b.side){matches++;w.classList.add('matched');first.w.classList.add('matched');
document.getElementById('sc').textContent='Matches: '+matches+' / 4';
if(matches===4){const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add('good');fb.textContent='All taxes matched!';}
first=null;lock=false;return;}
setTimeout(()=>{w.classList.remove('flipped');first.w.classList.remove('flipped');first=null;lock=false;},650);}
build();""",
    )

    games["insurance-pick"] = page(
        "Coverage drop",
        """<h1>Drop the shield</h1><p class="sub">Drag an icon onto the scenario that fits best.</p>
<div class="score" id="sc"></div>
<div class="chip-tray" id="tray"></div>
<div class="card" id="scene" style="min-height:92px"></div>
<div class="feedback hidden" id="fb"></div>""",
        """const rounds=[
{t:"🚗 Car crash you caused — which coverage?",ok:"Auto insurance"},
{t:"🏥 Broken arm on a hike — which coverage?",ok:"Health insurance"},
{t:"🏠 Stolen stuff in your rental — which?",ok:"Renters insurance"}];
const icons=[{i:"🚗",lab:"Auto insurance"},{i:"🏥",lab:"Health insurance"},{i:"🏠",lab:"Renters insurance"},{i:"🦽",lab:"Disability insurance"}];
let ri=0,score=0;
function scene(){if(ri>=rounds.length){document.getElementById('scene').innerHTML='<p><strong>Done!</strong> '+score+'/'+rounds.length+'</p>';document.getElementById('tray').innerHTML='';return;}
const r=rounds[ri];document.getElementById('sc').textContent='Round '+(ri+1)+' / '+rounds.length;
document.getElementById('scene').innerHTML='<p>'+r.t+'</p>';
document.getElementById('tray').innerHTML='';
icons.forEach(x=>{const d=document.createElement('div');d.className='drag-chip';d.draggable=true;d.textContent=x.i+' '+x.lab;
d.ondragstart=e=>e.dataTransfer.setData('text/plain',x.lab);document.getElementById('tray').appendChild(d);});
const z=document.getElementById('scene');
z.ondragover=e=>e.preventDefault();z.ondrop=e=>{e.preventDefault();const lab=e.dataTransfer.getData('text/plain');const fb=document.getElementById('fb');
fb.classList.remove('hidden');fb.classList.remove('good','bad');
if(lab===r.ok){score++;fb.classList.add('good');fb.textContent='Right shield!';ri++;setTimeout(()=>{fb.classList.add('hidden');scene();},420);}
else{fb.classList.add('bad');fb.textContent='Not the best fit — try another icon.';setTimeout(()=>fb.classList.add('hidden'),700);}};}
scene();""",
    )

    games["loan-compare"] = page(
        "Pick the card",
        """<h1>Tap the cheaper loan</h1><p class="sub">Same $3k / 24 mo — which tile is usually gentler on your wallet?</p>
<div class="hero-pick">
<button type="button" class="hero-tile" id="a">📄<small>Loan A<br>8% APR</small></button>
<button type="button" class="hero-tile" id="b">📄<small>Loan B<br>0% then 18%</small></button>
</div>
<div class="feedback hidden" id="fb"></div>""",
        """document.getElementById('a').onclick=()=>{const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add('good');
fb.textContent='Often yes — steady lower APR beats a teaser that jumps. Always read fees and the full amortization.';};
document.getElementById('b').onclick=()=>{const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add('bad');
fb.textContent='Promo 0% can cost more once the rate resets. Compare total interest paid, not just the first year.';};""",
    )

    games["crypto-myths"] = page(
        "Flip fact cards",
        """<h1>Flip, then answer</h1><p class="sub">Tap the card to read the claim, then True or False.</p>
<div class="score" id="sc"></div>
<div class="perspective" style="max-width:280px;margin:0 auto"><div class="flip-wrap" id="fw"><div class="flip-inner">
<div class="flip-face flip-front" id="ff">?</div>
<div class="flip-face flip-back" id="fbk"></div>
</div></div></div>
<div class="row" style="justify-content:center;margin-top:12px"><button class="btn btn-good" id="t">True</button><button class="btn btn-bad" id="f">False</button></div>
<div class="feedback hidden" id="out"></div>""",
        """const qs=[["Governments can trace many crypto flows",true],["Prices can swing wildly in a day",true],["FDIC covers crypto like a bank account",false],["Lost keys can mean lost coins forever",true],["“Guaranteed daily returns” is usually a scam",true]];
let i=0,s=0,flipped=false;
const fw=document.getElementById('fw');
function load(){flipped=false;fw.classList.remove('flipped');
if(i>=qs.length){document.getElementById('fbk').textContent='Done!';document.getElementById('ff').textContent='🏁';document.getElementById('sc').textContent='Score '+s+'/'+qs.length;return;}
document.getElementById('ff').textContent='Tap to flip';document.getElementById('fbk').textContent=qs[i][0];document.getElementById('sc').textContent='Card '+(i+1)+' / '+qs.length;}
fw.onclick=()=>{if(i>=qs.length)return;flipped=!flipped;fw.classList.toggle('flipped',flipped);};
document.getElementById('t').onclick=()=>{if(i>=qs.length||!flipped)return;if(qs[i][1])s++;i++;load();};
document.getElementById('f').onclick=()=>{if(i>=qs.length||!flipped)return;if(!qs[i][1])s++;i++;load();};
load();""",
    )

    games["profit-blitz"] = page(
        "Lemonade stacks",
        """<h1>Count the cups</h1><p class="sub">40 cups × $2 revenue. Costs shown as stacks.</p>
<div class="row" style="justify-content:center;gap:6px;flex-wrap:wrap;margin:10px 0" id="cups"></div>
<div class="score">Variable cost stack (40 × $0.40)</div>
<div class="row" style="justify-content:center;gap:4px;flex-wrap:wrap" id="varc"></div>
<div class="score" style="margin-top:8px">Fixed: sign $15</div>
<button class="btn btn-primary" id="go">Reveal profit bar</button>
<div class="bar" style="height:14px;margin-top:10px"><i id="bar" style="width:0%"></i></div>
<div class="feedback hidden" id="out"></div>""",
        """for(let k=0;k<12;k++){const d=document.createElement('div');d.className='pick-tile';d.style.width='36px';d.style.height='44px';d.style.fontSize='1.1rem';d.textContent='🥤';document.getElementById('cups').appendChild(d);}
for(let k=0;k<8;k++){const d=document.createElement('div');d.className='pick-tile';d.style.width='32px';d.style.height='32px';d.style.fontSize='0.9rem';d.textContent='🪙';document.getElementById('varc').appendChild(d);}
document.getElementById('go').onclick=()=>{const rev=80,vc=16,fx=15,p=rev-vc-fx;
document.getElementById('bar').style.width='100%';const o=document.getElementById('out');o.classList.remove('hidden');
o.textContent='Revenue $'+rev+' − variable $'+vc+' − fixed $'+fx+' = profit $'+p+'.';};""",
    )

    games["emergency-steps"] = page(
        "Reorder the ladder",
        """<h1>Drag into order</h1><p class="sub">Top = do first. Goal: track → goal → automate → rules.</p>
<div class="sort-list" id="lst"></div>
<button class="btn btn-primary" id="chk" style="margin-top:10px">Check order</button>
<div class="feedback hidden" id="fb"></div>""",
        """const ideal=["Track spending for 2 weeks","Set a starter goal (~$500)","Automate savings transfer","Emergencies only"];
let items=ideal.slice().sort(()=>Math.random()-.5);let drag=null;
function paint(){const lst=document.getElementById('lst');lst.innerHTML='';
items.forEach((t,idx)=>{const d=document.createElement('div');d.className='sort-item';d.draggable=true;d.textContent=(idx+1)+'. '+t;d.dataset.idx=idx;
d.ondragstart=()=>{drag=idx;d.classList.add('dragging');};
d.ondragend=()=>d.classList.remove('dragging');
d.ondragover=e=>e.preventDefault();
d.ondrop=()=>{if(drag===null)return;const to=+d.dataset.idx;const x=items.splice(drag,1)[0];items.splice(to,0,x);drag=null;paint();};
lst.appendChild(d);});}
document.getElementById('chk').onclick=()=>{const ok=items.every((t,i)=>t===ideal[i]);const fb=document.getElementById('fb');fb.classList.remove('hidden');
fb.classList.add(ok?'good':'bad');fb.textContent=ok?'Perfect ladder!':'Not quite — try: track, goal, automate, rules.';};
paint();""",
    )

    games["paycheck-puzzle"] = page(
        "Match stubs",
        """<h1>Icon ↔ label</h1><p class="sub">Pick one emoji tile, then one definition — make 4 pairs.</p>
<div class="score" id="sc">Pairs: 0 / 4</div>
<div class="match-grid-2" id="left"></div>
<div class="match-grid-2" id="right"></div>
<div class="feedback hidden" id="fb"></div>""",
        """const left=[{k:0,g:'💵',t:'Gross pay'},{k:1,g:'🏛️',t:'Income tax withheld'},{k:2,g:'🧾',t:'FICA / payroll taxes'},{k:3,g:'✅',t:'Net pay'}];
const right=[{k:0,d:'Before taxes'},{k:1,d:'Federal withholding'},{k:2,d:'Social Security / Medicare'},{k:3,d:'Deposited to you'}];
let selL=null,selR=null,pairs=0;const matched=new Set();
function shuf(a){return a.slice().sort(()=>Math.random()-.5);}
function draw(){document.getElementById('left').innerHTML='';document.getElementById('right').innerHTML='';
shuf(left.filter(x=>!matched.has(x.k))).forEach(x=>{const b=document.createElement('button');b.type='button';b.className='pick-tile';b.textContent=x.g;b.dataset.k=x.k;
b.onclick=()=>{document.querySelectorAll('#left .pick-tile').forEach(z=>z.classList.remove('on'));b.classList.add('on');selL=x.k;tryPair();};document.getElementById('left').appendChild(b);});
shuf(right.filter(x=>!matched.has(x.k))).forEach(x=>{const b=document.createElement('button');b.type='button';b.className='pick-tile';b.style.fontSize='0.78rem';b.textContent=x.d;b.dataset.k=x.k;
b.onclick=()=>{document.querySelectorAll('#right .pick-tile').forEach(z=>z.classList.remove('on'));b.classList.add('on');selR=x.k;tryPair();};document.getElementById('right').appendChild(b);});}
function tryPair(){if(selL===null||selR===null||selL!==selR)return;
matched.add(selL);pairs++;selL=selR=null;document.getElementById('sc').textContent='Pairs: '+pairs+' / 4';
if(pairs===4){const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add('good');fb.textContent='Paycheck decoded!';}
else draw();}
draw();""",
    )

    games["opportunity-cost"] = page(
        "Pick a chest",
        """<h1>Two paths</h1><p class="sub">$200 — tap a chest to see the tradeoff.</p>
<div class="hero-pick">
<button type="button" class="hero-tile" id="a">🎵<small>Concert<br>$200</small></button>
<button type="button" class="hero-tile" id="b">💻<small>Laptop fund<br>$200</small></button>
</div>
<div class="feedback hidden" id="out"></div>""",
        """document.getElementById('a').onclick=()=>{const o=document.getElementById('out');o.classList.remove('hidden');o.textContent='Great memories — opportunity cost: $200 not growing toward the laptop + missed interest.';};
document.getElementById('b').onclick=()=>{const o=document.getElementById('out');o.classList.remove('hidden');o.textContent='Closer to the laptop — opportunity cost: skipping the concert vibe this month.';};""",
    )

    games["rule-of-72"] = page(
        "Spin the dial",
        """<h1>Rule of 72 dial</h1><p class="sub">Slide rate — dial shows rough years to double.</p>
<label>Interest rate %</label><input type="range" id="r" min="1" max="15" value="6">
<div class="score">Years to double ≈ <span id="y">12.0</span></div>
<div style="width:min(220px,100%);height:120px;margin:10px auto;position:relative">
<div id="dial" style="position:absolute;left:50%;bottom:0;width:120px;height:120px;margin-left:-60px;border-radius:50%;border:10px solid #e2e8f0;border-top-color:var(--gold);transform:rotate(-72deg);transition:transform .25s"></div>
</div>
<div class="feedback" id="out"></div>""",
        """const r=document.getElementById('r'),d=document.getElementById('dial');
function upd(){const rv=+r.value||1;const y=72/rv;document.getElementById('y').textContent=y.toFixed(1);
d.style.transform='rotate('+(-90+rv*6)+'deg)';
document.getElementById('out').textContent='Approx doubling: 72 ÷ '+rv+' ≈ '+y.toFixed(1)+' years (rule of thumb).';}
r.oninput=upd;upd();""",
    )

    games["debt-strategy"] = page(
        "Three doors",
        """<h1>Open a door</h1><p class="sub">Flip a door, then pick the best real strategy for the prompt.</p>
<div class="score" id="pr"></div>
<div class="door-row" id="doors"></div>
<div class="row" style="justify-content:center;margin-top:8px"><button class="btn btn-outline" id="av">Choose Avalanche</button>
<button class="btn btn-outline" id="sn">Choose Snowball</button><button class="btn btn-outline" id="no">Choose “Bad idea”</button></div>
<div class="feedback hidden" id="fb"></div>""",
        """const rounds=[
{t:"Pay highest APR first while paying minimums elsewhere",ok:"av"},
{t:"Smallest balance first for quick wins",ok:"sn"},
{t:"Ignore bills until you feel like it",ok:"no"}];
const labels=["Avalanche","Snowball","Bad idea"];let ri=0,score=0;
function doors(){document.getElementById('pr').textContent=rounds[ri].t;
document.getElementById('doors').innerHTML=labels.map((L,i)=>'<div class="door" data-i="'+i+'"><div class="door-inner"><div class="door-face door-front">?</div><div class="door-face door-back">'+L+'</div></div></div>').join('');
[...document.querySelectorAll('.door')].forEach(d=>d.onclick=()=>d.classList.toggle('flipped'));}
function pick(id){const ok=rounds[ri].ok===id;const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add(ok?'good':'bad');
if(ok)score++;fb.textContent=ok?'Yes!':'Review avalanche vs snowball — both can work; ignoring bills does not.';
ri++;if(ri>=rounds.length){fb.textContent='Finished — '+score+'/'+rounds.length+' correct.';['av','sn','no'].forEach(x=>document.getElementById(x).disabled=true);return;}
doors();}
document.getElementById('av').onclick=()=>pick('av');
document.getElementById('sn').onclick=()=>pick('sn');
document.getElementById('no').onclick=()=>pick('no');
doors();""",
    )

    games["inflation-shop"] = page(
        "Price tag flip",
        """<h1>Milk on the shelf</h1><p class="sub">Today $4. Tap the tag to roll 10 years at ~3% inflation.</p>
<div class="shop-shelf">
<div class="milk-carton"></div>
<button type="button" class="price-tag" id="tag">$4.00</button>
</div>
<div class="feedback hidden" id="out"></div>""",
        """let flipped=false;
document.getElementById('tag').onclick=()=>{const p=4*Math.pow(1.03,10);flipped=!flipped;
document.getElementById('tag').textContent=flipped?('$'+p.toFixed(2)):'$4.00';
const o=document.getElementById('out');o.classList.remove('hidden');
o.textContent=flipped?'Future tag (illustration) — investing aims to beat inflation over long horizons.':'Today’s sticker price.';};""",
    )

    games["goal-ranker"] = page(
        "Podium drag",
        """<h1>Build the podium</h1><p class="sub">Drag tiles onto 🥇 🥈 🥉 slots — most urgent first.</p>
<div class="row" style="gap:10px;flex-wrap:wrap;margin-bottom:8px">
<div class="drop-bin" id="p0" style="min-height:76px;flex:1"><h3>🥇 1st</h3></div>
<div class="drop-bin" id="p1" style="min-height:76px;flex:1"><h3>🥈 2nd</h3></div>
<div class="drop-bin" id="p2" style="min-height:76px;flex:1"><h3>🥉 3rd</h3></div>
</div>
<div class="chip-tray" id="tray"></div>
<button class="btn btn-primary" id="go">Score podium</button>
<div class="feedback hidden" id="fb"></div>""",
        """const goals=["Past-due bill","Starter emergency fund","401(k) match","Vacation"];const ideal=["Past-due bill","Starter emergency fund","401(k) match"];
const heads=["🥇 1st","🥈 2nd","🥉 3rd"];let slots=["","",""];let pool=goals.slice().sort(()=>Math.random()-.5);
function tray(){const t=document.getElementById('tray');t.innerHTML='';
pool.forEach(g=>{const d=document.createElement('div');d.className='drag-chip';d.draggable=true;d.textContent=g;
d.ondragstart=e=>e.dataTransfer.setData('text/plain',g);t.appendChild(d);});}
function wire(id,rk){const el=document.getElementById(id);
el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();if(slots[rk])return;const g=e.dataTransfer.getData('text/plain');
if(!pool.includes(g))return;slots[rk]=g;pool=pool.filter(x=>x!==g);el.innerHTML='<h3>'+heads[rk]+'</h3><span class="drag-chip in-bin" style="font-size:0.72rem">'+g+'</span>';tray();};}
wire('p0',0);wire('p1',1);wire('p2',2);tray();
document.getElementById('go').onclick=()=>{let pts=0;ideal.forEach((g,i)=>{if(slots[i]===g)pts++;});
const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add(pts>=2?'good':'bad');
fb.textContent=pts+'/3 match the sample priority (your life may differ).';};""",
    )

    games["scam-spotter"] = page(
        "SMS red flags",
        """<h1>Spot the scams</h1><p class="sub">Tap the sketchy phrases inside the message (3 hits).</p>
<div class="scam-screen" id="msg"></div>
<div class="score" id="sc">Flags: 0 / 3</div>""",
        """const parts=[
{t:'Hi — ',ok:false},{t:'URGENT: account deleted in 1 hr',ok:true},{t:' — click ',ok:false},{t:'verify SSN here',ok:true},{t:' — also ',ok:false},{t:'wire gift cards for refund',ok:true},{t:' — thanks',ok:false}];
let hits=0;
document.getElementById('msg').innerHTML=parts.map((p,i)=>'<span class="'+(p.ok?'scam-hotspot':'')+'" data-i="'+i+'">'+p.t+'</span>').join('');
document.getElementById('msg').onclick=e=>{const s=e.target.closest('.scam-hotspot');if(!s||s.classList.contains('found'))return;
const i=+s.dataset.i;if(!parts[i].ok)return;s.classList.add('found');hits++;document.getElementById('sc').textContent='Flags: '+hits+' / 3';};""",
    )

    games["side-hustle-balance"] = page(
        "Seesaw hours",
        """<h1>Balance the hustle</h1><p class="sub">Slide gig hours — plank tilts with load.</p>
<label>Gig hours / week: <span id="v">5</span></label>
<input type="range" id="h" min="0" max="25" value="5">
<div class="seesaw-wrap"><div class="seesaw-plank" id="pl"></div><div class="seesaw-fulcrum"></div></div>
<div class="feedback" id="out"></div>""",
        """const el=document.getElementById('h'),pl=document.getElementById('pl');
function upd(){const g=+el.value;document.getElementById('v').textContent=g;
pl.style.transform='rotate('+(g-5)*2.2+'deg)';
document.getElementById('out').textContent=g>15?'Plank tips hard — protect sleep and school.':g>0?'Light tilt — small gigs can fund goals.':'All study time — also valuable.';}
el.oninput=upd;upd();""",
    )

    games["wants-needs-speed"] = page(
        "Pop quiz",
        """<h1>Pop-up sort</h1><p class="sub">Tap the floating tile: Need 🏠 or Want ✨ before it vanishes.</p>
<div class="score" id="sc"></div>
<div class="pop-area" id="pop"></div>
<div class="row" style="justify-content:center"><button class="btn btn-good" id="n">Need</button><button class="btn btn-bad" id="w">Want</button></div>
<div class="feedback" id="fb"></div>""",
        """const items=[["🍎 Lunch",true],["🎮 Skin",false],["💡 Electric bill",true],["🎟️ VIP tickets",false],["📚 Class book",true],["☕ Fancy latte habit",false]];
let i=0,s=0,timer=null,cur=null;
function spawn(){clearTimeout(timer);const p=document.getElementById('pop');p.innerHTML='';
if(i>=items.length){document.getElementById('fb').textContent='Final score '+s+' / '+items.length;return;}
cur=items[i];
const el=document.createElement('div');el.className='pop-target';el.textContent=cur[0].split(' ')[0];
el.style.left=(10+Math.random()*58)+'%';el.style.top=(12+Math.random()*40)+'%';p.appendChild(el);
document.getElementById('sc').textContent='Round '+(i+1)+' / '+items.length+' — tap Need or Want';
timer=setTimeout(()=>{document.getElementById('sc').textContent='Missed!';i++;spawn();},2000);}
function grade(need){clearTimeout(timer);if(i>=items.length||!cur)return;const ok=(need===cur[1]);if(ok)s++;
i++;document.getElementById('sc').textContent=ok?'Nice!':'Not quite';spawn();}
document.getElementById('n').onclick=()=>grade(true);
document.getElementById('w').onclick=()=>grade(false);
spawn();""",
    )

    games["pay-yourself-first"] = page(
        "Split tubes",
        """<h1>Two tubes</h1><p class="sub">Slide savings % — watch the tubes fill.</p>
<label>Pay yourself first: <span id="svl">10</span>%</label>
<input type="range" id="s" min="0" max="30" value="10">
<div class="split-tubes">
<div class="tube"><div class="tube-fill save" id="fs"></div></div>
<div class="tube"><div class="tube-fill spend" id="fp"></div></div>
</div>
<div class="score">Save tube · Spend tube</div>
<div class="feedback" id="o"></div>""",
        """document.getElementById('s').oninput=()=>{const sv=+document.getElementById('s').value;document.getElementById('svl').textContent=sv;
document.getElementById('fs').style.height=sv*3.2+'%';document.getElementById('fp').style.height=(100-sv)*3.2+'%';
document.getElementById('o').textContent=sv>=10?'Strong habit shape.':sv>0?'Every % trains the reflex.':'Try 1–2% to start.';};
document.getElementById('s').dispatchEvent(new Event('input'));""",
    )

    games["entrepreneur-margin"] = page(
        "Block margin",
        """<h1>Subtract blocks</h1><p class="sub">Green = $3 price · Red = $1.20 cost per sticker.</p>
<div class="row" style="justify-content:center;gap:4px;flex-wrap:wrap;margin:10px 0" id="rev"></div>
<div class="row" style="justify-content:center;gap:4px;flex-wrap:wrap;margin:10px 0" id="cost"></div>
<button class="btn btn-primary" id="go">Show what’s left</button>
<div class="feedback hidden" id="o"></div>""",
        """for(let i=0;i<6;i++){const d=document.createElement('div');d.style.width='34px';d.style.height='34px';d.style.borderRadius='6px';d.style.background='#22c55e';d.textContent='$';d.style.display='flex';d.style.alignItems='center';d.style.justifyContent='center';d.style.color='#fff';d.style.fontWeight='800';document.getElementById('rev').appendChild(d);}
for(let i=0;i<3;i++){const d=document.createElement('div');d.style.width='40px';d.style.height='24px';d.style.borderRadius='6px';d.style.background='#e53e3e';document.getElementById('cost').appendChild(d);}
document.getElementById('go').onclick=()=>{const m=3-1.2;document.getElementById('o').classList.remove('hidden');
document.getElementById('o').textContent='Gross margin ≈ $'+m.toFixed(2)+' each — still add time + other costs.';};""",
    )

    games["scholarship-hunt"] = page(
        "Aid memory",
        """<h1>Match aid types</h1><p class="sub">Flip two cards; pair the phrase with the right label.</p>
<div class="score" id="sc">Pairs: 0 / 4</div>
<div class="memory-grid" id="grid"></div>
<div class="feedback hidden" id="fb"></div>""",
        """const pairs=[["Gift aid you keep if eligible","Grant / scholarship"],["Borrowed money + interest","Student loan"],["FAFSA helps assess federal need aid","FAFSA form"],["Must repay on a schedule","Loan repayment"]];
let cards=[],first=null,lock=false,matches=0;
function build(){cards=[];pairs.forEach(([a,b],i)=>{cards.push({id:i,t:a});cards.push({id:i,t:b});});cards.sort(()=>Math.random()-.5);
const g=document.getElementById('grid');g.innerHTML='';
cards.forEach((c,idx)=>{const w=document.createElement('div');w.className='flip-wrap perspective';w.dataset.idx=idx;
w.innerHTML='<div class="flip-inner"><div class="flip-face flip-front">?</div><div class="flip-face flip-back" style="font-size:0.68rem">'+c.t+'</div></div>';
w.onclick=()=>flip(w);g.appendChild(w);});}
function flip(w){if(lock||w.classList.contains('matched')||w.classList.contains('flipped'))return;w.classList.add('flipped');
const idx=+w.dataset.idx,c=cards[idx];if(!first){first={w,c};return;}lock=true;const a=first.c,b=c;
if(a.id===b.id&&a.t!==b.t){matches++;w.classList.add('matched');first.w.classList.add('matched');document.getElementById('sc').textContent='Pairs: '+matches+' / 4';
if(matches===4){const fb=document.getElementById('fb');fb.classList.remove('hidden');fb.classList.add('good');fb.textContent='Financial aid pairs locked in!';}
first=null;lock=false;return;}
setTimeout(()=>{w.classList.remove('flipped');first.w.classList.remove('flipped');first=null;lock=false;},650);}
build();""",
    )

    games["budget-percent"] = page(
        "Live pie",
        """<h1>Paint the pie</h1><p class="sub">You earn $400/mo in this drill. Slide the three slices.</p>
<label>Needs $<span id="nv">200</span></label><input type="range" id="n" min="0" max="400" value="200">
<label>Wants $<span id="wv">120</span></label><input type="range" id="w" min="0" max="400" value="120">
<label>Savings $<span id="sv">80</span></label><input type="range" id="s" min="0" max="400" value="80">
<div class="pie-visual" id="pie"></div>
<div class="feedback" id="o"></div>""",
        """function paint(){const n=+document.getElementById('n').value,w=+document.getElementById('w').value,s=+document.getElementById('s').value,t=n+w+s||1;
document.getElementById('nv').textContent=n;document.getElementById('wv').textContent=w;document.getElementById('sv').textContent=s;
const N=n/t*360,W=w/t*360;document.getElementById('pie').style.background='conic-gradient(#22c55e 0deg '+(N)+'deg, #f5a623 '+(N)+'deg '+(N+W)+'deg, #64748b '+(N+W)+'deg 360deg)';
document.getElementById('o').textContent='Needs '+(n/t*100).toFixed(0)+'%, wants '+(w/t*100).toFixed(0)+'%, save '+(s/t*100).toFixed(0)+'%. 50/30/20 is a starting template.';}
['n','w','s'].forEach(id=>document.getElementById(id).oninput=paint);paint();""",
    )

    games["risk-vs-return"] = page(
        "Climb the ladder",
        """<h1>Risk ladder</h1><p class="sub">Tap rungs low → high typical risk (5 steps).</p>
<div class="ladder" id="ld"></div>
<div class="score" id="sc"></div>""",
        """const items=["🏦 Savings","📜 Bonds","📊 Index fund","🎯 One stock","🎲 Speculative crypto"];
const order=[0,1,2,3,4];let step=0;
document.getElementById('ld').innerHTML=items.map((t,i)=>'<button type="button" class="ladder-rung" data-i="'+i+'">'+t+'</button>').join('');
[...document.querySelectorAll('.ladder-rung')].forEach(b=>b.onclick=()=>{const i=+b.dataset.i;if(b.classList.contains('done'))return;
if(i!==order[step]){b.classList.add('wrong');setTimeout(()=>b.classList.remove('wrong'),400);document.getElementById('sc').textContent='Start with the safest rung.';return;}
b.classList.add('done');step++;document.getElementById('sc').textContent='Rung '+step+' / 5';
if(step===5)document.getElementById('sc').textContent='Top! Risk tends to rise with potential return — not guaranteed.';});""",
    )

    game_templates = Path(__file__).resolve().parent / "game_templates"
    for slug in ("founder-floor-rush", "aid-maze-duo", "expense-tracker-showdown"):
        tpl = game_templates / f"{slug}.html"
        games[slug] = tpl.read_text(encoding="utf-8")

    for slug, html in games.items():
        dest = HERE / slug
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "index.html").write_text(html, encoding="utf-8")

    meta = [{"slug": s, "bytes": len(h)} for s, h in games.items()]
    print("Wrote", len(games), "games:", ", ".join(sorted(games.keys())))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
