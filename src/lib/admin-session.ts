import "server-only";
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

const sessionLifetimeSeconds = 60 * 60;

function signature(key: string, payload: string) {
  return createHmac("sha256", key).update(`heardit-admin-v1:${payload}`).digest("hex");
}

export function createAdminSession(key: string) {
  const payload = `${Math.floor(Date.now() / 1000)}.${randomBytes(16).toString("hex")}`;
  return `${payload}.${signature(key, payload)}`;
}

export function isValidAdminSession(key: string, value?: string) {
  if (!value || key.length < 32) return false;
  const parts = value.split(".");
  if (parts.length !== 3 || !/^\d+$/.test(parts[0]) || !/^[a-f0-9]{32}$/.test(parts[1])) return false;
  const issuedAt = Number(parts[0]);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isSafeInteger(issuedAt) || issuedAt > now || now - issuedAt > sessionLifetimeSeconds) return false;
  const expected = Buffer.from(signature(key, `${parts[0]}.${parts[1]}`), "hex");
  const supplied = Buffer.from(parts[2], "hex");
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}
