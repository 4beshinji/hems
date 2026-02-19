import type { LedgerEntry } from '../api/wallet';

const TYPE_LABELS: Record<string, string> = {
  INFRASTRUCTURE_REWARD: 'Infra Reward',
  TASK_REWARD: 'Task Reward',
  P2P_TRANSFER: 'Transfer',
  FEE_BURN: 'Fee Burn',
  DEMURRAGE_BURN: 'Demurrage',
};

interface TransactionItemProps {
  entry: LedgerEntry;
}

export default function TransactionItem({ entry }: TransactionItemProps) {
  const isCredit = entry.entry_type === 'CREDIT';
  const sign = isCredit ? '+' : '-';
  const colorClass = isCredit ? 'text-emerald-400' : 'text-red-400';
  const label = TYPE_LABELS[entry.transaction_type] || entry.transaction_type;
  const date = new Date(entry.created_at);
  const timeStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;

  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-800 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-200 truncate">{label}</p>
        {entry.description && (
          <p className="text-xs text-gray-500 truncate">{entry.description}</p>
        )}
        <p className="text-xs text-gray-600">{timeStr}</p>
      </div>
      <div className={`text-right ml-3 flex-shrink-0 ${colorClass}`}>
        <p className="text-sm font-semibold">{sign}{(Math.abs(entry.amount) / 1000).toFixed(3)}</p>
        <p className="text-xs text-gray-600">{(entry.balance_after / 1000).toFixed(3)}</p>
      </div>
    </div>
  );
}
