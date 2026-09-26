import AlertScene from './AlertScene'
import BriefingScene from './BriefingScene'
import FlowScene from './FlowScene'
import FunnelScene from './FunnelScene'
import HealthScene from './HealthScene'
import MapScene from './MapScene'
import PulseScene from './PulseScene'

export const scenes = [
  { id: 'briefing', title: 'Briefing', seconds: 22, Component: BriefingScene },
  { id: 'pulse', title: 'Pulse', seconds: 18, Component: PulseScene },
  { id: 'flow', title: 'Money & people', seconds: 16, Component: FlowScene },
  { id: 'map', title: 'Map', seconds: 18, Component: MapScene },
  { id: 'funnel', title: 'Onboarding', seconds: 16, Component: FunnelScene },
  { id: 'health', title: 'Health', seconds: 18, Component: HealthScene },
]

export const alertScene = { id: 'alert', title: 'Alert', seconds: 15, Component: AlertScene }

export const ATTENTION_BONUS_SECONDS = 8
