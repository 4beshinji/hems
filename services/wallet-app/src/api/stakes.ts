/**
 * Stakes / Investment API client.
 *
 * Follows the same pattern as wallet.ts (bare fetch, BASE URL, error handling).
 */

const BASE = import.meta.env.VITE_WALLET_API_URL || '/api/wallet';

// ── Types ──────────────────────────────────────────────

export interface Device {
  id: number;
  device_id: string;
  owner_id: number;
  device_type: string;
  display_name: string | null;
  is_active: boolean;
  total_shares: number;
  available_shares: number;
  share_price: number;
  funding_open: boolean;
  power_mode: string;
  battery_pct: number | null;
  utility_score: number;
  xp: number;
  last_heartbeat_at: string | null;
}

export interface StakeResponse {
  id: number;
  device_id: number;
  user_id: number;
  shares: number;
  percentage: number;
  acquired_at: string;
}

export interface DeviceFundingResponse {
  device_id: string;
  total_shares: number;
  available_shares: number;
  share_price: number;
  funding_open: boolean;
  stakeholders: StakeResponse[];
  estimated_reward_per_hour: number;
}

export interface PortfolioEntry {
  device_id: string;
  device_type: string;
  shares: number;
  total_shares: number;
  percentage: number;
  estimated_reward_per_hour: number;
}

export interface PortfolioResponse {
  user_id: number;
  stakes: PortfolioEntry[];
  total_estimated_reward_per_hour: number;
}

export interface PoolListItem {
  id: number;
  title: string;
  goal_jpy: number;
  raised_jpy: number;
  status: string;
  progress_pct: number;
  created_at: string;
}

// ── API Functions ──────────────────────────────────────

export async function getDevices(): Promise<Device[]> {
  const res = await fetch(`${BASE}/devices/`);
  if (!res.ok) throw new Error(`Failed to get devices: ${res.status}`);
  return res.json();
}

export async function getDeviceFunding(deviceId: string): Promise<DeviceFundingResponse> {
  const res = await fetch(`${BASE}/devices/${deviceId}/stakes`);
  if (!res.ok) throw new Error(`Failed to get device funding: ${res.status}`);
  return res.json();
}

export async function buyShares(deviceId: string, userId: number, shares: number): Promise<StakeResponse> {
  const res = await fetch(`${BASE}/devices/${deviceId}/stakes/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, shares }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Purchase failed' }));
    throw new Error(err.detail || `Purchase failed: ${res.status}`);
  }
  return res.json();
}

export async function returnShares(deviceId: string, userId: number, shares: number): Promise<StakeResponse> {
  const res = await fetch(`${BASE}/devices/${deviceId}/stakes/return`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, shares }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Return failed' }));
    throw new Error(err.detail || `Return failed: ${res.status}`);
  }
  return res.json();
}

export async function getPortfolio(userId: number): Promise<PortfolioResponse> {
  const res = await fetch(`${BASE}/users/${userId}/portfolio`);
  if (!res.ok) throw new Error(`Failed to get portfolio: ${res.status}`);
  return res.json();
}

export async function getPools(): Promise<PoolListItem[]> {
  const res = await fetch(`${BASE}/pools`);
  if (!res.ok) throw new Error(`Failed to get pools: ${res.status}`);
  return res.json();
}
