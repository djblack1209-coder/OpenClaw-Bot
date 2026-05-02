export const accountSummary = {
  userInitials: 'DJ',
  plan: '月卡 Pro',
  balance: '¥81.58',
  todayCost: '¥18.42',
  monthCost: '¥428.90',
  quotaLeft: '¥81.58',
  packageQuota: '¥64.00',
  boosterQuota: '¥17.58',
  usageTotal: '¥428.90',
  todayCalls: '186 次',
  renewalDate: '2026-05-28',
};

export const apiKeys = [
  {
    id: 'key-main',
    name: '主力 Key',
    preview: 'fk-live-••••••9x2a',
    enabled: true,
    cost: '¥428.90',
    tokens: '25.58M',
    lastUsed: '20:16',
    expiresAt: '-',
  },
];

export const channelChecks = [
  {
    provider: 'Claude',
    channel: '官渠主线',
    model: 'claude-haiku-4-5-20251001',
    endpoint: 'https://api.frist.example.com/claude/office',
    ok: true,
    latencyMs: 1912,
    pingMs: 87,
    checkedAt: '20:16',
    officialStatus: '正常',
    availability: '89.65%',
    successLabel: '8101/9036 成功',
    history: ['ok', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'down', 'ok', 'ok', 'ok'],
    replacement: 'Claude 备用线',
  },
  {
    provider: 'Claude',
    channel: '经济备用线',
    model: 'claude-haiku-4-5-20251001',
    endpoint: 'https://api.frist.example.com/claude/kiro',
    ok: true,
    latencyMs: 1378,
    pingMs: 94,
    checkedAt: '20:15',
    officialStatus: '正常',
    availability: '94.17%',
    successLabel: '9484/10071 成功',
    history: ['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'ok'],
    replacement: 'Claude 官渠主线',
  },
  {
    provider: 'OpenAI',
    channel: 'Codex Pro',
    model: 'gpt-5.5',
    endpoint: 'https://api.frist.example.com/openai/pro',
    ok: true,
    latencyMs: 1771,
    pingMs: 196,
    checkedAt: '20:16',
    officialStatus: '降级',
    availability: '99.24%',
    successLabel: '9994/10071 成功',
    history: ['ok', 'ok', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'slow', 'ok', 'ok'],
    replacement: 'Codex Plus',
  },
  {
    provider: 'OpenAI',
    channel: 'Codex Plus',
    model: 'gpt-5.5',
    endpoint: 'https://api.frist.example.com/openai/plus',
    ok: true,
    latencyMs: 2446,
    pingMs: 91,
    checkedAt: '20:13',
    officialStatus: '降级',
    availability: '93.76%',
    successLabel: '9443/10071 成功',
    history: ['ok', 'ok', 'down', 'ok', 'ok', 'slow', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok'],
    replacement: 'Codex Pro',
  },
];

export const modelUsage = [
  { model: 'Claude', family: 'Anthropic', percent: 42, amount: '¥179.22', calls: '326 次', tokens: '9.83M' },
  { model: 'OpenAI', family: 'OpenAI', percent: 31, amount: '¥132.96', calls: '284 次', tokens: '8.12M' },
  { model: 'Codex', family: 'OpenAI', percent: 17, amount: '¥72.91', calls: '91 次', tokens: '4.46M' },
  { model: 'OpenCode', family: 'Other', percent: 10, amount: '¥43.81', calls: '54 次', tokens: '3.17M' },
];

export const modelCatalog = [
  {
    model: 'gpt-5.5',
    family: 'OpenAI',
    tagline: '推理和代码主力',
    context: '1M 上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-5.4',
    family: 'OpenAI',
    tagline: '日常问答和代码补全',
    context: '1M 上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-5.4-mini',
    family: 'OpenAI',
    tagline: '轻量代码和快速问答',
    context: '长上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
  {
    model: 'gpt-image-2',
    family: 'OpenAI',
    tagline: '图片生成',
    context: '按图计费',
    price: '按张结算',
    available: true,
  },
  {
    model: 'claude-haiku-4-5-20251001',
    family: 'Claude',
    tagline: '轻量长文和低延迟',
    context: '长上下文',
    price: '官方同档 · 折扣结算',
    available: true,
  },
];

export const rechargeOptions = [
  { label: '日卡', caption: '30刀额度', plan: 'day', cny: '¥3.87', active: true },
  { label: '月卡', caption: '连续使用', plan: 'month', cny: '¥29.90', active: false },
  { label: '余额', caption: '按量扣费', plan: 'balance', cny: '¥50.00', active: false },
];

export const importTargets = ['Claude', 'Codex', 'OpenCode', 'OpenClaw', 'Hermes'];

export const helpLinks = [
  { title: 'CC Switch', detail: '导入 Frist-API', href: '#switch' },
  { title: 'OpenCode', detail: '复制配置文件', href: '#switch' },
  { title: '邮件', detail: 'support@frist-api.example', href: 'mailto:support@frist-api.example' },
];
