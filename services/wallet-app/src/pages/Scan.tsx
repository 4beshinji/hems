import { useRef, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { claimTaskReward } from '../api/wallet';

interface ScanProps {
  userId: number;
}

interface QRPayload {
  task_id: number;
  amount: number;
}

function parseQR(text: string): QRPayload | null {
  try {
    const url = new URL(text);
    if (url.protocol !== 'soms:' || url.hostname !== 'reward') return null;
    const taskId = parseInt(url.searchParams.get('task_id') || '', 10);
    const amount = parseInt(url.searchParams.get('amount') || '', 10);
    if (isNaN(taskId) || isNaN(amount)) return null;
    return { task_id: taskId, amount };
  } catch {
    return null;
  }
}

export default function Scan({ userId }: ScanProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<'idle' | 'scanning' | 'claiming' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [claimedAmount, setClaimedAmount] = useState(0);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const navigate = useNavigate();

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStatus('scanning');
      setCameraError(null);
    } catch {
      setCameraError('Camera access denied. Please allow camera permissions.');
    }
  }, []);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    startCamera();
    return stopCamera;
  }, [startCamera, stopCamera]);

  // BarcodeDetector-based scanning
  useEffect(() => {
    if (status !== 'scanning') return;

    const detector = 'BarcodeDetector' in window
      ? new (window as unknown as { BarcodeDetector: new (opts: { formats: string[] }) => { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }).BarcodeDetector({ formats: ['qr_code'] })
      : null;

    if (!detector) {
      setMessage('QR scanning requires BarcodeDetector API (Chrome/Edge).');
      return;
    }

    let running = true;
    async function scan() {
      while (running && videoRef.current) {
        try {
          const barcodes = await detector!.detect(videoRef.current);
          for (const barcode of barcodes) {
            const payload = parseQR(barcode.rawValue);
            if (payload) {
              running = false;
              stopCamera();
              setStatus('claiming');
              setClaimedAmount(payload.amount);
              setMessage(`Claiming ${payload.amount} SOMS...`);
              try {
                await claimTaskReward(userId, payload.task_id, payload.amount);
                setStatus('success');
                setMessage(`+${payload.amount} SOMS`);
              } catch (e) {
                setStatus('error');
                setMessage(e instanceof Error ? e.message : 'Claim failed');
              }
              return;
            }
          }
        } catch { /* ignore detect errors */ }
        await new Promise(r => setTimeout(r, 300));
      }
    }

    scan();
    return () => { running = false; };
  }, [status, userId, stopCamera]);

  // Auto-navigate to home after success
  useEffect(() => {
    if (status !== 'success') return;
    const timer = setTimeout(() => navigate('/'), 3000);
    return () => clearTimeout(timer);
  }, [status, navigate]);

  const handleReset = () => {
    setStatus('idle');
    setMessage('');
    setClaimedAmount(0);
    startCamera();
  };

  return (
    <div className="p-4 pb-24 space-y-4">
      <h1 className="text-xl font-bold">QR Scan</h1>
      <p className="text-sm text-gray-400">Scan a task QR code to claim rewards.</p>

      {/* Camera viewfinder (hidden on success) */}
      {status !== 'success' && (
        <div className="relative rounded-2xl overflow-hidden bg-black aspect-square">
          <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
          <canvas ref={canvasRef} className="hidden" />
          {status === 'scanning' && (
            <div className="absolute inset-0 border-2 border-amber-400/50 rounded-2xl pointer-events-none">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 border-2 border-amber-400 rounded-lg" />
            </div>
          )}
          {status === 'claiming' && (
            <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
              <div className="w-12 h-12 border-4 border-amber-400 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      )}

      {/* Success animation */}
      {status === 'success' && (
        <div className="flex flex-col items-center justify-center py-12 space-y-6 animate-fade-in">
          {/* Checkmark circle */}
          <div className="relative w-28 h-28">
            <svg viewBox="0 0 100 100" className="w-full h-full">
              <circle
                cx="50" cy="50" r="45"
                fill="none" stroke="#22c55e" strokeWidth="4"
                className="animate-draw-circle"
              />
              <path
                d="M30 52 L44 66 L72 38"
                fill="none" stroke="#22c55e" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"
                className="animate-draw-check"
              />
            </svg>
          </div>

          {/* Amount display */}
          <div className="text-center">
            <p className="text-5xl font-bold text-amber-400">
              +{claimedAmount}
            </p>
            <p className="text-lg text-gray-400 mt-1">SOMS</p>
          </div>

          <p className="text-sm text-gray-500">3 seconds to home...</p>
        </div>
      )}

      {cameraError && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-300">
          {cameraError}
        </div>
      )}

      {message && status === 'error' && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-300">
          {message}
        </div>
      )}

      {(status === 'success' || status === 'error') && (
        <button
          onClick={status === 'success' ? () => navigate('/') : handleReset}
          className="w-full py-3 bg-amber-500 text-black font-semibold rounded-xl"
        >
          {status === 'success' ? 'Go Home' : 'Scan Again'}
        </button>
      )}

      <style>{`
        @keyframes fade-in {
          from { opacity: 0; transform: scale(0.9); }
          to { opacity: 1; transform: scale(1); }
        }
        .animate-fade-in {
          animation: fade-in 0.4s ease-out;
        }
        @keyframes draw-circle {
          from { stroke-dasharray: 283; stroke-dashoffset: 283; }
          to { stroke-dasharray: 283; stroke-dashoffset: 0; }
        }
        .animate-draw-circle {
          animation: draw-circle 0.6s ease-out forwards;
        }
        @keyframes draw-check {
          from { stroke-dasharray: 80; stroke-dashoffset: 80; }
          to { stroke-dasharray: 80; stroke-dashoffset: 0; }
        }
        .animate-draw-check {
          animation: draw-check 0.4s ease-out 0.4s forwards;
          stroke-dasharray: 80;
          stroke-dashoffset: 80;
        }
      `}</style>
    </div>
  );
}
