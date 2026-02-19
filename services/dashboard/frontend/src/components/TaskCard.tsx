import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MapPin, Coins, Zap, Circle, AlertCircle, AlertTriangle, QrCode, X } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import Card from './ui/Card';
import Badge from './ui/Badge';
import Button from './ui/Button';

export interface Task {
    id: number;
    title: string;
    description: string;
    location?: string;
    bounty_gold: number;
    bounty_xp: number;
    urgency: number;
    is_completed: boolean;
    announcement_audio_url?: string;
    announcement_text?: string;
    completion_audio_url?: string;
    completion_text?: string;
    created_at: string;
    completed_at?: string;
    task_type?: string[];
    assigned_to?: number;
    report_status?: string;
    completion_note?: string;
}

export interface TaskReport {
    status: string;
    note: string;
}

interface TaskCardProps {
    task: Task;
    isAccepted?: boolean;
    onAccept?: (taskId: number) => void;
    onComplete?: (taskId: number, report?: TaskReport) => void;
    onIgnore?: (taskId: number) => void;
}

const getUrgencyBadge = (urgency: number) => {
    if (urgency >= 3) {
        return {
            variant: 'error' as const,
            icon: <AlertTriangle size={12} />,
            label: '高優先度',
        };
    }
    if (urgency >= 2) {
        return {
            variant: 'warning' as const,
            icon: <AlertCircle size={12} />,
            label: '中優先度',
        };
    }
    return {
        variant: 'success' as const,
        icon: <Circle size={12} />,
        label: '低優先度',
    };
};

const REPORT_STATUSES = [
    { value: 'no_issue', label: '問題なし' },
    { value: 'resolved', label: '対応済み' },
    { value: 'needs_followup', label: '要追加対応' },
    { value: 'cannot_resolve', label: '対応不可' },
] as const;

export default function TaskCard({ task, isAccepted, onAccept, onComplete, onIgnore }: TaskCardProps) {
    const urgencyBadge = getUrgencyBadge(task.urgency ?? 2);
    const [showReport, setShowReport] = useState(false);
    const [reportStatus, setReportStatus] = useState('');
    const [reportNote, setReportNote] = useState('');
    const [showQR, setShowQR] = useState(false);

    return (
        <Card elevation={2} padding="medium" hoverable>
            <div className="space-y-4">
                {/* Header with title and urgency */}
                <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                        <h3 className="text-xl font-semibold text-[var(--gray-900)] mb-1">
                            {task.title}
                        </h3>
                        {task.location && (
                            <div className="flex items-center gap-1 text-sm text-[var(--gray-600)]">
                                <MapPin size={14} />
                                <span>{task.location}</span>
                            </div>
                        )}
                    </div>
                    <Badge variant={urgencyBadge.variant} icon={urgencyBadge.icon}>
                        {urgencyBadge.label}
                    </Badge>
                </div>

                {/* Description */}
                {task.description && (
                    <p className="text-[var(--gray-700)] leading-relaxed">
                        {task.description}
                    </p>
                )}

                <div className="flex items-center gap-3 flex-wrap">
                    <Badge variant="gold" icon={<Coins size={14} />}>
                        {task.bounty_gold} SOMS
                    </Badge>
                    <Badge variant="xp" icon={<Zap size={14} />}>
                        {task.bounty_xp} システム活動値
                    </Badge>
                </div>

                {/* Actions */}
                {!task.is_completed && !isAccepted && (
                    <motion.div
                        className="flex gap-2 pt-2"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                    >
                        <Button
                            variant="primary"
                            size="medium"
                            onClick={() => onAccept?.(task.id)}
                            className="flex-1"
                        >
                            受諾
                        </Button>
                        <Button
                            variant="ghost"
                            size="medium"
                            onClick={() => onIgnore?.(task.id)}
                        >
                            無視
                        </Button>
                    </motion.div>
                )}

                {!task.is_completed && isAccepted && !showReport && (
                    <motion.div
                        className="flex gap-2 pt-2"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                    >
                        <Badge variant="info" size="medium">
                            対応中
                        </Badge>
                        <Button
                            variant="secondary"
                            size="medium"
                            onClick={() => setShowReport(true)}
                            className="flex-1"
                        >
                            完了
                        </Button>
                    </motion.div>
                )}

                {!task.is_completed && isAccepted && showReport && (
                    <motion.div
                        className="pt-2 space-y-3"
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        transition={{ duration: 0.2 }}
                    >
                        <p className="text-sm font-medium text-[var(--gray-700)]">結果を報告</p>
                        <div className="grid grid-cols-2 gap-2">
                            {REPORT_STATUSES.map(s => (
                                <button
                                    key={s.value}
                                    onClick={() => setReportStatus(s.value)}
                                    className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                                        reportStatus === s.value
                                            ? 'border-[var(--primary-500)] bg-[var(--primary-50)] text-[var(--primary-700)] font-medium'
                                            : 'border-[var(--gray-300)] bg-white text-[var(--gray-600)] hover:border-[var(--gray-400)]'
                                    }`}
                                >
                                    {s.label}
                                </button>
                            ))}
                        </div>
                        <textarea
                            value={reportNote}
                            onChange={e => setReportNote(e.target.value)}
                            placeholder="詳細を入力..."
                            rows={2}
                            maxLength={500}
                            className="w-full px-3 py-2 text-sm border border-[var(--gray-300)] rounded-lg resize-none focus:outline-none focus:border-[var(--primary-500)]"
                        />
                        <div className="flex gap-2">
                            <Button
                                variant="primary"
                                size="medium"
                                onClick={() => onComplete?.(task.id, { status: reportStatus, note: reportNote })}
                                className="flex-1"
                                disabled={!reportStatus}
                            >
                                送信
                            </Button>
                            <Button
                                variant="ghost"
                                size="medium"
                                onClick={() => {
                                    setShowReport(false);
                                    setReportStatus('');
                                    setReportNote('');
                                }}
                            >
                                戻る
                            </Button>
                        </div>
                    </motion.div>
                )}

                {task.is_completed && (
                    <div className="pt-2 flex items-center gap-2">
                        <Badge variant="success" size="medium">
                            ✓ 完了済み
                        </Badge>
                        {task.bounty_gold > 0 && (
                            <Button
                                variant="secondary"
                                size="small"
                                onClick={() => setShowQR(true)}
                                className="flex items-center gap-1"
                            >
                                <QrCode size={14} />
                                QR で報酬を受け取る
                            </Button>
                        )}
                    </div>
                )}
            </div>

            {/* QR Reward Modal */}
            <AnimatePresence>
                {showQR && (
                    <motion.div
                        className="fixed inset-0 bg-black/80 flex items-center justify-center z-50"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setShowQR(false)}
                    >
                        <motion.div
                            className="relative bg-white p-8 rounded-2xl text-center max-w-sm mx-4"
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.8, opacity: 0 }}
                            onClick={e => e.stopPropagation()}
                        >
                            <button
                                onClick={() => setShowQR(false)}
                                className="absolute top-3 right-3 text-[var(--gray-400)] hover:text-[var(--gray-600)]"
                            >
                                <X size={20} />
                            </button>
                            <QRCodeSVG
                                value={`soms://reward?task_id=${task.id}&amount=${task.bounty_gold}`}
                                size={280}
                                level="M"
                            />
                            <p className="mt-4 text-lg font-bold text-[var(--gray-900)]">
                                スマホで読み取ってください
                            </p>
                            <div className="mt-2 flex items-center justify-center gap-1 text-[var(--gold-dark)]">
                                <Coins size={18} />
                                <span className="text-xl font-bold">{task.bounty_gold} SOMS</span>
                            </div>
                            <p className="text-sm text-[var(--gray-500)] mt-2">
                                {task.title}
                            </p>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </Card>
    );
}
