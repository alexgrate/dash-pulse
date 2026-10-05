import {
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Loader2,
  RotateCcw,
  Search,
  X,
  XCircle,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { kindLabel, list, tx } from '../lib/explore'
import { num } from '../lib/format'

const OUTCOME = {
  SUCCESS: { icon: CheckCircle2, tone: 'text-good', bg: 'bg-good/10', label: 'Successful' },
  FAILED: { icon: XCircle, tone: 'text-bad', bg: 'bg-bad/10', label: 'Failed' },
  REVERSED: { icon: RotateCcw, tone: 'text-warn', bg: 'bg-warn/10', label: 'Reversed' },
  PENDING: { icon: Clock3, tone: 'text-muted', bg: 'bg-white/5', label: 'Pending' },
}

const SIDES = {
  customer: "customer's side",
  account: 'account on hold',
  system: 'system side',
  unknown: 'no reason saved',
  other: 'other',
}

const STATUS_TABS = [
  ['', 'All'],
  ['FAILED', 'Failed'],
  ['SUCCESS', 'Successful'],
  ['REVERSED', 'Reversed'],
  ['PENDING', 'Pending'],
]

const money = new Intl.NumberFormat('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const naira = (v) => `₦${money.format(v ?? 0)}`
const time = (iso) => (iso ? iso.slice(11, 19) : '—')
const when = (iso) =>
  iso
    ? new Date(`${iso}+01:00`).toLocaleString('en-GB', {
        timeZone: 'Africa/Lagos',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—'
const todayIso = () => new Date(Date.now() + 3600e3).toISOString().slice(0, 10)

function query(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue
    p.set(k, Array.isArray(v) ? v.join(',') : v)
  }
  return p.toString()
}

function useApi(url) {
  const [res, setRes] = useState({ url: null, data: null, error: null })
  useEffect(() => {
    let alive = true
    api(url)
      .then((data) => alive && setRes({ url, data, error: null }))
      .catch((e) => alive && setRes({ url, data: null, error: e.status === 403 ? 'Not allowed.' : e.message }))
    return () => {
      alive = false
    }
  }, [url])
  return {
    loading: res.url !== url,
    data: res.url === url ? res.data : null,
    error: res.url === url ? res.error : null,
  }
}

export default function ExplorePanel({ stack, setStack }) {
  const top = stack[stack.length - 1]
  const close = () => setStack([])
  const push = (frame) => setStack((s) => [...s, frame])
  const back = () => setStack((s) => s.slice(0, -1))
  const replace = (frame) => setStack((s) => [...s.slice(0, -1), frame])

  useEffect(() => {
    if (!top) return
    const onKey = (e) => e.key === 'Escape' && setStack([])
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [top, setStack])

  return (
    <AnimatePresence>
      {top && (
        <>
          <motion.div
            key="shade"
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />
          <motion.aside
            key="panel"
            className="fixed inset-y-0 right-0 z-50 flex w-[min(820px,96vw)] flex-col border-l border-white/10 bg-[#080b14] text-sm shadow-2xl"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 260, damping: 32 }}
          >
            <div className="flex items-center gap-3 border-b border-white/10 px-6 py-4">
              {stack.length > 1 && (
                <button
                  type="button"
                  onClick={back}
                  className="rounded-lg p-1.5 text-muted hover:bg-white/5 hover:text-slate-100"
                >
                  <ArrowLeft className="size-5" />
                </button>
              )}
              <div className="flex-1 text-xs tracking-[0.2em] text-brand-soft uppercase">Explore</div>
              <button
                type="button"
                onClick={close}
                className="rounded-lg p-1.5 text-muted hover:bg-white/5 hover:text-slate-100"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              {top.type === 'list' && (
                <ListView filters={top.filters} onChange={(f) => replace(list(f))} onOpen={(id) => push(tx(id))} />
              )}
              {top.type === 'tx' && <TxView id={top.id} onOpen={(id) => push(tx(id))} />}
              {top.type === 'onboarding' && <OnboardingView frame={top} onChange={(f) => replace({ ...top, ...f })} />}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function Outcome({ outcome }) {
  const o = OUTCOME[outcome] ?? OUTCOME.PENDING
  const Icon = o.icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${o.tone} ${o.bg}`}>
      <Icon className="size-3.5" /> {o.label}
    </span>
  )
}

function Chip({ children, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 py-1 pr-1.5 pl-3 text-xs">
      {children}
      <button
        type="button"
        onClick={onRemove}
        className="rounded-full p-0.5 text-muted hover:bg-white/10 hover:text-slate-100"
      >
        <X className="size-3" />
      </button>
    </span>
  )
}

function Pager({ page, pages, onPage }) {
  if (pages <= 1) return null
  return (
    <div className="mt-4 flex items-center justify-end gap-3 text-xs text-muted">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className="rounded-lg border border-white/10 p-1.5 disabled:opacity-30"
      >
        <ChevronLeft className="size-4" />
      </button>
      Page {page} of {pages}
      <button
        type="button"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        className="rounded-lg border border-white/10 p-1.5 disabled:opacity-30"
      >
        <ChevronRight className="size-4" />
      </button>
    </div>
  )
}

function SearchBox({ value, onSearch, placeholder }) {
  const [text, setText] = useState(value ?? '')
  useEffect(() => {
    if (text === (value ?? '')) return
    const id = setTimeout(() => onSearch(text), 400)
    return () => clearTimeout(id)
  }, [text, value, onSearch])
  return (
    <label className="flex flex-1 items-center gap-2 rounded-xl border border-white/10 bg-black/30 px-3 py-2">
      <Search className="size-4 text-muted" />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-slate-100 outline-none placeholder:text-muted/60"
      />
    </label>
  )
}

function Loading({ error }) {
  return (
    <div className="grid place-items-center py-20 text-muted">
      {error ? <span className="text-bad">{error}</span> : <Loader2 className="size-6 animate-spin" />}
    </div>
  )
}

function ListView({ filters, onChange, onOpen }) {
  const f = { date: todayIso(), page: 1, ...filters }
  const { data, loading, error } = useApi(`/api/explore/transactions?${query(f)}`)
  const set = (patch) => onChange({ ...f, page: 1, ...patch })

  const title = [
    f.status ? OUTCOME[f.status]?.label : 'All',
    'transactions',
    f.hour != null
      ? `· ${String(f.hour).padStart(2, '0')}:00–${String((Number(f.hour) + 1) % 24).padStart(2, '0')}:00`
      : '',
  ].join(' ')

  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="date"
          value={f.date}
          max={todayIso()}
          onChange={(e) => set({ date: e.target.value })}
          className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-slate-100 [color-scheme:dark]"
        />
        <SearchBox
          value={f.search}
          onSearch={(search) => set({ search })}
          placeholder="Reference, account number or name"
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {STATUS_TABS.map(([value, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => set({ status: value })}
            className={`rounded-full px-3 py-1 text-xs ${
              (f.status ?? '') === value
                ? 'bg-brand text-white ring-1 ring-brand-soft/40'
                : 'bg-white/5 text-muted hover:text-slate-100'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {f.kinds?.length > 0 && <Chip onRemove={() => set({ kinds: [] })}>{f.kinds.map(kindLabel).join(' + ')}</Chip>}
        {f.bank && <Chip onRemove={() => set({ bank: '' })}>To {f.bank}</Chip>}
        {f.reason && <Chip onRemove={() => set({ reason: '' })}>{f.reason}</Chip>}
        {f.hour != null && f.hour !== '' && (
          <Chip onRemove={() => set({ hour: null })}>{String(f.hour).padStart(2, '0')}:00 hour</Chip>
        )}
      </div>

      {!data ? (
        <Loading error={error} />
      ) : (
        <div className={loading ? 'opacity-50' : ''}>
          <div className="mt-5 grid grid-cols-5 gap-2 text-center">
            {[
              ['Shown', data.total, 'text-slate-100'],
              ['Successful', data.summary.success, 'text-good'],
              ['Failed', data.summary.failed, 'text-bad'],
              ['Reversed', data.summary.reversed, 'text-warn'],
              ['Pending', data.summary.pending, 'text-muted'],
            ].map(([label, value, tone]) => (
              <div key={label} className="rounded-xl bg-white/[0.03] py-2">
                <div className={`tabular text-lg font-semibold ${tone}`}>{num(value)}</div>
                <div className="text-[11px] text-muted">{label}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-xs text-muted">
            Money moved by the successful ones: <span className="text-slate-200">{naira(data.summary.value)}</span>
          </div>

          {!f.reason && data.reasons.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-xs text-muted">Failure reasons · click to filter</div>
              <div className="flex flex-wrap gap-1.5">
                {data.reasons.map((r) => (
                  <button
                    key={r.reason}
                    type="button"
                    onClick={() => set({ reason: r.reason, status: 'FAILED' })}
                    className="rounded-full bg-bad/10 px-3 py-1 text-xs text-bad hover:bg-bad/20"
                  >
                    {r.reason} · {num(r.count)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5 divide-y divide-white/5 rounded-2xl border border-white/10">
            {data.items.length === 0 && <div className="p-6 text-center text-muted">No transactions match.</div>}
            {data.items.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onOpen(t.id)}
                className="grid w-full grid-cols-[70px_1fr_auto] items-center gap-4 px-4 py-3 text-left hover:bg-white/[0.04]"
              >
                <span className="tabular text-xs text-muted">{time(t.at)}</span>
                <span className="min-w-0">
                  <span className="block truncate text-slate-100">
                    {kindLabel(t.kind)}
                    {t.bank && <span className="text-muted"> → {t.bank}</span>}
                    {t.beneficiary && <span className="text-muted"> · {t.beneficiary}</span>}
                  </span>
                  <span className="block truncate text-xs text-muted">
                    {t.account} · {t.reference}
                  </span>
                  {t.reason && <span className="block truncate text-xs text-bad">{t.reason}</span>}
                </span>
                <span className="text-right">
                  <span className="tabular block font-semibold">{naira(t.amount)}</span>
                  <Outcome outcome={t.outcome} />
                </span>
              </button>
            ))}
          </div>
          <Pager page={data.page} pages={data.pages} onPage={(page) => onChange({ ...f, page })} />
        </div>
      )}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-xs tracking-[0.18em] text-muted uppercase">{title}</h3>
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">{children}</div>
    </section>
  )
}

function Field({ label, value, mono = false }) {
  const missing = value == null || String(value).trim() === '' || String(value).trim() === '-'
  return (
    <div className="flex justify-between gap-6 py-1">
      <span className="text-muted">{label}</span>
      {missing ? (
        <span className="text-right text-muted/60 italic">Not recorded</span>
      ) : (
        <span className={`text-right break-all text-slate-100 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
      )}
    </div>
  )
}

function TxView({ id, onOpen }) {
  const { data: t, error } = useApi(`/api/explore/transactions/${id}`)
  if (!t) return <Loading error={error} />
  const r = t.responses
  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-muted">{kindLabel(t.kind)}</div>
          <div className="tabular mt-1 text-3xl font-semibold">{naira(t.amount)}</div>
          <div className="mt-1 text-muted">{when(t.created)}</div>
        </div>
        <Outcome outcome={t.outcome} />
      </div>
      {t.reason && (
        <div className="mt-4 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-bad">
          Failed because: <span className="font-semibold">{t.reason}</span>
          <span className="ml-2 text-xs opacity-80">({SIDES[t.reason_kind] ?? t.reason_kind})</span>
        </div>
      )}
      {t.narration && <div className="mt-3 text-slate-300">“{t.narration}”</div>}

      <Section title="What happened">
        <ol className="space-y-2">
          {t.timeline.map((s, i) => (
            <li key={i} className="flex gap-3">
              <span className="tabular w-20 shrink-0 text-xs text-muted">{time(s.at)}</span>
              <span className="text-slate-100">{s.label}</span>
            </li>
          ))}
        </ol>
      </Section>

      <div className="grid gap-x-4 md:grid-cols-2">
        <Section title="From (customer)">
          <Field label="Name" value={t.customer?.name ?? t.sender.name} />
          <Field label="Account" value={t.sender.account} mono />
          <Field label="Phone" value={t.customer?.phone} />
          <Field label="Email" value={t.customer?.email} />
          <Field label="KYC tier" value={t.customer?.kyc_tier} />
          <Field label="Account opened" value={when(t.customer?.opened)} />
        </Section>
        <Section title="To (beneficiary)">
          <Field label="Name" value={t.beneficiary.name} />
          <Field label="Account" value={t.beneficiary.account} mono />
          <Field label="Bank" value={t.beneficiary.bank} />
          <Field label="Bank code" value={t.beneficiary.bank_code} mono />
        </Section>
      </div>

      <Section title="References">
        <Field label="Payment reference" value={t.references.payment} mono />
        <Field label="Core banking reference" value={t.references.core_banking} mono />
        <Field label="Provider reference" value={t.references.provider} mono />
        <Field label="NIP session ID" value={t.references.nip_session} mono />
      </Section>

      <Section title="System responses (raw)">
        <Field label="Provider" value={r.provider} />
        <Field label="Core banking accepted" value={r.core_banking_ok} />
        <Field label="Core banking message" value={r.core_banking_message} />
        <Field label="Provider code" value={r.provider_code} mono />
        <Field label="Provider message" value={r.provider_message} />
        <Field label="Payment status" value={r.payment_status} />
        <Field label="Payment response code" value={r.payment_code} mono />
        <Field label="Status re-checks" value={r.requery_count} />
        <Field label="Reversal" value={r.reversal} />
        <Field label="Reversal message" value={r.reversal_message} />
      </Section>

      <Section title={`This customer's transactions that day (${t.same_day.length})`}>
        <div className="divide-y divide-white/5">
          {t.same_day.map((h) => (
            <button
              key={h.id}
              type="button"
              onClick={() => h.id !== t.id && onOpen(h.id)}
              className={`grid w-full grid-cols-[70px_1fr_auto] items-center gap-3 py-2 text-left ${
                h.id === t.id ? 'opacity-50' : 'hover:bg-white/[0.04]'
              }`}
            >
              <span className="tabular text-xs text-muted">{time(h.at)}</span>
              <span className="truncate">
                {kindLabel(h.kind)}
                {h.reason && <span className="text-xs text-bad"> · {h.reason}</span>}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular">{naira(h.amount)}</span>
                <Outcome outcome={h.outcome} />
              </span>
            </button>
          ))}
        </div>
      </Section>
    </div>
  )
}

function OnboardingView({ frame, onChange }) {
  const f = { page: 1, scope: '30d', ...frame }
  const { data, loading, error } = useApi(
    `/api/explore/onboarding?${query({ phase: f.phase, scope: f.scope, search: f.search, page: f.page })}`,
  )
  return (
    <div>
      <div className="text-xs tracking-[0.18em] text-muted uppercase">Stuck in onboarding</div>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight">{data?.label ?? '…'}</h2>
      <div className="mt-1 font-mono text-xs text-muted">{f.phase}</div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {[
          ['today', 'Started today'],
          ['30d', 'Last 30 days'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => onChange({ scope: value, page: 1 })}
            className={`rounded-full px-3 py-1 text-xs ${
              f.scope === value
                ? 'bg-brand text-white ring-1 ring-brand-soft/40'
                : 'bg-white/5 text-muted hover:text-slate-100'
            }`}
          >
            {label}
          </button>
        ))}
        <SearchBox
          value={f.search}
          onSearch={(search) => onChange({ search, page: 1 })}
          placeholder="Name, email or phone"
        />
      </div>
      {!data ? (
        <Loading error={error} />
      ) : (
        <div className={loading ? 'opacity-50' : ''}>
          <div className="mt-4 text-muted">
            <span className="text-lg font-semibold text-slate-100">{num(data.total)}</span> people are at this step.
          </div>
          <div className="mt-4 divide-y divide-white/5 rounded-2xl border border-white/10">
            {data.items.length === 0 && <div className="p-6 text-center text-muted">Nobody here.</div>}
            {data.items.map((p) => (
              <div key={p.id} className="grid grid-cols-[1fr_auto] gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-slate-100">{p.name ?? 'No name yet'}</div>
                  <div className="truncate text-xs text-muted">
                    {p.phone ?? '—'} · {p.email ?? '—'}
                  </div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div>Started {when(p.started)}</div>
                  <div>
                    Waiting <span className="text-slate-200">{p.waiting_hours} h</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Pager page={data.page} pages={data.pages} onPage={(page) => onChange({ page })} />
        </div>
      )}
    </div>
  )
}
