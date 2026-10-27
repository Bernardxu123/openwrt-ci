// ==UserScript==
// @name         xx.290490.xyz 连通性诊断
// @namespace    https://github.com/Bernardxu123/net-diag
// @version      1.0.0
// @description  在任意页面检测 https://xx.290490.xyz/ 与 /card/ 的可达性、耗时、错误类型；多轮采样抓间歇失败。不碰任何 cookie（含 app.brevo.com）。
// @author       Bernardxu123
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM.xmlHttpRequest
// @grant        GM_registerMenuCommand
// @grant        GM.setMenuCommand
// @grant        GM_setClipboard
// @grant        GM.setClipboard
// @connect      xx.290490.xyz
// @connect      www.baidu.com
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const TARGETS = [
    { name: '主站 /', url: 'https://xx.290490.xyz/' },
    { name: '面板 /card/', url: 'https://xx.290490.xyz/card/' },
  ];
  const CONTROL = { name: '对照 baidu', url: 'https://www.baidu.com/' };
  const ROUNDS = 3;
  const GAP_MS = 800;

  const STYLE = `
  #xxdiag{position:fixed;right:16px;bottom:16px;z-index:2147483646;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#d7e0ea}
  #xxdiag .xx-fab{cursor:pointer;background:#0f172a;border:1px solid #334155;color:#7dd3fc;padding:8px 12px;border-radius:999px;box-shadow:0 4px 16px rgba(0,0,0,.35);user-select:none}
  #xxdiag .xx-panel{display:none;margin-top:8px;width:360px;max-height:70vh;overflow:auto;background:#0b1220;border:1px solid #1e293b;border-radius:12px;padding:12px;box-shadow:0 8px 32px rgba(0,0,0,.45)}
  #xxdiag.open .xx-panel{display:block}
  #xxdiag h3{margin:0 0 8px;font-size:13px;color:#f8fafc}
  #xxdiag .row{display:flex;gap:8px;margin:6px 0}
  #xxdiag button{cursor:pointer;background:#134e4a;border:1px solid #0f766e;color:#ccfbf1;padding:6px 10px;border-radius:8px;font:inherit}
  #xxdiag button.ghost{background:#1e293b;border-color:#334155;color:#cbd5e1}
  #xxdiag pre{margin:8px 0 0;padding:8px;background:#020617;border:1px solid #1e293b;border-radius:8px;white-space:pre-wrap;word-break:break-all;max-height:36vh;overflow:auto;color:#94a3b8}
  #xxdiag .ok{color:#4ade80} #xxdiag .bad{color:#f87171} #xxdiag .warn{color:#fbbf24}
  #xxdiag .note{margin-top:8px;color:#64748b;font-size:11px}
  `;

  function injectStyle() {
    if (document.getElementById('xxdiag-style')) return;
    const s = document.createElement('style');
    s.id = 'xxdiag-style';
    s.textContent = STYLE;
    (document.head || document.documentElement).appendChild(s);
  }

  function gmXhr() {
    if (typeof GM_xmlhttpRequest === 'function') return GM_xmlhttpRequest;
    if (typeof GM !== 'undefined' && GM.xmlHttpRequest) return GM.xmlHttpRequest;
    return null;
  }

  /** 单次探测：优先 GM_xmlhttpRequest（可跨域、避开页面扩展 fetch 钩子），失败再退 fetch */
  function probeOnce(url) {
    const t0 = performance.now();
    return new Promise((resolve) => {
      const finish = (r) => {
        r.ms = Math.round(performance.now() - t0);
        resolve(r);
      };
      const xhrFn = gmXhr();
      if (xhrFn) {
        try {
          xhrFn({
            method: 'GET',
            url,
            timeout: 15000,
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' },
            onload: (res) => finish({ ok: res.status >= 200 && res.status < 400, status: res.status, via: 'GM_xmlhttpRequest', finalUrl: res.finalUrl || url }),
            onerror: (e) => finish({ ok: false, error: (e && (e.error || e.statusText)) || 'network error', via: 'GM_xmlhttpRequest' }),
            ontimeout: () => finish({ ok: false, error: 'timeout 15s', via: 'GM_xmlhttpRequest' }),
          });
          return;
        } catch (e) {
          /* fallthrough */
        }
      }
      fetch(url, { method: 'GET', cache: 'no-store', credentials: 'omit', mode: 'cors' })
        .then((res) => finish({ ok: res.ok || (res.status >= 200 && res.status < 400), status: res.status, via: 'fetch', finalUrl: res.url }))
        .catch((err) => {
          // no-cors 再试一次，区分「CORS」和「连不上」
          fetch(url, { method: 'GET', cache: 'no-store', credentials: 'omit', mode: 'no-cors' })
            .then(() => finish({ ok: true, status: 'opaque', via: 'fetch:no-cors', note: 'CORS 受限但 TCP/TLS 可达' }))
            .catch(() => finish({ ok: false, error: String(err && err.message ? err.message : err), via: 'fetch' }));
        });
    });
  }

  function fmtLine(label, r) {
    if (r.ok) {
      const st = r.status != null ? r.status : 'OK';
      return `<span class="ok">✔</span> ${label}  <b>${st}</b>  ${r.ms}ms  <span class="warn">${r.via || ''}</span>${r.note ? ' ' + r.note : ''}`;
    }
    return `<span class="bad">✘</span> ${label}  ${r.ms}ms  ${r.error || 'fail'}  <span class="warn">${r.via || ''}</span>`;
  }

  async function runDiag(outPre) {
    const log = [];
    const push = (s) => {
      log.push(s);
      outPre.textContent = log.join('\n');
      outPre.scrollTop = outPre.scrollHeight;
    };

    push(`# xx.290490.xyz 诊断  ${new Date().toLocaleString()}`);
    push(`页面: ${location.href}`);
    push(`UA: ${navigator.userAgent}`);
    push(`onLine=${navigator.onLine}`);
    try {
      const c = navigator.connection;
      if (c) push(`connection: ${c.effectiveType || ''} downlink=${c.downlink || ''} rtt=${c.rtt || ''}`);
    } catch (e) {}
    push('');

    // 对照组
    push('## 对照（判断是全网问题还是单站问题）');
    for (let i = 1; i <= ROUNDS; i++) {
      const r = await probeOnce(CONTROL.url);
      push(fmtLine(`[${i}/${ROUNDS}] ${CONTROL.name}`, r));
      await sleep(GAP_MS);
    }
    push('');

    // 目标站
    for (const t of TARGETS) {
      push(`## ${t.name}  ${t.url}`);
      for (let i = 1; i <= ROUNDS; i++) {
        const r = await probeOnce(t.url);
        push(fmtLine(`[${i}/${ROUNDS}] ${t.name}`, r));
        await sleep(GAP_MS);
      }
      push('');
    }

    // 经验提示
    push('## 提示（按优先级）');
    push('1. 若对照通、目标多数失败 → 服务端/线路/证书问题；看 error 是 timeout 还是 connection reset');
    push('2. 若对照也慢/挂 → 本机网络或代理');
    push('3. 若 GM 成功但 fetch 失败 → 扩展钩子/页面 CSP；可禁用沉浸式翻译、uBL、VisualKit 再试');
    push('4. 检查系统代理残留 127.0.0.1:10808 是否被启用（chrome://settings）');
    push('5. 勿清理 app.brevo.com 的 cookie（登录麻烦，保留）');
    push('');
    push('## 汇总');
    push('（复制本框内容发给我即可进一步判断）');
    return log.join('\n');
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function copyText(text) {
    if (typeof GM_setClipboard === 'function') return GM_setClipboard(text, 'text');
    if (typeof GM !== 'undefined' && GM.setClipboard) return GM.setClipboard(text, 'text');
    try {
      navigator.clipboard.writeText(text);
    } catch (e) {}
  }

  function buildUI() {
    injectStyle();
    if (document.getElementById('xxdiag')) return;
    const root = document.createElement('div');
    root.id = 'xxdiag';
    root.innerHTML = `
      <div class="xx-fab">📡 连通诊断</div>
      <div class="xx-panel">
        <h3>xx.290490.xyz 检测</h3>
        <div class="row">
          <button id="xxdiag-run">开始检测</button>
          <button id="xxdiag-copy" class="ghost">复制报告</button>
          <button id="xxdiag-close" class="ghost">关闭</button>
        </div>
        <pre id="xxdiag-out">点「开始检测」。脚本只发 GET 探测，不会读写任何站点 cookie。</pre>
        <div class="note">保留 Brevo 登录态 · 不做清理。检测跨域走 GM_xmlhttpRequest。</div>
      </div>`;
    document.documentElement.appendChild(root);

    const panel = root.querySelector('.xx-panel');
    root.querySelector('.xx-fab').onclick = () => root.classList.toggle('open');
    root.querySelector('#xxdiag-close').onclick = () => root.classList.remove('open');
    const out = root.querySelector('#xxdiag-out');
    root.querySelector('#xxdiag-run').onclick = async () => {
      out.textContent = '检测中…（每项 3 轮，约 10 秒）';
      await runDiag(out);
    };
    root.querySelector('#xxdiag-copy').onclick = () => {
      copyText(out.textContent);
      root.querySelector('#xxdiag-copy').textContent = '已复制';
      setTimeout(() => (root.querySelector('#xxdiag-copy').textContent = '复制报告'), 1200);
    };
  }

  function boot() {
    buildUI();
    const open = () => {
      buildUI();
      document.getElementById('xxdiag').classList.add('open');
    };
    if (typeof GM_registerMenuCommand === 'function') {
      GM_registerMenuCommand('检测 xx.290490.xyz', open);
    } else if (typeof GM !== 'undefined' && GM.setMenuCommand) {
      GM.setMenuCommand('检测 xx.290490.xyz', open);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
