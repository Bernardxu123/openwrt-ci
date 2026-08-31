---
kind: build_system
name: Notifuse 构建与制品管理系统
category: build_system
scope:
    - '**'
source_files:
    - notifuse/Makefile
    - notifuse/Dockerfile
    - notifuse/compose.yaml
    - notifuse/go.mod
    - notifuse/Makefile.integration
    - notifuse/tests/compose.test.yaml
---

## 构建系统概览

Notifuse 采用多阶段 Docker 构建 + Makefile 编排的混合构建系统，支持 Go 后端、React 控制台和通知中心前端的一体化打包。

### 核心构建工具链
- Go 1.25.4：后端编译，使用 go build 生成静态二进制文件（CGO_ENABLED=0）
- Node.js 22 Alpine：两个 React 前端应用（console 和 notification_center）的构建环境
- Docker BuildKit：多阶段构建，分离前端构建、Go 编译和运行时镜像
- Makefile：统一的开发、测试、构建入口点
- Docker Compose：本地开发和集成测试环境编排

### 多阶段构建架构
Dockerfile 定义了四个构建阶段：
1. console-frontend-builder：构建管理控制台（console/）
2. notification-center-builder：构建通知中心前端（notification_center/）
3. backend-builder：编译 Go 后端，禁用 CGO 生成纯静态二进制
4. runtime：基于 Alpine 3.19 的最小运行时镜像，包含 CA 证书、时区和 PostgreSQL 客户端

最终产物是一个单容器镜像，同时提供 HTTP API（8080端口）和 SMTP 桥接服务（587端口）。

### 构建目标体系
Makefile 提供了完整的构建生命周期管理：
- 开发构建：make build（启用 CGO 以支持 V8）、make dev（air 热重载）
- 单元测试：make test-unit、make coverage（覆盖率报告）
- 集成测试：独立的 Makefile.integration，通过 Docker Compose 启动测试数据库和 Mailpit
- Docker 构建：make docker-build、make docker-publish（支持多平台 amd64/arm64）
- OpenAPI 工具：make openapi-bundle/lint/preview 用于 API 文档管理

### 依赖管理策略
- Go 模块：使用 go.mod 和 go.sum 进行依赖版本锁定，所有依赖显式声明
- Node.js 依赖：分别维护 console 和 notification_center 的 package.json，使用 npm ci 确保可重现构建
- Docker 层缓存优化：先复制 package*.json 和 go.mod/go.sum，利用 Docker 层缓存加速构建

### 测试基础设施
集成测试使用独立的 Docker Compose 配置（tests/compose.test.yaml），提供：
- PostgreSQL 17（端口 5433，最大连接数 300）
- Mailpit SMTP 服务器（端口 1025/8025）
- 健康检查确保服务就绪

### 环境变量配置
通过 compose.yaml 和 env.example 管理配置，支持：
- 数据库连接（DB_HOST, DB_PORT, DB_USER, DB_PASSWORD）
- SMTP 桥接配置（SMTP_BRIDGE_*）
- 应用设置（SECRET_KEY, ROOT_EMAIL, API_ENDPOINT）
- 首次启动通过 Setup Wizard 交互式配置

### 发布流程
支持多平台 Docker 镜像发布到 Docker Hub：
make docker-publish v1.0.0  # 构建并推送特定版本标签
make docker-publish         # 默认推送 latest 标签

构建时使用 docker buildx 创建跨平台构建器，同时生成 linux/amd64 和 linux/arm64 镜像。

### 开发者约定
1. 本地开发使用 make dev 配合 air 进行热重载
2. 提交前运行 make test-unit 和 make coverage-report
3. 新功能需要添加对应的集成测试
4. 修改 OpenAPI 规范后运行 make openapi-bundle 更新 JSON 导出
5. 生产部署使用 make docker-publish 生成多平台镜像