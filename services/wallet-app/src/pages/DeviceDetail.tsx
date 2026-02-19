import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDeviceFunding, getDevices, buyShares, returnShares } from '../api/stakes';
import type { DeviceFundingResponse } from '../api/stakes';
import DeviceTypeBadge from '../components/DeviceTypeBadge';
import ProgressBar from '../components/ProgressBar';

export default function DeviceDetail({ userId }: { userId: number }) {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DeviceFundingResponse | null>(null);
  const [deviceType, setDeviceType] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action state
  const [buyQty, setBuyQty] = useState('');
  const [returnQty, setReturnQty] = useState('');
  const [actionMsg, setActionMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function loadData() {
    if (!deviceId) return;
    try {
      const d = await getDeviceFunding(deviceId);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!deviceId) return;
      try {
        const [funding, devices] = await Promise.all([
          getDeviceFunding(deviceId),
          getDevices(),
        ]);
        if (cancelled) return;
        setData(funding);
        const dev = devices.find(d => d.device_id === deviceId);
        if (dev) setDeviceType(dev.device_type);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [deviceId]);

  if (!deviceId) return null;

  const myStake = data?.stakeholders.find(s => s.user_id === userId);
  const isOwner = data?.stakeholders.some(s => s.user_id === userId && s.shares === data.total_shares);
  const soldShares = data ? data.total_shares - data.available_shares : 0;
  const soldPct = data ? (soldShares / data.total_shares) * 100 : 0;

  async function handleBuy() {
    const qty = parseInt(buyQty, 10);
    if (!qty || qty <= 0) return;
    setSubmitting(true);
    setActionMsg(null);
    try {
      await buyShares(deviceId!, userId, qty);
      setActionMsg({ type: 'success', text: `${qty} shares purchased` });
      setBuyQty('');
      await loadData();
    } catch (e) {
      setActionMsg({ type: 'error', text: e instanceof Error ? e.message : 'Purchase failed' });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReturn() {
    const qty = parseInt(returnQty, 10);
    if (!qty || qty <= 0) return;
    setSubmitting(true);
    setActionMsg(null);
    try {
      await returnShares(deviceId!, userId, qty);
      setActionMsg({ type: 'success', text: `${qty} shares returned` });
      setReturnQty('');
      await loadData();
    } catch (e) {
      setActionMsg({ type: 'error', text: e instanceof Error ? e.message : 'Return failed' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="p-4 pb-24 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/invest')} className="text-gray-400 hover:text-white">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-xl font-bold truncate">{deviceId}</h1>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-3 text-red-300 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-900 rounded-xl animate-pulse" />)}
        </div>
      ) : data && (
        <>
          {/* Device info */}
          <div className="bg-gray-900 rounded-xl p-4 space-y-2">
            <div className="flex items-center gap-2">
              {deviceType && <DeviceTypeBadge type={deviceType} />}
              <span className="text-sm text-gray-400">
                {(data.share_price / 1000).toFixed(3)} SOMS/share
              </span>
            </div>
            <div className="text-sm text-gray-400">
              Estimated reward: <span className="text-amber-400 font-medium">{(data.estimated_reward_per_hour / 1000).toFixed(3)} SOMS/hr</span>
            </div>
          </div>

          {/* Funding status */}
          <div className="bg-gray-900 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Funding</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                data.funding_open ? 'bg-emerald-900/60 text-emerald-300' : 'bg-gray-800 text-gray-400'
              }`}>
                {data.funding_open ? 'Open' : 'Closed'}
              </span>
            </div>
            <div className="text-sm text-gray-400">
              {soldShares}/{data.total_shares} shares sold &middot; {data.available_shares} available
            </div>
            <ProgressBar value={soldPct} color={data.funding_open ? 'bg-amber-500' : 'bg-gray-600'} />
          </div>

          {/* Stakeholders */}
          <div className="bg-gray-900 rounded-xl p-4 space-y-2">
            <h2 className="text-sm font-medium mb-2">Stakeholders</h2>
            {data.stakeholders.length === 0 ? (
              <div className="text-gray-500 text-sm">No stakeholders yet</div>
            ) : (
              data.stakeholders.map(s => (
                <div
                  key={s.id}
                  className={`flex items-center justify-between text-sm py-1 ${
                    s.user_id === userId ? 'text-amber-400' : 'text-gray-300'
                  }`}
                >
                  <span>User #{s.user_id}{s.user_id === userId ? ' (you)' : ''}</span>
                  <span>{s.shares} shares ({s.percentage.toFixed(1)}%)</span>
                </div>
              ))
            )}
          </div>

          {/* Actions */}
          {isOwner ? (
            <div className="bg-gray-900 rounded-xl p-4 text-center text-sm text-gray-400">
              あなたはこのデバイスのオーナーです
            </div>
          ) : (
            <div className="space-y-3">
              {/* Buy */}
              {data.funding_open && data.available_shares > 0 && (
                <div className="bg-gray-900 rounded-xl p-4 space-y-3">
                  <h2 className="text-sm font-medium">Buy Shares</h2>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max={data.available_shares}
                      value={buyQty}
                      onChange={e => setBuyQty(e.target.value)}
                      placeholder="Qty"
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"
                    />
                    <button
                      onClick={handleBuy}
                      disabled={submitting || !buyQty || parseInt(buyQty) <= 0}
                      className="px-4 py-2 bg-amber-500 text-black font-semibold rounded-lg text-sm disabled:opacity-40"
                    >
                      Buy
                    </button>
                  </div>
                  {buyQty && parseInt(buyQty) > 0 && (
                    <div className="text-xs text-gray-400">
                      Cost: {(parseInt(buyQty) * data.share_price / 1000).toFixed(3)} SOMS
                    </div>
                  )}
                </div>
              )}

              {/* Return */}
              {myStake && myStake.shares > 0 && (
                <div className="bg-gray-900 rounded-xl p-4 space-y-3">
                  <h2 className="text-sm font-medium">Return Shares</h2>
                  <div className="text-xs text-gray-400 mb-1">
                    You own {myStake.shares} shares
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max={myStake.shares}
                      value={returnQty}
                      onChange={e => setReturnQty(e.target.value)}
                      placeholder="Qty"
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500"
                    />
                    <button
                      onClick={handleReturn}
                      disabled={submitting || !returnQty || parseInt(returnQty) <= 0}
                      className="px-4 py-2 bg-gray-700 text-white font-semibold rounded-lg text-sm disabled:opacity-40"
                    >
                      Return
                    </button>
                  </div>
                  {returnQty && parseInt(returnQty) > 0 && (
                    <div className="text-xs text-gray-400">
                      Refund: {(parseInt(returnQty) * data.share_price / 1000).toFixed(3)} SOMS
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Result message */}
          {actionMsg && (
            <div className={`rounded-xl p-3 text-sm ${
              actionMsg.type === 'success'
                ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300'
                : 'bg-red-900/30 border border-red-700 text-red-300'
            }`}>
              {actionMsg.text}
            </div>
          )}
        </>
      )}
    </div>
  );
}
