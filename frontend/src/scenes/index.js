import AlertScene from './AlertScene'
import BanksScene from './BanksScene'
import FlowScene from './FlowScene'
import FunnelScene from './FunnelScene'
import HealthScene from './HealthScene'
import LiveScene from './LiveScene'
import MapScene from './MapScene'
import PulseScene from './PulseScene'
import TrendsScene from './TrendsScene'

export const scenes = [
  { id: 'live', title: 'Live', seconds: 24, Component: LiveScene },
  { id: 'pulse', title: 'Pulse', seconds: 18, Component: PulseScene },
  { id: 'trends', title: 'Trends', seconds: 18, Component: TrendsScene },
  { id: 'flow', title: 'Money & people', seconds: 16, Component: FlowScene },
  { id: 'banks', title: 'Banks & devices', seconds: 18, Component: BanksScene },
  { id: 'map', title: 'Map', seconds: 18, Component: MapScene },
  { id: 'funnel', title: 'Onboarding', seconds: 16, Component: FunnelScene },
  { id: 'health', title: 'Health', seconds: 18, Component: HealthScene },
]

export const alertScene = { id: 'alert', title: 'Alert', seconds: 15, Component: AlertScene }

export const ATTENTION_BONUS_SECONDS = 8

export const MAP_MIN_CITIES = 3

export const isShowable = (scene, data) => scene.id !== 'map' || (data?.geography?.city_count ?? 0) >= MAP_MIN_CITIES
