/* 手寫 SVG 圖表。刻意不引入任何外部函式庫——會議室網路擋掉 CDN 時，
   圖表全白比圖表樸素嚴重得多。整份網站零外部請求。 */
const C = {
  ink:'#222E36', mute:'#6B7A83', line:'#D8DEDC', grid:'#EDF0EF',
  navy:'#1B3A57', chill:'#0F6E78', amber:'#D9772F', frost:'#3D5A98',
  alert:'#B23A34', good:'#2E7D5B'
};
const ZONE = {'冷藏':C.chill, '常溫':C.amber, '冷凍':C.frost};

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = (n, d=0) => Number(n).toLocaleString('zh-TW',
  {minimumFractionDigits:d, maximumFractionDigits:d});
const el = (id) => document.getElementById(id);

function svg(w, h, body, extra='', surface='dark') {
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet"
    font-family="var(--sans)" data-surface="${surface}" ${extra}>${body}</svg>`;
}
function txt(x, y, s, o={}) {
  return `<text x="${x}" y="${y}" font-size="${o.size||11}"
    fill="${o.fill||C.mute}" text-anchor="${o.anchor||'start'}"
    font-weight="${o.weight||400}"
    ${o.mono?'font-family="var(--mono)"':''}>${esc(s)}</text>`;
}
function tip(t) { return `<title>${esc(t)}</title>`; }

/* ── 橫條圖 ───────────────────────────────────────── */
function hbar(rows, o={}) {
  const w = o.w||660, padL = o.padL||132, padR = o.padR||o.labelRight?150:46,
        rowH = o.rowH||26, top = 14;
  const h = top + rows.length*rowH + 26;
  const max = Math.max(...rows.map(r=>r.v), o.min||0) * 1.02 || 1;
  const sx = v => padL + (w-padL-padR) * (v/max);
  let b = '';
  for (let g=0; g<=4; g++) {
    const x = padL + (w-padL-padR)*g/4;
    b += `<line x1="${x}" y1="${top}" x2="${x}" y2="${top+rows.length*rowH}"
      stroke="${C.grid}"/>` +
      txt(x, top+rows.length*rowH+16, fmt(max*g/4, o.dec||0), {anchor:'middle', size:10});
  }
  rows.forEach((r,i)=>{
    const y = top + i*rowH + 4, bh = rowH-9;
    b += txt(padL-8, y+bh-3, r.k, {anchor:'end', size:11, fill:C.ink});
    b += `<rect x="${padL}" y="${y}" width="${Math.max(1,sx(r.v)-padL)}" height="${bh}"
      fill="${r.c||C.chill}" rx="1">${tip(`${r.k}　${fmt(r.v,o.dec||0)}`)}</rect>`;
    if (r.right) b += txt(sx(r.v)+7, y+bh-3, r.right, {size:10});
    else if (o.showVal!==false) b += txt(sx(r.v)+7, y+bh-3, fmt(r.v,o.dec||0), {size:10, mono:1});
  });
  return svg(w, h, b);
}

/* ── 散佈圖 ───────────────────────────────────────── */
function scatter(pts, o={}) {
  const w=o.w||620, h=o.h||400, p={l:58,r:18,t:16,b:44};
  const xs=pts.map(d=>d.x), ys=pts.map(d=>d.y);
  const x0=o.x0??Math.min(...xs), x1=o.x1??Math.max(...xs);
  const y0=o.y0??Math.min(...ys), y1=o.y1??Math.max(...ys);
  const X=v=>p.l+(w-p.l-p.r)*(v-x0)/((x1-x0)||1);
  const Y=v=>h-p.b-(h-p.t-p.b)*(v-y0)/((y1-y0)||1);
  const bubbles=pts.map(d=>({x:X(d.x),y:Y(d.y),r:d.r||5}));
  const labelBoxes=[];
  const hit=(a,z,pad=3)=>a.l<z.r+pad&&a.r>z.l-pad&&a.t<z.b+pad&&a.b>z.t-pad;
  const hitsBubble=(box,bubble,pad=4)=>{
    const cx=Math.max(box.l,Math.min(bubble.x,box.r));
    const cy=Math.max(box.t,Math.min(bubble.y,box.b));
    return (bubble.x-cx)**2+(bubble.y-cy)**2<(bubble.r+pad)**2;
  };
  const labelWidth=s=>Array.from(String(s)).reduce((n,ch)=>
    n+(/[ -~]/.test(ch)?6.2:10.4),0);
  const labelBox=(x,y,anchor,width)=>({
    l:anchor==='middle'?x-width/2:anchor==='end'?x-width:x,
    r:anchor==='middle'?x+width/2:anchor==='end'?x:x+width,
    t:y-11,b:y+3
  });
  const placeLabel=(d,i)=>{
    const x=bubbles[i].x, y=bubbles[i].y, r=bubbles[i].r;
    const width=labelWidth(d.label);
    const candidates=[
      {x,y:y-r-8,anchor:'middle'},
      {x:x+r+9,y:y+4,anchor:'start'},
      {x:x-r-9,y:y+4,anchor:'end'},
      {x,y:y+r+17,anchor:'middle'},
      {x:x+r*.7+7,y:y-r*.7-6,anchor:'start'},
      {x:x-r*.7-7,y:y-r*.7-6,anchor:'end'},
      {x:x+r*.7+7,y:y+r*.7+10,anchor:'start'},
      {x:x-r*.7-7,y:y+r*.7+10,anchor:'end'},
    ];
    for(const candidate of candidates){
      const box=labelBox(candidate.x,candidate.y,candidate.anchor,width);
      const inside=box.l>=p.l+2&&box.r<=w-p.r-2&&box.t>=p.t+2&&box.b<=h-p.b-2;
      const clearLabels=!labelBoxes.some(other=>hit(box,other));
      const clearBubbles=!bubbles.some(bubble=>hitsBubble(box,bubble));
      if(inside&&clearLabels&&clearBubbles){
        labelBoxes.push(box);
        return candidate;
      }
    }
    const fallback=candidates[0], box=labelBox(fallback.x,fallback.y,fallback.anchor,width);
    labelBoxes.push(box);
    return fallback;
  };
  let b='';
  for(let g=0;g<=4;g++){
    const yy=p.t+(h-p.t-p.b)*g/4, vv=y1-(y1-y0)*g/4;
    b+=`<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="${C.grid}"/>`
      + txt(p.l-7, yy+4, fmt(vv,o.ydec||0), {anchor:'end', size:10});
    const xx=p.l+(w-p.l-p.r)*g/4, xv=x0+(x1-x0)*g/4;
    b+=txt(xx, h-p.b+17, fmt(xv,o.xdec||0), {anchor:'middle', size:10});
  }
  if(o.diag) b+=`<line x1="${X(x0)}" y1="${Y(x0)}" x2="${X(Math.min(x1,y1))}"
    y2="${Y(Math.min(x1,y1))}" stroke="${C.line}" stroke-dasharray="4 3"/>`;
  if(o.vline!==undefined) b+=`<line x1="${X(o.vline)}" y1="${p.t}" x2="${X(o.vline)}"
    y2="${h-p.b}" stroke="${C.mute}" stroke-dasharray="3 3"/>`;
  pts.forEach((d,i)=>{
    b+=`<circle cx="${bubbles[i].x}" cy="${bubbles[i].y}" r="${bubbles[i].r}" fill="${d.c||C.chill}"
      fill-opacity="${d.o??.75}" stroke="#fff" stroke-width="1">${tip(d.t||'')}</circle>`;
  });
  pts.forEach((d,i)=>{
    if(!d.label) return;
    const label=placeLabel(d,i);
    b+=txt(label.x,label.y,d.label,{anchor:label.anchor,size:10,fill:C.ink});
  });
  b+=txt(w/2, h-6, o.xlab||'', {anchor:'middle', size:11});
  b+=`<text x="14" y="${h/2}" font-size="11" fill="${C.mute}" text-anchor="middle"
    transform="rotate(-90 14 ${h/2})">${esc(o.ylab||'')}</text>`;
  return svg(w,h,b);
}

/* ── 折線圖（可帶區間帶） ─────────────────────────── */
function lineChart(series, o={}) {
  const w=o.w||660, h=o.h||330, p={l:52,r:16,t:14,b:40};
  const labels=o.labels||[];
  const all=series.flatMap(s=>s.pts.flatMap(d=>[d.y, d.lo, d.hi].filter(v=>v!=null)));
  const y0=o.y0??Math.min(...all)*.92, y1=o.y1??Math.max(...all)*1.06;
  const n=labels.length||Math.max(...series.map(s=>s.pts.length));
  const X=i=>p.l+(w-p.l-p.r)*(n<2?0.5:i/(n-1));
  const Y=v=>h-p.b-(h-p.t-p.b)*(v-y0)/((y1-y0)||1);
  let b='';
  for(let g=0;g<=4;g++){
    const yy=p.t+(h-p.t-p.b)*g/4;
    b+=`<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="${C.grid}"/>`
      + txt(p.l-7, yy+4, fmt(y1-(y1-y0)*g/4), {anchor:'end', size:10});
  }
  const step=Math.ceil(n/8);
  labels.forEach((L,i)=>{ if(i%step===0) b+=txt(X(i), h-p.b+16, L, {anchor:'middle', size:9}); });
  series.forEach(s=>{
    const idx=d=>labels.length?labels.indexOf(d.d):s.pts.indexOf(d);
    if(s.band){
      const up=s.pts.filter(d=>d.hi!=null).map(d=>`${X(idx(d))},${Y(d.hi)}`);
      const dn=s.pts.filter(d=>d.lo!=null).reverse().map(d=>`${X(idx(d))},${Y(d.lo)}`);
      if(up.length) b+=`<polygon points="${up.concat(dn).join(' ')}" fill="${s.c}"
        fill-opacity=".13"/>`;
    }
    const pts=s.pts.filter(d=>d.y!=null);
    b+=`<polyline points="${pts.map(d=>`${X(idx(d))},${Y(d.y)}`).join(' ')}"
      fill="none" stroke="${s.c}" stroke-width="${s.w||2}"
      ${s.dash?'stroke-dasharray="5 4"':''}/>`;
    if(s.dots!==false) pts.forEach(d=>{
      b+=`<circle cx="${X(idx(d))}" cy="${Y(d.y)}" r="3.2" fill="${s.c}">
        ${tip(`${d.d}　${fmt(d.y,1)}`)}</circle>`; });
  });
  return svg(w,h,b);
}

/* ── 直方圖 ───────────────────────────────────────── */
function histogram(vals, o={}) {
  const w=o.w||620, h=o.h||280, p={l:52,r:16,t:14,b:38}, bins=o.bins||30;
  const lo=o.lo??Math.min(...vals), hi=o.hi??Math.max(...vals);
  const cnt=new Array(bins).fill(0);
  vals.forEach(v=>{ let i=Math.floor((v-lo)/((hi-lo)||1)*bins); i=Math.min(bins-1,Math.max(0,i)); cnt[i]++; });
  const max=Math.max(...cnt)||1;
  let b='';
  for(let g=0;g<=4;g++){
    const yy=p.t+(h-p.t-p.b)*g/4;
    b+=`<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="${C.grid}"/>`
      +txt(p.l-7,yy+4,fmt(max-max*g/4),{anchor:'end',size:10});
  }
  const bw=(w-p.l-p.r)/bins;
  cnt.forEach((c,i)=>{
    const bh=(h-p.t-p.b)*c/max;
    b+=`<rect x="${p.l+i*bw+.5}" y="${h-p.b-bh}" width="${bw-1}" height="${bh}"
      fill="${o.c||C.chill}">${tip(`${fmt(lo+(hi-lo)*i/bins,2)}–${fmt(lo+(hi-lo)*(i+1)/bins,2)}　${c} 位`)}</rect>`;
  });
  for(let g=0;g<=4;g++) b+=txt(p.l+(w-p.l-p.r)*g/4, h-p.b+16, fmt(lo+(hi-lo)*g/4,2), {anchor:'middle',size:10});
  return svg(w,h,b);
}

/* ── 混淆矩陣 ─────────────────────────────────────── */
function confusion(m, o={}) {
  const w=o.w||430, h=250, cw=(w-110)/2, ch=78;
  const cells=[
    {r:0,c:0,k:'TN 正確判留',v:m.TN,note:'沒花錢，客人也真的留',col:'#EEF2F1',fg:C.ink},
    {r:0,c:1,k:'FP 誤判流失',v:m.FP,note:'白打的電話',col:'#FBEFE6',fg:C.amber},
    {r:1,c:0,k:'FN 漏掉流失',v:m.FN,note:'生意丟了',col:'#F8E9E8',fg:C.alert},
    {r:1,c:1,k:'TP 正確攔截',v:m.TP,note:'提早預警',col:'#E8F1ED',fg:C.good},
  ];
  let b=txt(110+cw, 16, '模型判斷', {anchor:'middle', size:11, weight:600, fill:C.ink});
  b+=txt(110+cw/2, 32, '會留', {anchor:'middle', size:10});
  b+=txt(110+cw*1.5, 32, '會走', {anchor:'middle', size:10});
  b+=`<text x="18" y="${40+ch}" font-size="11" font-weight="600" fill="${C.ink}"
    text-anchor="middle" transform="rotate(-90 18 ${40+ch})">實際</text>`;
  cells.forEach(c=>{
    const x=110+c.c*cw, y=40+c.r*ch;
    b+=`<rect x="${x}" y="${y}" width="${cw-4}" height="${ch-4}" fill="${c.col}"
      stroke="${C.line}" rx="2"/>`;
    b+=txt(x+10, y+18, c.k, {size:10, fill:c.fg, weight:600});
    b+=`<text x="${x+10}" y="${y+48}" font-size="26" font-family="var(--mono)"
      font-weight="600" fill="${c.fg}">${c.v}</text>`;
    b+=txt(x+10, y+66, c.note, {size:9.5});
  });
  b+=txt(48, 40+ch*0.5, '實際會留', {anchor:'middle', size:10});
  b+=txt(48, 40+ch*1.5, '實際會走', {anchor:'middle', size:10});
  return svg(w, h, b, '', 'light');
}

/* ── 時窗帶狀圖（招牌） ───────────────────────────── */
function ribbon(rows, o={}) {
  const w=o.w||700, padL=o.padL||148, padR=26, rowH=23, top=26;
  const h=top+rows.length*rowH+30;
  const t0=6*60, t1=17*60;
  const X=t=>padL+(w-padL-padR)*(t-t0)/(t1-t0);
  let b='';
  for(let t=t0;t<=t1;t+=60){
    b+=`<line x1="${X(t)}" y1="${top-6}" x2="${X(t)}" y2="${top+rows.length*rowH}"
      stroke="${C.grid}"/>`;
    b+=txt(X(t), top-12, `${String(t/60|0).padStart(2,'0')}:00`, {anchor:'middle', size:9.5});
  }
  rows.forEach((r,i)=>{
    const y=top+i*rowH, barY=y+3, barH=rowH-9, cy=barY+barH/2;
    b+=txt(padL-9, cy+4, r.name, {anchor:'end', size:10.5, fill:C.ink});
    b+=`<rect x="${X(r.open)}" y="${barY}" width="${Math.max(2,X(r.close)-X(r.open))}"
      height="${barH}" fill="#DCE2E1" rx="2">
      ${tip(`${r.name}　可收貨 ${r.tw}`)}</rect>`;
    if(r.arrive!=null){
      const bad=r.bad;
      b+=`<circle cx="${X(r.arrive)}" cy="${cy}" r="5.4" fill="${bad?C.alert:C.chill}"
        stroke="#fff" stroke-width="1.6">${tip(r.tipText)}</circle>`;
    }
  });
  return svg(w,h,b);
}

/* ── 路線地圖（等距圓柱投影，無底圖） ─────────────── */
function routeMap(stores, stops, depot, o={}) {
  const w=o.w||700, h=o.h||500, p=44;
  const lats=stores.map(s=>s.lat), lons=stores.map(s=>s.lon);
  const la0=Math.min(...lats), la1=Math.max(...lats);
  const lo0=Math.min(...lons), lo1=Math.max(...lons);
  const k=Math.cos((la0+la1)/2*Math.PI/180);
  const sx=(lo1-lo0)*k, sy=(la1-la0);
  const sc=Math.min((w-2*p)/sx, (h-2*p)/sy);
  const X=lon=>p+((lon-lo0)*k)*sc+((w-2*p)-sx*sc)/2;
  const Y=lat=>h-p-((lat-la0)*sc)-((h-2*p)-sy*sc)/2;
  const vcol={};
  ['#22ff62','#ffd064','#9ab8ff'].forEach((c,i)=>vcol['V'+(i+1)]=c);
  let b=`<rect x="0" y="0" width="${w}" height="${h}" fill="#011a0a"
    stroke="#0c7930" stroke-width="1"/>`;
  for(let g=0;g<=6;g++){
    b+=`<line x1="${p+(w-2*p)*g/6}" y1="${p*0.6}" x2="${p+(w-2*p)*g/6}" y2="${h-p*0.6}"
      stroke="#147a33" stroke-opacity=".82"/>`;
    b+=`<line x1="${p*0.6}" y1="${p*0.6+(h-1.2*p)*g/6}" x2="${w-p*0.6}" y2="${p*0.6+(h-1.2*p)*g/6}"
      stroke="#147a33" stroke-opacity=".82"/>`;
  }
  const byV={};
  stops.forEach(s=>{ (byV[s.vehicle_id]=byV[s.vehicle_id]||[]).push(s); });
  Object.entries(byV).forEach(([vid,list])=>{
    list.sort((a,b2)=>a.stop_order-b2.stop_order);
    const pts=[[depot.lon,depot.lat],...list.map(s=>[s.lon,s.lat]),[depot.lon,depot.lat]];
    b+=`<polyline points="${pts.map(c=>`${X(c[0])},${Y(c[1])}`).join(' ')}"
      fill="none" stroke="${vcol[vid]||C.mute}" stroke-width="8" stroke-opacity=".14"
      stroke-linejoin="round"/>`;
    b+=`<polyline points="${pts.map(c=>`${X(c[0])},${Y(c[1])}`).join(' ')}"
      fill="none" stroke="${vcol[vid]||C.mute}" stroke-width="2.8" stroke-opacity=".96"
      stroke-linejoin="round"/>`;
  });
  Object.entries(byV).forEach(([vid,list])=>{
    list.forEach(s=>{
      const bad=(s.late_min>0)||(s.early_min>0);
      b+=`<circle cx="${X(s.lon)}" cy="${Y(s.lat)}" r="11" fill="${bad?C.alert:(vcol[vid]||C.mute)}"
        stroke="#c8ffd3" stroke-width="2">${tip(`${s.stop_order}. ${s.store_name}
${s.vehicle_name}　抵達 ${s.arrive_hhmm}　${s.demand_kg} kg`)}</circle>`;
      b+=`<text x="${X(s.lon)}" y="${Y(s.lat)+3.6}" font-size="10" fill="#001006"
        font-weight="700" text-anchor="middle" pointer-events="none">${s.stop_order}</text>`;
    });
  });
  b+=`<rect x="${X(depot.lon)-9}" y="${Y(depot.lat)-9}" width="18" height="18"
    fill="#052b14" stroke="#22ff62" stroke-width="2.2">${tip('台中工業區主倉')}</rect>`;
  return svg(w,h,b);
}

/* ── 決策樹（逐層展開） ───────────────────────────── */
function treePath(steps) {
  let b='';
  steps.forEach((s,i)=>{
    b+=`<div class="tp-step">`;
    if(s.leaf){
      b+=`<b>結論</b>：這群人共 ${s.samples} 位，其中 ${(s.prob*100).toFixed(0)}% 會流失`;
    }else{
      b+=`<b>問</b>：${s.zh} ${s.go_left?'≤':'>'} ${fmt(s.threshold,1)}？　`
       + `<span class="pill">實際 ${fmt(s.value,1)}　→　${s.go_left?'是':'否'}</span>`;
    }
    b+=`</div>`;
  });
  return b;
}
