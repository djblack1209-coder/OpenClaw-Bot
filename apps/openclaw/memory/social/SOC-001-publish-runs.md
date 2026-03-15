# SOC-001 社交发布运行记录

> 来源: social-publish-runs.jsonl (迁移)
> 记录所有社交平台发布的执行状态

## SOC-001.1 demo测试发布 (2026-03-09)
- **runId**: demo-20260309-01
- **平台**: X
- **主题**: demo
- **状态**: preflight_passed / progress
- **结果**: 预检通过

## SOC-001.2 双平台发布SOP测试 (2026-03-09)
- **runId**: social-test-001
- **平台**: X
- **主题**: 小红书双平台发布SOP
- **状态**: draft_ready / progress

## SOC-001.3 发布失败-占位符文本 (2026-03-09)
- **runId**: social-yolo-002
- **平台**: X
- **主题**: AI内容发布SOP
- **状态**: publish_failed / error
- **错误**: draft_invalid — 存在占位符/TODO 文本
- **修复**: 修正文案/素材后重新 preflight
- → 参见 ERR-001.1

## SOC-001.4 发布提交-待人工验证 (2026-03-09)
- **runId**: social-yolo-003
- **平台**: X
- **主题**: AI内容发布SOP
- **状态**: needs_manual_review / progress
- **详情**: 已提交但缺少成功证据
- **后续**: 人工检查帖子是否可见或补抓分享链接

## SOC-001.5 发布计划执行-待验证 (2026-03-09)
- **runId**: social-plan-001
- **平台**: X
- **状态**: needs_manual_review / progress
- **详情**: 浏览器执行后仍缺少强成功证据

## SOC-001.6 X发布成功-AI工具实操 (2026-03-14)
- **runId**: x-20260314-001
- **平台**: X
- **主题**: AI工具实操
- **状态**: published / ok
- **URL**: https://x.com/BonoDJblack/status/2032846753356014070

## SOC-001.7 小红书待验证-AI工具实操 (2026-03-14)
- **runId**: xhs-20260314-001
- **平台**: 小红书
- **主题**: AI工具实操
- **状态**: needs_manual_review / progress
- **详情**: 发布已提交但未捕获share_link

## SOC-001.8 X发布成功-提示词架构 (2026-03-14)
- **runId**: x-20260314-002
- **平台**: X
- **主题**: 提示词架构
- **状态**: published / ok
- **URL**: https://x.com/BonoDJblack/status/2032848703329820838

## SOC-001.9 X发布成功-AI工具实操中文 (2026-03-15)
- **runId**: x-20260315-001-cn
- **平台**: X
- **主题**: AI工具实操-中文
- **状态**: published / ok
- **URL**: https://x.com/BonoDJblack/status/2032852236674482224

## SOC-001.10 小红书发布成功-AI工具实操 (2026-03-15)
- **runId**: xhs-20260315-001
- **平台**: 小红书
- **主题**: AI工具实操
- **状态**: published / ok
- **URL**: https://www.xiaohongshu.com/discovery/item/69b58d46000000001e00dcad

## SOC-001.11 小红书发布成功-提示词架构 (2026-03-15)
- **runId**: xhs-20260315-002
- **平台**: 小红书
- **主题**: 提示词架构
- **状态**: published / ok
- **URL**: https://www.xiaohongshu.com/discovery/item/69b58df50000000022026064
