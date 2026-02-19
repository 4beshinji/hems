import { useEffect, useState, useCallback, useRef } from 'react';
import { getHistory, type LedgerEntry } from '../api/wallet';
import TransactionItem from '../components/TransactionItem';

const TX_TYPES = ['ALL', 'TASK_REWARD', 'P2P_TRANSFER', 'INFRASTRUCTURE_REWARD', 'FEE_BURN', 'DEMURRAGE_BURN'] as const;
const TYPE_LABELS: Record<string, string> = {
  ALL: 'All',
  TASK_REWARD: 'Task',
  P2P_TRANSFER: 'P2P',
  INFRASTRUCTURE_REWARD: 'Infra',
  FEE_BURN: 'Fee',
  DEMURRAGE_BURN: 'Demurrage',
};

interface HistoryProps {
  userId: number;
}

const PAGE_SIZE = 20;

export default function History({ userId }: HistoryProps) {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [filter, setFilter] = useState<string>('ALL');
  const offsetRef = useRef(0);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const loadMore = useCallback(async () => {
    if (!hasMore) return;
    setLoading(true);
    try {
      const batch = await getHistory(userId, PAGE_SIZE, offsetRef.current);
      if (batch.length < PAGE_SIZE) setHasMore(false);
      setEntries(prev => [...prev, ...batch]);
      offsetRef.current += batch.length;
    } catch {
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [userId, hasMore]);

  // Initial load
  useEffect(() => {
    offsetRef.current = 0;
    setEntries([]);
    setHasMore(true);
    loadMore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting && !loading) loadMore(); },
      { threshold: 0.1 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, loading]);

  const filtered = filter === 'ALL'
    ? entries
    : entries.filter(e => e.transaction_type === filter);

  return (
    <div className="p-4 pb-24 space-y-4">
      <h1 className="text-xl font-bold">Transaction History</h1>

      {/* Filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
        {TX_TYPES.map(type => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              filter === type
                ? 'bg-amber-500 text-black'
                : 'bg-gray-800 text-gray-400'
            }`}
          >
            {TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      {filtered.length === 0 && !loading ? (
        <p className="text-gray-500 text-sm text-center py-8">No transactions found.</p>
      ) : (
        <div className="bg-gray-900 rounded-xl px-4">
          {filtered.map(entry => (
            <TransactionItem key={entry.id} entry={entry} />
          ))}
        </div>
      )}

      <div ref={sentinelRef} className="h-4" />

      {loading && (
        <div className="flex justify-center py-4">
          <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
}
