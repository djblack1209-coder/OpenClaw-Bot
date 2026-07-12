import { createHash, timingSafeEqual } from 'node:crypto';
import { isIP } from 'node:net';

export const DISPLAY_USD_TO_CNY = 7.2;

export function safeEqual(left, right) {
  const leftDigest = createHash('sha256').update(String(left ?? '')).digest();
  const rightDigest = createHash('sha256').update(String(right ?? '')).digest();
  return timingSafeEqual(leftDigest, rightDigest);
}

export function formatCny(cents) {
  return `¥${(Number(cents || 0) / 100).toFixed(2)}`;
}

export function formatUsdFromCnyCents(cents, rate = DISPLAY_USD_TO_CNY) {
  const safeRate = Number(rate || DISPLAY_USD_TO_CNY) || DISPLAY_USD_TO_CNY;
  return `$${(Number(cents || 0) / 100 / safeRate).toFixed(2)}`;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

export function formatEmailTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || '-');
  }
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Shanghai',
  }).format(date);
}

export function requestOrigin(request) {
  const forwardedProtocol = trustedProxyHeader(request, 'x-forwarded-proto').toLowerCase().replace(/:$/, '');
  const protocol = forwardedProtocol === 'https' || (!forwardedProtocol && request.socket?.encrypted) ? 'https' : 'http';
  const forwardedHost = trustedProxyHeader(request, 'x-forwarded-host');
  const host = normalizeOriginHost(forwardedHost || firstHeaderToken(request.headers.host)) || '127.0.0.1';
  return `${protocol}://${host}`;
}

export function clientIp(request) {
  const remoteAddress = normalizeIpAddress(request.socket?.remoteAddress);
  if (!remoteAddress || !isPrivateIpLiteral(remoteAddress)) {
    return remoteAddress || 'unknown';
  }
  const cloudflareAddress = normalizeIpAddress(headerValue(request, 'cf-connecting-ip'));
  if (cloudflareAddress) {
    return cloudflareAddress;
  }
  const realAddress = normalizeIpAddress(headerValue(request, 'x-real-ip'));
  if (realAddress) {
    return realAddress;
  }
  const forwardedAddresses = headerValue(request, 'x-forwarded-for')
    .split(',')
    .map(normalizeIpAddress)
    .filter(Boolean);
  return forwardedAddresses.findLast((address) => !isPrivateIpLiteral(address)) || forwardedAddresses.at(-1) || remoteAddress;
}

function headerValue(request, name) {
  const value = request.headers[name.toLowerCase()];
  if (Array.isArray(value)) {
    return value[0] || '';
  }
  return value || '';
}

function trustedProxyHeader(request, name) {
  const remoteAddress = normalizeIpAddress(request.socket?.remoteAddress);
  if (!remoteAddress || !isPrivateIpLiteral(remoteAddress)) {
    return '';
  }
  return firstHeaderToken(headerValue(request, name));
}

function firstHeaderToken(value) {
  const raw = Array.isArray(value) ? value[0] : String(value || '');
  return raw.split(',')[0].trim();
}

function normalizeOriginHost(value) {
  const raw = String(value || '').trim().replace(/^https?:\/\//i, '').split('/')[0].trim();
  if (!raw || /[\s\\@?#]/.test(raw)) {
    return '';
  }
  try {
    const parsed = new URL(`http://${raw}`);
    return parsed.username || parsed.password || parsed.pathname !== '/' ? '' : parsed.host;
  } catch {
    return '';
  }
}

function normalizeIpAddress(value) {
  const normalized = String(value || '').trim().replace(/^\[|\]$/g, '').toLowerCase();
  const ip = normalized.startsWith('::ffff:') ? normalized.slice('::ffff:'.length) : normalized;
  return isIP(ip) ? ip : '';
}

function isPrivateIpLiteral(value) {
  const ip = String(value || '').replace(/^\[|\]$/g, '').toLowerCase();
  if (!isIP(ip)) return false;
  if (ip === '::1' || ip === '0:0:0:0:0:0:0:1') return true;
  if (/^(fc|fd|fe80):/i.test(ip)) return true;
  if (ip.startsWith('::ffff:')) {
    return isPrivateIpLiteral(ip.slice('::ffff:'.length));
  }
  const parts = ip.split('.').map((item) => Number(item));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  const [first, second] = parts;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}
