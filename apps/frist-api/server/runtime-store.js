import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';
import { mkdir, open, readFile, rename, rm } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';

import { isEncryptedRuntimeSecret, publicError } from './shared.js';


async function writeFileAtomic(filePath, text) {
  await mkdir(dirname(filePath), { recursive: true });
  const tempPath = join(
    dirname(filePath),
    `.${basename(filePath)}.${process.pid}.${Date.now()}.${randomBytes(4).toString('hex')}.tmp`,
  );
  const handle = await open(tempPath, 'w', 0o600);
  try {
    await handle.writeFile(text, 'utf8');
    await handle.sync();
  } catch (error) {
    await rm(tempPath, { force: true }).catch(() => {});
    throw error;
  } finally {
    await handle.close();
  }
  await rename(tempPath, filePath);
}


export function createRuntimeStore(dataFile, encryptionKey = '', beforeSave = null, normalizeData) {
  if (typeof normalizeData !== 'function') {
    throw new TypeError('runtime store 必须提供同步数据规范化函数');
  }
  let writeQueue = Promise.resolve();
  const encryption = createRuntimeEncryption(encryptionKey);

  async function load() {
    try {
      const raw = await readFile(dataFile, 'utf8');
      return normalizeData(decryptRuntimeData(JSON.parse(raw), encryption));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
      return normalizeData({});
    }
  }

  async function save(data) {
    const normalized = normalizeData(data);
    if (typeof beforeSave === 'function') {
      await beforeSave(normalized);
    }
    await writeFileAtomic(dataFile, `${JSON.stringify(encryptRuntimeData(normalized, encryption), null, 2)}\n`);
  }

  function enqueueMutation(mutator, { allowAsyncMutator }) {
    const run = writeQueue.then(async () => {
      const data = await load();
      const pendingResult = mutator(data);
      if (!allowAsyncMutator && pendingResult && typeof pendingResult.then === 'function') {
        throw new TypeError('runtime 写队列只允许同步数据变更，外部异步调用必须在队列外执行');
      }
      const result = allowAsyncMutator ? await pendingResult : pendingResult;
      try {
        await save(data);
      } catch (error) {
        process.emitWarning(`CC中转 runtime 写入失败: ${error.message}`, {
          code: 'FRIST_API_RUNTIME_WRITE_FAILED',
        });
        throw error;
      }
      return result;
    });
    writeQueue = run.catch(() => {});
    return run;
  }

  function mutate(mutator) {
    return enqueueMutation(mutator, { allowAsyncMutator: false });
  }

  function mutateBlocking(mutator) {
    return enqueueMutation(mutator, { allowAsyncMutator: true });
  }

  return { load, mutate, mutateBlocking };
}


function createRuntimeEncryption(secret) {
  const value = String(secret || '').trim();
  if (!value) {
    return null;
  }
  return createHash('sha256').update(value).digest();
}


function encryptRuntimeData(data, encryption) {
  if (!encryption) {
    return data;
  }
  const copy = structuredCloneJson(data);
  copy.__encryption = {
    version: 1,
    algorithm: 'aes-256-gcm',
    fields: ['userKeys.secret', 'credentials.rawKey', 'plusAccounts.secrets', 'rtAccounts.refreshToken'],
  };
  copy.userKeys = copy.userKeys.map((key) => ({
    ...key,
    secret: encryptSecretField(key.secret, encryption),
  }));
  copy.credentials = copy.credentials.map((credential) => ({
    ...credential,
    rawKey: encryptSecretField(credential.rawKey, encryption),
  }));
  copy.plusAccounts = copy.plusAccounts.map((account) => ({
    ...account,
    secrets: encryptSecretField(account.secrets, encryption),
  }));
  copy.rtAccounts = copy.rtAccounts.map((account) => ({
    ...account,
    refreshToken: encryptSecretField(account.refreshToken, encryption),
  }));
  return copy;
}


function decryptRuntimeData(data, encryption) {
  const copy = structuredCloneJson(data || {});
  if (!encryption) {
    return copy;
  }
  const hasEncryptionMarker = Boolean(copy.__encryption);
  const decryptRuntimeSecret = (value) =>
    decryptRuntimeSecretField(value, encryption, {
      allowUnreadableEncrypted: true,
      allowLegacyOrphan: !hasEncryptionMarker,
    });
  try {
    copy.userKeys = Array.isArray(copy.userKeys)
      ? copy.userKeys.map((key) => ({ ...key, secret: decryptRuntimeSecret(key.secret) }))
      : [];
    copy.credentials = Array.isArray(copy.credentials)
      ? copy.credentials.map((credential) => ({ ...credential, rawKey: decryptRuntimeSecret(credential.rawKey) }))
      : [];
    copy.plusAccounts = Array.isArray(copy.plusAccounts)
      ? copy.plusAccounts.map((account) => ({ ...account, secrets: decryptRuntimeSecret(account.secrets) }))
      : [];
    copy.rtAccounts = Array.isArray(copy.rtAccounts)
      ? copy.rtAccounts.map((account) => ({ ...account, refreshToken: decryptRuntimeSecret(account.refreshToken) }))
      : [];
    delete copy.__encryption;
    return copy;
  } catch (error) {
    throw normalizePublicError(error);
  }
}


function decryptRuntimeSecretField(value, encryption, options = {}) {
  try {
    return decryptSecretField(value, encryption);
  } catch (error) {
    // 历史密钥不可恢复时保留密文，让上层脱敏并提示重新生成，避免整站不可用。
    if ((options.allowUnreadableEncrypted || options.allowLegacyOrphan) && isEncryptedRuntimeSecret(value)) {
      return String(value || '');
    }
    throw error;
  }
}


export function encryptSecretField(value, encryption) {
  const text = String(value || '');
  if (!text || text.startsWith('enc:v1:')) {
    return text;
  }
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', encryption, iv);
  const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
  return `enc:v1:${iv.toString('base64url')}:${cipher.getAuthTag().toString('base64url')}:${encrypted.toString('base64url')}`;
}


export function decryptSecretField(value, encryption) {
  const text = String(value || '');
  if (!text.startsWith('enc:v1:')) {
    return text;
  }
  const [, version, ivText, authTagText, encryptedText] = text.split(':');
  if (version !== 'v1' || !ivText || !authTagText || !encryptedText) {
    throw publicError(500, '运行数据加密字段格式不正确');
  }
  try {
    const decipher = createDecipheriv('aes-256-gcm', encryption, Buffer.from(ivText, 'base64url'));
    decipher.setAuthTag(Buffer.from(authTagText, 'base64url'));
    return `${decipher.update(Buffer.from(encryptedText, 'base64url'), undefined, 'utf8')}${decipher.final('utf8')}`;
  } catch {
    throw publicError(500, '运行数据加密密钥不匹配');
  }
}


function structuredCloneJson(value) {
  return JSON.parse(JSON.stringify(value || {}));
}


function normalizePublicError(error) {
  if (error?.expose) {
    return error;
  }
  return publicError(500, String(error?.message || '服务暂时不可用'));
}
