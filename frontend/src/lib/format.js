const whole = new Intl.NumberFormat('en-NG')
const compact = new Intl.NumberFormat('en-NG', { notation: 'compact', maximumFractionDigits: 2 })

export const num = (n) => whole.format(Math.round(n ?? 0))
export const naira = (n) => `₦${compact.format(n ?? 0)}`
export const pct = (ratio, digits = 1) => (ratio == null ? '—' : `${(ratio * 100).toFixed(digits)}%`)

export const change = (today, yesterday) => (yesterday ? (today - yesterday) / yesterday : null)
