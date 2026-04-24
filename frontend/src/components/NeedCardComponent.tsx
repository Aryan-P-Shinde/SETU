import type { NeedCard } from '../lib/api'

const NEED_COLORS: Record<string, string> = {
  medical:   '#c2442a',
  food:      '#9a6200',
  water:     '#185fa5',
  shelter:   '#534ab7',
  rescue:    '#c2442a',
  logistics: '#3a3a36',
  other:     '#3a3a36',
}

const STATUS_COLORS: Record<string, string> = {
  open:      '#c2442a',
  matched:   '#9a6200',
  fulfilled: '#0f6e56',
  stale:     '#a8a8a0',
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ${m % 60}m`
  return `${Math.floor(h / 24)}d`
}

interface Props {
  card: NeedCard
  selected?: boolean
  onClick?: () => void
  brief?: string
  onGenerateBrief?: () => void
  briefLoading?: boolean
}

export function NeedCardComponent({ card, selected, onClick, brief, onGenerateBrief, briefLoading }: Props) {
  const urgencyColor = card.urgency_score_eff >= 9 ? '#c2442a'
    : card.urgency_score_eff >= 7 ? '#9a6200'
    : card.urgency_score_eff >= 5 ? '#3a3a36'
    : '#a8a8a0'

  const urgencyPct = (card.urgency_score_eff / 10) * 100

  return (
    <div
      onClick={onClick}
      style={{
        borderTop: `3px solid ${NEED_COLORS[card.need_type] || '#3a3a36'}`,
        borderLeft: '1px solid var(--rule)',
        borderRight: '1px solid var(--rule)',
        borderBottom: '1px solid var(--rule)',
        padding: '12px 14px',
        cursor: onClick ? 'pointer' : 'default',
        background: selected ? 'var(--paper2)' : 'var(--paper)',
        transition: 'background 0.1s',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: NEED_COLORS[card.need_type], letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          {card.need_type}
        </span>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink4)' }}>
          {card.id.slice(0, 8)} · {timeAgo(card.created_at)} ago
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 9, padding: '2px 7px', border: `1px solid ${STATUS_COLORS[card.status]}`, color: STATUS_COLORS[card.status], display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: STATUS_COLORS[card.status], display: 'inline-block' }} />
          {card.status.toUpperCase()}
          {card.needs_review && <span style={{ marginLeft: 4, color: '#c2442a' }}>· REVIEW</span>}
        </span>
      </div>

      {/* Urgency bar */}
      <div style={{ height: 3, background: 'var(--paper3)', marginBottom: 4 }}>
        <div style={{ height: '100%', width: `${urgencyPct}%`, background: urgencyColor, transition: 'width 0.4s' }} />
      </div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', marginBottom: 8 }}>
        urgency {card.urgency_score_eff.toFixed(1)} / 10
        {card.report_count > 1 && <span style={{ marginLeft: 8 }}>· {card.report_count} reports merged</span>}
      </div>

      {/* Description */}
      <div style={{ fontFamily: 'var(--serif)', fontSize: 14, fontWeight: 300, lineHeight: 1.45, marginBottom: 10, color: 'var(--ink)' }}>
        {card.description_clean}
      </div>

      {/* Fields grid */}
      <div style={{ display: 'grid', gridTemplate: 'auto / 1fr 1fr', borderTop: '1px solid var(--rule)' }}>
        {[
          ['affected', card.affected_count ? `~${card.affected_count} people` : '—'],
          ['location', card.location_text_raw || '—'],
          ['skills', card.skills_needed.length ? card.skills_needed.join(', ') : '—'],
          ['contact', card.contact_name ? `${card.contact_name} · ${card.contact_detail}` : '—'],
        ].map(([k, v], i) => (
          <div key={k} style={{
            padding: '5px 0',
            borderBottom: '0.5px solid var(--rule)',
            paddingRight: i % 2 === 0 ? 10 : 0,
            paddingLeft: i % 2 === 1 ? 10 : 0,
            borderRight: i % 2 === 0 ? '0.5px solid var(--rule)' : 'none',
          }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>{k}</div>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink)', wordBreak: 'break-word' }}>{v}</div>
          </div>
        ))}
      </div>

      {/* Brief section */}
      {(brief || onGenerateBrief) && (
        <div style={{ marginTop: 12, borderLeft: '3px solid var(--teal)', paddingLeft: 10 }}>
          {brief ? (
            <>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>volunteer brief</div>
              <div style={{ fontSize: 13, color: 'var(--ink2)', lineHeight: 1.7, background: 'var(--paper2)', padding: '8px 10px' }}>{brief}</div>
              <button
                onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(brief) }}
                style={{ marginTop: 6, fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.06em', padding: '4px 10px', border: '1px solid var(--rule-s)', background: 'transparent', cursor: 'pointer', color: 'var(--teal)', textTransform: 'uppercase' }}
              >
                copy for whatsapp
              </button>
            </>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); onGenerateBrief?.() }}
              disabled={briefLoading}
              style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.06em', padding: '6px 14px', border: '1px solid var(--teal)', background: 'transparent', cursor: 'pointer', color: 'var(--teal)', textTransform: 'uppercase', opacity: briefLoading ? 0.5 : 1 }}
            >
              {briefLoading ? 'generating…' : 'generate brief'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}