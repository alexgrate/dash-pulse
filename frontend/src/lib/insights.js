import {
  Activity,
  Check,
  CircleHelp,
  Filter,
  Gift,
  Lock,
  MapPin,
  RotateCcw,
  ScanFace,
  Server,
  ShieldCheck,
  Siren,
  Target,
  TrendingDown,
  TrendingUp,
  User,
  UserPlus,
  XCircle,
  Zap,
} from 'lucide-react'
import { createElement } from 'react'

export const ICONS = {
  activity: Activity,
  check: Check,
  filter: Filter,
  gift: Gift,
  'help-circle': CircleHelp,
  lock: Lock,
  'map-pin': MapPin,
  'rotate-ccw': RotateCcw,
  'scan-face': ScanFace,
  server: Server,
  'shield-check': ShieldCheck,
  siren: Siren,
  target: Target,
  'trending-down': TrendingDown,
  'trending-up': TrendingUp,
  user: User,
  'user-plus': UserPlus,
  'x-circle': XCircle,
  zap: Zap,
}

export const TONES = {
  bad: { text: 'text-bad', bg: 'bg-bad/12', border: 'border-bad/40', bar: 'bg-bad' },
  warn: { text: 'text-warn', bg: 'bg-warn/12', border: 'border-warn/40', bar: 'bg-warn' },
  good: { text: 'text-good', bg: 'bg-good/12', border: 'border-good/30', bar: 'bg-good' },
  info: { text: 'text-brand-soft', bg: 'bg-brand/40', border: 'border-brand-soft/30', bar: 'bg-brand-soft' },
}

export const iconFor = (insight) => ICONS[insight.icon] ?? Activity

export const InsightIcon = ({ insight, className }) => createElement(iconFor(insight), { className })

export const itemsOf = (data) => data?.intelligence?.items ?? []

export const topFor = (data, sceneId) => itemsOf(data).find((i) => i.scene === sceneId)

export const needsAttention = (data, sceneId) =>
  itemsOf(data).some((i) => i.scene === sceneId && (i.severity === 'warn' || i.severity === 'bad'))
