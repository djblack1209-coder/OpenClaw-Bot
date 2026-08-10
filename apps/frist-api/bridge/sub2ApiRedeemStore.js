import pg from 'pg';

const { Pool } = pg;
const ALLOWED_DENOMINATIONS = new Set([1, 10, 30, 50, 100, 300, 500, 1000]);

export function createSub2ApiRedeemStore(options = {}) {
  if (options.xianyuRedeemStore) return options.xianyuRedeemStore;
  const connectionString = String(
    options.sub2ApiDatabaseUrl ?? process.env.FRIST_API_SUB2API_DATABASE_URL ?? '',
  ).trim();
  if (!connectionString) return null;

  const pool = new Pool({
    connectionString,
    max: 2,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 3_000,
    application_name: 'jiyu-xianyu-fulfillment-bridge',
  });

  return {
    async reserve({ orderHash, denomination, planId = '' }) {
      assertOrderHash(orderHash);
      assertDenomination(denomination);
      const result = await pool.query(
        'SELECT * FROM jiyu_xianyu_reserve_redeem_code($1, $2, $3)',
        [orderHash, denomination, String(planId).slice(0, 120)],
      );
      return normalizeReservation(result.rows[0]);
    },

    async remap({ oldOrderHash, newOrderHash }) {
      assertOrderHash(oldOrderHash);
      assertOrderHash(newOrderHash);
      const result = await pool.query(
        'SELECT * FROM jiyu_xianyu_remap_redeem_reservation($1, $2)',
        [oldOrderHash, newOrderHash],
      );
      return normalizeReservation(result.rows[0]);
    },

    async close() {
      await pool.end();
    },
  };
}

export function isAllowedXianyuDenomination(value) {
  return ALLOWED_DENOMINATIONS.has(Number(value));
}

function assertOrderHash(value) {
  if (!/^[a-f0-9]{64}$/.test(String(value || ''))) {
    throw new TypeError('订单哈希格式无效');
  }
}

function assertDenomination(value) {
  if (!isAllowedXianyuDenomination(value)) {
    throw new TypeError('商品面额不受支持');
  }
}

function normalizeReservation(row) {
  if (!row?.redeem_code_id || !row?.code) {
    throw new Error('Sub2API 未返回可用兑换码');
  }
  return {
    redeemCodeId: String(row.redeem_code_id),
    code: String(row.code),
    type: String(row.type || 'balance'),
    denomination: Number(row.value),
    status: String(row.status || 'unused'),
    reservedAt: row.reserved_at ? new Date(row.reserved_at).toISOString() : '',
    idempotent: Boolean(row.idempotent),
  };
}
