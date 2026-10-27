/* ============================================================
 * data.js — 户型房间 / 现网设备 / 默认方案
 * 坐标：平面图像素空间（0..1020），80 px = 1 m
 * ============================================================ */
var DATA = (function () {
  'use strict';

  const PLAN_PX = 1020;
  const PX_PER_M = 80;

  /* 房间：矩形 [x0,y0,x1,y1]（内空区域，近似到墙内表面）
   * 依据：扫描图墙体提取 + 图纸标注（TOILET / W.C / 厨）
   * 说明：这是「评估区域」，用于热力图遮罩与逐房间统计，
   *       与墙体的精确位置无关（墙体来自扫描图自动提取）。 */
  const ROOMS = [
    { id:'bed_nw',  name:'厨房',           box:[316, 62, 460, 316],  kind:'kitchen' },
    { id:'bed_n',   name:'外厕所',         box:[486, 112, 610, 250], kind:'bath'    },
    { id:'bath_m',  name:'洗漱区',         box:[486, 268, 610, 344], kind:'bath'    },
    { id:'bed_ne',  name:'工作室（榻榻米）', box:[646, 112, 828, 330], kind:'study'  },
    { id:'kit',     name:'工作室飘窗',     box:[676, 48, 794, 96],   kind:'bay'     },
    { id:'bed_e',   name:'内厕所',         box:[752, 348, 908, 498], kind:'bath'    },
    { id:'living',  name:'主卧',           box:[648, 522, 908, 914], kind:'bedroom' },
    { id:'balc_s',  name:'主卧飘窗',       box:[708, 948, 858, 974], kind:'bay'     },
    { id:'dining',  name:'客厅',           box:[316, 362, 610, 832], kind:'living'  },
    { id:'hall_c',  name:'过道（东）',     box:[652, 356, 700, 502], kind:'hall'    },
    { id:'bed_sw',  name:'次卧',           box:[ 72, 576, 290, 840], kind:'bedroom' },
    { id:'balc_w',  name:'西阳台',         box:[ 78, 868, 246, 898], kind:'balcony' },
    { id:'bath_sw', name:'卫生间（西南）', box:[216, 524, 290, 546], kind:'bath'    },
    { id:'entry',   name:'玄关',           box:[216, 356, 290, 466], kind:'hall'    },
  ];

  /* 户型整体外轮廓（用于绘制描边与面积估算） */
  /* 户型外轮廓（顺时针，plan 像素）。沿墙体中线走一圈，
   * 包含：北侧三间 + 厨房凸出、东侧客厅 + 南阳台、西侧主卧 + 西阳台、
   * 中部玄关凸出。用于判定「室内 / 室外」与外墙带。 */
  const OUTLINE = [
    [290, 36],   // 西北角
    [487, 36],   // 北墙 -> 书房东
    [487, 88],   // 下折（厨房凸出前）
    [640, 88],
    [640, 28],   // 厨房北凸
    [854, 28],
    [854, 340],  // 东侧上段
    [935, 340],  // 客厅东凸
    [935, 1003],
    [640, 1003], // 南墙
    [640, 940],
    [296, 940],
    [296, 932],  // 西阳台南沿
    [45, 932],
    [45, 552],   // 西侧
    [196, 552],  // 玄关凸出
    [196, 352],
    [290, 352],
  ];

  /* ---------------- 现网设备（来自 AGENTS.md 2026-10-19 实况） ---------------- */
  const DEVICES = [
    {
      id: 'ont', type: 'router', name: '光猫 HG5585F', model: 'ponwrt / AN7581',
      ip: '192.168.31.1', mac: 'd0:69:ff:16:32:80',
      role: '主路由 · 拨号 · DHCP · Passwall 透明代理',
      x: 608, y: 700,                       // 图示位置：客厅东侧墙边
      bands: {
        '2.4': { enabled: true, ch: 6,  width: 20, tx: 20 },
        '5':   { enabled: true, ch: 149, width: 80, tx: 23 },
      },
      wired: true,
      notes: 'PPPoE pon0.995，WAN 100.80.202.91；2.4G HE20 ch6，5G HE80 ch149，country=CN',
    },
    {
      id: 'ap', type: 'ap', name: '小米 BE6500 Pro', model: 'IPQ5332 · 有线 AP 模式',
      ip: '192.168.31.158', mac: 'a4:a9:30:81:e9:2e',
      role: '旁挂 AP · 有线回程',
      x: 809, y: 222,                       // 图示位置：工作室（榻榻米）内
      bands: {
        '2.4': { enabled: true, ch: 1,  width: 40, tx: 20 },
        '5':   { enabled: true, ch: 36, width: 160, tx: 23 },
      },
      wired: true,
      notes: '5G ch36/160（CN 唯一 160 块）；2.4G 重启后实际 HT40，与 ONT ch6 部分重叠',
    },
  ];

  /* 终端设备（位置为估计值，可在界面拖动） */
  const CLIENTS = [
    { id:'pc',      name:'主力 PC',        sub:'DESKTOP-D9JEEE4', ip:'192.168.31.109',
      mac:'80:fa:5b:90:d1:c0', band:'5',   x:760, y:250, demand:'high',  note:'代理测速 / 大文件（工作室）' },
    { id:'phone14', name:'小米 14 Pro',    sub:'手机',             ip:'192.168.31.127',
      mac:'—',                 band:'5',   x:770, y:300, demand:'mid',   note:'日常' },
    { id:'pad',     name:'华为平板 DMG-W00', sub:'平板',           ip:'192.168.31.122',
      mac:'52:b9:ab:5f:63:09', band:'5',   x:150, y:700, demand:'mid',   note:'次卧；YouTube，曾因出口跳变 403' },
    { id:'tv',      name:'Vidda S70 电视', sub:'主卧电视',        ip:'—',
      mac:'—',                 band:'5',   x:780, y:800, demand:'high',  note:'4K 流媒体（主卧）' },
    { id:'iot',     name:'IoT / 智能家居', sub:'多设备',           ip:'—',
      mac:'—',                 band:'2.4', x:400, y:500, demand:'low',   note:'2.4G only' },
    { id:'nb',      name:'笔记本',        sub:'移动',             ip:'—',
      mac:'—',                 band:'5',   x:460, y:600, demand:'mid',   note:'客厅' },
  ];

  /* 有线骨干（拓扑图用） */
  const LINKS = [
    { from:'wan', to:'ont', kind:'fiber',  label:'10G-EPON · VLAN 995' },
    { from:'ont', to:'ap',  kind:'copper', label:'千兆有线回程' },
  ];

  /* 优化方案（预设场景） */
  const SCENARIOS = [
    {
      id:'now', name:'现状', desc:'光猫在客厅东侧墙边 + 小米 AP 在工作室（榻榻米）内',
      devices: null,   // null = 用 DEVICES 默认
    },
    {
      id:'add_west', name:'方案 A：西侧补 AP', desc:'次卧（西南）加一台 AP，补西侧 5G 空洞',
      devices: [
        { ref:'ont' }, { ref:'ap' },
        { id:'ap2', type:'ap', name:'AP-2（西）', model:'新增', ip:'192.168.31.16x',
          role:'旁挂 AP · 有线回程', x:180, y:700,
          bands:{ '2.4':{enabled:true,ch:11,width:20,tx:20},
                  '5':  {enabled:true,ch:100,width:80,tx:23} }, wired:true },
      ],
    },
    {
      id:'move_center', name:'方案 B：AP 移中', desc:'小米 AP 移出工作室，放到过道与客厅之间',
      devices: [
        { ref:'ont' },
        { id:'ap', type:'ap', name:'小米 BE6500 Pro', model:'IPQ5332 · 有线 AP 模式',
          ip:'192.168.31.158', mac:'a4:a9:30:81:e9:2e', role:'旁挂 AP · 有线回程',
          x:668, y:520,
          bands:{ '2.4':{enabled:true,ch:1,width:20,tx:20},
                  '5':  {enabled:true,ch:36,width:80,tx:23} }, wired:true },
      ],
    },
    {
      id:'tri', name:'方案 C：三点覆盖', desc:'光猫 + 工作室 AP + 次卧 AP，5G 三信道组分离',
      devices: [
        { ref:'ont' },
        { id:'ap', type:'ap', name:'AP-东', model:'BE6500 Pro', ip:'192.168.31.158',
          role:'旁挂 AP', x:809, y:222,
          bands:{ '2.4':{enabled:true,ch:1,width:20,tx:20},
                  '5':  {enabled:true,ch:36,width:80,tx:23} }, wired:true },
        { id:'ap2', type:'ap', name:'AP-西', model:'新增', ip:'192.168.31.16x',
          role:'旁挂 AP', x:170, y:700,
          bands:{ '2.4':{enabled:true,ch:11,width:20,tx:20},
                  '5':  {enabled:true,ch:100,width:80,tx:23} }, wired:true },
      ],
    },
  ];

  return {
    PLAN_PX: PLAN_PX, PX_PER_M: PX_PER_M,
    ROOMS: ROOMS, OUTLINE: OUTLINE,
    DEVICES: DEVICES, CLIENTS: CLIENTS, LINKS: LINKS, SCENARIOS: SCENARIOS,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = DATA;
