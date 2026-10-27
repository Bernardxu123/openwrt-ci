// ==UserScript==
// @name         daed - 群组当前最优(Ai/proxy)常驻徽标
// @namespace    https://github.com/Bernardxu123/daed-badge
// @version      1.4.2
// @description  仅 AI/proxy 两个群组常驻显示当前最优节点与延迟。支持 /graphql 真实 groups+nodeLatencies，自动处理 daed 登录鉴权，未测速时自动回落 DOM 的 157ms 解析。
// @author       Bernardxu123 + Reasonix
// @match        http://192.168.31.1:2023/*
// @match        http://192.168.31.1:2023/#/*
// @grant        GM_xmlhttpRequest
// @grant        GM.xmlHttpRequest
// @connect      192.168.31.1
// @run-at       document-start
// ==/UserScript==

(function () {
  'use strict';

  const STYLE = `
  .daed-head-badge{display:inline-flex;align-items:center;gap:6px;margin-left:8px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:rgba(255,185,0,.14);border:1px solid rgba(255,185,0,.28);color:#fff8c8;vertical-align:middle;max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .daed-head-badge .lat{color:#00e676}
  `;
  function injectStyle(){ if(document.getElementById('daed-badge-style')) return; const s=document.createElement('style'); s.id='daed-badge-style'; s.textContent=STYLE; (document.head||document.documentElement).appendChild(s); }
  function esc(s){ return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

  let lastGroups=null; // Group[]
  let lastLatencies=null; // Map id -> {id,latencyMs,alive}

  function setLatencies(arr){ if(!Array.isArray(arr)) return; const m=new Map(); for(const x of arr) if(x&&x.id) m.set(String(x.id), x); lastLatencies=m; }

  // Auth: read token from localStorage/cookie if present, else use default xpw:123 basic to get token via graphql
  function getStoredToken(){
    try{
      for(let i=0;i<localStorage.length;i++){
        const k=localStorage.key(i); const v=localStorage.getItem(k);
        if(!v) continue;
        if(/token|auth|daed/i.test(k) && v.length>20) return v.replace(/^"|"$/g,'');
        if(v.includes('eyJ') && v.length>40) return v;
      }
      const m=document.cookie.match(/(?:^|;\s*)(token|auth|daed[^=]*)=([^;]+)/i);
      if(m) return decodeURIComponent(m[2]);
    }catch(e){}
    return null;
  }

  // ---- graphql via GM__ if page interception yields 401 ----
  let activeToken = null;
  function fetchGraphQL(query){
    return new Promise((resolve,reject)=>{
      const url=location.origin + '/graphql';
      const headers={'Content-Type':'application/json'};
      const tok = activeToken || getStoredToken();
      if(tok) headers['Authorization']='Bearer ' + tok;
      const body=JSON.stringify({query});
      const doReq=(h)=> {
        const xhr = (typeof GM_xmlhttpRequest !== 'undefined' ? GM_xmlhttpRequest : (typeof GM!=='undefined'&&GM.xmlHttpRequest?GM.xmlHttpRequest:null));
        if(xhr){
          xhr({method:'POST', url, headers:h, data:body, onload:r=>{ try{ resolve(JSON.parse(r.responseText)); }catch(e){ reject(e); }}, onerror:e=>reject(e)});
        } else {
          fetch(url,{method:'POST', headers:h, body, credentials:'include'}).then(r=>r.json()).then(resolve).catch(reject);
        }
      };
      doReq(headers);
    });
  }

  async function ensureGroups(){
    const qGroups='query{groups{id name policy policyParams{key val} nodes{id name protocol tag} subscriptions{subscription{id tag} nameFilterRegex matchedCount matchedNodes{id name protocol tag}} } nodeLatencies{id latencyMs alive} general{dae{running version}}}';
    try{
      let j=await fetchGraphQL(qGroups);
      if(j?.errors && String(j.errors[0]?.message||'').includes('access denied')){
        // try to obtain token via Basic xpw:123 -> backend will set cookie/token on next request with credentials
        // Fallback: try token query
        const tokQ='query{token(username:"xpw", password:"123")}';
        const tj=await fetchGraphQL(tokQ);
        if(tj?.data?.token){ activeToken=tj.data.token; try{localStorage.setItem('daed_token',tj.data.token);}catch(e){} }
        j=await fetchGraphQL(qGroups);
      }
      if(j?.data?.groups){ lastGroups=j.data.groups; }
      if(j?.data?.nodeLatencies){ setLatencies(j.data.nodeLatencies); }
      if(j?.data?.groups || j?.data?.nodeLatencies) schedule();
      return j;
    }catch(e){ return null; }
  }

  // Also keep passive interception of page's own graphql calls
  const _fetch=window.fetch;
  window.fetch=async function(...a){
    const r=await _fetch.apply(this,a);
    try{
      const url=String(typeof a[0]==='string'?a[0]:(a[0]&&a[0].url)||'');
      if(url.includes('/graphql')) r.clone().text().then(t=>{ try{ const j=JSON.parse(t); if(j?.data?.groups){lastGroups=j.data.groups; schedule();} if(j?.data?.nodeLatencies){setLatencies(j.data.nodeLatencies); schedule();} }catch(e){} });
    }catch(e){}
    return r;
  };
  const _open=XMLHttpRequest.prototype.open; const _send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(...a){ this._url=a[1]; return _open.apply(this,a); };
  XMLHttpRequest.prototype.send=function(...a){
    this.addEventListener('load', function(){
      try{ if(this._url && String(this._url).includes('/graphql') && this.responseText){ const j=JSON.parse(this.responseText); if(j?.data?.groups){lastGroups=j.data.groups; schedule();} if(j?.data?.nodeLatencies){setLatencies(j.data.nodeLatencies); schedule();} } }catch(e){}
    });
    return _send.apply(this,a);
  };

  // ---- helpers ----
  function pickSelected(g){
    const cand=[];
    if(Array.isArray(g.nodes)) cand.push(...g.nodes);
    if(Array.isArray(g.subscriptions)) for(const s of g.subscriptions) if(Array.isArray(s.matchedNodes)) cand.push(...s.matchedNodes);
    if(!cand.length) return null;
    const withLat=cand.map(n=>{
      const l=lastLatencies?lastLatencies.get(String(n.id)):null;
      return {node:n, lat:l?l.latencyMs:null, alive:l?l.alive:null};
    });
    const alive=withLat.filter(x=>x.alive!==false && x.lat!=null).sort((a,b)=>a.lat-b.lat);
    if(alive.length) return alive[0];
    const any=withLat.filter(x=>x.lat!=null).sort((a,b)=>a.lat-b.lat);
    if(any.length) return any[0];
    return {node:cand[0], lat:null, alive:null};
  }
  function fmt(g){
    const p=pickSelected(g);
    if(!p) return null;
    return {name:p.node?.name||p.node?.tag||'—', proto:(p.node?.protocol||'').toUpperCase(), lat:p.lat!=null?`${p.lat} ms`:'未测速', policy:g.policy||'', total:(g.nodes?.length||0)+(g.subscriptions?.reduce((a,s)=>a+(s.matchedCount||0),0)||0), p};
  }
  function groupByName(n){ if(!lastGroups) return null; return lastGroups.find(g=>g.name===n) || lastGroups.find(g=>String(g.name).toLowerCase()===n.toLowerCase()) || null; }

  function findGroupSection(){
    const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n, best=null;
    while(n=walker.nextNode()){
      if((n.nodeValue||'').trim()==='群组'){
        let el=n.parentElement;
        for(let i=0;i<5&&el;i++){ if(el.textContent&&el.textContent.includes('AI')&&el.textContent.includes('proxy')&&el.children.length>2){best=el;break;} el=el.parentElement; }
        if(best) break;
      }
    }
    if(best) return best;
    let cand=null; document.querySelectorAll('div').forEach(d=>{ const t=d.textContent||''; if(t.includes('AI')&&t.includes('proxy')&&t.includes('min_avg10')&&t.includes('min_moving_avg')&&!cand) cand=d; });
    return cand;
  }
  function findAiProxyCards(){
    const section=findGroupSection(); const scope=section||document.body;
    const all=[]; const walker=document.createTreeWalker(scope, NodeFilter.SHOW_TEXT); let n;
    while(n=walker.nextNode()){
      const t=n.nodeValue||'';
      if(t.includes('min_avg10')||t.includes('min_moving_avg')){
        let el=n.parentElement;
        for(let i=0;i<10&&el;i++){
          const txt=el.textContent||'';
          const hasAi=txt.includes('AI')&&txt.includes('min_avg10');
          const hasProxy=txt.includes('proxy')&&txt.includes('min_moving_avg');
          if((hasAi||hasProxy)&&el.children.length<80&&el!==scope){ all.push(el); break; }
          el=el.parentElement;
        }
      }
    }
    const uniq=[...new Set(all)];
    const mapped=[];
    for(const el of uniq){
      const txt=el.textContent||'';
      let name=null;
      if(txt.includes('AI')&&txt.includes('min_avg10')) name='AI';
      else if(txt.includes('proxy')&&txt.includes('min_moving_avg')) name='proxy';
      if(name) mapped.push({el, name});
    }
    const byName=new Map(); for(const m of mapped) if(!byName.has(m.name)) byName.set(m.name, m);
    const out=[]; if(byName.has('AI')) out.push(byName.get('AI')); if(byName.has('proxy')) out.push(byName.get('proxy'));
    return out;
  }
  function fallbackParse(cardText){
    const lines=[...cardText.matchAll(/([^\n]{1,40}?)\s+(\d+)\s*ms/g)];
    let bestName='', bestLat=Infinity;
    for(const mm of lines){ const lat=parseInt(mm[2],10); if(lat<bestLat){ bestLat=lat; bestName=mm[1].trim().slice(-28); } }
    return {bestName, bestLat};
  }
  function render(){
    injectStyle();
    // remove legacy top panel (red box) if present
    const legacy=document.getElementById('daed-groups-panel');
    if(legacy) legacy.remove();
    // Badges on cards only (as requested)
    const cards=findAiProxyCards();
    for(const {el,name} of cards){
      const g=groupByName(name);
      let badgeText='', title='';
      const f=g?fmt(g):null;
      if(f){ badgeText=`${f.name} · ${f.lat}`; title=`${name} / ${f.policy} → ${f.name} ${f.proto} ${f.lat}`; }
      else {
        const {bestName,bestLat}=fallbackParse(el.textContent||'');
        if(bestName) { badgeText=`${bestName} · ${bestLat} ms`; title=`${name} → ${bestName} (本地解析)`; }
      }
      if(!badgeText) continue;
      let header=null;
      for(const c of el.querySelectorAll('*')){ const t=c.textContent||''; if(/min_avg10|min_moving_avg|fixed/.test(t)&&c.children.length<20){header=c;break;} }
      if(!header) header=el;
      let badge=header.querySelector(':scope > .daed-head-badge');
      if(!badge){ badge=document.createElement('span'); badge.className='daed-head-badge'; header.appendChild(badge); }
      badge.textContent=badgeText; badge.title=title;
    }
  }

  let t=null; function schedule(){ clearTimeout(t); t=setTimeout(()=>{ try{ render(); }catch(e){} }, 80); }
  const obs=new MutationObserver(schedule);
  function start(){
    injectStyle();
    // remove legacy top panel once
    const legacy0=document.getElementById('daed-groups-panel');
    if(legacy0) legacy0.remove();
    obs.observe(document.documentElement,{childList:true, subtree:true});
    setInterval(schedule, 2500);
    // active fetch for auth case
    setTimeout(ensureGroups, 600);
    setInterval(ensureGroups, 20000);
    schedule();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
