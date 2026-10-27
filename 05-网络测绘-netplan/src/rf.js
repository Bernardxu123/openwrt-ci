/* ============================================================
 * rf.js — 室内射频传播模型（多墙模型）
 * 纯函数，无 DOM 依赖；浏览器挂 window.RF，node 下可 require
 * 坐标系：平面图像素（0..planPx，默认 1020）
 * ============================================================ */
var RF = (function () {
  'use strict';

  const BANDS = {
    '2.4': {
      key: '2.4', label: '2.4 GHz', short: '2.4G',
      fspl1: 40.05, n: 2.7, eirp: 20, noise: -92,
      widths: [20, 40], defaultWidth: 20,
      channels: [1,2,3,4,5,6,7,8,9,10,11,12,13],
      color: '#f59e0b',
      note: '穿墙强、速率低、干扰重。适合兜底覆盖，但只用 20 MHz。',
    },
    '5': {
      key: '5', label: '5 GHz', short: '5G',
      fspl1: 46.42, n: 3.2, eirp: 23, noise: -95,
      widths: [20, 40, 80, 160], defaultWidth: 80,
      channels: [36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,
                 132,136,140,144,149,153,157,161,165],
      color: '#3b82f6',
      note: '速率高、穿墙差。80 MHz 是覆盖与速率的平衡点。',
    },
  };

  const WALL_PRESETS = {
    light: { key:'light', label:'轻质隔墙（石膏板 / 轻钢龙骨）', ext:6,  int:3,  win:2 },
    brick: { key:'brick', label:'砖墙（默认）',                  ext:12, int:6,  win:3 },
    heavy: { key:'heavy', label:'承重墙 / 混凝土',               ext:20, int:12, win:4 },
  };

  const BAND_LOSS_MULT = { '2.4': 1.0, '5': 1.55 };
  const W_NONE = 0, W_INT = 1, W_EXT = 2, W_WIN = 3;

  const clamp = (v, a, b) => v < a ? a : (v > b ? b : v);

  function pathLoss(bandKey, dMeters) {
    const b = BANDS[bandKey];
    return b.fspl1 + 10 * b.n * Math.log10(Math.max(dMeters, 0.5));
  }

  /* ---------- 形态学辅助 ---------- */
  function dilate(src, N, R) {
    const out = new Uint8Array(N * N);
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        if (!src[y * N + x]) continue;
        const y0 = Math.max(0, y - R), y1 = Math.min(N - 1, y + R);
        const x0 = Math.max(0, x - R), x1 = Math.min(N - 1, x + R);
        for (let yy = y0; yy <= y1; yy++) {
          const row = yy * N;
          for (let xx = x0; xx <= x1; xx++) out[row + xx] = 1;
        }
      }
    }
    return out;
  }

  function erode(src, N, R) {
    const out = new Uint8Array(N * N);
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        let v = 1;
        const y0 = Math.max(0, y - R), y1 = Math.min(N - 1, y + R);
        const x0 = Math.max(0, x - R), x1 = Math.min(N - 1, x + R);
        for (let yy = y0; yy <= y1 && v; yy++) {
          const row = yy * N;
          for (let xx = x0; xx <= x1; xx++) if (!src[row + xx]) { v = 0; break; }
        }
        out[y * N + x] = v;
      }
    }
    return out;
  }

  /* 从图边界洪泛（4 邻域），src 为可通行掩码 */
  function floodFromBorder(passable, N) {
    const seen = new Uint8Array(N * N);
    const stack = [];
    for (let x = 0; x < N; x++) { stack.push(x, 0); stack.push(x, N - 1); }
    for (let y = 0; y < N; y++) { stack.push(0, y); stack.push(N - 1, y); }
    while (stack.length) {
      const y = stack.pop(), x = stack.pop();
      if (x < 0 || y < 0 || x >= N || y >= N) continue;
      const i = y * N + x;
      if (seen[i] || !passable[i]) continue;
      seen[i] = 1;
      stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
    }
    return seen;
  }

  /* ---------- 多边形光栅化（扫描线填充） ---------- */
  function rasterPolygon(poly, N, planPx) {
    const k = N / planPx;
    const pts = poly.map(p => [p[0] * k, p[1] * k]);
    const mask = new Uint8Array(N * N);
    for (let y = 0; y < N; y++) {
      const yc = y + 0.5;
      const xs = [];
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const yi = pts[i][1], yj = pts[j][1];
        if ((yi > yc) !== (yj > yc)) {
          xs.push(pts[i][0] + (yc - yi) * (pts[j][0] - pts[i][0]) / (yj - yi));
        }
      }
      xs.sort((a, b) => a - b);
      for (let i = 0; i + 1 < xs.length; i += 2) {
        const x0 = Math.max(0, Math.ceil(xs[i] - 0.5));
        const x1 = Math.min(N - 1, Math.floor(xs[i + 1] - 0.5));
        for (let x = x0; x <= x1; x++) mask[y * N + x] = 1;
      }
    }
    return mask;
  }

  /* 多边形边 -> 掩码（Bresenham） */
  function rasterPolygonEdges(poly, N, planPx) {
    const k = N / planPx;
    const pts = poly.map(p => [Math.round(p[0] * k), Math.round(p[1] * k)]);
    const mask = new Uint8Array(N * N);
    const put = (x, y) => { if (x >= 0 && y >= 0 && x < N && y < N) mask[y * N + x] = 1; };
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      let x0 = pts[j][0], y0 = pts[j][1];
      const x1 = pts[i][0], y1 = pts[i][1];
      const dx = Math.abs(x1 - x0), dy = Math.abs(y1 - y0);
      const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
      let err = dx - dy;
      for (let guard = 0; guard < 4000; guard++) {
        put(x0, y0);
        if (x0 === x1 && y0 === y1) break;
        const e2 = 2 * err;
        if (e2 > -dy) { err -= dy; x0 += sx; }
        if (e2 < dx) { err += dx; y0 += sy; }
      }
    }
    return mask;
  }

  /* 倒角距离变换（两遍扫描，欧氏近似） */
  function distanceTransform(seed, N) {
    const INF = 1e9;
    const d = new Float32Array(N * N);
    for (let i = 0; i < d.length; i++) d[i] = seed[i] ? 0 : INF;
    const D1 = 1, D2 = Math.SQRT2;
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        const i = y * N + x;
        let v = d[i];
        if (y > 0) v = Math.min(v, d[i - N] + D1);
        if (x > 0) v = Math.min(v, d[i - 1] + D1);
        if (x > 0 && y > 0) v = Math.min(v, d[i - N - 1] + D2);
        if (x < N - 1 && y > 0) v = Math.min(v, d[i - N + 1] + D2);
        d[i] = v;
      }
    }
    for (let y = N - 1; y >= 0; y--) {
      for (let x = N - 1; x >= 0; x--) {
        const i = y * N + x;
        let v = d[i];
        if (y < N - 1) v = Math.min(v, d[i + N] + D1);
        if (x < N - 1) v = Math.min(v, d[i + 1] + D1);
        if (x < N - 1 && y < N - 1) v = Math.min(v, d[i + N + 1] + D2);
        if (x > 0 && y < N - 1) v = Math.min(v, d[i + N - 1] + D2);
        d[i] = v;
      }
    }
    return d;
  }

  /* ---------- 墙体分类：内墙 / 外墙 ----------
   * 用「户型外轮廓多边形」判定：距轮廓线 BW 格以内的墙 = 外墙，
   * 轮廓以外的墙（阳台栏板等）= 外墙，其余 = 内墙。 */
  function classifyWalls(wallLvl, N, opts) {
    opts = opts || {};
    const BW = opts.BW || 20;
    const poly = opts.outline;
    const planPx = opts.planPx || 1020;

    const raw = new Uint8Array(N * N);
    for (let i = 0; i < raw.length; i++) raw[i] = wallLvl[i] > 0 ? 1 : 0;
    // 3x3 闭运算：把双线墙之间的白缝填实
    const solid = erode(dilate(raw, N, 1), N, 1);

    let band = null, inside = null;
    if (poly && poly.length > 2) {
      inside = rasterPolygon(poly, N, planPx);
      const edge = rasterPolygonEdges(poly, N, planPx);
      const dist = distanceTransform(edge, N);
      band = new Uint8Array(N * N);
      for (let i = 0; i < band.length; i++) band[i] = dist[i] <= BW ? 1 : 0;
    }

    const cls = new Uint8Array(N * N);
    for (let i = 0; i < solid.length; i++) {
      if (!solid[i]) { cls[i] = W_NONE; continue; }
      if (!inside) { cls[i] = W_INT; continue; }
      cls[i] = (band[i] || !inside[i]) ? W_EXT : W_INT;
    }
    // 射线专用的「加厚墙」：每格取 3x3 邻域最大等级。
    // 目的：1 格厚的墙不会被斜射线从缝里漏过，也不会因邻域兜底把
    //       一段墙拆成多段（后者会让穿墙数虚高、损耗爆掉）。
    const ray = new Uint8Array(N * N);
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        let m = 0;
        for (let dy = -1; dy <= 1; dy++) {
          const ny = y + dy;
          if (ny < 0 || ny >= N) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const nx = x + dx;
            if (nx < 0 || nx >= N) continue;
            const v = cls[ny * N + nx];
            if (v > m) m = v;
          }
        }
        ray[y * N + x] = m;
      }
    }
    return { cls: cls, ray: ray, solid: solid, inside: inside, band: band };
  }

  /* ---------- 沿线段累计穿墙损耗（连续墙段只计一次） ----------
   * cls 传「加厚墙」（RF.classifyWalls 返回的 ray），保证斜射线不漏缝。 */
  function segmentWallLoss(cls, N, x0, y0, x1, y1, bandKey, preset) {
    const mult = BAND_LOSS_MULT[bandKey] || 1;
    const dx = x1 - x0, dy = y1 - y0;
    const len = Math.hypot(dx, dy);
    const steps = Math.max(2, Math.ceil(len * 1.6));
    let loss = 0, crossings = 0;
    let prev = W_NONE, runKind = W_NONE;
    function settle() {
      if (runKind === W_EXT) loss += preset.ext * mult;
      else if (runKind === W_INT) loss += preset.int * mult;
      else if (runKind === W_WIN) loss += preset.win * mult;
      runKind = W_NONE;
    }
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const x = Math.round(x0 + dx * t), y = Math.round(y0 + dy * t);
      let c = W_NONE;
      if (x >= 0 && y >= 0 && x < N && y < N) c = cls[y * N + x];
      if (c !== W_NONE && prev === W_NONE) { crossings++; runKind = c; }
      else if (c !== W_NONE) {
        if (c === W_WIN) runKind = W_WIN;
        else if (runKind !== W_WIN && c > runKind) runKind = c;
      } else if (c === W_NONE && prev !== W_NONE) settle();
      prev = c;
    }
    if (prev !== W_NONE) settle();
    return { loss: loss, crossings: crossings };
  }

  /* ---------- 单链路（planPx 空间） ---------- */
  function link(cls, N, ap, x, y, bandKey, preset, mPerPx, planPx) {
    planPx = planPx || 1020;
    const k = N / planPx;
    const dM = Math.max(Math.hypot(x - ap.x, y - ap.y) * mPerPx, 0.4);
    const w = segmentWallLoss(cls, N, ap.x * k, ap.y * k, x * k, y * k, bandKey, preset);
    const band = BANDS[bandKey];
    const eirp = (ap.tx == null ? band.eirp : ap.tx);
    return {
      rssi: eirp - pathLoss(bandKey, dM) - w.loss,
      dist: dM, wallLoss: w.loss, walls: w.crossings,
    };
  }

  /* ---------- 覆盖热力图 ---------- */
  function coverage(opts) {
    const cls = opts.cls, N = opts.N, aps = opts.aps, res = opts.res;
    const bandKey = opts.bandKey, preset = opts.preset;
    const mPerPx = opts.mPerPx, planPx = opts.planPx || 1020;
    const inside = opts.inside;                 // (x,y) => bool，plan 像素
    const band = BANDS[bandKey];
    const out = new Float32Array(res * res).fill(NaN);
    const k = N / planPx;
    const step = planPx / res;
    // 判定可用性：必须在室内、非墙体，且周围 2 格内无墙（避免墙边伪低值）
    const usable = (sx, sy) => {
      if (sx < 2 || sy < 2 || sx >= N - 2 || sy >= N - 2) return false;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          if (cls[(sy + dy) * N + sx + dx] !== W_NONE) return false;
        }
      }
      return true;
    };
    for (let gy = 0; gy < res; gy++) {
      const py = (gy + 0.5) * step;
      for (let gx = 0; gx < res; gx++) {
        const px = (gx + 0.5) * step;
        if (inside && !inside(px, py)) continue;
        const sx = Math.round(px * k), sy = Math.round(py * k);
        if (!usable(sx, sy)) continue;
        let best = -Infinity;
        for (let i = 0; i < aps.length; i++) {
          const ap = aps[i];
          if (ap.enabled === false) continue;
          const dM = Math.max(Math.hypot(px - ap.x, py - ap.y) * mPerPx, 0.4);
          const w = segmentWallLoss(cls, N, ap.x * k, ap.y * k, sx, sy, bandKey, preset);
          const eirp = (ap.tx == null ? band.eirp : ap.tx);
          const r = eirp - pathLoss(bandKey, dM) - w.loss;
          if (r > best) best = r;
        }
        out[gy * res + gx] = best;
      }
    }
    return out;
  }

  /* ---------- SNR -> PHY 速率（2x2 MIMO, 802.11ax 近似） ---------- */
  const MCS20 = [
    [2,8.6],[4,17.2],[6,25.8],[8,34.4],[10,51.6],[12,77.4],[14,103.2],
    [16,114.7],[18,129.0],[20,143.4],[22,172.1],[24,200.7],[26,229.4],
    [28,258.1],[30,286.8],[32,344.1],[34,400.0],[36,458.0],
  ];

  function phyRate(bandKey, width, snrDb) {
    if (snrDb < 2) return 0;
    let rate = 0;
    for (let i = 0; i < MCS20.length; i++) if (snrDb >= MCS20[i][0]) rate = MCS20[i][1];
    if (!rate) return 0;
    const mult = width / 20;
    const eff = width >= 160 ? 0.80 : width >= 80 ? 0.88 : width >= 40 ? 0.94 : 1;
    return Math.round(rate * mult * eff);
  }

  const snrOf = (bandKey, r) => r - BANDS[bandKey].noise;
  const throughput = (bandKey, width, r) =>
    Math.round(phyRate(bandKey, width, snrOf(bandKey, r)) * 0.5);

  function grade(r) {
    if (!isFinite(r)) return { key:'none', label:'无信号', color:'#64748b' };
    if (r >= -55) return { key:'excellent', label:'极佳', color:'#10b981' };
    if (r >= -65) return { key:'good',      label:'良好', color:'#84cc16' };
    if (r >= -72) return { key:'fair',      label:'可用', color:'#f59e0b' };
    if (r >= -80) return { key:'weak',      label:'较弱', color:'#f97316' };
    return { key:'bad', label:'不可用', color:'#ef4444' };
  }

  function heatColor(r) {
    if (!isFinite(r)) return null;
    const t = clamp((r + 88) / 48, 0, 1);
    const stops = [
      [0.00, [239, 68, 68]],
      [0.26, [249, 115, 22]],
      [0.44, [250, 204, 21]],
      [0.62, [163, 230, 53]],
      [0.80, [16, 185, 129]],
      [1.00, [14, 165, 233]],
    ];
    for (let i = 0; i < stops.length - 1; i++) {
      const t0 = stops[i][0], c0 = stops[i][1];
      const t1 = stops[i+1][0], c1 = stops[i+1][1];
      if (t >= t0 && t <= t1) {
        const k = (t - t0) / (t1 - t0);
        return 'rgb(' + Math.round(c0[0]+(c1[0]-c0[0])*k) + ',' +
                        Math.round(c0[1]+(c1[1]-c0[1])*k) + ',' +
                        Math.round(c0[2]+(c1[2]-c0[2])*k) + ')';
      }
    }
    return 'rgb(14,165,233)';
  }

  /* ---------- 信道重叠 ---------- */
  function overlapRatio(bandKey, chA, wA, chB, wB) {
    const half = w => (w / 5) / 2;
    const lo = Math.max(chA - half(wA), chB - half(wB));
    const hi = Math.min(chA + half(wA), chB + half(wB));
    if (hi <= lo) return 0;
    return clamp(((hi - lo) * 5) / Math.min(wA, wB), 0, 1);
  }

  /* 5G 80MHz 所属组（0..5），2.4G 返回 -1 */
  function chGroup(bandKey, ch) {
    if (bandKey !== '5') return -1;
    const g = [[36,48],[52,64],[100,112],[116,128],[132,144],[149,161]];
    for (let i = 0; i < g.length; i++) if (ch >= g[i][0] && ch <= g[i][1]) return i;
    return -1;
  }

  /* 点是否在多边形内 */
  function pointInPoly(x, y, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i][0], yi = poly[i][1];
      const xj = poly[j][0], yj = poly[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }

  const CH_HINTS = {
    '2.4': '只有 1 / 6 / 11 三个 20 MHz 信道互不重叠；40 MHz 会吃掉整个频段。',
    '5': '80 MHz 可用 36-48 / 100-128 / 149-161 三组；相邻 AP 各占一组即互不干扰。',
  };

  return {
    BANDS, WALL_PRESETS, BAND_LOSS_MULT,
    W_NONE, W_INT, W_EXT, W_WIN,
    clamp, pathLoss, dilate, erode, classifyWalls, segmentWallLoss,
    link, coverage, phyRate, throughput, snrOf, grade, heatColor,
    overlapRatio, chGroup, pointInPoly, CH_HINTS,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = RF;
