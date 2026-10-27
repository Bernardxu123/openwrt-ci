/* ============================================================
 * app.js — 户型网络规划器
 * 依赖：RF（rf.js）、DATA（data.js）、PLAN_PNG / WALL_GRID（assets.js）
 * ============================================================ */
(function () {
  'use strict';

  const PLAN = DATA.PLAN_PX;               // 1020
  const PPM  = DATA.PX_PER_M;              // 80
  const MPP  = 1 / PPM;
  const GRID_N = 256;

  /* ---------------- 全局状态 ---------------- */
  const S = {
    band: '5',
    view: 'plan',
    wallPreset: 'brick',
    scenario: 'now',
    aps: [],
    clients: [],
    sel: null,                       // { type:'ap'|'cli', id }
    show: { heat:true, clients:true, links:true, rooms:true, walls:true, contour:false },
    zoom: 1, panX: 0, panY: 0,
    coverage: null,                  // Float32Array res*res
    covRes: 170,
    stats: null,
    issues: [],
  };

  const WALL = { cls: null, solid: null };

  /* ---------------- 工具 ---------------- */
  const $ = s => document.querySelector(s);
  const $$ = s => Array.prototype.slice.call(document.querySelectorAll(s));
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  const fmt = (v, d) => (v == null || !isFinite(v)) ? '—' : v.toFixed(d == null ? 1 : d);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));

  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
  }

  /* ---------------- 加载墙体 ---------------- */
  function decodeWalls(b64) {
    const bin = atob(b64);
    const N = GRID_N;
    const lvl = new Uint8Array(N * N);
    let p = 0;
    for (let gy = 0; gy < N; gy++) {
      for (let gx = 0; gx < N; gx += 4) {
        const b = bin.charCodeAt(p++);
        lvl[gy * N + gx]     = b & 3;
        lvl[gy * N + gx + 1] = (b >> 2) & 3;
        lvl[gy * N + gx + 2] = (b >> 4) & 3;
        lvl[gy * N + gx + 3] = (b >> 6) & 3;
      }
    }
    return lvl;
  }

  /* ============================================================
   * 房间标定：名字 / 范围可改，存 localStorage
   * ============================================================ */
  const LS_ROOMS = 'netplan/rooms/v1';
  const LS_APS = 'netplan/aps/v1';

  function loadRoomOverrides() {
    try {
      const raw = localStorage.getItem(LS_ROOMS);
      if (!raw) return;
      const ov = JSON.parse(raw);
      DATA.ROOMS.forEach(r => {
        if (ov[r.id]) {
          if (typeof ov[r.id].name === 'string' && ov[r.id].name) r.name = ov[r.id].name;
          if (Array.isArray(ov[r.id].box) && ov[r.id].box.length === 4) r.box = ov[r.id].box.slice();
        }
      });
    } catch (e) { /* 忽略损坏的存储 */ }
  }

  function saveRoomOverrides() {
    const ov = {};
    DATA.ROOMS.forEach(r => { ov[r.id] = { name: r.name, box: r.box.slice() }; });
    localStorage.setItem(LS_ROOMS, JSON.stringify(ov));
  }

  function resetRoomOverrides() {
    localStorage.removeItem(LS_ROOMS);
  }

  function loadApOverrides() {
    try {
      const raw = localStorage.getItem(LS_APS);
      if (!raw) return;
      const ov = JSON.parse(raw);
      DATA.DEVICES.forEach(d => {
        if (ov[d.id]) {
          if (typeof ov[d.id].x === 'number') d.x = ov[d.id].x;
          if (typeof ov[d.id].y === 'number') d.y = ov[d.id].y;
          if (ov[d.id].bands) {
            for (const b of ['2.4', '5']) {
              if (ov[d.id].bands[b] && d.bands[b]) Object.assign(d.bands[b], ov[d.id].bands[b]);
            }
          }
        }
      });
    } catch (e) { /* 忽略 */ }
  }

  function saveApOverrides() {
    const ov = {};
    DATA.DEVICES.forEach(d => {
      ov[d.id] = { x: d.x, y: d.y, bands: JSON.parse(JSON.stringify(d.bands)) };
    });
    localStorage.setItem(LS_APS, JSON.stringify(ov));
  }

  /* 把当前 S.aps 的位置/信道回写进 DATA.DEVICES，便于方案切换时保留 */
  function syncApsToData() {
    for (const a of S.aps) {
      const d = DATA.DEVICES.find(x => x.id === a.id);
      if (!d) continue;
      d.x = a.x; d.y = a.y;
      for (const b of ['2.4', '5']) {
        if (a.bands[b] && d.bands[b]) Object.assign(d.bands[b], a.bands[b]);
      }
    }
  }

  /* ---------------- 部署方案 ---------------- */
  function applyScenario(id) {
    const sc = DATA.SCENARIOS.find(s => s.id === id) || DATA.SCENARIOS[0];
    S.scenario = id;
    const src = sc.devices || DATA.DEVICES.map(d => ({ ref: d.id }));
    const byId = {};
    DATA.DEVICES.forEach(d => byId[d.id] = d);
    S.aps = src.map(spec => {
      const base = spec.ref ? byId[spec.ref] : null;
      const d = base ? Object.assign({}, base, spec, { ref: undefined }) : spec;
      return {
        id: d.id, type: d.type || 'ap', name: d.name, model: d.model || '',
        ip: d.ip || '—', mac: d.mac || '—', role: d.role || '',
        notes: d.notes || '', wired: d.wired !== false,
        x: d.x, y: d.y,
        bands: JSON.parse(JSON.stringify(d.bands)),
      };
    });
    S.sel = null;
  }

  function syncClients() {
    S.clients = DATA.CLIENTS.map(c => Object.assign({}, c));
  }

  /* ---------------- 计算 ---------------- */
  function activeAps() {
    return S.aps.filter(a => a.bands[S.band] && a.bands[S.band].enabled !== false);
  }

  function apListForCalc() {
    return activeAps().map(a => ({
      id: a.id, name: a.name, x: a.x, y: a.y,
      tx: a.bands[S.band].tx, enabled: true,
      width: a.bands[S.band].width,
    }));
  }

  function recompute() {
    const preset = RF.WALL_PRESETS[S.wallPreset];
    const aps = apListForCalc();
    const res = S.covRes;
    const inside = (x, y) => RF.pointInPoly(x, y, DATA.OUTLINE);

    S.coverage = RF.coverage({
      cls: WALL.ray, N: GRID_N, aps, bandKey: S.band, preset,
      mPerPx: MPP, planPx: PLAN, res, inside,
    });

    // ---- 逐房间 ----
    const rooms = DATA.ROOMS.map(r => {
      const cx = (r.box[0] + r.box[2]) / 2, cy = (r.box[1] + r.box[3]) / 2;
      let best = null;
      for (const ap of aps) {
        const l = RF.link(WALL.ray, GRID_N, ap, cx, cy, S.band, preset, MPP, PLAN);
        if (!best || l.rssi > best.rssi) best = Object.assign({ apId: ap.id, apName: ap.name }, l);
      }
      // 房间内采样（取中位数，避免单点偶然）
      const samples = [];
      const step = 14;
      for (let y = r.box[1] + 8; y < r.box[3] - 6; y += step) {
        for (let x = r.box[0] + 8; x < r.box[2] - 6; x += step) {
          if (!inside(x, y)) continue;
          let b = -Infinity;
          for (const ap of aps) {
            const l = RF.link(WALL.ray, GRID_N, ap, x, y, S.band, preset, MPP, PLAN);
            if (l.rssi > b) b = l.rssi;
          }
          if (isFinite(b)) samples.push(b);
        }
      }
      samples.sort((a, b) => a - b);
      const med = samples.length ? samples[Math.floor(samples.length / 2)] : (best ? best.rssi : NaN);
      const p10 = samples.length ? samples[Math.floor(samples.length * 0.1)] : NaN;
      const ap = aps.find(a => a.id === (best && best.apId));
      const w = ap ? ap.width : RF.BANDS[S.band].defaultWidth;
      return {
        id: r.id, name: r.name, kind: r.kind, box: r.box,
        rssi: med, rssiWorst: p10,
        ap: best ? best.apName : '—',
        tp: RF.throughput(S.band, w, med),
        cx, cy,
      };
    });

    // ---- 逐终端 ----
    const clients = S.clients.map(c => {
      let best = null;
      for (const ap of aps) {
        const l = RF.link(WALL.ray, GRID_N, ap, c.x, c.y, c.band, preset, MPP, PLAN);
        if (!best || l.rssi > best.rssi) best = Object.assign({ apId: ap.id, apName: ap.name }, l);
      }
      const ap = aps.find(a => a.id === (best && best.apId));
      const w = ap ? ap.width : RF.BANDS[c.band].defaultWidth;
      return Object.assign({}, c, {
        rssi: best ? best.rssi : NaN,
        dist: best ? best.dist : NaN,
        walls: best ? best.walls : 0,
        wallLoss: best ? best.wallLoss : 0,
        apId: best ? best.apId : null,
        apName: best ? best.apName : '—',
        tp: RF.throughput(c.band, w, best ? best.rssi : -100),
      });
    });

    // ---- 覆盖率统计 ----
    let n = 0, sum = 0, c65 = 0, c72 = 0, c80 = 0;
    for (let i = 0; i < S.coverage.length; i++) {
      const v = S.coverage[i];
      if (!isFinite(v)) continue;
      n++; sum += v;
      if (v < -65) c65++;
      if (v < -72) c72++;
      if (v < -80) c80++;
    }
    const band = RF.BANDS[S.band];
    S.stats = {
      n, avg: n ? sum / n : NaN,
      p65: n ? c65 / n : 0, p72: n ? c72 / n : 0, p80: n ? c80 / n : 0,
      good: n ? 1 - c72 / n : 0,
    };

    S.rooms = rooms;
    S.clientCalcs = clients;
    S.issues = diagnose(rooms, clients);
    renderAll();
  }

  /* ============================================================
   * 最优位置搜索：在室内网格上枚举候选点，评估覆盖收益
   * ============================================================ */
  function searchBestSpot(opts) {
    opts = opts || {};
    const preset = RF.WALL_PRESETS[S.wallPreset];
    const step = opts.step || 34;              // 候选点间距（plan px）
    const cur = apListForCalc();
    const res = 64;                            // 评分用的粗网格
    const inside = (x, y) => RF.pointInPoly(x, y, DATA.OUTLINE);
    const mPerPx = MPP;

    // 基准：现有 AP 的覆盖（不含候选点）
    const base = RF.coverage({
      cls: WALL.ray, N: GRID_N, aps: cur, bandKey: S.band, preset,
      mPerPx, planPx: PLAN, res, inside,
    });

    const candidates = [];
    for (let y = 30; y < PLAN - 30; y += step) {
      for (let x = 30; x < PLAN - 30; x += step) {
        if (!inside(x, y)) continue;
        const gx = Math.round(x * GRID_N / PLAN), gy = Math.round(y * GRID_N / PLAN);
        // 必须在空地上（离墙 ≥ 2 格）
        let blocked = false;
        for (let dy = -2; dy <= 2 && !blocked; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            const v = WALL.solid[(gy + dy) * GRID_N + gx + dx];
            if (v) { blocked = true; break; }
          }
        }
        if (blocked) continue;
        candidates.push({ x, y, gx, gy });
      }
    }

    // 逐个评估：候选点加入后，平均 RSSI 提升 + 死角减少。
    // 优化：先算出每个格点「新增 AP 单独提供的 RSSI」，再与基准取 max，
    //       避免对每个候选点重算整张热力图（O(K·res²) -> O(K·res²) 但常数小得多）。
    const txC = opts.tx == null ? 23 : opts.tx;
    const band = RF.BANDS[S.band];
    const k = GRID_N / PLAN;
    const cell = PLAN / res;
    const nCells = res * res;

    // 预取所有格点的 plan 坐标与可用性
    const cells = [];
    for (let gy = 0; gy < res; gy++) {
      for (let gx = 0; gx < res; gx++) {
        const px = (gx + 0.5) * cell, py = (gy + 0.5) * cell;
        if (!inside(px, py)) continue;
        const sx = Math.round(px * k), sy = Math.round(py * k);
        let ok = true;
        for (let dy = -2; dy <= 2 && ok; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            if (WALL.ray[(sy + dy) * GRID_N + sx + dx] !== RF.W_NONE) { ok = false; break; }
          }
        }
        if (!ok) continue;
        cells.push({ px, py, sx, sy, base: base[gy * res + gx] });
      }
    }
    const nBase = cells.length;

    const scored = [];
    for (const c of candidates) {
      let sum = 0, bad = 0, sumBase = 0, n = 0;
      for (let i = 0; i < nBase; i++) {
        const cell2 = cells[i];
        const dM = Math.max(Math.hypot(cell2.px - c.x, cell2.py - c.y) * mPerPx, 0.4);
        const w = RF.segmentWallLoss(WALL.ray, GRID_N, c.gx, c.gy, cell2.sx, cell2.sy, S.band, preset);
        const rNew = txC - RF.pathLoss(S.band, dM) - w.loss;
        const b = cell2.base;
        const best = (isFinite(b) && b > rNew) ? b : rNew;
        if (!isFinite(best)) continue;
        n++; sum += best;
        if (isFinite(b)) sumBase += b;
        if (best < -72) bad++;
      }
      if (!n) continue;
      const avg = sum / n;
      const avgBase = sumBase / n;
      scored.push({
        x: c.x, y: c.y,
        avg, gain: avg - avgBase,
        badRatio: bad / n,
        score: (avg - avgBase) * 2 - (bad / n) * 100,
      });
    }
    scored.sort((a, b) => b.score - a.score);

    // 去重：与已选点距离 < 70px 的丢弃
    const picked = [];
    for (const s of scored) {
      if (picked.some(p => Math.hypot(p.x - s.x, p.y - s.y) < 70)) continue;
      picked.push(s);
      if (picked.length >= (opts.top || 6)) break;
    }
    return { base: { avg: baseAvg(base) }, candidates: picked };
  }

  function baseAvg(cov) {
    let sum = 0, n = 0;
    for (let i = 0; i < cov.length; i++) { if (isFinite(cov[i])) { sum += cov[i]; n++; } }
    return n ? sum / n : NaN;
  }

  /* ---------------- 诊断引擎 ---------------- */
  function diagnose(rooms, clients) {
    const out = [];
    const band = S.band;
    const bandLabel = RF.BANDS[band].label;
    const preset = RF.WALL_PRESETS[S.wallPreset];

    // 1) 覆盖空洞
    const weakRooms = rooms.filter(r => r.rssi < -72).sort((a, b) => a.rssi - b.rssi);
    if (weakRooms.length) {
      out.push({
        sev: 'high', t: weakRooms.length + ' 个房间 ' + bandLabel + ' 覆盖不足',
        d: weakRooms.slice(0, 4).map(r => `<code>${esc(r.name)}</code> ${fmt(r.rssi)} dBm`).join('、')
           + (weakRooms.length > 4 ? ` 等 ${weakRooms.length} 处` : '')
           + `。低于 −72 dBm 会出现卡顿、重传、切换失败。`,
      });
    } else {
      out.push({ sev: 'ok', t: bandLabel + ' 全屋覆盖达标', d: '所有房间中位信号 ≥ −72 dBm，无需增加 AP。' });
    }

    // 2) 跨墙最严重的链路
    const worst = rooms.slice().sort((a, b) => a.rssi - b.rssi)[0];
    if (worst && worst.rssi < -70) {
      out.push({
        sev: 'mid', t: '最差房间：' + worst.name,
        d: `中位 <code>${fmt(worst.rssi)} dBm</code>（10 分位 ${fmt(worst.rssiWorst)} dBm），由 <code>${esc(worst.ap)}</code> 服务。建议在该房间与 AP 之间加一台有线回程 AP，或改用 2.4 GHz 承载。`,
      });
    }

    // 3) 信道重叠
    const aps = S.aps.filter(a => a.bands[band] && a.bands[band].enabled !== false);
    for (let i = 0; i < aps.length; i++) {
      for (let j = i + 1; j < aps.length; j++) {
        const a = aps[i].bands[band], b = aps[j].bands[band];
        const ov = RF.overlapRatio(band, a.ch, a.width, b.ch, b.width);
        if (ov > 0.02) {
          out.push({
            sev: ov > 0.5 ? 'high' : 'mid',
            t: `${aps[i].name} 与 ${aps[j].name} 信道重叠 ${(ov * 100).toFixed(0)}%`,
            d: `ch${a.ch}/${a.width}MHz 与 ch${b.ch}/${b.width}MHz。同频共存会平分空口时间，实际吞吐约降 ${(ov * 50).toFixed(0)}%。` +
               (band === '2.4' ? ' 2.4G 只有 1/6/11 可选，请把两者分到不同信道。' : ' 5G 请把两者分到不同 80 MHz 组（36-48 / 100-128 / 149-161）。'),
          });
        }
      }
    }

    // 4) 2.4G 40MHz 警告
    const a24 = S.aps.filter(a => a.bands['2.4'] && a.bands['2.4'].enabled && a.bands['2.4'].width > 20);
    if (band === '2.4' && a24.length) {
      out.push({
        sev: 'mid', t: a24.length + ' 台 AP 的 2.4G 开了 40 MHz',
        d: a24.map(a => esc(a.name)).join('、') + '。2.4 GHz 频段总共只有约 83 MHz，40 MHz 会吃掉大半个频段并与邻居互相干扰，实际速率通常反而下降。建议全部改回 <code>20 MHz</code>。',
      });
    }

    // 5) 5G 160MHz 提示
    const a160 = S.aps.filter(a => a.bands['5'] && a.bands['5'].enabled && a.bands['5'].width >= 160);
    if (band === '5' && a160.length > 1) {
      out.push({
        sev: 'mid', t: a160.length + ' 台 AP 同时使用 160 MHz',
        d: '国内 5G 只有 36-64 一段可用 160 MHz，多台 AP 同时开 160 必然同频。建议只保留一台开 160，其余降到 80 MHz。',
      });
    } else if (band === '5' && a160.length === 1) {
      out.push({
        sev: 'low', t: a160[0].name + ' 使用 160 MHz',
        d: '160 MHz 吞吐最高但覆盖半径最小，且要求客户端也支持。若该 AP 覆盖的房间边缘信号偏弱，可降到 80 MHz 换取约 3 dB 的链路余量。',
      });
    }

    // 6) 终端离 AP 太远
    const farCli = clients.filter(c => c.rssi < -70);
    if (farCli.length) {
      out.push({
        sev: 'mid', t: farCli.length + ' 台终端信号偏弱',
        d: farCli.map(c => `<code>${esc(c.name)}</code> ${fmt(c.rssi)} dBm / ${fmt(c.dist)} m`).join('、') +
           '。弱信号终端会拖慢整个 BSS 的空口效率（低速率占用更长时间）。',
      });
    }

    // 7) 2.4G / 5G 分工
    const cli24 = clients.filter(c => c.band === '2.4' && c.demand !== 'low');
    if (cli24.length) {
      out.push({
        sev: 'low', t: '仍有高需求终端挂在 2.4 GHz',
        d: cli24.map(c => esc(c.name)).join('、') + '。建议把支持 5G 的终端固定到 5 GHz，2.4 GHz 留给 IoT。',
      });
    }

    // 8) 单点故障
    if (S.aps.length === 1) {
      out.push({
        sev: 'mid', t: '全网只有一台 AP（单点故障）',
        d: '任何一台设备重启都会导致全屋断网，且单台 AP 无法同时覆盖户型的对角。建议至少再增加一台有线回程 AP。',
      });
    }

    // 9) 墙体材质提示
    if (S.wallPreset !== 'brick') {
      out.push({
        sev: 'low', t: '当前墙体模型：' + preset.label,
        d: `外墙 ${preset.ext} dB / 内墙 ${preset.int} dB / 窗 ${preset.win} dB。实际穿墙损耗请以现场实测校准——把手机贴着 AP 与目标房间各测一次 RSSI 即可反推。`,
      });
    }

    const order = { high: 0, mid: 1, low: 2, ok: 3 };
    out.sort((a, b) => order[a.sev] - order[b.sev]);
    return out;
  }

  /* ============================================================
   * 渲染
   * ============================================================ */
  const canvas = $('#planCanvas');
  const ctx = canvas.getContext('2d');
  let planImg = new Image();
  let planReady = false;
  let dpr = Math.min(window.devicePixelRatio || 1, 2);

  planImg.onload = () => { planReady = true; draw(); };
  planImg.src = 'data:image/png;base64,' + PLAN_PNG;

  function fitTransform() {
    const rect = canvas.getBoundingClientRect();
    const s = Math.min(rect.width / PLAN, rect.height / PLAN) * 0.94;
    S.zoom = s;
    S.panX = (rect.width - PLAN * s) / 2;
    S.panY = (rect.height - PLAN * s) / 2;
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    draw();
  }

  const toScreen = (x, y) => [x * S.zoom + S.panX, y * S.zoom + S.panY];
  const toPlan = (sx, sy) => [(sx - S.panX) / S.zoom, (sy - S.panY) / S.zoom];

  /* ---------------- 主绘制 ---------------- */
  let heatCache = null, heatKey = '';

  function draw() {
    if (!canvas.width) return;
    const w = canvas.width, h = canvas.height;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w / dpr, h / dpr);

    // 网格背景
    drawGridBg();

    ctx.save();
    ctx.translate(S.panX, S.panY);
    ctx.scale(S.zoom, S.zoom);

    // 1. 热力图
    if (S.show.heat && S.coverage) drawHeat();

    // 2. 户型图（透明 PNG，白线）
    if (planReady) {
      ctx.save();
      ctx.globalAlpha = S.show.walls ? 0.95 : 0;
      ctx.drawImage(planImg, 0, 0, PLAN, PLAN);
      ctx.restore();
    }

    // 3. 房间标注（标定模式改由 drawCalib 统一绘制，避免双份重叠）
    if (S.show.rooms && S.view !== 'calib') drawRooms();

    // 4. 关联连线
    if (S.show.links) drawLinks();

    // 5. 终端
    if (S.show.clients) drawClients();

    // 6. AP
    drawAps();

    // 6.5 标定模式叠加
    if (S.view === 'calib') drawCalib();

    // 7. AP 位置候选（搜索后显示）
    if (S.spots && S.spots.length) drawSpots();

    // 8. 实测打点
    if (S.measurePins && S.measurePins.length) drawMeasurePins();

    ctx.restore();
  }

  function drawGridBg() {
    const rect = canvas.getBoundingClientRect();
    const g = 40;
    ctx.save();
    ctx.strokeStyle = 'rgba(56,189,248,.045)';
    ctx.lineWidth = 1;
    const ox = S.panX % (g * S.zoom), oy = S.panY % (g * S.zoom);
    for (let x = ox; x < rect.width; x += g * S.zoom) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, rect.height); ctx.stroke();
    }
    for (let y = oy; y < rect.height; y += g * S.zoom) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(rect.width, y); ctx.stroke();
    }
    ctx.restore();
  }

  function drawHeat() {
    const res = S.covRes;
    const cov = S.coverage;
    const key = S.band + '|' + S.wallPreset + '|' + S.scenario + '|' +
                S.aps.map(a => a.id + a.x + ',' + a.y + ',' + (a.bands[S.band].enabled ? a.bands[S.band].ch + ':' + a.bands[S.band].width : 'off')).join(';');
    if (heatKey !== key || !heatCache) {
      const off = document.createElement('canvas');
      off.width = res; off.height = res;
      const octx = off.getContext('2d');
      const img = octx.createImageData(res, res);
      const d = img.data;
      for (let i = 0; i < cov.length; i++) {
        const v = cov[i];
        if (!isFinite(v)) continue;
        const c = RF.heatColor(v);
        const m = c.match(/(\d+),\s*(\d+),\s*(\d+)/);
        d[i * 4]     = +m[1];
        d[i * 4 + 1] = +m[2];
        d[i * 4 + 2] = +m[3];
        d[i * 4 + 3] = 200;
      }
      octx.putImageData(img, 0, 0);
      heatCache = off;
      heatKey = key;
    }
    ctx.save();
    ctx.globalAlpha = 0.82;
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(heatCache, 0, 0, PLAN, PLAN);
    ctx.restore();

    // 等信号线
    if (S.show.contour) drawContours();
  }

  function drawContours() {
    const res = S.covRes, cov = S.coverage;
    const levels = [-85, -80, -72, -65, -55];
    const cell = PLAN / res;
    ctx.save();
    ctx.lineWidth = 1.2 / S.zoom;
    ctx.strokeStyle = 'rgba(255,255,255,.42)';
    ctx.setLineDash([4 / S.zoom, 3 / S.zoom]);
    for (const lv of levels) {
      ctx.beginPath();
      for (let gy = 0; gy < res - 1; gy++) {
        for (let gx = 0; gx < res - 1; gx++) {
          const a = cov[gy * res + gx], b = cov[gy * res + gx + 1];
          const c = cov[(gy + 1) * res + gx];
          if (!isFinite(a)) continue;
          const x = (gx + 0.5) * cell, y = (gy + 0.5) * cell;
          if (isFinite(b) && (a - lv) * (b - lv) < 0) { ctx.moveTo(x + cell / 2, y); ctx.lineTo(x + cell / 2, y + cell * 0.6); }
          if (isFinite(c) && (a - lv) * (c - lv) < 0) { ctx.moveTo(x, y + cell / 2); ctx.lineTo(x + cell * 0.6, y + cell / 2); }
        }
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawRooms() {
    const rooms = S.rooms || [];
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const r of rooms) {
      const g = RF.grade(r.rssi);
      const fs = 9;
      // 标签锚点：房间框内偏上，且避开 AP 图钉
      // 扁房间（阳台）锚点放在框中央，避免标签溢出到图外
      const boxH = r.box[3] - r.box[1];
      let ax = r.cx, ay = boxH < 44 ? (r.box[1] + r.box[3]) / 2 - 2 : r.box[1] + 16;
      for (const a of S.aps) {
        if (Math.abs(a.x - ax) < 46 && Math.abs(a.y - ay) < 30) { ay = r.box[3] - 26; break; }
      }
      // 房间名
      ctx.font = `600 ${fs}px -apple-system, "PingFang SC", sans-serif`;
      ctx.fillStyle = 'rgba(8,13,24,.74)';
      const tw = ctx.measureText(r.name).width;
      roundRect(ax - tw / 2 - 4, ay - fs / 2 - 4, tw + 8, fs + 7, 3.5);
      ctx.fill();
      ctx.fillStyle = 'rgba(222,232,248,.94)';
      ctx.fillText(r.name, ax, ay - 1);
      // 数值
      ctx.font = `700 ${fs}px ui-monospace, monospace`;
      const txt = fmt(r.rssi, 0) + ' dBm';
      const tw2 = ctx.measureText(txt).width;
      ctx.fillStyle = 'rgba(8,13,24,.74)';
      roundRect(ax - tw2 / 2 - 4, ay + fs / 2 + 2, tw2 + 8, fs + 5, 3.5);
      ctx.fill();
      ctx.fillStyle = g.color;
      ctx.fillText(txt, ax, ay + fs / 2 + 6);
    }
    ctx.restore();
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawLinks() {
    const cl = S.clientCalcs || [];
    ctx.save();
    for (const c of cl) {
      const ap = S.aps.find(a => a.id === c.apId);
      if (!ap) continue;
      const g = RF.grade(c.rssi);
      ctx.beginPath();
      ctx.moveTo(ap.x, ap.y);
      ctx.lineTo(c.x, c.y);
      ctx.strokeStyle = g.color;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 1.4 / S.zoom;
      ctx.setLineDash([5 / S.zoom, 4 / S.zoom]);
      ctx.stroke();
      ctx.setLineDash([]);
      // 中点数值
      const mx = (ap.x + c.x) / 2, my = (ap.y + c.y) / 2;
      ctx.font = `600 8px ui-monospace, monospace`;
      const t = fmt(c.rssi, 0);
      const tw = ctx.measureText(t).width;
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = 'rgba(8,13,24,.85)';
      roundRect(mx - tw / 2 - 3, my - 6, tw + 6, 11, 3);
      ctx.fill();
      ctx.fillStyle = g.color;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(t, mx, my);
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  function drawClients() {
    const cl = S.clientCalcs || [];
    ctx.save();
    for (const c of cl) {
      const sel = S.sel && S.sel.type === 'cli' && S.sel.id === c.id;
      const g = RF.grade(c.rssi);
      const r = 5.2;
      // 光晕
      ctx.beginPath();
      ctx.arc(c.x, c.y, r + 3.5, 0, Math.PI * 2);
      ctx.fillStyle = g.color;
      ctx.globalAlpha = sel ? 0.34 : 0.18;
      ctx.fill();
      ctx.globalAlpha = 1;
      // 圆点：实测定位用绿色实心，模型推算用空心
      const isMeasured = !!c.measured;
      const measOk = isMeasured && c.measured.reliable !== false;
      ctx.beginPath();
      ctx.arc(c.x, c.y, r, 0, Math.PI * 2);
      if (isMeasured && measOk) {
        ctx.fillStyle = '#10b981';
        ctx.fill();
        ctx.lineWidth = 1.6 / S.zoom;
        ctx.strokeStyle = '#a7f3d0';
        ctx.stroke();
      } else if (isMeasured) {
        // 不可靠：黄色空心 + 不确定度圆环
        ctx.fillStyle = '#0b1220';
        ctx.fill();
        ctx.lineWidth = 1.8 / S.zoom;
        ctx.strokeStyle = '#fbbf24';
        ctx.stroke();
        const rad = (c.measured.spread_m || 2) * PPM;
        ctx.beginPath();
        ctx.arc(c.x, c.y, Math.min(rad, 260), 0, Math.PI * 2);
        ctx.setLineDash([4 / S.zoom, 4 / S.zoom]);
        ctx.strokeStyle = 'rgba(251,191,36,.35)';
        ctx.lineWidth = 1 / S.zoom;
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = '#0b1220';
        ctx.fill();
        ctx.lineWidth = 2 / S.zoom;
        ctx.strokeStyle = g.color;
        ctx.stroke();
      }
      // 小标
      ctx.font = `700 5.6px ui-monospace, monospace`;
      ctx.fillStyle = (isMeasured && measOk) ? '#04210f' : isMeasured ? '#fbbf24' : g.color;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(isMeasured ? (measOk ? '✓' : '?') : (c.band === '5' ? '5' : '2'), c.x, c.y + 0.3);
      if (sel) {
        ctx.beginPath();
        ctx.arc(c.x, c.y, r + 7, 0, Math.PI * 2);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.4 / S.zoom;
        ctx.stroke();
      }
      // 名称（避开 AP 附近，避免与 AP 标签重叠）
      let tooClose = false;
      for (const a of S.aps) {
        if (Math.hypot(a.x - c.x, a.y - c.y) < 34) { tooClose = true; break; }
      }
      if (!tooClose) {
        ctx.font = `600 7.4px -apple-system, "PingFang SC", sans-serif`;
        const tw = ctx.measureText(c.name).width;
        ctx.fillStyle = 'rgba(8,13,24,.8)';
        roundRect(c.x - tw / 2 - 3, c.y + r + 3, tw + 6, 10, 3);
        ctx.fill();
        ctx.fillStyle = sel ? '#7dd3fc' : 'rgba(200,215,235,.9)';
        ctx.fillText(c.name, c.x, c.y + r + 8.4);
      }
    }
    ctx.restore();
  }

  function drawAps() {
    ctx.save();
    for (const a of S.aps) {
      const sel = S.sel && S.sel.type === 'ap' && S.sel.id === a.id;
      const cfg = a.bands[S.band];
      const on = cfg && cfg.enabled !== false;
      const color = on ? RF.BANDS[S.band].color : '#475569';
      const R = 9;

      // 覆盖环（象征性，不代表真实范围）
      if (on) {
        ctx.beginPath();
        ctx.arc(a.x, a.y, R + 5, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.28;
        ctx.lineWidth = 1.5 / S.zoom;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      // 机身
      ctx.beginPath();
      ctx.arc(a.x, a.y, R, 0, Math.PI * 2);
      ctx.fillStyle = '#0b1220';
      ctx.fill();
      ctx.lineWidth = 2.4 / S.zoom;
      ctx.strokeStyle = color;
      ctx.stroke();

      // WiFi 图标
      ctx.save();
      ctx.translate(a.x, a.y + 2.2);
      ctx.strokeStyle = color;
      ctx.lineCap = 'round';
      ctx.lineWidth = 1.15;
      for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        ctx.arc(0, 0, 2 + i * 1.9, -Math.PI * 0.78, -Math.PI * 0.22);
        ctx.globalAlpha = 1 - i * 0.22;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(0, 0, 0.85, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();

      // 名称
      ctx.font = `700 8px -apple-system, "PingFang SC", sans-serif`;
      const tw = ctx.measureText(a.name).width;
      ctx.fillStyle = 'rgba(8,13,24,.86)';
      roundRect(a.x - tw / 2 - 4, a.y - R - 15, tw + 8, 11.5, 3.5);
      ctx.fill();
      ctx.fillStyle = sel ? '#7dd3fc' : '#e2e8f0';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(a.name, a.x, a.y - R - 9);

      if (sel) {
        ctx.beginPath();
        ctx.arc(a.x, a.y, R + 8, 0, Math.PI * 2);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.5 / S.zoom;
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawMeasurePins() {
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const p of S.measurePins) {
      const g = RF.grade(p.rssi);
      // 十字准星
      ctx.strokeStyle = g.color;
      ctx.lineWidth = 1.3 / S.zoom;
      const s = 5;
      ctx.beginPath();
      ctx.moveTo(p.x - s, p.y); ctx.lineTo(p.x + s, p.y);
      ctx.moveTo(p.x, p.y - s); ctx.lineTo(p.x, p.y + s);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = g.color;
      ctx.fill();
      // 数值
      ctx.font = `700 7.5px ui-monospace, monospace`;
      const t = String(p.rssi);
      const tw = ctx.measureText(t).width;
      ctx.fillStyle = 'rgba(8,13,24,.86)';
      roundRect(p.x - tw / 2 - 3, p.y + 6, tw + 6, 10, 3);
      ctx.fill();
      ctx.fillStyle = g.color;
      ctx.fillText(t, p.x, p.y + 11.2);
    }
    ctx.restore();
  }

  function drawSpots() {
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    S.spots.forEach((sp, i) => {
      const col = i === 0 ? '#22d3ee' : 'rgba(34,211,238,.62)';
      const R = i === 0 ? 11 : 9;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, R, 0, Math.PI * 2);
      ctx.setLineDash([4 / S.zoom, 3 / S.zoom]);
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.6 / S.zoom;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, R * 0.32, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
      ctx.font = `700 8px ui-monospace, monospace`;
      ctx.fillStyle = 'rgba(8,13,24,.85)';
      const t = String(i + 1);
      roundRect(sp.x - 5, sp.y - R - 12, 10, 10, 3);
      ctx.fill();
      ctx.fillStyle = col;
      ctx.fillText(t, sp.x, sp.y - R - 7);
      if (i === 0) {
        ctx.font = `700 7.6px -apple-system, "PingFang SC", sans-serif`;
        const lbl = '推荐补点';
        const tw = ctx.measureText(lbl).width;
        ctx.fillStyle = 'rgba(8,13,24,.85)';
        roundRect(sp.x - tw / 2 - 4, sp.y + R + 3, tw + 8, 11, 3.5);
        ctx.fill();
        ctx.fillStyle = col;
        ctx.fillText(lbl, sp.x, sp.y + R + 9);
      }
    });
    ctx.restore();
  }

  /* ============================================================
   * 拓扑视图
   * ============================================================ */
  function drawTopo() {
    const svg = $('#topoSvg');
    const rect = svg.getBoundingClientRect();
    const W = rect.width || 800, H = rect.height || 600;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const NS = 'http://www.w3.org/2000/svg';
    const mk = (t, attrs) => {
      const n = document.createElementNS(NS, t);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      return n;
    };
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const defs = mk('defs');
    defs.innerHTML = `
      <linearGradient id="gWan" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#1e3a5f"/><stop offset="1" stop-color="#122236"/>
      </linearGradient>
      <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="4" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>`;
    svg.appendChild(defs);

    const cx = W / 2;
    const rows = {
      wan:    { y: 62,  label: '联通 10G-EPON', sub: 'WAN 100.80.202.91 · CGNAT · 有 IPv6' },
      router: { y: 175, label: '光猫 HG5585F（ponwrt）', sub: '192.168.31.1 · 拨号 / DHCP / 透明代理' },
      ap:     { y: 300 },
      cli:    { y: 445 },
    };

    // ---- WAN 云 ----
    const wan = mk('g', {});
    wan.appendChild(mk('rect', { x: cx - 108, y: rows.wan.y - 30, width: 216, height: 58, rx: 12,
      fill: 'url(#gWan)', stroke: '#2a4a70', 'stroke-width': 1.4 }));
    const t1 = mk('text', { x: cx, y: rows.wan.y - 8, 'text-anchor': 'middle', fill: '#cfe0f5',
      'font-size': 13, 'font-weight': 600 });
    t1.textContent = rows.wan.label;
    const t2 = mk('text', { x: cx, y: rows.wan.y + 11, 'text-anchor': 'middle', fill: '#5b7fa6', 'font-size': 9.5 });
    t2.textContent = rows.wan.sub;
    wan.appendChild(t1); wan.appendChild(t2);
    svg.appendChild(wan);

    // ---- 主路由 ----
    const ont = S.aps.find(a => a.type === 'router') || S.aps[0];
    const router = mk('g', {});
    const rw = 250, rh = 66;
    router.appendChild(mk('rect', { x: cx - rw / 2, y: rows.router.y - rh / 2, width: rw, height: rh, rx: 12,
      fill: '#101b2e', stroke: '#38bdf8', 'stroke-width': 1.6, filter: 'url(#glow)' }));
    const r1 = mk('text', { x: cx, y: rows.router.y - 8, 'text-anchor': 'middle', fill: '#e6eefb', 'font-size': 13, 'font-weight': 600 });
    r1.textContent = ont ? ont.name : '主路由';
    const r2 = mk('text', { x: cx, y: rows.router.y + 10, 'text-anchor': 'middle', fill: '#7f9ec2', 'font-size': 9.5 });
    r2.textContent = ont ? (ont.ip + ' · ' + ont.model) : '';
    router.appendChild(r1); router.appendChild(r2);
    svg.appendChild(router);

    // WAN -> 路由 连线
    const lw = mk('line', { x1: cx, y1: rows.wan.y + 28, x2: cx, y2: rows.router.y - rh / 2 - 2,
      stroke: '#38bdf8', 'stroke-width': 2, opacity: .8 });
    svg.appendChild(lw);
    const lwl = mk('text', { x: cx + 8, y: (rows.wan.y + 28 + rows.router.y - rh / 2) / 2 + 3, fill: '#5b7fa6', 'font-size': 9 });
    lwl.textContent = 'PPPoE · VLAN 995';
    svg.appendChild(lwl);

    // ---- AP 层 ----
    const aps = S.aps.filter(a => a.type === 'ap');
    const apY = rows.ap.y;
    const apSpan = Math.min(W - 120, Math.max(360, aps.length * 230));
    const apPos = aps.map((a, i) => {
      const x = aps.length === 1 ? cx : cx - apSpan / 2 + (apSpan / (aps.length - 1 || 1)) * i;
      return { ap: a, x };
    });

    for (const { ap, x } of apPos) {
      const node = mk('g', {});
      const bw = 190, bh = 62;
      const color = RF.BANDS[S.band].color;
      node.appendChild(mk('rect', { x: x - bw / 2, y: apY - bh / 2, width: bw, height: bh, rx: 10,
        fill: '#0f1a2c', stroke: color, 'stroke-width': 1.4 }));
      const n1 = mk('text', { x, y: apY - 9, 'text-anchor': 'middle', fill: '#dbe7f8', 'font-size': 12, 'font-weight': 600 });
      n1.textContent = ap.name;
      const cfg = ap.bands[S.band];
      const n2 = mk('text', { x, y: apY + 8, 'text-anchor': 'middle', fill: '#7f9ec2', 'font-size': 9.5 });
      n2.textContent = ap.ip + ' · ' + (cfg ? `ch${cfg.ch}/${cfg.width}MHz` : '未启用');
      node.appendChild(n1); node.appendChild(n2);

      // 上行链路（有线 / 无线）
      const up = mk('path', {
        d: `M ${cx} ${rows.router.y + rh / 2} C ${cx} ${(rows.router.y + rh / 2 + apY - bh / 2) / 2}, ${x} ${(rows.router.y + rh / 2 + apY - bh / 2) / 2}, ${x} ${apY - bh / 2}`,
        fill: 'none', stroke: ap.wired ? '#22d3ee' : '#f59e0b', 'stroke-width': 2, opacity: .55,
        'stroke-dasharray': ap.wired ? '' : '5 4',
      });
      svg.appendChild(up);
      const ul = mk('text', { x: (cx + x) / 2 + 4, y: (rows.router.y + rh / 2 + apY - bh / 2) / 2 - 4,
        fill: ap.wired ? '#3b82a8' : '#b8860b', 'font-size': 8.5 });
      ul.textContent = ap.wired ? '有线回程' : '无线回程';
      svg.appendChild(ul);
      svg.appendChild(node);
    }

    // ---- 终端层 ----
    const cl = S.clientCalcs || [];
    const cliSpan = Math.min(W - 90, Math.max(320, cl.length * 128));
    cl.forEach((c, i) => {
      const x = cl.length === 1 ? cx : cx - cliSpan / 2 + (cliSpan / (cl.length - 1 || 1)) * i;
      const y = rows.cli.y + (i % 2) * 76;
      const ap = apPos.find(p => p.ap.id === c.apId);
      const g = RF.grade(c.rssi);
      if (ap) {
        const p = mk('path', {
          d: `M ${ap.x} ${apY + 31} C ${ap.x} ${(apY + 31 + y - 24) / 2}, ${x} ${(apY + 31 + y - 24) / 2}, ${x} ${y - 24}`,
          fill: 'none', stroke: g.color, 'stroke-width': 1.6, opacity: .5,
          'stroke-dasharray': '4 4',
        });
        svg.appendChild(p);
      }
      const node = mk('g', {});
      node.appendChild(mk('rect', { x: x - 56, y: y - 24, width: 112, height: 48, rx: 9,
        fill: '#0c1524', stroke: g.color, 'stroke-width': 1.3 }));
      const c1 = mk('text', { x, y: y - 8, 'text-anchor': 'middle', fill: '#d3e0f2', 'font-size': 10.5, 'font-weight': 600 });
      c1.textContent = c.name.length > 10 ? c.name.slice(0, 10) + '…' : c.name;
      const c2 = mk('text', { x, y: y + 6, 'text-anchor': 'middle', fill: g.color, 'font-size': 9.5, 'font-family': 'ui-monospace, monospace' });
      c2.textContent = `${fmt(c.rssi, 0)} dBm · ${c.tp} Mbps`;
      const c3 = mk('text', { x, y: y + 18, 'text-anchor': 'middle', fill: '#4d6383', 'font-size': 8.5 });
      c3.textContent = c.band === '5' ? '5 GHz' : '2.4 GHz';
      node.appendChild(c1); node.appendChild(c2); node.appendChild(c3);
      svg.appendChild(node);
    });
  }

  /* ============================================================
   * 面板渲染
   * ============================================================ */
  function renderAll() {
    renderApList();
    renderCliList();
    renderKpis();
    renderRoomTable();
    renderCliTable();
    renderChannels();
    renderIssues();
    if (S.view === 'topo') drawTopo();
    else draw();
  }

  function renderApList() {
    const box = $('#apList');
    box.innerHTML = '';
    $('#apCount').textContent = S.aps.length + ' 台';
    for (const a of S.aps) {
      const cfg = a.bands[S.band];
      const card = el('div', 'dev-card' + (S.sel && S.sel.type === 'ap' && S.sel.id === a.id ? ' sel' : ''));
      card.innerHTML = `
        <div class="top">
          <span class="dot" style="background:${cfg && cfg.enabled !== false ? RF.BANDS[S.band].color : '#475569'}"></span>
          <span class="nm">${esc(a.name)}</span>
          <button class="mini-btn" data-del="${a.id}" title="删除">✕</button>
        </div>
        <div class="meta">${esc(a.ip)}${a.wired ? ' · 有线' : ' · 无线'}</div>
        <div class="chips">
          ${a.bands['2.4'] ? `<span class="chip b2">2.4G ch${a.bands['2.4'].ch}/${a.bands['2.4'].width}</span>` : ''}
          ${a.bands['5'] ? `<span class="chip b5">5G ch${a.bands['5'].ch}/${a.bands['5'].width}</span>` : ''}
        </div>`;
      card.addEventListener('click', e => {
        if (e.target.dataset.del) {
          e.stopPropagation();
          if (S.aps.length <= 1) return toast('至少保留一台 AP');
          S.aps = S.aps.filter(x => x.id !== e.target.dataset.del);
          S.sel = null;
          S.spots = null;
          recompute();
          return;
        }
        S.sel = { type: 'ap', id: a.id };
        renderAll();
        openApEditor(a);
      });
      box.appendChild(card);
    }
  }

  function renderCliList() {
    const box = $('#cliList');
    box.innerHTML = '';
    $('#cliCount').textContent = S.clients.length + ' 台';
    for (const c of (S.clientCalcs || [])) {
      const g = RF.grade(c.rssi);
      const card = el('div', 'dev-card' + (S.sel && S.sel.type === 'cli' && S.sel.id === c.id ? ' sel' : ''));
      card.innerHTML = `
        <div class="top">
          <span class="dot" style="background:${g.color}"></span>
          <span class="nm">${esc(c.name)}</span>
        </div>
        <div class="meta">${fmt(c.rssi, 0)} dBm · ${c.tp} Mbps</div>
        <div class="chips">
          <span class="chip ${c.band === '5' ? 'b5' : 'b2'}">${c.band === '5' ? '5 GHz' : '2.4 GHz'}</span>
          <span class="chip">${esc(c.apName)}</span>
        </div>`;
      card.addEventListener('click', () => {
        S.sel = { type: 'cli', id: c.id };
        renderAll();
      });
      box.appendChild(card);
    }
  }

  function renderKpis() {
    const st = S.stats;
    if (!st) return;
    const band = RF.BANDS[S.band];
    const g = RF.grade(st.avg);
    const badge = $('#covBadge');
    badge.textContent = band.short + ' · ' + (st.p72 < 0.05 ? '达标' : st.p72 < 0.15 ? '基本达标' : '不足');
    badge.style.color = st.p72 < 0.05 ? '#34d399' : st.p72 < 0.15 ? '#fbbf24' : '#f87171';

    $('#kpis').innerHTML = `
      <div class="kpi"><div class="v" style="color:${g.color}">${fmt(st.avg, 0)}<small>dBm</small></div><div class="k">平均信号</div></div>
      <div class="kpi"><div class="v" style="color:${st.p72 < 0.05 ? '#34d399' : st.p72 < 0.15 ? '#fbbf24' : '#f87171'}">${(st.good * 100).toFixed(0)}<small>%</small></div><div class="k">≥ −72 dBm 覆盖</div></div>
      <div class="kpi"><div class="v">${(st.p80 * 100).toFixed(1)}<small>%</small></div><div class="k">死角（&lt; −80）</div></div>
      <div class="kpi"><div class="v">${S.aps.filter(a => a.bands[S.band] && a.bands[S.band].enabled !== false).length}<small>台</small></div><div class="k">在网 AP</div></div>`;
  }

  function renderRoomTable() {
    const tb = $('#roomTable');
    tb.innerHTML = '';
    for (const r of (S.rooms || [])) {
      const g = RF.grade(r.rssi);
      const tr = el('tr');
      tr.innerHTML = `
        <td class="name">${esc(r.name)}</td>
        <td style="color:${g.color}">${fmt(r.rssi, 0)}</td>
        <td>${r.tp}</td>
        <td style="color:var(--text-3);font-size:10px">${esc(r.ap.replace(/（.*?）/g, '').slice(0, 8))}</td>`;
      tb.appendChild(tr);
    }
  }

  function renderCliTable() {
    const tb = $('#cliTable');
    tb.innerHTML = '';
    for (const c of (S.clientCalcs || [])) {
      const g = RF.grade(c.rssi);
      const tr = el('tr');
      tr.innerHTML = `
        <td class="name">${esc(c.name)}</td>
        <td style="color:${c.band === '5' ? '#7dd3fc' : '#fbbf24'}">${c.band === '5' ? '5G' : '2.4G'}</td>
        <td style="color:${g.color}">${fmt(c.rssi, 0)}</td>
        <td>${c.tp}<span style="color:var(--text-3);font-size:9px"> Mbps</span></td>`;
      tb.appendChild(tr);
    }
  }

  function renderChannels() {
    const box = $('#chBody');
    const band = S.band;
    const aps = S.aps.filter(a => a.bands[band] && a.bands[band].enabled !== false);
    let html = '';
    // 条形占用图
    const chs = RF.BANDS[band].channels;
    const minCh = Math.min.apply(null, chs), maxCh = Math.max.apply(null, chs);
    html += `<div style="position:relative;height:52px;margin-bottom:8px;background:#0a1220;border:1px solid var(--line);border-radius:7px;overflow:hidden">`;
    aps.forEach((a, i) => {
      const cfg = a.bands[band];
      const half = (cfg.width / 5) / 2;
      const l = (cfg.ch - half - minCh) / (maxCh - minCh + 1) * 100;
      const w = (half * 2) / (maxCh - minCh + 1) * 100;
      const col = i === 0 ? '#38bdf8' : i === 1 ? '#a78bfa' : i === 2 ? '#34d399' : '#fbbf24';
      html += `<div title="${esc(a.name)} ch${cfg.ch}/${cfg.width}MHz"
        style="position:absolute;left:${l}%;width:${w}%;top:${6 + i * 13}px;height:9px;border-radius:3px;
        background:${col};opacity:.55;border:1px solid ${col}"></div>
        <div style="position:absolute;left:calc(${l}% + 4px);top:${6 + i * 13}px;font-size:8px;color:${col};line-height:9px;font-family:var(--mono)">${esc(a.name.slice(0, 6))} ch${cfg.ch}</div>`;
    });
    // 刻度
    const ticks = band === '5' ? [36, 64, 100, 128, 149, 165] : [1, 6, 11, 13];
    ticks.forEach(t => {
      const p = (t - minCh) / (maxCh - minCh + 1) * 100;
      html += `<div style="position:absolute;left:${p}%;bottom:0;top:0;width:1px;background:#1e2d4d"></div>
        <div style="position:absolute;left:${p}%;bottom:1px;font-size:8px;color:#4d6383;font-family:var(--mono);transform:translateX(-50%)">${t}</div>`;
    });
    html += `</div>`;

    // 重叠矩阵
    if (aps.length > 1) {
      html += `<table style="margin-top:2px"><thead><tr><th></th>`;
      aps.forEach(a => html += `<th style="font-size:9px">${esc(a.name.slice(0, 4))}</th>`);
      html += `</tr></thead><tbody>`;
      aps.forEach((a, i) => {
        html += `<tr><td class="name" style="font-size:10px">${esc(a.name.slice(0, 6))}</td>`;
        aps.forEach((b, j) => {
          if (i === j) { html += `<td style="color:var(--text-3)">—</td>`; return; }
          const ov = RF.overlapRatio(band, a.bands[band].ch, a.bands[band].width, b.bands[band].ch, b.bands[band].width);
          const col = ov > 0.5 ? '#f87171' : ov > 0.02 ? '#fbbf24' : '#34d399';
          html += `<td style="color:${col}">${ov > 0.02 ? (ov * 100).toFixed(0) + '%' : '无'}</td>`;
        });
        html += `</tr>`;
      });
      html += `</tbody></table>`;
    }
    html += `<div style="font-size:10.5px;color:var(--text-3);line-height:1.6;margin-top:8px;padding-top:8px;border-top:1px solid var(--line)">
      ${esc(RF.CH_HINTS[band])}</div>`;
    box.innerHTML = html;
  }

  function renderSpots(res, ms) {
    const box = $('#spotList');
    const badge = $('#spotBadge');
    if (!res || !res.candidates.length) {
      box.innerHTML = '没有找到合适位置。';
      return;
    }
    badge.textContent = res.candidates.length + ' 处候选 · ' + ms + 'ms';
    let html = `<div style="font-size:10.5px;color:var(--text-3);margin-bottom:8px">
      当前平均 <b style="color:var(--text-2)">${fmt(res.base.avg, 1)} dBm</b>。
      以下位置新增一台 AP（23 dBm）的收益排序：</div>`;
    res.candidates.forEach((c, i) => {
      const col = c.badRatio < 0.02 ? '#34d399' : c.badRatio < 0.08 ? '#fbbf24' : '#f87171';
      html += `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid rgba(30,45,77,.5)">
        <span style="width:17px;height:17px;border-radius:5px;background:rgba(56,189,248,.16);color:#38bdf8;
          display:grid;place-items:center;font-size:9.5px;font-weight:700;flex:0 0 auto">${i + 1}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:11px;color:var(--text)">(${Math.round(c.x)}, ${Math.round(c.y)})
            <span style="color:var(--text-3);font-size:9.5px">px</span></div>
          <div style="font-size:10px;color:var(--text-3);font-family:var(--mono)">
            平均 ${fmt(c.avg, 1)} dBm · 死角 <span style="color:${col}">${(c.badRatio * 100).toFixed(1)}%</span></div>
        </div>
        <span style="font-family:var(--mono);font-size:10.5px;color:${c.gain > 3 ? '#34d399' : '#8fa3c4'}">
          ${c.gain > 0 ? '+' : ''}${fmt(c.gain, 1)} dB</span>
      </div>`;
    });
    html += `<div style="font-size:10px;color:var(--text-3);margin-top:8px;line-height:1.6">
      选点约束：室内空地、离墙 ≥ 0.3 m。评分 = 平均提升×2 − 死角占比×100。
      实际安装还需考虑：<b style="color:var(--text-2)">有没有网线</b>（有线回程优先）、电源插座、以及家具遮挡。</div>`;
    box.innerHTML = html;
  }

  /* ---------------- 标定视图 ---------------- */
  function renderCalibList() {
    const box = $('#calibList');
    if (!box) return;
    box.innerHTML = '';
    DATA.ROOMS.forEach(r => {
      const row = el('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px';
      const sel = S.calibSel === r.id;
      row.innerHTML = `
        <input data-room="${r.id}" value="${esc(r.name)}"
          style="flex:1;min-width:0;background:${sel ? '#16213a' : '#0c1526'};
          border:1px solid ${sel ? '#38bdf8' : '#1e2d4d'};border-radius:6px;
          color:#dce6f7;padding:4px 7px;font-size:11px;font-family:inherit;outline:none">
        <span style="font-size:9.5px;color:#5b6f92;font-family:ui-monospace,monospace;flex:0 0 auto">
          ${Math.round((r.box[2] - r.box[0]) / PPM * 10) / 10}×${Math.round((r.box[3] - r.box[1]) / PPM * 10) / 10}m</span>`;
      const inp = row.querySelector('input');
      inp.oninput = e => { r.name = e.target.value; draw(); };
      // 只切高亮，不重建 DOM —— 重建会把正在输入的 input 销毁，打字丢失
      inp.onfocus = () => {
        if (S.calibSel === r.id) return;
        S.calibSel = r.id;
        Array.prototype.forEach.call(box.querySelectorAll('input'), n2 => {
          const on = n2.dataset.room === r.id;
          n2.style.background = on ? '#16213a' : '#0c1526';
          n2.style.borderColor = on ? '#38bdf8' : '#1e2d4d';
        });
        draw();
      };
      box.appendChild(row);
    });
  }

  function drawCalib() {
    // 在平面图上叠加可拖动的房间框
    ctx.save();
    DATA.ROOMS.forEach(r => {
      const on = S.calibSel === r.id;
      const [x0, y0, x1, y1] = r.box;
      ctx.beginPath();
      ctx.rect(x0, y0, x1 - x0, y1 - y0);
      ctx.strokeStyle = on ? '#38bdf8' : 'rgba(56,189,248,.35)';
      ctx.lineWidth = (on ? 2.2 : 1.3) / S.zoom;
      ctx.setLineDash(on ? [] : [5 / S.zoom, 4 / S.zoom]);
      ctx.stroke();
      ctx.setLineDash([]);
      if (on) {
        ctx.fillStyle = 'rgba(56,189,248,.09)';
        ctx.fill();
        // 四角手柄
        const hs = 7 / S.zoom;
        for (const [hx, hy] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) {
          ctx.beginPath();
          ctx.rect(hx - hs / 2, hy - hs / 2, hs, hs);
          ctx.fillStyle = '#38bdf8';
          ctx.fill();
        }
      }
      // 名字
      ctx.font = `600 9px -apple-system, "PingFang SC", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const tw = ctx.measureText(r.name).width;
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      ctx.fillStyle = 'rgba(8,13,24,.8)';
      roundRect(cx - tw / 2 - 4, cy - 7, tw + 8, 14, 3.5);
      ctx.fill();
      ctx.fillStyle = on ? '#7dd3fc' : 'rgba(200,215,235,.9)';
      ctx.fillText(r.name, cx, cy);
    });
    ctx.restore();
  }

  /* ============================================================
   * 实时信号：连本地 server.py，点房间即记录当前 RSSI
   * ============================================================ */
  const LIVE = { base: '', ok: false, timer: null, last: null };

  function liveBase() {
    // 用当前页面来源；file:// 打开时退回到手动填的地址
    if (location.protocol === 'http:' || location.protocol === 'https:') {
      return location.origin;
    }
    return localStorage.getItem('netplan/liveBase') || 'http://127.0.0.1:8787';
  }

  async function liveFetch(path, opts) {
    const base = liveBase();
    const url = base.replace(/\/$/, '') + path;
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), 25000);
    try {
      const r = await fetch(url, Object.assign({ signal: ctl.signal }, opts || {}));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } finally {
      clearTimeout(tid);
    }
  }

  async function liveConnect(silent) {
    const badge = $('#liveBadge');
    const info = $('#liveInfo');
    try {
      const p = await liveFetch('/api/ping');
      LIVE.ok = true;
      LIVE.base = liveBase();
      badge.textContent = '已连接';
      badge.style.color = '#34d399';
      $('#btnLiveMeasure').disabled = false;
      info.innerHTML = `<div style="font-size:10px;color:var(--text-3)">
        服务 ${esc(p.lan)} · 本机识别为 ${esc(p.client)}</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:3px">
        手机请打开 <b style="color:#7dd3fc">http://${esc(p.lan)}:${(liveBase().match(/:\d+/)||[':8787'])[0].slice(1)}/</b></div>`;
      if (!silent) toast('已连接路由器实时信号');
      // 连上后每 8 秒刷一次全屋概览
      if (!LIVE.timer) LIVE.timer = setInterval(livePoll, 8000);
      livePoll();
      return true;
    } catch (e) {
      LIVE.ok = false;
      badge.textContent = '离线';
      badge.style.color = '#f87171';
      $('#btnLiveMeasure').disabled = true;
      if (!silent) toast('连不上 server.py：' + e.message);
      return false;
    }
  }

  async function livePoll() {
    if (!LIVE.ok) return;
    try {
      const d = await liveFetch('/api/live');
      LIVE.last = d;
      renderLivePanel(d);
    } catch (e) { /* 静默 */ }
  }

  function renderLivePanel(d) {
    const info = $('#liveInfo');
    if (!info || !d) return;
    const devs = (d.devices || []).slice(0, 5);
    let html = `<div style="font-size:10px;color:var(--text-3);margin-bottom:5px">
      在线 ${d.count} 台 · ${esc((d.ts || '').slice(11, 19))}</div>`;
    for (const v of devs) {
      const obs = v.obs.map(o => `${o.ap.replace(/^(ONT|AP)-/, '')}${o.rssi}`).join(' ');
      html += `<div style="display:flex;gap:5px;font-size:10px;align-items:center">
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2)">${esc(v.name.slice(0, 22))}</span>
        <span style="font-family:var(--mono);color:${RF.grade(v.best.rssi).color}">${v.best.rssi}</span>
        <span style="font-family:var(--mono);color:#5b6f92;font-size:9px">${esc(obs)}</span>
      </div>`;
    }
    info.innerHTML = html;
  }

  /* 点房间/点图 -> 测当前这台设备的信号 */
  async function measureHere(x, y) {
    if (!LIVE.ok && !(await liveConnect(true))) {
      toast('先运行 python server.py，再点「连接」');
      return;
    }
    const room = roomAt(x, y);
    const box = $('#liveResult');
    box.innerHTML = `<div style="font-size:10px;color:#fbbf24">测量中…</div>`;
    try {
      const r = await liveFetch('/api/measure?room=' + encodeURIComponent(room ? room.name : ''),
                                { method: 'POST', body: JSON.stringify({ room: room ? room.name : '' }) });
      renderMeasureResult(r, room, x, y);
    } catch (e) {
      box.innerHTML = `<div style="font-size:10px;color:#f87171">测量失败：${esc(e.message)}</div>`;
    }
  }

  function roomAt(x, y) {
    for (const r of DATA.ROOMS) {
      const [x0, y0, x1, y1] = r.box;
      if (x >= x0 && x <= x1 && y >= y0 && y <= y1) return r;
    }
    return null;
  }

  function renderMeasureResult(r, room, x, y) {
    const box = $('#liveResult');
    if (!r.matched) {
      box.innerHTML = `<div style="font-size:10px;color:#fbbf24;line-height:1.5">${esc(r.hint || '没匹配到设备')}</div>`;
      return;
    }
    const d = r.device;
    const best = d.obs[0];
    const g = RF.grade(best.rssi);
    let html = `<div style="background:#0c1526;border:1px solid var(--line);border-radius:7px;padding:7px">
      <div style="display:flex;align-items:baseline;gap:6px">
        <span style="font-size:17px;font-weight:600;font-family:var(--mono);color:${g.color}">${best.rssi}</span>
        <span style="font-size:10px;color:var(--text-3)">dBm · ${esc(g.label)}</span>
      </div>
      <div style="font-size:10px;color:var(--text-2);margin-top:2px">${esc(room ? room.name : '未标定区域')}</div>
      <div style="font-size:9.5px;color:var(--text-3);margin-top:4px;font-family:var(--mono)">
        ${d.obs.map(o => `${esc(o.ap)} ch${o.ch}/${o.width} ${o.rssi}dBm`).join('<br>')}</div>
    </div>`;
    box.innerHTML = html;

    // 记录到实测点
    S.measureLog = S.measureLog || [];
    S.measureLog.push({
      ts: r.ts, room: room ? room.name : '', x, y,
      mac: d.mac, name: d.name,
      obs: d.obs, best: best,
    });
    // 图上打点
    S.measurePins = S.measurePins || [];
    S.measurePins.push({ x, y, rssi: best.rssi, ap: best.ap, room: room ? room.name : '' });
    draw();
    toast(`已记录：${room ? room.name : '点位'} ${best.rssi} dBm`);
  }

  /* ---------------- 实测数据：应用到终端 ---------------- */
  function applyMeasured(g) {
    if (!g || !g.devices) return;
    S.measured = g;
    // AP 位置也用实测里的（如果给了）
    if (g.apPos) {
      for (const a of S.aps) {
        const p = g.apPos[a.id] || g.apPos[a.name];
        if (Array.isArray(p) && p.length === 2) { a.x = p[0]; a.y = p[1]; }
      }
    }
    // 把实测到的终端塞进客户端列表（按 MAC 匹配，匹配不上则新增）
    const byMac = {};
    for (const c of S.clients) if (c.mac && c.mac !== '—') byMac[c.mac.toUpperCase()] = c;
    for (const d of g.devices) {
      const mac = (d.mac || '').toUpperCase();
      const hit = byMac[mac];
      if (hit) {
        hit.x = d.x; hit.y = d.y;
        hit.measured = d;
      } else {
        S.clients.push({
          id: 'm_' + mac.replace(/:/g, ''),
          name: d.name || mac,
          sub: '实测定位', ip: d.ip || '—', mac: mac,
          band: d.band === '2.4' ? '2.4' : '5',
          x: d.x, y: d.y, demand: 'mid', note: '由双 AP RSSI 反解',
          measured: d,
        });
      }
    }
    renderMeasuredPanel(g);
    heatKey = '';
    recompute();
  }

  function renderMeasuredPanel(g) {
    const badge = $('#measBadge');
    const info = $('#measInfo');
    if (!badge || !info) return;
    badge.textContent = (g.devices || []).length + ' 台';
    badge.style.color = '#34d399';
    let html = `<div style="font-size:10px;color:var(--text-3);margin-bottom:6px">
      生成于 ${esc((g.generated || '').slice(0, 19).replace('T', ' '))}</div>`;
    html += '<div style="display:flex;flex-direction:column;gap:5px">';
    for (const d of (g.devices || []).slice(0, 6)) {
      const ok = d.reliable !== false;
      const col = ok ? '#34d399' : '#fbbf24';
      const spread = d.spread_m ? ` ±${d.spread_m}m` : '';
      html += `<div style="display:flex;gap:6px;align-items:center;font-size:10px">
        <span style="color:${col};flex:0 0 auto">${ok ? '✓' : '?'}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2)">${esc(d.name || d.mac)}</span>
        <span style="font-family:var(--mono);color:${col}">${Math.round(d.x)},${Math.round(d.y)}${spread}</span>
      </div>`;
    }
    html += '</div>';
    const unreliable = (g.devices || []).filter(d => d.reliable === false).length;
    if (unreliable) {
      html += `<div style="font-size:9.5px;color:#fbbf24;margin-top:7px;line-height:1.55;
        background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.25);
        border-radius:6px;padding:6px">
        ${unreliable} 台定位不可靠：两台 AP 的 RSSI 差太小（&lt; 2 dB），
        解是一段圆弧而非一个点。让设备靠近其中一台 AP 重采，或走到户型对角再采，
        差值拉开到 6 dB 以上就准了。</div>`;
    }
    html += `<div style="font-size:9.5px;color:var(--text-3);margin-top:7px;line-height:1.55">
      实测定位点已用<span style="color:#34d399">绿色实心</span>标出，与模型推算的虚线轨迹对比即可校准 AP 坐标。</div>`;
    info.innerHTML = html;
  }

  function renderIssues() {
    const box = $('#issues');
    box.innerHTML = '';
    const cnt = { high: 0, mid: 0, low: 0 };
    S.issues.forEach(i => { if (cnt[i.sev] != null) cnt[i.sev]++; });
    const total = cnt.high + cnt.mid + cnt.low;
    const badge = $('#issueCount');
    badge.textContent = total ? `${total} 项` : '无';
    badge.style.color = cnt.high ? '#f87171' : cnt.mid ? '#fbbf24' : '#34d399';

    const ico = { high: '!', mid: '!', low: 'i', ok: '✓' };
    for (const i of S.issues) {
      const d = el('div', 'issue sev-' + i.sev);
      d.innerHTML = `<div class="ico">${ico[i.sev]}</div><div class="txt"><div class="t">${esc(i.t)}</div><div class="d">${i.d}</div></div>`;
      box.appendChild(d);
    }
  }

  /* ============================================================
   * AP 编辑器（侧滑面板，简单实现：用 toast + 快捷键 / 弹层）
   * ============================================================ */
  let editorEl = null;
  function openApEditor(ap) {
    closeEditor();
    const band = S.band;
    const cfg = ap.bands[band];
    if (!cfg) return;

    const box = el('div');
    box.style.cssText = `position:absolute;left:16px;top:58px;width:250px;z-index:30;
      background:rgba(13,20,36,.97);backdrop-filter:blur(14px);border:1px solid var(--line-2);
      border-radius:11px;padding:12px;box-shadow:var(--shadow)`;
    const chOpts = RF.BANDS[band].channels.map(c => `<option value="${c}" ${c === cfg.ch ? 'selected' : ''}>ch ${c}</option>`).join('');
    const wOpts = RF.BANDS[band].widths.map(w => `<option value="${w}" ${w === cfg.width ? 'selected' : ''}>${w} MHz</option>`).join('');
    box.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="font-size:12px;font-weight:600;flex:1">${esc(ap.name)}</span>
        <button class="mini-btn" id="edClose">关闭</button>
      </div>
      <div style="font-size:10px;color:var(--text-3);margin-bottom:10px;line-height:1.5">${esc(ap.role || '')}</div>
      <div style="display:grid;gap:8px">
        <label style="display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-2)">
          <input type="checkbox" id="edOn" ${cfg.enabled !== false ? 'checked' : ''}> 启用 ${RF.BANDS[band].label}
        </label>
        <div style="display:flex;gap:8px">
          <label style="flex:1;font-size:10px;color:var(--text-3)">信道<select id="edCh" style="width:100%;margin-top:3px">${chOpts}</select></label>
          <label style="flex:1;font-size:10px;color:var(--text-3)">带宽<select id="edW" style="width:100%;margin-top:3px">${wOpts}</select></label>
        </div>
        <label style="font-size:10px;color:var(--text-3)">发射功率 <span id="edTxV" style="color:var(--text)">${cfg.tx} dBm</span>
          <input type="range" id="edTx" min="5" max="30" step="1" value="${cfg.tx}" style="width:100%;margin-top:4px">
        </label>
      </div>
      <div style="font-size:9.5px;color:var(--text-3);margin-top:10px;padding-top:9px;border-top:1px solid var(--line);line-height:1.55">
        ${esc(ap.notes || '')}
      </div>`;
    document.querySelector('main').appendChild(box);
    editorEl = box;

    box.querySelector('#edClose').onclick = closeEditor;
    box.querySelector('#edOn').onchange = e => { cfg.enabled = e.target.checked; recompute(); };
    box.querySelector('#edCh').onchange = e => { cfg.ch = +e.target.value; recompute(); };
    box.querySelector('#edW').onchange = e => { cfg.width = +e.target.value; recompute(); };
    const tx = box.querySelector('#edTx');
    tx.oninput = e => {
      cfg.tx = +e.target.value;
      box.querySelector('#edTxV').textContent = cfg.tx + ' dBm';
    };
    tx.onchange = () => recompute();
  }
  function closeEditor() {
    if (editorEl && editorEl.parentNode) editorEl.parentNode.removeChild(editorEl);
    editorEl = null;
  }

  /* ============================================================
   * 交互
   * ============================================================ */
  let drag = null;

  function hitTest(px, py) {
    const tol = 16 / S.zoom;
    for (const a of S.aps) if (Math.hypot(a.x - px, a.y - py) < Math.max(tol, 12)) return { type: 'ap', obj: a };
    if (S.show.clients) {
      for (const c of (S.clientCalcs || [])) if (Math.hypot(c.x - px, c.y - py) < Math.max(tol, 10)) return { type: 'cli', obj: c };
    }
    // 标定模式：先判角点，再判房间体
    if (S.view === 'calib') {
      const ht = 12 / S.zoom;
      const r = DATA.ROOMS.find(x => x.id === S.calibSel);
      if (r) {
        const [x0, y0, x1, y1] = r.box;
        const corners = [['nw', x0, y0], ['ne', x1, y0], ['sw', x0, y1], ['se', x1, y1]];
        for (const [k, cx, cy] of corners) {
          if (Math.hypot(cx - px, cy - py) < Math.max(ht, 10)) return { type: 'corner', corner: k, obj: r };
        }
      }
      for (const rr of DATA.ROOMS) {
        const [x0, y0, x1, y1] = rr.box;
        if (px >= x0 && px <= x1 && py >= y0 && py <= y1) return { type: 'room', obj: rr };
      }
    }
    return null;
  }

  function stagePos(e) {
    const r = canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function bindStage() {
    const stage = $('#stage');

    stage.addEventListener('mousedown', e => {
      if (S.view !== 'plan') return;
      const [sx, sy] = stagePos(e);
      const [px, py] = toPlan(sx, sy);
      const hit = hitTest(px, py);
      if (hit && hit.type === 'corner') {
        S.calibSel = hit.obj.id;
        drag = { mode: 'corner', id: hit.obj.id, corner: hit.corner };
        stage.classList.add('dragging');
        renderCalibList();
        draw();
        e.preventDefault();
        return;
      }
      if (hit && hit.type === 'room') {
        S.calibSel = hit.obj.id;
        drag = null;
        renderCalibList();
        draw();
        e.preventDefault();
        return;
      }
      if (hit) {
        S.sel = { type: hit.type, id: hit.obj.id };
        drag = { mode: 'node', type: hit.type, id: hit.obj.id, dx: hit.obj.x - px, dy: hit.obj.y - py };
        stage.classList.add('dragging');
        renderAll();
        if (hit.type === 'ap') openApEditor(hit.obj); else closeEditor();
      } else {
        drag = { mode: 'pan', sx, sy, panX: S.panX, panY: S.panY, moved: false, px, py };
        stage.classList.add('dragging');
        S.sel = null;
        closeEditor();
        renderAll();
      }
      e.preventDefault();
    });

    window.addEventListener('mousemove', e => {
      if (!drag) return;
      const [sx, sy] = stagePos(e);
      if (drag.mode === 'pan') {
        const dx = sx - drag.sx, dy = sy - drag.sy;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) drag.moved = true;
        S.panX = drag.panX + dx;
        S.panY = drag.panY + dy;
        draw();
      } else if (drag.mode === 'corner') {
        const [px, py] = toPlan(sx, sy);
        const r = DATA.ROOMS.find(x => x.id === drag.id);
        if (r) {
          const b = r.box;
          const cx = RF.clamp(px, 8, PLAN - 8);
          const cy = RF.clamp(py, 8, PLAN - 8);
          if (drag.corner === 'nw') { b[0] = Math.min(cx, b[2] - 30); b[1] = Math.min(cy, b[3] - 30); }
          if (drag.corner === 'ne') { b[2] = Math.max(cx, b[0] + 30); b[1] = Math.min(cy, b[3] - 30); }
          if (drag.corner === 'sw') { b[0] = Math.min(cx, b[2] - 30); b[3] = Math.max(cy, b[1] + 30); }
          if (drag.corner === 'se') { b[2] = Math.max(cx, b[0] + 30); b[3] = Math.max(cy, b[1] + 30); }
        }
        draw();
      } else {
        const [px, py] = toPlan(sx, sy);
        const x = RF.clamp(px + drag.dx, 10, PLAN - 10);
        const y = RF.clamp(py + drag.dy, 10, PLAN - 10);
        if (drag.type === 'ap') {
          const ap = S.aps.find(a => a.id === drag.id);
          if (ap) { ap.x = x; ap.y = y; }
        } else {
          const c = S.clients.find(a => a.id === drag.id);
          if (c) { c.x = x; c.y = y; }
        }
        scheduleRecompute();
      }
    });

    window.addEventListener('mouseup', () => {
      if (!drag) return;
      const d = drag;
      drag = null;
      stage.classList.remove('dragging');
      if (d.mode === 'node') recompute();
      else if (d.mode === 'corner') { recompute(); renderCalibList(); }
      else if (d.mode === 'pan' && !d.moved && S.liveMeasureMode) {
        // 单击平面图 = 测这个点的当前信号
        measureHere(d.px, d.py);
      }
    });

    stage.addEventListener('wheel', e => {
      if (S.view !== 'plan') return;
      e.preventDefault();
      const [sx, sy] = stagePos(e);
      const [px, py] = toPlan(sx, sy);
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const nz = RF.clamp(S.zoom * factor, 0.3, 6);
      S.panX = sx - px * nz;
      S.panY = sy - py * nz;
      S.zoom = nz;
      $('#zoomVal').textContent = Math.round(S.zoom / (Math.min(canvas.getBoundingClientRect().width / PLAN, canvas.getBoundingClientRect().height / PLAN) * 0.94) * 100) + '%';
      draw();
    }, { passive: false });

    stage.addEventListener('dblclick', () => {
      fitTransform();
      $('#zoomVal').textContent = '100%';
      draw();
    });
  }

  let rafPending = false;
  function scheduleRecompute() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      recompute();
    });
  }

  /* ============================================================
   * 启动
   * ============================================================ */
  function init() {
    // 墙格 + 分类（用户型外轮廓多边形判定外墙 / 内墙）
    const lvl = decodeWalls(WALL_GRID);
    const W = RF.classifyWalls(lvl, GRID_N, {
      outline: DATA.OUTLINE, BW: 20, planPx: PLAN,
    });
    WALL.ray = W.cls;
    WALL.solid = W.solid;
    WALL.inside = W.inside;

    // 方案下拉
    const sel = $('#scenarioSel');
    DATA.SCENARIOS.forEach(s => {
      const o = document.createElement('option');
      o.value = s.id; o.textContent = s.name + ' — ' + s.desc;
      sel.appendChild(o);
    });
    sel.value = 'now';
    sel.onchange = () => {
      applyScenario(sel.value);
      heatKey = '';
      S.spots = null;
      $('#spotList').innerHTML = '点击下方按钮，在户型内枚举候选点并评估覆盖收益。';
      $('#spotBadge').textContent = '—';
      recompute();
      toast('已切换到：' + DATA.SCENARIOS.find(s => s.id === sel.value).name);
    };

    // 先恢复用户标定的房间名 / AP 位置，再套方案
    loadRoomOverrides();
    loadApOverrides();

    applyScenario('now');
    syncClients();

    // 视图切换
    $$('#viewSeg button').forEach(b => {
      b.onclick = () => {
        $$('#viewSeg button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        S.view = b.dataset.view;
        document.body.classList.toggle('topo', S.view === 'topo');
        document.body.classList.toggle('calib', S.view === 'calib');
        $('#calibCard').style.display = S.view === 'calib' ? '' : 'none';
        closeEditor();
        if (S.view === 'topo') { drawTopo(); }
        else { if (S.view === 'calib') renderCalibList(); draw(); }
      };
    });

    // 频段切换
    $$('#bandSeg button').forEach(b => {
      b.onclick = () => {
        $$('#bandSeg button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        S.band = b.dataset.band;
        heatKey = '';
        closeEditor();
        S.spots = null;
        $('#spotList').innerHTML = '点击下方按钮，在户型内枚举候选点并评估覆盖收益。';
        $('#spotBadge').textContent = '—';
        recompute();
      };
    });

    // 墙体
    $('#wallSel').onchange = e => {
      S.wallPreset = e.target.value;
      heatKey = '';
      recompute();
    };

    // 图层
    const map = { lyHeat: 'heat', lyClients: 'clients', lyLinks: 'links', lyRooms: 'rooms', lyWalls: 'walls', lyContour: 'contour' };
    Object.keys(map).forEach(id => {
      const cb = $('#' + id);
      cb.onchange = () => {
        S.show[map[id]] = cb.checked;
        if (map[id] === 'heat') heatKey = '';
        draw();
      };
    });

    // HUD
    $('#zoomIn').onclick = () => zoomBy(1.25);
    $('#zoomOut').onclick = () => zoomBy(1 / 1.25);
    $('#zoomFit').onclick = () => { fitTransform(); $('#zoomVal').textContent = '100%'; draw(); };

    bindStage();
    resize();
    fitTransform();
    recompute();

    window.addEventListener('resize', () => { resize(); if (S.view === 'topo') drawTopo(); });

    // 键盘
    window.addEventListener('keydown', e => {
      if (e.key === 'Escape') { S.sel = null; closeEditor(); renderAll(); }
    });

    // 标定房间
    $('#btnCalibSave').onclick = () => {
      saveRoomOverrides();
      syncApsToData();
      saveApOverrides();
      toast('已保存房间名与 AP 位置（存本机浏览器）');
      recompute();
    };
    $('#btnCalibReset').onclick = () => {
      if (!confirm('恢复默认房间名与范围？已保存的标定会被清除。')) return;
      resetRoomOverrides();
      location.reload();
    };

    // 实测数据导入
    $('#btnLoadGeo').onclick = () => $('#fileGeo').click();
    $('#fileGeo').onchange = ev => {
      const f = ev.target.files && ev.target.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = () => {
        try {
          const g = JSON.parse(rd.result);
          applyMeasured(g);
          toast('已导入 ' + (g.devices || []).length + ' 台实测定位');
        } catch (e) {
          toast('geo.json 解析失败：' + e.message);
        }
      };
      rd.readAsText(f, 'utf-8');
      ev.target.value = '';
    };

    // 实时信号
    S.liveMeasureMode = true;
    $('#btnLiveConnect').onclick = () => liveConnect(false);
    $('#btnLiveMeasure').onclick = () => {
      // 测「图中心」或上次点击位置；优先用最后一个测量点
      const last = (S.measurePins && S.measurePins.length) ? S.measurePins[S.measurePins.length - 1] : null;
      measureHere(last ? last.x : PLAN / 2, last ? last.y : PLAN / 2);
    };
    // 页面以 http 打开时自动连（file:// 打开则等用户点）
    if (location.protocol === 'http:' || location.protocol === 'https:') {
      liveConnect(true);
    }

    // 导出报告
    $('#btnReport').onclick = exportReport;

    // AP 位置推荐
    $('#btnSearch').onclick = () => {
      const btn = $('#btnSearch');
      btn.disabled = true;
      btn.textContent = '搜索中…';
      setTimeout(() => {
        const t0 = performance.now();
        const r = searchBestSpot({ step: 32, res: 64, top: 5 });
        const dt = Math.round(performance.now() - t0);
        S.spots = r.candidates;
        renderSpots(r, dt);
        draw();
        btn.disabled = false;
        btn.textContent = '重新搜索';
      }, 30);
    };

    // 提示淡出
    setTimeout(() => { const h = $('#hint'); if (h) h.style.opacity = '0.35'; }, 6000);
  }

  /* ============================================================
   * 导出报告：把当前布局 / 测算结果 / 实测值打包成 Markdown，
   * 便于贴回给 AI 做下一轮优化。
   * ============================================================ */
  function exportReport() {
    const band = S.band, st = S.stats;
    const L = [];
    const sc = DATA.SCENARIOS.find(x => x.id === S.scenario);

    L.push('# 家庭 Wi-Fi 覆盖评估报告');
    L.push('');
    L.push('> 生成时间：' + new Date().toLocaleString('zh-CN'));
    L.push('> 部署方案：' + (sc ? sc.name + '（' + sc.desc + '）' : S.scenario));
    L.push('> 墙体模型：' + RF.WALL_PRESETS[S.wallPreset].label +
           '（外墙 ' + RF.WALL_PRESETS[S.wallPreset].ext + ' dB / 内墙 ' +
           RF.WALL_PRESETS[S.wallPreset].int + ' dB）');
    L.push('> 频段：' + RF.BANDS[band].label);
    L.push('');
    L.push('## 1. 户型');
    L.push('');
    L.push('- 比例尺：80 px = 1 m（图幅 1020 × 1020 px ≈ 12.75 × 12.75 m）');
    L.push('- 房间 ' + DATA.ROOMS.length + ' 个，AP ' + S.aps.length + ' 台，终端 ' + S.clients.length + ' 台');
    L.push('');
    L.push('## 2. 接入点配置');
    L.push('');
    L.push('| 设备 | 型号 | IP | 位置 (px) | 2.4G | 5G | 回程 |');
    L.push('|---|---|---|---|---|---|---|');
    for (const a of S.aps) {
      const b2 = a.bands['2.4'], b5 = a.bands['5'];
      L.push('| ' + a.name + ' | ' + (a.model || '—') + ' | ' + a.ip + ' | ' +
        Math.round(a.x) + ',' + Math.round(a.y) + ' | ' +
        (b2 ? (b2.enabled === false ? '关' : 'ch' + b2.ch + '/' + b2.width + 'MHz/' + b2.tx + 'dBm') : '—') + ' | ' +
        (b5 ? (b5.enabled === false ? '关' : 'ch' + b5.ch + '/' + b5.width + 'MHz/' + b5.tx + 'dBm') : '—') + ' | ' +
        (a.wired ? '有线' : '无线') + ' |');
    }
    L.push('');
    L.push('## 3. 覆盖汇总（' + RF.BANDS[band].label + '）');
    L.push('');
    L.push('- 平均信号：' + fmt(st.avg, 1) + ' dBm');
    L.push('- ≥ −72 dBm 覆盖面积占比：' + (st.good * 100).toFixed(1) + '%');
    L.push('- < −80 dBm 死角占比：' + (st.p80 * 100).toFixed(1) + '%');
    L.push('- 采样格点：' + st.n + ' 个（' + S.covRes + '×' + S.covRes + ' 网格）');
    L.push('');
    L.push('## 4. 逐房间信号');
    L.push('');
    L.push('| 房间 | 中位 RSSI | 10 分位 | 预估速率 | 服务 AP |');
    L.push('|---|---|---|---|---|');
    for (const r of S.rooms) {
      L.push('| ' + r.name + ' | ' + fmt(r.rssi, 1) + ' dBm | ' + fmt(r.rssiWorst, 1) +
        ' dBm | ' + r.tp + ' Mbps | ' + r.ap + ' |');
    }
    L.push('');
    L.push('## 5. 终端关联');
    L.push('');
    L.push('| 终端 | 频段 | RSSI | 距离 | 穿墙 | 墙损耗 | 预估速率 | 服务 AP |');
    L.push('|---|---|---|---|---|---|---|---|');
    for (const c of S.clientCalcs) {
      L.push('| ' + c.name + ' | ' + (c.band === '5' ? '5G' : '2.4G') + ' | ' +
        fmt(c.rssi, 1) + ' dBm | ' + fmt(c.dist, 2) + ' m | ' + c.walls + ' | ' +
        fmt(c.wallLoss, 1) + ' dB | ' + c.tp + ' Mbps | ' + c.apName + ' |');
    }
    L.push('');
    L.push('## 6. 信道规划');
    L.push('');
    L.push('| AP | 频段 | 信道 | 带宽 | 发射功率 |');
    L.push('|---|---|---|---|---|');
    for (const a of S.aps) {
      for (const bk of ['2.4', '5']) {
        const cfg = a.bands[bk];
        if (!cfg || cfg.enabled === false) continue;
        L.push('| ' + a.name + ' | ' + (bk === '5' ? '5G' : '2.4G') + ' | ch' + cfg.ch +
          ' | ' + cfg.width + ' MHz | ' + cfg.tx + ' dBm |');
      }
    }
    L.push('');
    const aps = S.aps.filter(a => a.bands[band] && a.bands[band].enabled !== false);
    if (aps.length > 1) {
      L.push('信道重叠：');
      for (let i = 0; i < aps.length; i++) {
        for (let j = i + 1; j < aps.length; j++) {
          const A = aps[i].bands[band], B = aps[j].bands[band];
          const ov = RF.overlapRatio(band, A.ch, A.width, B.ch, B.width);
          L.push('- ' + aps[i].name + ' ↔ ' + aps[j].name + '：' +
            (ov > 0.02 ? (ov * 100).toFixed(0) + '% 重叠' : '无重叠 ✓'));
        }
      }
      L.push('');
    }
    L.push('## 7. 诊断与建议');
    L.push('');
    for (const i of S.issues) {
      const tag = { high: '🔴 高', mid: '🟠 中', low: '🔵 低', ok: '🟢 正常' }[i.sev] || i.sev;
      L.push('### [' + tag + '] ' + i.t);
      L.push('');
      L.push(i.d.replace(/<code>/g, '`').replace(/<\/code>/g, '`').replace(/<[^>]+>/g, ''));
      L.push('');
    }
    L.push('## 8. 实测数据回填区');
    L.push('');
    L.push('> 用手机在各房间实测后填这里，下一轮优化会以实测为准（当前为模型推算）。');
    L.push('');
    L.push('| 房间 | 实测 RSSI | 实测速率 | 备注 |');
    L.push('|---|---|---|---|');
    for (const r of S.rooms) L.push('| ' + r.name + ' |  |  |  |');
    L.push('');
    L.push('---');
    L.push('');
    L.push('*本报告由「户型网络规划器」生成。传播模型：多墙模型 ' +
           'PL = ' + RF.BANDS[band].fspl1 + ' + 10·' + RF.BANDS[band].n + '·log10(d) + Σ墙损耗；' +
           '速率由 SNR 映射 802.11ax 2×2 MIMO MCS 表，吞吐取物理层 50%。*');

    const md = L.join('\n');
    downloadFile('wifi-report-' + new Date().toISOString().slice(0, 10) + '.md', md, 'text/markdown');
    toast('报告已导出（Markdown），可直接贴回给 AI 做下一轮优化');
  }

  function downloadFile(name, text, mime) {
    const blob = new Blob([text], { type: (mime || 'text/plain') + ';charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }

  function zoomBy(f) {
    const rect = canvas.getBoundingClientRect();
    const sx = rect.width / 2, sy = rect.height / 2;
    const [px, py] = toPlan(sx, sy);
    const nz = RF.clamp(S.zoom * f, 0.3, 6);
    S.panX = sx - px * nz;
    S.panY = sy - py * nz;
    S.zoom = nz;
    draw();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();
