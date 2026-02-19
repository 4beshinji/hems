const COLORS: Record<string, string> = {
  llm_node: 'bg-purple-900/60 text-purple-300',
  sensor_node: 'bg-cyan-900/60 text-cyan-300',
  hub: 'bg-yellow-900/60 text-yellow-300',
  relay_node: 'bg-emerald-900/60 text-emerald-300',
  remote_node: 'bg-gray-800 text-gray-300',
};

export default function DeviceTypeBadge({ type }: { type: string }) {
  const color = COLORS[type] || COLORS.remote_node;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {type.replace('_', ' ')}
    </span>
  );
}
