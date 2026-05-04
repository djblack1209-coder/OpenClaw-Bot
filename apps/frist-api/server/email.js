import { createHash, randomBytes } from 'node:crypto';
import { connect as connectTls } from 'node:tls';
import { connect as connectNet, isIP } from 'node:net';
import { lookup as lookupDns } from 'node:dns/promises';
import {
  formatCny, formatEmailTime, escapeHtml, escapeAttribute, formatUsdFromCnyCents, DISPLAY_USD_TO_CNY,
} from './shared.js';

export function createBalanceAlertEmailSender(options = {}) {
  const host = String(options.host ?? process.env.FRIST_API_SMTP_HOST ?? '').trim();
  const user = String(options.user ?? process.env.FRIST_API_SMTP_USER ?? '').trim();
  const password = String(options.password ?? process.env.FRIST_API_SMTP_PASSWORD ?? '');
  const from = String(options.from ?? process.env.FRIST_API_SMTP_FROM ?? user).trim();
  if (!host || !user || !password || !from) {
    return null;
  }

  const port = Number(options.port ?? process.env.FRIST_API_SMTP_PORT ?? 465);
  const secure =
    typeof options.secure === 'boolean'
      ? options.secure
      : String(process.env.FRIST_API_SMTP_SECURE ?? '1') !== '0';
  const fromName = String(
    options.fromName ?? process.env.FRIST_API_BALANCE_ALERT_FROM_NAME ?? 'Frist-API Billing',
  ).trim();
  const family = normalizeSmtpAddressFamily(options.family ?? process.env.FRIST_API_SMTP_FAMILY ?? 'auto');

  return async (message) =>
    sendSmtpMail({
      host, port, secure, family, user, password, from, fromName,
      to: message.to, subject: message.subject, text: message.text, html: message.html,
    });
}

export async function resolveSmtpSocketTargets(options) {
  const family = normalizeSmtpAddressFamily(options.family ?? 'auto');
  const port = Number(options.port || 465);
  const ipFamily = isIP(options.host);
  if (ipFamily) {
    return [{ host: options.host, port, servername: options.host, family: ipFamily }];
  }

  const addresses = Array.isArray(options.addresses)
    ? options.addresses
    : await lookupDns(options.host, { all: true, verbatim: true });
  const normalized = addresses
    .map((address) => ({
      host: address.address, port, servername: options.host, family: Number(address.family),
    }))
    .filter((address) => address.host && (family === 'auto' || String(address.family) === family));
  if (!normalized.length) {
    return [{ host: options.host, port, servername: options.host, family: 0 }];
  }
  return normalized;
}

function connectSmtpSocketTarget(options, target) {
  const socketOptions = {
    host: target.host, port: target.port, family: target.family || undefined, servername: target.servername,
  };
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      callback(value);
    };
    const socket = options.secure
      ? connectTls(socketOptions, () => finish(resolve, socket))
      : connectNet(socketOptions, () => finish(resolve, socket));
    socket.setTimeout(Number(options.timeoutMs || 8_000));
    socket.once('error', (error) => finish(reject, error));
    socket.once('timeout', () => {
      socket.destroy();
      finish(reject, new Error('SMTP 连接超时'));
    });
  });
}

function normalizeSmtpAddressFamily(value) {
  const family = String(value || 'auto').trim().toLowerCase();
  if (family === '4' || family === 'ipv4') return '4';
  if (family === '6' || family === 'ipv6') return '6';
  return 'auto';
}

async function sendSmtpMail(options) {
  const socket = await openSmtpSocket(options);
  const reader = createSmtpReader(socket);
  const writer = (line) => socket.write(`${line}\r\n`);
  try {
    await readSmtpReply(reader, [220]);
    writer(`EHLO ${smtpDomain(options.from)}`);
    await readSmtpReply(reader, [250]);
    writer('AUTH PLAIN ' + Buffer.from(`\u0000${options.user}\u0000${options.password}`).toString('base64'));
    await readSmtpReply(reader, [235]);
    writer(`MAIL FROM:<${options.from}>`);
    await readSmtpReply(reader, [250]);
    writer(`RCPT TO:<${options.to}>`);
    await readSmtpReply(reader, [250, 251]);
    writer('DATA');
    await readSmtpReply(reader, [354]);
    socket.write(`${buildMimeMessage(options)}\r\n.\r\n`);
    await readSmtpReply(reader, [250]);
    writer('QUIT');
    await readSmtpReply(reader, [221]);
  } finally {
    socket.end();
  }
}

async function openSmtpSocket(options) {
  const targets = await resolveSmtpSocketTargets(options);
  const errors = [];
  for (const target of targets) {
    try {
      return await connectSmtpSocketTarget(options, target);
    } catch (error) {
      errors.push(`${target.host}: ${error.message}`);
    }
  }
  throw new Error(`SMTP 连接失败: ${errors.join('; ')}`);
}

function createSmtpReader(socket) {
  const state = { buffer: '', waiters: [] };
  socket.setEncoding('utf8');
  socket.on('data', (chunk) => {
    state.buffer += chunk;
    flushSmtpWaiters(state);
  });
  socket.on('error', (error) => {
    const waiters = state.waiters.splice(0);
    for (const waiter of waiters) waiter.reject(error);
  });
  return state;
}

function flushSmtpWaiters(state) {
  while (state.waiters.length > 0) {
    const reply = takeCompleteSmtpReply(state);
    if (!reply) return;
    const waiter = state.waiters.shift();
    waiter.resolve(reply);
  }
}

function takeCompleteSmtpReply(state) {
  const lines = state.buffer.split(/\r?\n/);
  if (!state.buffer.match(/\r?\n$/)) {
    lines.pop();
  }
  let consumed = 0;
  for (const line of lines) {
    if (!line) { consumed += 1; continue; }
    consumed += 1;
    if (/^\d{3}\s/.test(line)) {
      const replyLines = lines.slice(0, consumed);
      state.buffer = lines.slice(consumed).join('\n');
      return replyLines.join('\n');
    }
  }
  return null;
}

function readSmtpReply(reader, expectedCodes) {
  return new Promise((resolve, reject) => {
    const complete = takeCompleteSmtpReply(reader);
    const handleReply = (reply) => {
      const code = Number(reply.slice(0, 3));
      if (!expectedCodes.includes(code)) {
        reject(new Error(`SMTP 返回异常: ${reply}`));
        return;
      }
      resolve(reply);
    };
    if (complete) {
      handleReply(complete);
      return;
    }
    reader.waiters.push({ resolve: handleReply, reject });
  });
}

function buildMimeMessage({ from, fromName, to, subject, text, html }) {
  const boundary = `frist-api-${randomBytes(12).toString('hex')}`;
  return [
    `From: ${encodeMimeHeader(fromName)} <${from}>`,
    `To: <${to}>`,
    `Subject: ${encodeMimeHeader(subject)}`,
    'MIME-Version: 1.0',
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${randomBytes(12).toString('hex')}@${smtpDomain(from)}>`,
    `Content-Type: multipart/alternative; boundary="${boundary}"`,
    '',
    `--${boundary}`,
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    wrapBase64(text || ''),
    `--${boundary}`,
    'Content-Type: text/html; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    wrapBase64(html || ''),
    `--${boundary}--`,
  ].join('\r\n');
}

function encodeMimeHeader(value) {
  const text = String(value || '');
  if (/^[\x20-\x7E]*$/.test(text)) {
    return text;
  }
  return `=?UTF-8?B?${Buffer.from(text, 'utf8').toString('base64')}?=`;
}

function wrapBase64(value) {
  return Buffer.from(String(value || ''), 'utf8')
    .toString('base64')
    .replace(/.{1,76}/g, '$&\r\n')
    .trim();
}

function smtpDomain(email) {
  return String(email || '').split('@')[1] || 'frist-api.local';
}

export function buildBalanceAlertEmail({
  user, to, thresholdCents, balanceCents, previousBalanceCents,
  model, quotaCost, publicGatewayBaseUrl, at, isTest = false,
}) {
  const subject = isTest
    ? 'Frist-API 余额预警测试'
    : `Frist-API 余额预警：当前 ${formatUsdFromCnyCents(balanceCents)}`;
  const accountEmail = user.email || 'Frist-API 用户';
  const dashboardUrl = publicGatewayBaseUrl
    ? String(publicGatewayBaseUrl).replace(/\/v1\/?$/i, '').replace(/\/+$/, '')
    : '';
  const modelText = model ? String(model) : 'API 调用';
  const currentBalanceText = formatUsdFromCnyCents(balanceCents);
  const thresholdText = formatUsdFromCnyCents(thresholdCents);
  const previousBalanceText = formatUsdFromCnyCents(previousBalanceCents);
  const quotaCostText = formatUsdFromCnyCents(quotaCost);
  const alertTimeText = formatEmailTime(at);
  const preheader = `${accountEmail} 当前余额 ${currentBalanceText}，已低于 ${thresholdText} 安全线。`;
  const html = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light dark" />
    <meta name="supported-color-schemes" content="light dark" />
    <title>${escapeHtml(subject)}</title>
    <style>
      @media (prefers-color-scheme: dark) {
        .email-bg { background: #111827 !important; }
        .email-card { background: #172033 !important; border-color: #374151 !important; }
        .email-text { color: #f8fafc !important; }
        .email-muted { color: #cbd5e1 !important; }
        .email-panel { background: #111827 !important; border-color: #334155 !important; }
        .email-row { border-color: #334155 !important; }
        .email-soft { background: #1f2937 !important; color: #f8fafc !important; border-color: #475569 !important; }
      }
      @media screen and (max-width: 600px) {
        .email-shell { padding: 18px 10px !important; }
        .email-card { border-radius: 14px !important; }
        .email-pad { padding-left: 18px !important; padding-right: 18px !important; }
        .metric-cell { display: block !important; width: auto !important; }
        .metric-gap { display: block !important; width: auto !important; height: 10px !important; }
      }
    </style>
  </head>
  <body class="email-bg" style="margin:0;background:#eef2f5;color:#111827;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">${escapeHtml(preheader)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-bg email-shell" style="background:#eef2f5;padding:30px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-card" style="max-width:680px;background:#ffffff;border:1px solid #d7dee8;border-radius:18px;overflow:hidden;box-shadow:0 18px 45px rgba(15,23,42,.12);">
            <tr>
              <td style="padding:0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0f172a;">
                  <tr>
                    <td class="email-pad" style="padding:22px 28px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td valign="middle">
                            <div style="font-size:12px;line-height:1.2;letter-spacing:1.6px;text-transform:uppercase;color:#93c5fd;font-weight:800;">Frist-API Balance Guard</div>
                            <div style="margin-top:8px;color:#ffffff;font-size:25px;font-weight:800;line-height:1.22;">余额进入预警区间</div>
                          </td>
                          <td align="right" valign="middle">
                            <span style="display:inline-block;background:#fee2e2;color:#991b1b;border-radius:999px;padding:7px 11px;font-size:12px;font-weight:800;white-space:nowrap;">${isTest ? '测试预览' : '低余额预警'}</span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad email-text" style="padding:28px 28px 10px;color:#111827;">
                <div style="font-size:13px;color:#64748b;font-weight:700;">账户</div>
                <div class="email-text" style="margin-top:6px;font-size:18px;font-weight:800;color:#111827;line-height:1.35;">${escapeHtml(accountEmail)}</div>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:8px 28px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td class="metric-cell" width="50%" valign="top" style="width:50%;padding:18px;background:#ef4444;color:#ffffff;border:1px solid #dc2626;border-radius:16px;">
                      <div style="font-size:12px;line-height:1.2;opacity:.9;font-weight:800;">当前余额</div>
                      <div style="margin-top:10px;font-size:38px;font-weight:900;line-height:1;">${currentBalanceText}</div>
                      <div style="margin-top:10px;font-size:13px;line-height:1.45;color:#fee2e2;">低于安全线，需要关注</div>
                    </td>
                    <td class="metric-gap" width="12" style="width:12px;font-size:0;line-height:0;">&nbsp;</td>
                    <td class="metric-cell email-soft" width="50%" valign="top" style="width:50%;padding:18px;background:#f8fafc;color:#0f172a;border:1px solid #dbe3ed;border-radius:16px;">
                      <div style="font-size:12px;line-height:1.2;color:#64748b;font-weight:800;">预警阈值</div>
                      <div class="email-text" style="margin-top:10px;font-size:34px;font-weight:900;line-height:1;color:#0f172a;">${thresholdText}</div>
                      <div class="email-muted" style="margin-top:10px;font-size:13px;line-height:1.45;color:#64748b;">你设置的余额安全线</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:0 28px 22px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-panel" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;">
                  <tr>
                    <td colspan="2" class="email-row" style="padding:15px 16px;border-bottom:1px solid #e2e8f0;">
                      <div style="font-size:12px;line-height:1.2;color:#64748b;font-weight:800;">事件摘要</div>
                      <div class="email-text" style="margin-top:6px;font-size:16px;line-height:1.45;color:#111827;font-weight:800;">一次 API 消耗让余额跌破预警阈值</div>
                    </td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">触发模型</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${escapeHtml(modelText)}</td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">上次余额</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${previousBalanceText}</td>
                  </tr>
                  <tr>
                    <td class="email-row email-muted" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;">本次扣费</td>
                    <td align="right" class="email-row email-text" style="padding:13px 16px;border-bottom:1px solid #e2e8f0;color:#111827;font-weight:800;">${quotaCostText}</td>
                  </tr>
                  <tr>
                    <td class="email-muted" style="padding:13px 16px;color:#64748b;">触发时间</td>
                    <td align="right" class="email-text" style="padding:13px 16px;color:#111827;font-weight:800;">${escapeHtml(alertTimeText)}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-pad" style="padding:0 28px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="email-soft" style="background:#f8fafc;border:1px solid #dbe3ed;border-radius:14px;">
                  <tr>
                    <td style="padding:16px 18px;">
                      <p class="email-text" style="margin:0;color:#1f2937;font-size:15px;line-height:1.7;">相当于油表已经进入红线区。为了避免 Codex、Claude Code 或 OpenCode 调用中断，建议尽快充值，或者把预警阈值调到更符合你使用节奏的位置。</p>
                    </td>
                  </tr>
                </table>
                ${
                  dashboardUrl
                    ? `<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:18px;">
                        <tr>
                          <td bgcolor="#111827" style="border-radius:999px;">
                            <a href="${escapeAttribute(dashboardUrl)}" style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;border-radius:999px;padding:13px 20px;font-size:14px;font-weight:900;">打开 Frist-API</a>
                          </td>
                          <td class="email-muted" style="padding-left:14px;color:#64748b;font-size:13px;line-height:1.45;">查看余额、充值或调整预警设置</td>
                        </tr>
                      </table>`
                    : ''
                }
              </td>
            </tr>
          </table>
          <div style="max-width:680px;margin-top:18px;color:#64748b;font-size:12px;line-height:1.65;text-align:left;">这是一封 Frist-API 余额预警通知。你可以在仪表盘关闭提醒、调整阈值或更换通知邮箱。</div>
        </td>
      </tr>
    </table>
  </body>
</html>`;
  const text = [
    subject, '', `账户: ${accountEmail}`, `当前余额: ${currentBalanceText}`,
    `预警阈值: ${thresholdText}`, `触发模型: ${modelText}`, `上次余额: ${previousBalanceText}`,
    `本次扣费: ${quotaCostText}`, `触发时间: ${alertTimeText}`,
    dashboardUrl ? `打开 Frist-API: ${dashboardUrl}` : '',
  ].filter(Boolean).join('\n');
  return { to, subject, html, text };
}

export function defaultBalanceAlert(email = '') {
  const normalizedEmail = normalizeAlertEmail(email);
  return {
    enabled: true, thresholdCents: Math.round(5 * DISPLAY_USD_TO_CNY * 100), email: normalizedEmail,
    lastAlertAt: '', lastAlertBalanceCents: 0, lastTriggeredThresholdCents: 0, updatedAt: '',
  };
}

export function normalizeBalanceAlertRecord(record, fallbackEmail = '') {
  const current = record && typeof record === 'object' ? record : {};
  const fallback = defaultBalanceAlert(fallbackEmail);
  const thresholdCents = normalizeAlertThresholdCents(current, fallback.thresholdCents);
  return {
    enabled: Object.prototype.hasOwnProperty.call(current, 'enabled') ? Boolean(current.enabled) : fallback.enabled,
    thresholdCents:
      Number.isFinite(thresholdCents) && thresholdCents > 0 && thresholdCents <= 1_000_000_00
        ? thresholdCents : fallback.thresholdCents,
    email: normalizeAlertEmail(current.email) || fallback.email,
    lastAlertAt: String(current.lastAlertAt || ''),
    lastAlertBalanceCents: Math.max(0, normalizeMoneyCents(current.lastAlertBalanceCents || 0)),
    lastTriggeredThresholdCents: Math.max(0, normalizeMoneyCents(current.lastTriggeredThresholdCents || 0)),
    updatedAt: String(current.updatedAt || ''),
  };
}

export function sanitizeBalanceAlert(record, fallbackEmail = '') {
  const alert = normalizeBalanceAlertRecord(record, fallbackEmail);
  return {
    enabled: alert.enabled, threshold: formatUsdFromCnyCents(alert.thresholdCents),
    thresholdCents: alert.thresholdCents,
    thresholdCny: Number((alert.thresholdCents / 100).toFixed(2)),
    thresholdUsd: Number((alert.thresholdCents / 100 / DISPLAY_USD_TO_CNY).toFixed(2)),
    email: alert.email, lastAlertAt: alert.lastAlertAt,
  };
}

export function normalizeAlertThresholdCents(record = {}, fallbackCents = Number.NaN) {
  if (record.thresholdCents !== undefined) return normalizeMoneyCents(record.thresholdCents);
  if (record.thresholdUsd !== undefined) {
    return normalizeMoneyCents(Number(record.thresholdUsd || 0) * DISPLAY_USD_TO_CNY * 100);
  }
  if (record.thresholdCny !== undefined) return normalizeMoneyCents(Number(record.thresholdCny || 0) * 100);
  if (record.threshold !== undefined) {
    const numeric = Number(String(record.threshold || '').replace(/[^\d.-]/g, ''));
    return normalizeMoneyCents(numeric * DISPLAY_USD_TO_CNY * 100);
  }
  return normalizeMoneyCents(fallbackCents);
}

export function normalizeMoneyCents(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return Number.NaN;
    const numeric = Number(trimmed.replace(/[^\d.-]/g, ''));
    return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.round(numeric) : Number.NaN;
}

export function normalizeAlertEmail(value) {
  const email = String(value || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return '';
  }
  return email.slice(0, 254);
}

export function maskEmail(email) {
  const [name, domain] = String(email || '').split('@');
  if (!name || !domain) return '';
  const head = name.slice(0, Math.min(2, name.length));
  return `${head}${name.length > 2 ? '***' : '*'}@${domain}`;
}
