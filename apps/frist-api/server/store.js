import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import {
  normalizeModelPrices, normalizeRechargePlans, mergeModelPrices,
  normalizeUserRecord, normalizeCredentialRecord, normalizeSupplierProfileRecord,
  pricingPayload as buildPricingPayload,
} from './catalog.js';

export { buildPricingPayload as pricingPayload };

export { normalizeUserRecord, normalizeCredentialRecord, normalizeSupplierProfileRecord };

export function createRuntimeStore(dataFile) {
  let writeQueue = Promise.resolve();

  async function load() {
    try {
      const raw = await readFile(dataFile, 'utf8');
      return normalizeRuntimeData(JSON.parse(raw));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
      return normalizeRuntimeData({});
    }
  }

  async function save(data) {
    await mkdir(dirname(dataFile), { recursive: true });
    await writeFile(dataFile, `${JSON.stringify(normalizeRuntimeData(data), null, 2)}\n`, 'utf8');
  }

  async function mutate(mutator) {
    const run = writeQueue.then(async () => {
      const data = await load();
      const result = await mutator(data);
      await save(data);
      return result;
    });
    writeQueue = run.catch(() => {});
    return run;
  }

  return { load, mutate };
}

function normalizeRuntimeData(data) {
  const pricing = normalizePricingConfig(data.pricing || {});
  return {
    users: Array.isArray(data.users) ? data.users.map(normalizeUserRecord) : [],
    sessions: data.sessions && typeof data.sessions === 'object' ? data.sessions : {},
    userKeys: Array.isArray(data.userKeys) ? data.userKeys : [],
    credentials: Array.isArray(data.credentials) ? data.credentials.map(normalizeCredentialRecord) : [],
    supplierProfiles: Array.isArray(data.supplierProfiles) ? data.supplierProfiles.map(normalizeSupplierProfileRecord) : [],
    priceDrafts: mergeModelPrices(Array.isArray(data.priceDrafts) ? data.priceDrafts : [], pricing.modelPrices),
    pricing,
    paymentOrders: Array.isArray(data.paymentOrders) ? data.paymentOrders : [],
    redemptions: Array.isArray(data.redemptions) ? data.redemptions : [],
    routeAffinities: data.routeAffinities && typeof data.routeAffinities === 'object' ? data.routeAffinities : {},
    lowInventoryAlerts: data.lowInventoryAlerts && typeof data.lowInventoryAlerts === 'object' ? data.lowInventoryAlerts : {},
    usedAdminClaimCodeHashes: Array.isArray(data.usedAdminClaimCodeHashes) ? data.usedAdminClaimCodeHashes : [],
    events: Array.isArray(data.events) ? data.events : [],
  };
}

function normalizePricingConfig(input = {}) {
  const rechargePlans = normalizeRechargePlans(input.rechargePlans);
  const modelPrices = normalizeModelPrices(input.modelPrices);
  return { rechargePlans, modelPrices };
}
