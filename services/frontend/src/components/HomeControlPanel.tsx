import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Home, Lightbulb, Thermometer, Blinds } from 'lucide-react'
import {
  fetchHome,
  controlLight,
  controlClimate,
  controlCover,
  type HomeData,
} from '../api'

function entityLabel(id: string): string {
  const parts = id.split('.')
  return parts[parts.length - 1].replace(/_/g, ' ')
}

export default function HomeControlPanel() {
  const queryClient = useQueryClient()

  const { data } = useQuery<HomeData>({
    queryKey: ['home'],
    queryFn: fetchHome,
    refetchInterval: 5000,
  })

  if (!data || data.status === 'no_data' || !data.bridge_connected) return null

  const lights = data.lights ? Object.entries(data.lights) : []
  const climates = data.climates ? Object.entries(data.climates) : []
  const covers = data.covers ? Object.entries(data.covers) : []

  if (lights.length === 0 && climates.length === 0 && covers.length === 0) return null

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <Home className="w-5 h-5 text-amber-600" />
        Smart Home
      </h2>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {lights.map(([id, light]) => (
          <LightCard key={id} entityId={id} light={light} queryClient={queryClient} />
        ))}
        {climates.map(([id, climate]) => (
          <ClimateCard key={id} entityId={id} climate={climate} queryClient={queryClient} />
        ))}
        {covers.map(([id, cover]) => (
          <CoverCard key={id} entityId={id} cover={cover} queryClient={queryClient} />
        ))}
      </div>
    </section>
  )
}

function LightCard({
  entityId,
  light,
  queryClient,
}: {
  entityId: string
  light: { on: boolean; brightness: number }
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const [brightness, setBrightness] = useState(light.brightness)

  const toggleMut = useMutation({
    mutationFn: () => controlLight(entityId, !light.on, brightness),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  const brightMut = useMutation({
    mutationFn: (val: number) => controlLight(entityId, true, val),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  return (
    <div className="bg-white rounded-xl elevation-1 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <Lightbulb className={`w-4 h-4 ${light.on ? 'text-yellow-500' : 'text-gray-400'}`} />
          {entityLabel(entityId)}
        </span>
        <button
          onClick={() => toggleMut.mutate()}
          disabled={toggleMut.isPending}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            light.on
              ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          {light.on ? 'ON' : 'OFF'}
        </button>
      </div>
      {light.on && (
        <div>
          <label className="text-xs text-gray-500">明るさ: {brightness}</label>
          <input
            type="range"
            min={0}
            max={255}
            value={brightness}
            onChange={(e) => setBrightness(Number(e.target.value))}
            onMouseUp={() => brightMut.mutate(brightness)}
            onTouchEnd={() => brightMut.mutate(brightness)}
            className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-yellow-500"
          />
        </div>
      )}
    </div>
  )
}

function ClimateCard({
  entityId,
  climate,
  queryClient,
}: {
  entityId: string
  climate: { mode: string; target_temp: number; current_temp: number }
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const MODES = ['off', 'cool', 'heat', 'dry', 'auto'] as const

  const modeMut = useMutation({
    mutationFn: (mode: string) => controlClimate(entityId, mode, climate.target_temp),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  const tempMut = useMutation({
    mutationFn: (temp: number) => controlClimate(entityId, climate.mode, temp),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  const isOn = climate.mode !== 'off'

  return (
    <div className="bg-white rounded-xl elevation-1 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <Thermometer className={`w-4 h-4 ${isOn ? 'text-blue-500' : 'text-gray-400'}`} />
          {entityLabel(entityId)}
        </span>
        <span className="text-xs text-gray-500">
          現在 {climate.current_temp}°C
        </span>
      </div>
      <div className="flex gap-1 mb-3">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => modeMut.mutate(m)}
            disabled={modeMut.isPending}
            className={`flex-1 text-xs py-1 rounded transition-colors ${
              climate.mode === m
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {m}
          </button>
        ))}
      </div>
      {isOn && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => tempMut.mutate(climate.target_temp - 1)}
            disabled={tempMut.isPending || climate.target_temp <= 16}
            className="w-8 h-8 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 text-sm font-bold"
          >
            -
          </button>
          <span className="text-lg font-bold text-blue-600 flex-1 text-center">
            {climate.target_temp}°C
          </span>
          <button
            onClick={() => tempMut.mutate(climate.target_temp + 1)}
            disabled={tempMut.isPending || climate.target_temp >= 30}
            className="w-8 h-8 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 text-sm font-bold"
          >
            +
          </button>
        </div>
      )}
    </div>
  )
}

function CoverCard({
  entityId,
  cover,
  queryClient,
}: {
  entityId: string
  cover: { position: number; is_open: boolean }
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const actionMut = useMutation({
    mutationFn: (action: string) => controlCover(entityId, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  const posMut = useMutation({
    mutationFn: (pos: number) => controlCover(entityId, undefined, pos),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
  })

  const [pos, setPos] = useState(cover.position)

  return (
    <div className="bg-white rounded-xl elevation-1 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <Blinds className={`w-4 h-4 ${cover.is_open ? 'text-cyan-500' : 'text-gray-400'}`} />
          {entityLabel(entityId)}
        </span>
        <span className="text-xs text-gray-500">{cover.position}%</span>
      </div>
      <div className="flex gap-2 mb-2">
        <button
          onClick={() => actionMut.mutate('open')}
          disabled={actionMut.isPending}
          className="flex-1 text-xs py-1.5 rounded bg-cyan-50 text-cyan-700 hover:bg-cyan-100"
        >
          開
        </button>
        <button
          onClick={() => actionMut.mutate('stop')}
          disabled={actionMut.isPending}
          className="flex-1 text-xs py-1.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
        >
          停止
        </button>
        <button
          onClick={() => actionMut.mutate('close')}
          disabled={actionMut.isPending}
          className="flex-1 text-xs py-1.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
        >
          閉
        </button>
      </div>
      <div>
        <input
          type="range"
          min={0}
          max={100}
          value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          onMouseUp={() => posMut.mutate(pos)}
          onTouchEnd={() => posMut.mutate(pos)}
          className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-cyan-500"
        />
      </div>
    </div>
  )
}
