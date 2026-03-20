## 闲鱼 Cookie 快速更新指南

### 方法1：Chrome浏览器（推荐）

1. 打开 Chrome，访问 https://2.taobao.com/
2. 登录你的闲鱼账号
3. 按 F12 打开开发者工具
4. 点击 "Application" 标签
5. 左侧展开 "Cookies" → 点击 "https://2.taobao.com"
6. 复制所有 Cookie，格式：name1=value1; name2=value2; ...

### 方法2：使用插件（最简单）

1. 安装 Chrome 插件：EditThisCookie
2. 访问 https://2.taobao.com/ 并登录
3. 点击插件图标 → Export → 复制

### 需要的关键 Cookie

必须包含这些字段：
- `_m_h5_tk`
- `_m_h5_tk_enc`
- `cna`
- `t`
- `unb`
- `_tb_token_`

### 更新到配置

复制完整 Cookie 字符串，替换 `config/.env` 中的：
```
XIANYU_COOKIES=你的新Cookie
```

### 注意事项

- Cookie 有效期约 24 小时，需定期更新
- 不要在多个设备同时登录（会导致 Cookie 失效）
- 确保网络能直连闲鱼（不要用代理）
