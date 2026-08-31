---
kind: frontend_style
name: 前端样式体系：Tailwind v4 + Ant Design + shadcn/ui 双栈
category: frontend_style
scope:
    - '**'
source_files:
    - notifuse/console/package.json
    - notifuse/notification_center/package.json
    - notifuse/console/vite.config.ts
    - notifuse/notification_center/vite.config.ts
    - notifuse/console/src/index.css
    - notifuse/notification_center/src/index.css
    - notifuse/notification_center/components.json
---

## 系统概览

Notifuse 项目包含两个独立的 React 前端应用，分别采用不同的 UI 风格与组件库：
- 控制台（console）：基于 Vite + TypeScript + Tailwind CSS v4 + Ant Design v5 的管理后台
- 通知中心（notification_center）：基于 Vite + React 19 + Tailwind CSS v4 + shadcn/ui（New York 风格）的轻量通知面板
两者均使用 Tailwind CSS v4 作为原子化样式引擎，通过 @import "tailwindcss" 引入，并借助 CSS 变量实现主题定制。

## 关键文件与包
- notifuse/console/package.json — 依赖 antd、@ant-design/icons、@ant-design/x、@fortawesome/react-fontawesome、@tiptap/*、echarts-for-react 等
- notifuse/notification_center/package.json — 依赖 @shadcn/ui、class-variance-authority、clsx、lucide-react、sonner、next-themes
- notifuse/console/vite.config.ts — 启用 @tailwindcss/vite 插件、Lingui i18n、React 插件
- notifuse/notification_center/vite.config.ts — 启用 @tailwindcss/vite 插件
- notifuse/console/src/index.css — 主样式入口，定义 Tailwind 主题变量、Ant Design 覆盖规则
- notifuse/notification_center/src/index.css — 完整的 shadcn/ui 主题变量映射（light/dark）
- notifuse/notification_center/components.json — shadcn/ui 配置（style: new-york, iconLibrary: lucide）

## 架构与约定
### Tailwind CSS v4 用法
- 通过 @import "tailwindcss" 在 CSS 中引入，而非传统 tailwind.config.js
- 使用 @theme { ... } 和 @theme inline { ... } 声明设计令牌（design tokens）
- 通过 CSS 变量（如 --primary、--background、--radius）集中管理主题色、圆角、阴影等
- notification_center 使用 @custom-variant dark (&:is(.dark *)) 配合 next-themes 实现暗色模式切换

### 控制台（console）样式策略
- 以 Ant Design v5 为默认 UI 框架，大量使用 antd 组件类名（.ant-table-*、.ant-alert-*、.ant-drawer-*）
- 通过全局 CSS 覆盖 Ant Design 默认样式（如表格固定列背景、Alert 左侧边框、Tabs 行高）
- 自定义品牌色 --color-primary: #7763f1，并通过 --primary CSS 变量注入到 Ant Design 主题
- 字体族统一为 Inter + system-ui 回退链

### 通知中心（notification_center）样式策略
- 采用 shadcn/ui 的 New York 风格，完全基于 Radix UI 原语 + Tailwind 原子类
- 使用 class-variance-authority + clsx + tw-animate-css 组合构建可组合式组件
- 完整映射 shadcn/ui 语义化颜色变量（foreground/secondary/muted/accent/destructive/chart-*）
- 使用 oklch 色彩空间定义明度感知配色，支持 light/dark 两套主题

### 图标与媒体资源
- console 同时使用 Font Awesome（@fortawesome/react-fontawesome）与 Ant Design Icons
- notification_center 统一使用 Lucide React 图标集
- 静态资源（logo、favicon、平台图标）存放于各自 public/ 目录

## 开发者应遵循的规则
1. 新增样式优先使用 Tailwind 原子类，仅在必要时通过 @layer base/utility 扩展
2. 主题色变更集中在 CSS 变量（--primary、--background 等），避免硬编码颜色值
3. 控制台页面如需覆盖 Ant Design 样式，应在 src/index.css 或对应组件级 CSS 文件中添加，并附带注释说明原因
4. 通知中心组件应遵循 shadcn/ui 的 class-variance-authority 模式，使用 cva() 定义变体
5. 暗色模式通过给根节点添加 .dark 类切换，所有颜色变量需同时提供 light/dark 两套值
6. 响应式设计使用 Tailwind 断点前缀（sm/md/lg/xl），避免手写媒体查询
7. 国际化文案使用 Lingui（console）或内置 translations（notification_center），不在 CSS 中写死文本内容