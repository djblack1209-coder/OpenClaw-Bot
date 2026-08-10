#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

const API_ORIGIN = 'https://jiyu.245334.xyz';
const ASYNC_API_URL = `${API_ORIGIN}/v1/images/generations/async`;
const TASK_API_URL = `${API_ORIGIN}/v1/images/tasks`;
const API_HOST = 'jiyu.245334.xyz';
const KEYCHAIN_SERVICE = 'JIYU AI 生图 API Key';
const MAX_RESPONSE_BYTES = 20 * 1024 * 1024;
const HTTP_TIMEOUT_MS = 30_000;
const MAX_TASK_WAIT_MS = 30 * 60_000;
const DEFAULT_POLL_INTERVAL_MS = 3_000;
const DEFAULT_MODEL = 'gpt-image-2';
const ALLOWED_SIZES = new Set(['1024x1024', '1536x1024', '1024x1536']);
const ALLOWED_QUALITIES = new Set(['auto', 'low', 'medium', 'standard', 'high']);
const ALLOWED_FORMATS = new Set(['png', 'jpeg', 'webp']);

function readApiKey() {
  const environmentKey = process.env.JIYU_IMAGE_API_KEY?.trim();
  if (environmentKey) {
    return environmentKey;
  }
  if (process.platform !== 'darwin') {
    throw new Error('尚未配置 JIYU 生图专用 Key');
  }
  try {
    return execFileSync('/usr/bin/security', [
      'find-generic-password',
      '-s',
      KEYCHAIN_SERVICE,
      '-w',
    ], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 5_000,
    }).trim();
  } catch {
    throw new Error('尚未在 macOS 钥匙串中配置 JIYU 生图专用 Key');
  }
}

function validateInput(input) {
  const prompt = typeof input.prompt === 'string' ? input.prompt.trim() : '';
  if (!prompt || prompt.length > 4_000) {
    throw new Error('提示词不能为空，且不能超过 4000 个字符');
  }
  const model = input.model || DEFAULT_MODEL;
  const size = input.size || '1024x1024';
  const quality = input.quality || 'low';
  const outputFormat = input.output_format || 'png';
  if (model !== DEFAULT_MODEL) {
    throw new Error('当前只支持 gpt-image-2');
  }
  if (!ALLOWED_SIZES.has(size)) {
    throw new Error('尺寸只支持 1024x1024、1536x1024 或 1024x1536');
  }
  if (!ALLOWED_QUALITIES.has(quality)) {
    throw new Error('质量只支持 auto、low、medium、standard 或 high');
  }
  if (!ALLOWED_FORMATS.has(outputFormat)) {
    throw new Error('输出格式只支持 png、jpeg 或 webp');
  }
  return { prompt, model, size, quality, outputFormat };
}

async function readLimitedBody(response) {
  const declaredLength = Number(response.headers.get('content-length') || 0);
  if (declaredLength > MAX_RESPONSE_BYTES) {
    throw new Error('生图响应超过 20 MiB 安全上限');
  }
  const chunks = [];
  let total = 0;
  for await (const chunk of response.body || []) {
    total += chunk.length;
    if (total > MAX_RESPONSE_BYTES) {
      throw new Error('生图响应超过 20 MiB 安全上限');
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, total);
}

function friendlyHttpError(status) {
  if (status === 401 || status === 403) {
    return '生图 Key 无效、已停用或没有生图分组权限';
  }
  if (status === 402) {
    return '余额不足，请先到 JIYU AI 充值中心充值';
  }
  if (status === 429) {
    return '生图请求过于频繁，请稍后再试';
  }
  if (status >= 500) {
    return '生图渠道暂时不可用，请稍后再试或切换渠道';
  }
  return `生图请求失败（HTTP ${status}）`;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('JIYU 服务响应超时，请稍后重试');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function readJsonResponse(response) {
  const rawBody = await readLimitedBody(response);
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.toLowerCase().includes('application/json')) {
    if (!response.ok) {
      throw new Error(friendlyHttpError(response.status));
    }
    throw new Error('站点返回了无法识别的响应格式');
  }
  try {
    return JSON.parse(rawBody.toString('utf8'));
  } catch {
    throw new Error('站点返回的生图结果无法解析');
  }
}

function validateTaskId(value) {
  if (typeof value !== 'string' || !/^imgtask_[A-Za-z0-9]{8,96}$/.test(value)) {
    throw new Error('站点没有返回有效的异步任务编号');
  }
  return value;
}

function trustedImageHost(hostname) {
  return hostname === API_HOST || hostname.endsWith('.r2.cloudflarestorage.com');
}

async function downloadJiyuImage(urlString) {
  const url = new URL(urlString);
  if (url.protocol !== 'https:' || url.username || url.password || !trustedImageHost(url.hostname)) {
    throw new Error('站点返回了不受信任的图片地址');
  }
  const response = await fetchWithTimeout(url, { redirect: 'error' });
  if (!response.ok) {
    throw new Error(friendlyHttpError(response.status));
  }
  const contentType = response.headers.get('content-type')?.split(';')[0]?.trim() || '';
  if (!contentType.startsWith('image/')) {
    throw new Error('站点返回的内容不是图片');
  }
  return { bytes: await readLimitedBody(response), mimeType: contentType };
}

async function generateImage(input) {
  const { prompt, model, size, quality, outputFormat } = validateInput(input);
  const apiKey = readApiKey();
  if (!apiKey || apiKey.length < 20) {
    throw new Error('JIYU 生图专用 Key 格式无效');
  }

  const submitResponse = await fetchWithTimeout(ASYNC_API_URL, {
    method: 'POST',
    redirect: 'error',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model,
      prompt,
      size,
      quality,
      output_format: outputFormat,
      n: 1,
    }),
  });
  const submitPayload = await readJsonResponse(submitResponse);
  if (!submitResponse.ok) {
    throw new Error(friendlyHttpError(submitResponse.status));
  }
  if (submitResponse.status !== 202) {
    throw new Error(`异步生图任务未被接受（HTTP ${submitResponse.status}）`);
  }

  const taskId = validateTaskId(submitPayload?.task_id || submitPayload?.id);
  const retryAfterHeader = submitResponse.headers.get('retry-after');
  const retryAfter = retryAfterHeader === null ? Number.NaN : Number(retryAfterHeader);
  const pollInterval = Number.isFinite(retryAfter)
    ? Math.min(10_000, Math.max(1_000, retryAfter * 1_000))
    : DEFAULT_POLL_INTERVAL_MS;
  const deadline = Date.now() + MAX_TASK_WAIT_MS;
  let payload = submitPayload;
  while (Date.now() < deadline) {
    await delay(pollInterval);
    const pollResponse = await fetchWithTimeout(`${TASK_API_URL}/${taskId}`, {
      redirect: 'error',
      headers: { authorization: `Bearer ${apiKey}` },
    });
    payload = await readJsonResponse(pollResponse);
    if (!pollResponse.ok) {
      throw new Error(friendlyHttpError(pollResponse.status));
    }
    if (payload?.status === 'failed' || payload?.status === 'cancelled' || payload?.status === 'expired') {
      throw new Error(friendlyHttpError(Number(payload?.http_status) || 502));
    }
    if (payload?.status === 'completed') {
      break;
    }
    if (!['processing', 'pending', 'queued'].includes(payload?.status)) {
      throw new Error('异步生图任务返回了未知状态');
    }
  }
  if (payload?.status !== 'completed') {
    throw new Error('异步生图任务超过 30 分钟，已安全停止轮询');
  }

  const imageUrl = payload?.result?.data?.[0]?.url || payload?.image_url;
  if (typeof imageUrl !== 'string') {
    throw new Error('站点没有返回对象存储图片地址');
  }
  const { bytes, mimeType } = await downloadJiyuImage(imageUrl);
  if (!bytes.length || bytes.length > MAX_RESPONSE_BYTES) {
    throw new Error('生成图片为空或超过 20 MiB 安全上限');
  }
  return { bytes, mimeType, model, size, quality, outputFormat };
}

const server = new Server(
  { name: 'jiyu-ai-image', version: '1.1.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: 'generate_image',
    description: '通过 JIYU AI 原生异步生图任务生成一张图片。每次成功调用都会产生按张费用。',
    inputSchema: {
      type: 'object',
      properties: {
        prompt: { type: 'string', description: '图片内容和风格要求。' },
        model: { type: 'string', enum: [DEFAULT_MODEL], default: DEFAULT_MODEL },
        size: { type: 'string', enum: [...ALLOWED_SIZES], default: '1024x1024' },
        quality: { type: 'string', enum: [...ALLOWED_QUALITIES], default: 'low' },
        output_format: { type: 'string', enum: [...ALLOWED_FORMATS], default: 'png' },
      },
      required: ['prompt'],
      additionalProperties: false,
    },
  }],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name !== 'generate_image') {
    return { isError: true, content: [{ type: 'text', text: '未知的 MCP 工具' }] };
  }
  try {
    const result = await generateImage(request.params.arguments || {});
    return {
      content: [
        { type: 'image', data: result.bytes.toString('base64'), mimeType: result.mimeType },
        {
          type: 'text',
          text: `已生成 1 张图片：${result.model}，${result.size}，${result.quality}，${result.outputFormat}`,
        },
      ],
    };
  } catch (error) {
    return {
      isError: true,
      content: [{ type: 'text', text: error instanceof Error ? error.message : '生图请求失败' }],
    };
  }
});

await server.connect(new StdioServerTransport());
