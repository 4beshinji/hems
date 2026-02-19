/**
 * Wallet Service API client.
 *
 * In dev mode, Vite proxies /api/wallet/* → wallet service at :8003.
 * In production, nginx handles the routing.
 *
 * See docs/parallel-dev/API_CONTRACTS.md §2 for full contract details.
 */

const BASE = import.meta.env.VITE_WALLET_API_URL || '/api/wallet';

export interface Wallet {
  id: number;
  user_id: number;
  balance: number; // milli-units (1000 = 1.0 SOMS)
  created_at: string;
  updated_at: string;
}

export interface LedgerEntry {
  id: number;
  transaction_id: string;
  wallet_id: number;
  amount: number;
  balance_after: number;
  entry_type: 'DEBIT' | 'CREDIT';
  transaction_type: string;
  description: string | null;
  reference_id: string | null;
  counterparty_wallet_id: number | null;
  created_at: string;
}

export interface SupplyStats {
  total_issued: number;
  total_burned: number;
  circulating: number;
}

export interface TransferFeeInfo {
  fee_rate: number;
  fee_amount: number;
  net_amount: number;
  min_transfer: number;
  below_minimum: boolean;
}

export async function getWallet(userId: number): Promise<Wallet> {
  const res = await fetch(`${BASE}/wallets/${userId}`);
  if (!res.ok) throw new Error(`Failed to get wallet: ${res.status}`);
  return res.json();
}

export async function getHistory(userId: number, limit = 50, offset = 0): Promise<LedgerEntry[]> {
  const res = await fetch(`${BASE}/wallets/${userId}/history?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`Failed to get history: ${res.status}`);
  return res.json();
}

export async function getSupply(): Promise<SupplyStats> {
  const res = await fetch(`${BASE}/supply`);
  if (!res.ok) throw new Error(`Failed to get supply: ${res.status}`);
  return res.json();
}

export async function previewFee(amount: number): Promise<TransferFeeInfo> {
  const res = await fetch(`${BASE}/transactions/transfer-fee?amount=${amount}`);
  if (!res.ok) throw new Error(`Failed to preview fee: ${res.status}`);
  return res.json();
}

export async function sendTransfer(fromUserId: number, toUserId: number, amount: number, description?: string) {
  const res = await fetch(`${BASE}/transactions/p2p-transfer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_user_id: fromUserId, to_user_id: toUserId, amount, description }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Transfer failed' }));
    throw new Error(err.detail || `Transfer failed: ${res.status}`);
  }
  return res.json();
}

export async function claimTaskReward(userId: number, taskId: number, amount: number) {
  const res = await fetch(`${BASE}/transactions/task-reward`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, amount, task_id: taskId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Claim failed' }));
    throw new Error(err.detail || `Claim failed: ${res.status}`);
  }
  return res.json();
}
