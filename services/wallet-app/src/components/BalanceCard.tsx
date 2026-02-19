interface BalanceCardProps {
  balance: number; // milli-units
  loading?: boolean;
}

export default function BalanceCard({ balance, loading }: BalanceCardProps) {
  const display = (balance / 1000).toFixed(3);

  return (
    <div className="bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl p-6 text-white shadow-lg">
      <p className="text-sm opacity-80 mb-1">SOMS Balance</p>
      {loading ? (
        <div className="h-10 w-32 bg-white/20 rounded animate-pulse" />
      ) : (
        <p className="text-4xl font-bold tracking-tight">{display}</p>
      )}
      <p className="text-xs opacity-60 mt-2">1 SOMS = 1,000 milli-units</p>
    </div>
  );
}
