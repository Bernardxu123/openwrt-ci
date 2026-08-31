---
kind: configuration_system
name: 配置系统：Viper + 环境变量 + 数据库动态覆盖
category: configuration_system
scope:
    - '**'
source_files:
    - notifuse/config/config.go
    - notifuse/config/oidc.go
    - notifuse/config/root_email.go
    - notifuse/config/platform.go
    - notifuse/cmd/api/main.go
    - notifuse/env.example
---

## 1. 采用的框架与工具
- Viper（github.com/spf13/viper）作为统一配置加载器，负责合并默认值、.env 文件与环境变量。
- PostgreSQL settings 表作为运行时持久化配置源，支持“环境优先、DB 回退”的叠加策略。
- 无外部配置中心/密钥管理服务；敏感字段通过 SECRET_KEY 在内存中解密后使用。

## 2. 核心文件与包
- notifuse/config/config.go — 主入口：定义所有配置结构体、默认值、加载流程、DB 读取与覆盖逻辑。
- notifuse/config/oidc.go — OIDC 配置的解析、验证与域名白名单处理。
- notifuse/config/root_email.go — ROOT_EMAIL 分割/匹配工具函数。
- notifuse/config/platform.go — 平台检测与黑名单（Railway）。
- notifuse/cmd/api/main.go — 应用启动入口，调用 config.Load() 并注入到 app.NewApp。
- notifuse/env.example — 完整的环境变量清单与注释说明。

## 3. 架构与约定
### 3.1 加载顺序与优先级
viper.SetDefault(...) → .env 文件（可选）→ 环境变量（大写+下划线）→ 数据库 settings 表（仅当 is_installed=true 且 DB 可达时生效）
- 环境变量始终优先于数据库。对 SMTP、SMTP Bridge、OIDC、Telemetry、CheckForUpdates 等关键项，若对应 env var 被显式设置（IsSet），则直接采用 env 值；否则回退到 DB。
- OIDC 的 Enabled / AutoCreateUsers 采用“三态字符串”模式（"true" / "false" / ""），空串表示“未设置”，允许 DB 值生效。

### 3.2 配置结构分层
- Config 聚合顶层字段（Server、Database、Security、Tracing、SMTP、SMTPBridge、OIDC、Broadcast、TaskScheduler、AutomationScheduler、Telemetry、LogLevel、Version、IsInstalled、MaxUsers/Workspaces 等）。
- 子配置结构体按领域拆分（ServerConfig、DatabaseConfig、SecurityConfig、SSLConfig、TracingConfig、SMTPConfig、SMTPBridgeConfig、BroadcastConfig、TaskSchedulerConfig、AutomationSchedulerConfig、DemoConfig、OIDCConfig）。
- EnvValues 记录哪些值来自真实环境变量（非默认/非 DB），供 Setup Wizard 判断“已配置项”。

### 3.3 敏感数据与加密
- SECRET_KEY（或兼容的 PASETO_PRIVATE_KEY）是必需项，用于：JWT HS256 签名（先尝试 base64 解码，失败则用原始字节）、数据库中 encrypted_smtp_*、encrypted_oidc_client_secret 等字段的加解密。
- 长度不足 32 字节会输出警告日志。

### 3.4 运行时校验与快速失败
- 数据库连接池参数有上下界校验（DB_MAX_CONNECTIONS 20~10000，DB_MAX_CONNECTIONS_PER_DB 1~50）。
- SMTP Bridge TLS 模式在启动阶段解析并校验：生产环境必须提供证书或使用 SMTP_BRIDGE_TLS=off。
- OIDC 启用时必须满足 IssuerURL/ClientID/ClientSecret/RedirectURI 非空，且 AutoCreateUsers=true 时要求 AllowedDomains 非空。

### 3.5 向后兼容
- SMTP Relay → SMTP Bridge 环境变量名迁移（SMTP_RELAY_* 仍被接受）。
- PASETO_PRIVATE_KEY 作为 SECRET_KEY 的兼容别名。

## 4. 开发者应遵循的规则
1. 新增配置项：在 LoadWithOptions 中通过 v.SetDefault("KEY", value) 声明默认值；在 Config 对应结构体中添加字段并在最终组装处赋值；如需从 DB 覆盖，遵循“env 显式设置才覆盖，否则回退 DB”的模式（参考 SMTP/OIDC 分支）。
2. 环境变量命名：全部大写、下划线分隔，`.` 会被 Viper 替换为 `_`（如 SERVER_PORT）。
3. 敏感字段：不要将密码/密钥写入 .env.example；如需存储到 DB，使用 encrypted_* 前缀并通过 crypto.DecryptFromHexString 解密。
4. OIDC 配置：使用 resolveOIDCConfig 统一解析，避免在各处重复实现 env-vs-DB 逻辑。
5. 平台限制：不要在 Railway.com 上部署（CheckBlockedPlatforms 会直接报错退出）。
6. 调试与可观测性：通过 TRACING_* 系列环境变量开启 Jaeger/Zipkin/Datadog/X-Ray 等导出器；LOG_LEVEL 控制日志级别。