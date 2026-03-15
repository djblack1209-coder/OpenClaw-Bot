---
name: cost
description: 成本看板快捷命令，映射到 cost-quota-dashboard。
metadata: {"openclaw":{"emoji":"💸"}}
---

# Cost Alias

当 Boss 输入 `/cost` 时：

1. 读取 `{baseDir}/../cost-quota-dashboard/SKILL.md`。
2. 生成中文成本与配额简报。
3. 结尾给出一句“明日预算建议”。
