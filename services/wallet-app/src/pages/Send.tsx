import { useState, useEffect } from 'react';
import { sendTransfer, previewFee, type TransferFeeInfo } from '../api/wallet';

interface SendProps {
  userId: number;
}

export default function Send({ userId }: SendProps) {
  const [toUserId, setToUserId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [fee, setFee] = useState<TransferFeeInfo | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  // Real-time fee preview
  useEffect(() => {
    const millis = Math.floor(parseFloat(amount || '0') * 1000);
    if (millis <= 0) {
      setFee(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const f = await previewFee(millis);
        setFee(f);
      } catch {
        setFee(null);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [amount]);

  const handleSend = async () => {
    const millis = Math.floor(parseFloat(amount) * 1000);
    const to = parseInt(toUserId, 10);
    if (isNaN(to) || millis <= 0) return;

    setSending(true);
    setResult(null);
    try {
      await sendTransfer(userId, to, millis, description || undefined);
      setResult({ success: true, message: `Sent ${(millis / 1000).toFixed(3)} SOMS to user #${to}` });
      setToUserId('');
      setAmount('');
      setDescription('');
      setFee(null);
    } catch (e) {
      setResult({ success: false, message: e instanceof Error ? e.message : 'Transfer failed' });
    } finally {
      setSending(false);
    }
  };

  const millis = Math.floor(parseFloat(amount || '0') * 1000);
  const canSend = parseInt(toUserId) > 0 && millis > 0 && !sending && !fee?.below_minimum;

  return (
    <div className="p-4 pb-24 space-y-6">
      <h1 className="text-xl font-bold">Send SOMS</h1>

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Recipient User ID</label>
          <input
            type="number"
            inputMode="numeric"
            value={toUserId}
            onChange={e => setToUserId(e.target.value)}
            placeholder="e.g. 2"
            className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-amber-500"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Amount (SOMS)</label>
          <input
            type="number"
            inputMode="decimal"
            step="0.001"
            min="0"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            placeholder="0.000"
            className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white text-2xl font-bold placeholder-gray-600 focus:outline-none focus:border-amber-500"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Note (optional)</label>
          <input
            type="text"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="What's this for?"
            maxLength={100}
            className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {fee && (
        <div className="bg-gray-900 rounded-xl p-4 space-y-2 text-sm">
          <div className="flex justify-between text-gray-400">
            <span>Fee ({(fee.fee_rate * 100).toFixed(0)}%)</span>
            <span className="text-red-400">-{(fee.fee_amount / 1000).toFixed(3)}</span>
          </div>
          <div className="flex justify-between text-gray-200 font-semibold">
            <span>Recipient gets</span>
            <span className="text-emerald-400">{(fee.net_amount / 1000).toFixed(3)}</span>
          </div>
          {fee.below_minimum && (
            <p className="text-red-400 text-xs">
              Below minimum transfer ({(fee.min_transfer / 1000).toFixed(3)} SOMS)
            </p>
          )}
        </div>
      )}

      {result && (
        <div className={`rounded-lg p-3 text-sm ${
          result.success ? 'bg-emerald-900/30 border border-emerald-700 text-emerald-300' :
          'bg-red-900/30 border border-red-700 text-red-300'
        }`}>
          {result.message}
        </div>
      )}

      <button
        onClick={handleSend}
        disabled={!canSend}
        className="w-full py-3 bg-amber-500 text-black font-semibold rounded-xl disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {sending ? 'Sending...' : 'Send'}
      </button>
    </div>
  );
}
