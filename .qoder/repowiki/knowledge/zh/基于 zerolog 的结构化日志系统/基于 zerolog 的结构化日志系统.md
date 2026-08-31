---
kind: logging_system
name: 基于 zerolog 的结构化日志系统
category: logging_system
scope:
    - '**'
source_files:
    - notifuse/pkg/logger/logger.go
    - notifuse/cmd/api/main.go
    - notifuse/internal/app/app.go
    - notifuse/config/config.go
---

## 1. 使用的系统与框架
- 核心日志库：`github.com/rs/zerolog`，输出 JSON 结构化日志到 stdout。
- 应用层通过 `pkg/logger` 包对 zerolog 进行薄封装，暴露统一的 `Logger` 接口（Debug/Info/Warn/Error/Fatal + WithField/WithFields），便于在测试中用 mockgen 生成替身。
- 全局日志级别通过环境变量或配置项 `LogLevel` 控制，支持 debug/info/warn/warning/error/fatal/panic/disabled/off 等值，默认 info。
- 进程启动入口 `cmd/api/main.go` 负责读取配置、初始化 logger，并注入到 `internal/app.App` 中；后续各组件通过依赖注入获取同一 logger 实例。

## 2. 关键文件与包
- `notifuse/pkg/logger/logger.go` — 定义 `Logger` 接口及 zerolog 实现，提供 `NewLogger()` / `NewLoggerWithLevel(level)` 工厂方法。
- `notifuse/cmd/api/main.go` — 应用入口，根据 `cfg.LogLevel` 创建 logger 并传递给 App。
- `notifuse/internal/app/app.go` — 应用装配器，持有 `logger.Logger` 字段，在数据库连接、迁移、HTTP 服务器、SMTP Bridge、OpenCensus 导出器等关键路径上记录结构化日志。
- `notifuse/config/config.go` — 包含 `LogLevel` 配置项，驱动日志级别选择。

## 3. 架构与设计约定
- **统一接口**：所有业务代码只依赖 `pkg/logger.Logger` 接口，不直接引用 zerolog，方便替换实现和单测 mock。
- **结构化字段**：通过 `WithField(key, value)` 和 `WithFields(map[string]interface{})` 附加上下文键值对，例如 `error`、`signal`、`trace_exporter`、`max_connections`、`active_requests` 等，便于下游日志聚合平台检索。
- **时间戳**：所有日志行自动附带 ISO 时间戳（`With().Timestamp()`）。
- **级别策略**：生产环境默认 info，可通过配置降为 debug 以排查问题；`Fatal` 会调用 `os.Exit(1)`，用于不可恢复的启动错误。
- **输出目标**：当前仅输出到 stdout，由容器/进程管理器（如 systemd、Docker）收集；未集成文件轮转或远程日志服务。
- **与追踪集成**：App 初始化时同时设置 OpenCensus tracing exporter，并通过 logger 记录 exporter 信息，便于关联日志与链路追踪。

## 4. 开发者应遵循的规则
- **不要直接使用 `fmt.Print*` / `log.Printf` 记录业务日志**，统一使用注入的 `logger.Logger` 实例。
- **优先使用结构化字段**：需要携带上下文时，先 `WithField`/`WithFields` 再调用 `Info`/`Error` 等，避免拼接字符串。
- **敏感信息脱敏**：示例中密码已做掩码处理（`maskedPassword`），不要在日志中明文输出密钥、令牌等敏感数据。
- **级别选择**：可恢复异常用 `Error`，预期内警告用 `Warn`，一般流程用 `Info`，调试细节用 `Debug`；仅在进程无法继续时使用 `Fatal`。
- **测试中注入 mock**：通过 `app.WithLogger(mockLogger)` 传入 mock 实现，避免测试产生真实日志输出。
- **如需扩展 sink**：在 `pkg/logger` 中新增实现即可，保持 `Logger` 接口不变，不影响上层调用。