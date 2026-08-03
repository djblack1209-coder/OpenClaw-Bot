# 每日资讯 V2 设计 QA

> 日期: 2026-08-04
> 决策: 方案 C + Top 3 + 候选 3
> 范围: Telegram 每日简报首屏，不替代内容正确性、Bot API 或生产投递验收

## 设计结论

- 采用深色终端风格和真实机柜封面，首屏只突出经过时效、去重和评分后的 Top 3。
- 视觉层级为“日期与核验状态 → 今日重点 → 三条信号 → 两行操作按钮”；市场使用红色强调，AI/科技使用青色强调。
- 生产封面使用 Telegram 友好的 16:9 品牌图，因此高度大于参考稿中的窄图；这是适配 `sendPhoto` 的有意差异，不是排版偏差。
- 按钮使用 Telegram 原生 inline keyboard，支持市场、AI、查看全部和中英文切换；正文与按钮无重叠。

## 同视口对比

| 项目 | 结果 |
|---|---|
| 参考视口 | 390 x 844 |
| 实现视口 | 390 x 844 |
| 合并对比图 | 804 x 892 |
| 控制台 | 0 error / 0 warning |
| 文本与控件 | 无重叠、无截断、按钮保持两行稳定布局 |

## 证据

- 参考图 SHA-256: `0d80a938b25e8c1fa640bb364a0ea6f9f7f694157a3cdf01ecd76fd660da5028`
- 实现截图 SHA-256: `da9f5d1dad1379768baaa18b8fb84b0a2ff20ceeb1d2c714e5e312d845878c38`
- 合并对比 SHA-256: `b67ac49294e03726864b693532858552ec5130294cd62350964cd1e17951435a`
- 生产封面: `packages/clawbot/assets/intel/openclaw-intel-brief-dark.jpg`，1280 x 720，SHA-256 `eee7a545db73d4020b3c2b96d38867e142437725fb9043bf2b458138859d5315`
- 本机可再生成截图: `output/playwright/openclaw-intel-brief-implemented.png`、`output/playwright/openclaw-intel-brief-comparison.png`。两者为 Git 忽略的本机 QA 证据，不属于可移植仓库基线。

## 验收边界

- 截图证明视觉排版和状态呈现，不证明 Telegram 网络投递成功。
- 真实验收仍需覆盖官方 `sendPhoto`、inline callback、同 brief 回放、跨日 `file_id` 复用、失效 `file_id` 重传与中英文切换。
- Telegram 官方没有 `sendRichMessage`；生产实现即使误开兼容开关也会在本地拒绝，并降级到官方 `sendPhoto`，不会请求不存在的接口。
