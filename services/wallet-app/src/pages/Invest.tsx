import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPortfolio, getDevices, getPools } from '../api/stakes';
import type { PortfolioResponse, Device, PoolListItem } from '../api/stakes';
import DeviceTypeBadge from '../components/DeviceTypeBadge';
import ProgressBar from '../components/ProgressBar';

type Tab = 'portfolio' | 'devices' | 'pools';

export default function Invest({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('portfolio');
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [pools, setPools] = useState<PoolListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [p, d, pl] = await Promise.all([
          getPortfolio(userId),
          getDevices(),
          getPools(),
        ]);
        if (cancelled) return;
        setPortfolio(p);
        setDevices(d);
        setPools(pl);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [userId]);

  const tabClass = (t: Tab) =>
    `px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
      tab === t ? 'bg-amber-500 text-black' : 'bg-gray-800 text-gray-400'
    }`;

  return (
    <div className="p-4 pb-24 space-y-4">
      <h1 className="text-xl font-bold">Invest</h1>

      {/* Tab pills */}
      <div className="flex gap-2">
        <button className={tabClass('portfolio')} onClick={() => setTab('portfolio')}>Portfolio</button>
        <button className={tabClass('devices')} onClick={() => setTab('devices')}>Devices</button>
        <button className={tabClass('pools')} onClick={() => setTab('pools')}>Pools</button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-3 text-red-300 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-900 rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <>
          {tab === 'portfolio' && <PortfolioTab portfolio={portfolio} navigate={navigate} />}
          {tab === 'devices' && <DevicesTab devices={devices} navigate={navigate} />}
          {tab === 'pools' && <PoolsTab pools={pools} />}
        </>
      )}
    </div>
  );
}

// ── Portfolio Tab ──────────────────────────────────────

function PortfolioTab({
  portfolio,
  navigate,
}: {
  portfolio: PortfolioResponse | null;
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (!portfolio || portfolio.stakes.length === 0) {
    return <div className="text-gray-500 text-center py-12">まだデバイスシェアを所有していません</div>;
  }

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="bg-gradient-to-r from-amber-900/30 to-amber-800/10 rounded-xl p-4">
        <div className="text-xs text-gray-400">Total Estimated Reward</div>
        <div className="text-2xl font-bold text-amber-400">
          {(portfolio.total_estimated_reward_per_hour / 1000).toFixed(3)}
          <span className="text-sm text-gray-400 ml-1">SOMS/hr</span>
        </div>
      </div>

      {portfolio.stakes.map(s => (
        <button
          key={s.device_id}
          onClick={() => navigate(`/invest/device/${s.device_id}`)}
          className="w-full bg-gray-900 rounded-xl p-3 text-left"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium truncate mr-2">{s.device_id}</span>
            <DeviceTypeBadge type={s.device_type} />
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400">
            <span>{s.shares}/{s.total_shares} shares ({s.percentage.toFixed(1)}%)</span>
            <span className="text-amber-400">{(s.estimated_reward_per_hour / 1000).toFixed(3)}/hr</span>
          </div>
        </button>
      ))}
    </div>
  );
}

// ── Devices Tab ───────────────────────────────────────

function DevicesTab({
  devices,
  navigate,
}: {
  devices: Device[];
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (devices.length === 0) {
    return <div className="text-gray-500 text-center py-12">登録デバイスなし</div>;
  }

  const sorted = [...devices].sort((a, b) => {
    if (a.funding_open !== b.funding_open) return a.funding_open ? -1 : 1;
    return a.device_id.localeCompare(b.device_id);
  });

  return (
    <div className="space-y-3">
      {sorted.map(d => (
        <button
          key={d.id}
          onClick={() => navigate(`/invest/device/${d.device_id}`)}
          className="w-full bg-gray-900 rounded-xl p-3 text-left"
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-medium truncate">{d.display_name || d.device_id}</span>
              <DeviceTypeBadge type={d.device_type} />
            </div>
            {d.funding_open && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-900/60 text-emerald-300 shrink-0">
                Open
              </span>
            )}
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400">
            <span>{d.available_shares}/{d.total_shares} available</span>
            <span>{(d.share_price / 1000).toFixed(3)} SOMS/share</span>
          </div>
        </button>
      ))}
    </div>
  );
}

// ── Pools Tab ─────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-emerald-900/60 text-emerald-300',
  funded: 'bg-amber-900/60 text-amber-300',
  active: 'bg-blue-900/60 text-blue-300',
  closed: 'bg-gray-800 text-gray-400',
};

function PoolsTab({ pools }: { pools: PoolListItem[] }) {
  if (pools.length === 0) {
    return <div className="text-gray-500 text-center py-12">プールなし</div>;
  }

  return (
    <div className="space-y-3">
      {pools.map(p => {
        const date = new Date(p.created_at);
        const dateStr = `${date.getMonth() + 1}/${date.getDate()}`;
        return (
          <div key={p.id} className="bg-gray-900 rounded-xl p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-medium">{p.title}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[p.status] || STATUS_COLORS.closed}`}>
                {p.status}
              </span>
            </div>
            <ProgressBar
              value={p.progress_pct}
              label={`\u00a5${p.raised_jpy.toLocaleString()} / \u00a5${p.goal_jpy.toLocaleString()}`}
            />
            <div className="text-xs text-gray-500 text-right">{dateStr}</div>
          </div>
        );
      })}
    </div>
  );
}
