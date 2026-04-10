# OpenCode 与 CC Switch 模型命名统一设计

> 领域: `infra`
> 范围: `OpenCode 桌面配置`, `CC Switch 本地数据库`

## 目标

- 统一 OpenCode 与 CC Switch 中的配置名称和模型显示名称。
- 让 OpenCode 的分组口径与 Claude 分组口径对齐，减少切换时的混乱。
- 为 Claude 补齐当前 OpenCode 已存在但 Claude 缺失的分组配置。

## 设计原则

- 配置名统一为 `渠道｜线路/计费｜应用`。
- 模型名统一为 `模型本体｜模式｜渠道`。
- 只改显示名称和分组配置，不改模型 ID、接口地址、认证密钥、当前默认模型指向。
- 修改前先做本地备份，保证可以回退。

## 目标数据源

### OpenCode

- 文件: `~/.config/opencode/opencode.json`
- 关注字段:
  - `provider.<providerId>.name`
  - `provider.<providerId>.models.<modelId>.name`

### CC Switch

- 数据库: `~/.cc-switch/cc-switch.db`
- 关注表:
  - `providers.name`
  - `providers.settings_config`
  - `provider_endpoints`

## 命名规则

### 配置名

- Claude:
  - `Tabcode｜Kiro逆向｜Claude`
  - `Tabcode｜官渠Max20x｜Claude`
  - `中转｜Token｜Claude`
  - `中转｜反重力MAX｜Claude`
  - `中转｜官转MAX｜Claude`
  - `中转｜按次｜Claude`

- OpenCode:
  - `XAPI｜主线路｜OpenCode`
  - `XAPI｜Claude按量｜OpenCode`
  - `中转｜Token｜OpenCode`
  - `中转｜Token备用｜OpenCode`
  - `中转｜反重力MAX｜OpenCode`
  - `中转｜官转MAX｜OpenCode`
  - `中转｜按次｜OpenCode`
  - `中转｜GPT专线｜OpenCode`
  - `Tabcode｜聚合｜OpenCode`

### 模型名

- `claude-opus-4-6` -> `Claude Opus 4.6｜标准｜<渠道>`
- `claude-opus-4-6-thinking` -> `Claude Opus 4.6｜Thinking｜<渠道>`
- `claude-opus-4-6-c` -> `Claude Opus 4.6｜按次｜中转`
- `claude-opus-4-6-L` -> `Claude Opus 4.6｜L版｜XAPI`
- `claude-sonnet-4-6` -> `Claude Sonnet 4.6｜标准｜中转`
- `claude-sonnet-4-6-thinking` -> `Claude Sonnet 4.6｜Thinking｜中转`
- `claude-sonnet-4-6-c` -> `Claude Sonnet 4.6｜按次｜中转`
- `claude-haiku-4-5-20251101` -> `Claude Haiku 4.5｜标准｜Tabcode`
- `claude-sonnet-4-5-20250929` -> `Claude Sonnet 4.5｜标准｜Tabcode`
- `gpt-5.4` -> `GPT-5.4｜标准｜<渠道>`
- `gpt-5.4-c` -> `GPT-5.4｜按次｜中转`
- `gpt-5.3-codex` -> `GPT-5.3 Codex｜标准｜<渠道>`
- `gemini-3-flash` -> `Gemini 3 Flash｜标准｜中转`
- `gemini-3.1-pro-high` -> `Gemini 3.1 Pro｜高配｜中转`

## 分组对齐策略

- 以 Claude 分组口径作为主线: `Token`、`反重力MAX`、`官转MAX`、`按次`、`Tabcode`。
- OpenCode 侧已有但 Claude 侧缺失的官转 MAX 分组，需要补到 Claude。
- XAPI 保留为 OpenCode 专属分组，不强行加入 Claude，因为当前 Claude 侧没有对应 Anthropic 配置结构和真实使用记录。
- GPT 专线保留为 OpenCode 专属分组，不并入 Claude。

## 风险控制

- 先备份 JSON 和数据库。
- 只更新本地显示层和配置层，不修改请求端点。
- 修改后重新读取配置，确认名称、分组、模型名已落地。
