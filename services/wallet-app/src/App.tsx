import { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useUserId } from './hooks/useUserId';
import BottomNav from './components/BottomNav';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Send from './pages/Send';
import History from './pages/History';
import Invest from './pages/Invest';
import DeviceDetail from './pages/DeviceDetail';

function SetupScreen({ onSubmit }: { onSubmit: (id: number) => void }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(input, 10);
    if (id > 0) onSubmit(id);
  };

  return (
    <div className="flex items-center justify-center min-h-screen p-6">
      <form onSubmit={handleSubmit} className="w-full max-w-xs space-y-6 text-center">
        <div>
          <h1 className="text-3xl font-bold text-amber-400">SOMS Wallet</h1>
          <p className="text-gray-400 mt-2 text-sm">Enter your User ID to get started</p>
        </div>
        <input
          type="number"
          inputMode="numeric"
          min="1"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="User ID"
          className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white text-center text-xl placeholder-gray-600 focus:outline-none focus:border-amber-500"
          autoFocus
        />
        <button
          type="submit"
          disabled={!input || parseInt(input) <= 0}
          className="w-full py-3 bg-amber-500 text-black font-semibold rounded-xl disabled:opacity-40"
        >
          Start
        </button>
      </form>
    </div>
  );
}

export default function App() {
  const [userId, setUserId] = useUserId();

  if (!userId) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <SetupScreen onSubmit={setUserId} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Routes>
        <Route path="/" element={<Home userId={userId} />} />
        <Route path="/scan" element={<Scan userId={userId} />} />
        <Route path="/send" element={<Send userId={userId} />} />
        <Route path="/history" element={<History userId={userId} />} />
        <Route path="/invest" element={<Invest userId={userId} />} />
        <Route path="/invest/device/:deviceId" element={<DeviceDetail userId={userId} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <BottomNav />
    </div>
  );
}
