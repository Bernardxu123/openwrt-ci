---
kind: error_handling
name: 错误处理体系：领域错误类型、邮件错误分类与 HTTP 响应封装
category: error_handling
scope:
    - '**'
source_files:
    - notifuse/internal/domain/errors.go
    - notifuse/pkg/emailerror/error.go
    - notifuse/pkg/emailerror/classifier.go
    - notifuse/internal/http/utils.go
    - notifuse/internal/http/middleware/auth.go
---

## 1. 采用的错误处理系统/模式
- **Go 原生 error 接口 + 自定义结构化错误类型**：在 `internal/domain` 中定义业务语义化的错误结构体（NotFound、TaskExecution、ValidationError、PermissionError），并通过 `Unwrap()` 支持 `errors.Is/As`。
- **邮件发送错误分类器**：`pkg/emailerror` 提供 `ClassifiedError`，将第三方邮件服务商（SES、Postmark、Mailgun、SendGrid、SparkPost、SMTP）的错误统一归类为 `recipient/provider/unknown` 三类，驱动熔断器决策。
- **HTTP 层统一 JSON 错误响应**：`internal/http/utils.go` 暴露 `WriteJSONError`，所有 handler 通过该函数返回 `{"error": "..."}` 格式的统一错误体。
- **panic/recover 作为最后防线**：仅在不可恢复的模板渲染、LLM 调用等边界场景使用，不用于常规业务分支。

## 2. 核心文件与包
- `notifuse/internal/domain/errors.go` — 领域错误类型集中定义
- `notifuse/pkg/emailerror/error.go` — ClassifiedError 及 ErrorType 枚举
- `notifuse/pkg/emailerror/classifier.go` — 按 provider 解析错误并推断 HTTP 状态码
- `notifuse/pkg/emailerror/{ses,postmark,mailgun,sendgrid,sparkpost,smtp}.go` — 各厂商具体匹配规则
- `notifuse/internal/http/utils.go` — `WriteJSONError` 统一响应封装
- `notifuse/internal/http/middleware/auth.go` — 认证中间件内嵌的 JSON 错误输出（与 utils 重复实现）
- `notifuse/internal/domain/event.go`、`notifuse/internal/http/llm_handler.go`、`notifuse/pkg/liquid/blog_renderer_go.go`、`notifuse/pkg/notifuse_mjml/liquid_secure.go` — panic/recover 使用点

## 3. 架构与约定
- **分层职责**：domain 层只抛出自描述错误；service/repository 层向上透传或包装为 domain 错误；http handler 层负责把 domain 错误映射为 HTTP 状态码与 JSON body。
- **邮件错误分类策略**：通过正则从错误消息中提取 HTTP 状态码，再依据 4xx/5xx/406/429 等规则判定是否触发熔断（provider 错误计数，recipient 错误跳过）。未知错误保守地视为 provider 错误。
- **权限错误常量**：`ErrInsufficientPermissions` 作为全局哨兵错误，配合 `NewPermissionError` 构造带 resource/permission/message 的结构化错误。
- **任务错误链式包装**：`ErrTaskExecution` 持有 `Err error` 字段并提供 `Unwrap()`，便于上层用 `errors.Unwrap` 获取根因。

## 4. 开发者应遵循的规则
1. **优先返回 domain 错误类型**：新增业务异常时，在 `internal/domain/errors.go` 中定义新的结构体并实现 `Error()/Unwrap()`，不要直接返回裸 `fmt.Errorf`。
2. **HTTP handler 统一响应**：使用 `internal/http/utils.go` 的 `WriteJSONError(message, statusCode)` 输出错误，避免在每个 handler 里重复写 JSON 编码逻辑。
3. **邮件错误一律经 Classifier**：调用邮件服务后，将 error 传入 `emailerror.Classifier.Classify(err, provider)`，根据 `ShouldTriggerCircuitBreaker()` 决定是否熔断。
4. **panic 仅限不可恢复路径**：模板渲染、外部 LLM 调用等可能崩溃的场景才使用 recover，业务逻辑分支禁止 panic。
5. **权限检查使用 `ErrInsufficientPermissions`**：需要鉴权失败时直接返回该哨兵错误，由上层统一映射为 403。