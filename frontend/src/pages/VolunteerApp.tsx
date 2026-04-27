/**
 * VolunteerApp.tsx — SETU
 * Rethemed to match LandingPage: dark nav, Fraunces headings, gold accents, warm paper.
 */

import { useState } from 'react'
import type {
  DispatchRecord,
  Volunteer,
  NeedCard,
} from '../lib/api'
import {
  acceptDispatch,
  completeDispatch,
  cancelDispatch,
} from '../lib/api'
import {
  SEED_DISPATCHES,
  SEED_VOLUNTEER,
  SEED_NEEDCARDS_BY_ID,
  SEED_HISTORY,
} from '../lib/volunteerSeedData'
import { logout } from '../lib/firebase'

type Tab = 'mission' | 'history'

const NEED_COLORS: Record<string, string> = {
  medical:   '#e03d25',
  rescue:    '#e03d25',
  food:      '#b97200',
  water:     '#1a6bbf',
  shelter:   '#5b4fd4',
  logistics: '#3a3a36',
  other:     '#3a3a36',
}

const URGENCY_LABEL: [number, string, string][] = [
  [9,  'CRITICAL',  '#e03d25'],
  [7,  'HIGH',      '#b97200'],
  [5,  'MODERATE',  '#3a3a36'],
  [3,  'LOW',       '#a8a8a0'],
  [0,  'ROUTINE',   '#a8a8a0'],
]

function urgencyMeta(score: number): { label: string; color: string } {
  for (const [threshold, label, color] of URGENCY_LABEL) {
    if (score >= threshold) return { label, color }
  }
  return { label: 'ROUTINE', color: '#a8a8a0' }
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 2) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function durHours(start: string, end?: string | null): number {
  const ms = new Date(end ?? Date.now()).getTime() - new Date(start).getTime()
  return Math.max(0, Math.round((ms / 3600000) * 10) / 10)
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function UrgencyBadge({ score }: { score: number }) {
  const { label, color } = urgencyMeta(score)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontFamily: "'DM Mono', monospace", fontSize: 9, letterSpacing: '0.08em',
      padding: '4px 10px',
      border: `1px solid ${color}`,
      color, borderRadius: 2,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {label}
    </span>
  )
}

function Rule() {
  return <div style={{ height: '0.5px', background: 'rgba(15,15,13,0.1)', margin: '16px 0' }} />
}

function ActionBtn({
  label, color = '#0f0f0d', fill = false, disabled = false, onClick,
}: {
  label: string; color?: string; fill?: boolean; disabled?: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        width: '100%', padding: '13px 0',
        fontFamily: "'DM Mono', monospace", fontSize: 10,
        letterSpacing: '0.08em', textTransform: 'uppercase',
        border: `1px solid ${disabled ? 'rgba(15,15,13,0.15)' : color}`,
        background: fill && !disabled ? color : 'transparent',
        color: fill && !disabled ? '#f5f2eb' : disabled ? '#c0bdb6' : color,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s',
        opacity: disabled ? 0.5 : 1,
        borderRadius: 2,
      }}
    >
      {label}
    </button>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{
        fontFamily: "'DM Mono', monospace", fontSize: 9,
        color: '#a8a8a0', letterSpacing: '0.07em',
        textTransform: 'uppercase', marginBottom: 4,
      }}>{label}</div>
      <div style={{
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 13, color: '#0f0f0d', lineHeight: 1.55,
      }}>{value}</div>
    </div>
  )
}

// ── Mission tab ────────────────────────────────────────────────────────────────

function MissionTab({
  dispatch, card, onAccept, onEnRoute, onComplete, onCancel, actionLoading,
}: {
  dispatch: DispatchRecord
  card: NeedCard
  onAccept: () => void
  onEnRoute: () => void
  onComplete: () => void
  onCancel: () => void
  actionLoading: boolean
}) {
  const { label: urgLabel, color: urgColor } = urgencyMeta(card.urgency_score_eff)
  const needColor = NEED_COLORS[card.need_type] || '#3a3a36'
  const urgPct = (card.urgency_score_eff / 10) * 100
  const mapLink = card.geo_confidence > 0.3
    ? `https://maps.google.com/?q=${card.geo_lat},${card.geo_lng}&zoom=17`
    : null

  const statusIs = (s: string) => dispatch.status === s

  return (
    <div style={{ padding: '22px 20px', paddingBottom: 36 }}>

      {/* Mission header */}
      <div style={{
        display: 'flex', alignItems: 'flex-start',
        justifyContent: 'space-between', marginBottom: 16,
      }}>
        <div>
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            color: needColor, letterSpacing: '0.1em',
            textTransform: 'uppercase', marginBottom: 8,
          }}>
            {card.need_type} · {dispatch.id.slice(0, 8)}
          </div>
          <UrgencyBadge score={card.urgency_score_eff} />
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 36, fontWeight: 300, color: urgColor, lineHeight: 1,
          }}>
            {card.urgency_score_eff.toFixed(1)}
          </div>
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 8,
            color: '#a8a8a0', letterSpacing: '0.06em', marginTop: 3,
          }}>/ 10</div>
        </div>
      </div>

      {/* Urgency bar */}
      <div style={{ height: 3, background: '#edeae2', marginBottom: 20, borderRadius: 2 }}>
        <div style={{
          height: '100%', width: `${urgPct}%`, background: urgColor,
          transition: 'width 0.6s ease', borderRadius: 2,
        }} />
      </div>

      {/* Brief */}
      {dispatch.brief_text ? (
        <div style={{ marginBottom: 18 }}>
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            color: '#a8a8a0', letterSpacing: '0.07em',
            textTransform: 'uppercase', marginBottom: 10,
          }}>
            mission brief
          </div>
          <div style={{
            fontFamily: "'DM Sans', sans-serif", fontSize: 14, lineHeight: 1.72,
            color: '#0f0f0d', background: '#edeae2',
            borderLeft: '3px solid #d4a847',
            padding: '14px 16px', borderRadius: '0 2px 2px 0',
          }}>
            {dispatch.brief_text}
          </div>
          <button
            onClick={() => navigator.clipboard.writeText(dispatch.brief_text)}
            style={{
              marginTop: 8,
              fontFamily: "'DM Mono', monospace", fontSize: 9,
              letterSpacing: '0.06em', padding: '5px 12px',
              border: '1px solid rgba(212,168,71,0.4)',
              background: 'transparent', cursor: 'pointer',
              color: '#b97200', textTransform: 'uppercase', borderRadius: 2,
            }}
          >
            copy for whatsapp
          </button>
        </div>
      ) : (
        <div style={{
          marginBottom: 18, padding: '14px 16px',
          border: '1px dashed rgba(15,15,13,0.15)',
          fontFamily: "'DM Mono', monospace",
          fontSize: 10, color: '#a8a8a0', borderRadius: 2,
        }}>
          Brief not yet generated — NGO will send it shortly.
        </div>
      )}

      <Rule />

      {/* Description */}
      <div style={{
        fontFamily: "'Fraunces', Georgia, serif",
        fontSize: 16, fontWeight: 300, lineHeight: 1.6,
        color: '#0f0f0d', marginBottom: 16,
      }}>
        {card.description_clean}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        {card.location_text_raw && <Field label="location" value={card.location_text_raw} />}
        {card.affected_count && <Field label="affected" value={`~${card.affected_count} people`} />}
        {card.contact_name && (
          <Field label="contact" value={`${card.contact_name}${card.contact_detail ? ' · ' + card.contact_detail : ''}`} />
        )}
        {card.skills_needed.length > 0 && (
          <Field label="skills needed" value={card.skills_needed.join(', ')} />
        )}
      </div>

      {/* Map link */}
      {mapLink && (
        <>
          <Rule />
          <a
            href={mapLink}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              fontFamily: "'DM Mono', monospace", fontSize: 10,
              color: '#2a9d70', letterSpacing: '0.06em',
              textDecoration: 'none', textTransform: 'uppercase',
              padding: '11px 16px',
              border: '1px solid rgba(42,157,112,0.4)',
              borderRadius: 2,
            }}
          >
            <span style={{ fontSize: 14 }}>📍</span>
            Open in Google Maps →
          </a>
        </>
      )}

      <Rule />

      {/* Mission timeline */}
      <div style={{ marginBottom: 18 }}>
        <div style={{
          fontFamily: "'DM Mono', monospace", fontSize: 9,
          color: '#a8a8a0', letterSpacing: '0.07em',
          textTransform: 'uppercase', marginBottom: 12,
        }}>
          mission timeline
        </div>
        {[
          { label: 'dispatched', ts: dispatch.dispatched_at,  done: true },
          { label: 'accepted',   ts: dispatch.accepted_at,    done: !!dispatch.accepted_at },
          { label: 'en route',   ts: null,                    done: dispatch.status === 'en_route' || dispatch.status === 'completed' },
          { label: 'completed',  ts: dispatch.completed_at,   done: !!dispatch.completed_at },
        ].map(({ label, ts, done }) => (
          <div key={label} style={{
            display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8,
          }}>
            <div style={{
              width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
              background: done ? '#2a9d70' : '#e5e3dc',
              border: done ? 'none' : '1px solid rgba(15,15,13,0.15)',
            }} />
            <span style={{
              fontFamily: "'DM Mono', monospace", fontSize: 9,
              color: done ? '#0f0f0d' : '#a8a8a0',
              letterSpacing: '0.05em', textTransform: 'uppercase', flex: 1,
            }}>
              {label}
            </span>
            {ts && (
              <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#a8a8a0' }}>
                {timeAgo(typeof ts === 'string' ? ts : (ts as any).toISOString())}
              </span>
            )}
          </div>
        ))}
      </div>

      <Rule />

      {/* Action buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {statusIs('pending') && (
          <>
            <ActionBtn label="Accept mission" color="#2a9d70" fill onClick={onAccept} disabled={actionLoading} />
            <ActionBtn label="Decline" color="#e03d25" onClick={onCancel} disabled={actionLoading} />
          </>
        )}
        {statusIs('accepted') && (
          <>
            <ActionBtn label="I'm on my way →" color="#2a9d70" fill onClick={onEnRoute} disabled={actionLoading} />
            <ActionBtn label="Cancel" color="#e03d25" onClick={onCancel} disabled={actionLoading} />
          </>
        )}
        {statusIs('en_route') && (
          <>
            <ActionBtn label="Mark mission complete ✓" color="#2a9d70" fill onClick={onComplete} disabled={actionLoading} />
            <ActionBtn label="Cancel" color="#e03d25" onClick={onCancel} disabled={actionLoading} />
          </>
        )}
        {statusIs('completed') && (
          <div style={{
            padding: '13px 16px',
            background: 'rgba(42,157,112,0.1)',
            border: '1px solid rgba(42,157,112,0.3)',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            color: '#2a9d70', letterSpacing: '0.07em',
            textAlign: 'center', borderRadius: 2,
          }}>
            ✓ Mission complete · {durHours(
              typeof dispatch.dispatched_at === 'string' ? dispatch.dispatched_at : (dispatch.dispatched_at as any).toISOString(),
              dispatch.completed_at ? (typeof dispatch.completed_at === 'string' ? dispatch.completed_at : (dispatch.completed_at as any).toISOString()) : null
            )}h logged
          </div>
        )}
        {statusIs('cancelled') && (
          <div style={{
            padding: '13px 16px',
            background: 'rgba(224,61,37,0.08)',
            border: '1px solid rgba(224,61,37,0.25)',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            color: '#e03d25', letterSpacing: '0.07em',
            textAlign: 'center', borderRadius: 2,
          }}>
            Mission cancelled
          </div>
        )}
      </div>

      {/* Match context */}
      <Rule />
      <div style={{ display: 'flex', gap: 0 }}>
        {[
          { k: 'match score', v: `${Math.round(dispatch.match_score * 100)}%` },
          { k: 'distance',    v: `${dispatch.distance_km.toFixed(1)} km` },
          { k: 'skill overlap', v: dispatch.skill_overlap.length ? dispatch.skill_overlap.join(', ') : '—' },
        ].map(({ k, v }, i) => (
          <div key={k} style={{
            flex: 1,
            padding: '12px 0',
            borderTop: '1px solid rgba(15,15,13,0.1)',
            borderRight: i < 2 ? '1px solid rgba(15,15,13,0.1)' : 'none',
            paddingRight: i < 2 ? 14 : 0,
            paddingLeft: i > 0 ? 14 : 0,
          }}>
            <div style={{
              fontFamily: "'DM Mono', monospace", fontSize: 8,
              color: '#a8a8a0', letterSpacing: '0.07em',
              textTransform: 'uppercase', marginBottom: 4,
            }}>{k}</div>
            <div style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 15, fontWeight: 300, color: '#0f0f0d',
            }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── History tab ────────────────────────────────────────────────────────────────

function HistoryTab({
  volunteer,
  history,
}: {
  volunteer: Volunteer
  history: Array<{ dispatch: DispatchRecord; card: NeedCard }>
}) {
  const totalH = history.reduce((sum, { dispatch }) => {
    if (dispatch.status !== 'completed') return sum
    return sum + durHours(
      typeof dispatch.dispatched_at === 'string' ? dispatch.dispatched_at : (dispatch.dispatched_at as any).toISOString(),
      dispatch.completed_at ? (typeof dispatch.completed_at === 'string' ? dispatch.completed_at : (dispatch.completed_at as any).toISOString()) : null
    )
  }, volunteer.total_hours ?? 0)

  return (
    <div style={{ padding: '22px 20px', paddingBottom: 36 }}>

      {/* Stats row */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
        marginBottom: 24,
        border: '1px solid rgba(15,15,13,0.1)',
        borderRadius: 2, overflow: 'hidden',
      }}>
        {[
          { v: volunteer.completed_missions + history.filter(h => h.dispatch.status === 'completed').length, l: 'missions' },
          { v: `${totalH.toFixed(1)}h`, l: 'hours' },
          { v: volunteer.max_radius_km + 'km', l: 'radius' },
        ].map(({ v, l }, i) => (
          <div key={l} style={{
            padding: '16px 0', textAlign: 'center',
            borderRight: i < 2 ? '1px solid rgba(15,15,13,0.1)' : 'none',
            background: i === 0 ? '#edeae2' : 'transparent',
          }}>
            <div style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 26, fontWeight: 300, color: '#0f0f0d', lineHeight: 1,
            }}>{v}</div>
            <div style={{
              fontFamily: "'DM Mono', monospace", fontSize: 8,
              color: '#a8a8a0', letterSpacing: '0.07em',
              textTransform: 'uppercase', marginTop: 5,
            }}>{l}</div>
          </div>
        ))}
      </div>

      {/* Skills */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          fontFamily: "'DM Mono', monospace", fontSize: 9,
          color: '#a8a8a0', letterSpacing: '0.07em',
          textTransform: 'uppercase', marginBottom: 10,
        }}>
          registered skills
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {volunteer.skills.map(s => (
            <span key={s} style={{
              fontFamily: "'DM Mono', monospace", fontSize: 9, letterSpacing: '0.05em',
              padding: '4px 10px',
              border: '1px solid rgba(15,15,13,0.15)',
              color: '#3a3a36', borderRadius: 2,
            }}>
              {s.replace(/_/g, ' ')}
            </span>
          ))}
          {volunteer.skills.length === 0 && (
            <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: '#a8a8a0' }}>
              No skills registered
            </span>
          )}
        </div>
      </div>

      <Rule />

      {/* Mission history list */}
      <div style={{
        fontFamily: "'DM Mono', monospace", fontSize: 9,
        color: '#a8a8a0', letterSpacing: '0.07em',
        textTransform: 'uppercase', marginBottom: 14,
      }}>
        past missions · {history.length} total
      </div>

      {history.length === 0 ? (
        <div style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 18, fontWeight: 300,
          color: '#c0bdb6', padding: '28px 0',
          letterSpacing: '-0.01em',
        }}>
          No past missions yet.
        </div>
      ) : (
        history.map(({ dispatch, card }) => {
          const needColor = NEED_COLORS[card.need_type] || '#3a3a36'
          const hours = dispatch.status === 'completed'
            ? durHours(
                typeof dispatch.dispatched_at === 'string' ? dispatch.dispatched_at : (dispatch.dispatched_at as any).toISOString(),
                dispatch.completed_at ? (typeof dispatch.completed_at === 'string' ? dispatch.completed_at : (dispatch.completed_at as any).toISOString()) : null
              )
            : null

          return (
            <div key={dispatch.id} style={{
              borderTop: `3px solid ${needColor}`,
              border: `1px solid rgba(15,15,13,0.1)`,
              borderTopWidth: 3,
              borderTopColor: needColor,
              padding: '12px 14px',
              marginBottom: 9,
              borderRadius: 2,
              background: '#fff',
            }}>
              <div style={{
                display: 'flex', alignItems: 'baseline',
                justifyContent: 'space-between', marginBottom: 6,
              }}>
                <span style={{
                  fontFamily: "'DM Mono', monospace", fontSize: 9,
                  color: needColor, letterSpacing: '0.08em', textTransform: 'uppercase',
                }}>
                  {card.need_type}
                </span>
                <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#a8a8a0' }}>
                  {timeAgo(typeof dispatch.dispatched_at === 'string' ? dispatch.dispatched_at : (dispatch.dispatched_at as any).toISOString())}
                </span>
              </div>
              <div style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 12, color: '#1a1a18', lineHeight: 1.5, marginBottom: 8,
                overflow: 'hidden', display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              }}>
                {card.description_clean}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{
                  fontFamily: "'DM Mono', monospace", fontSize: 8, letterSpacing: '0.06em',
                  padding: '3px 7px', borderRadius: 2,
                  border: `1px solid ${
                    dispatch.status === 'completed' ? 'rgba(42,157,112,0.4)'
                    : dispatch.status === 'cancelled' ? 'rgba(224,61,37,0.35)'
                    : 'rgba(15,15,13,0.15)'
                  }`,
                  color: dispatch.status === 'completed' ? '#2a9d70'
                    : dispatch.status === 'cancelled' ? '#e03d25'
                    : '#a8a8a0',
                  textTransform: 'uppercase',
                }}>
                  {dispatch.status}
                </span>
                {hours !== null && (
                  <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#a8a8a0' }}>
                    {hours}h
                  </span>
                )}
                {card.location_text_raw && (
                  <span style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#a8a8a0',
                    flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {card.location_text_raw}
                  </span>
                )}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

// ── Root component ─────────────────────────────────────────────────────────────

export function VolunteerApp({ onBack }: { onBack?: () => void }) {
  const [tab, setTab] = useState<Tab>('mission')
  const [dispatch, setDispatch] = useState<DispatchRecord>(SEED_DISPATCHES[0])
  const [card] = useState<NeedCard>(SEED_NEEDCARDS_BY_ID[dispatch.needcard_id])
  const [volunteer] = useState<Volunteer>(SEED_VOLUNTEER)
  const [history] = useState(SEED_HISTORY)
  const [actionLoading, setActionLoading] = useState(false)

  const mutateStatus = (status: DispatchRecord['status'], extra?: Partial<DispatchRecord>) => {
    setDispatch(prev => ({ ...prev, status, ...extra }))
  }

  const handleAccept = async () => {
    setActionLoading(true)
    try { await acceptDispatch(dispatch.id) } catch { /* demo */ }
    mutateStatus('accepted', { accepted_at: new Date() as unknown as string })
    setActionLoading(false)
  }

  const handleEnRoute = async () => {
    setActionLoading(true)
    try { await acceptDispatch(dispatch.id) } catch { /* demo */ }
    mutateStatus('en_route')
    setActionLoading(false)
  }

  const handleComplete = async () => {
    setActionLoading(true)
    try { await completeDispatch(dispatch.id) } catch { /* demo */ }
    mutateStatus('completed', { completed_at: new Date() as unknown as string })
    setActionLoading(false)
  }

  const handleCancel = async () => {
    setActionLoading(true)
    try { await cancelDispatch(dispatch.id) } catch { /* demo */ }
    mutateStatus('cancelled', { cancelled_at: new Date() as unknown as string })
    setActionLoading(false)
  }

  const needColor = NEED_COLORS[card.need_type] || '#3a3a36'

  return (
    <div style={{ height: '100vh', background: '#0d0d0b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      background: '#f5f2eb', color: '#0f0f0d',
      fontFamily: "'DM Sans', system-ui, sans-serif",
      width: '100%', maxWidth: 480,
      boxShadow: '0 0 0 1px rgba(255,255,255,0.06), 0 8px 60px rgba(0,0,0,0.55)',
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,700;1,9..144,300;1,9..144,400&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.35; transform: scale(0.65); }
        }
        .vol-avail-dot { animation: pulseDot 2s ease-in-out infinite; }
        .vol-tab-btn { transition: color 0.12s; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-track { background: #edeae2; }
        ::-webkit-scrollbar-thumb { background: #c0bdb6; }
      `}</style>

      {/* ── TOP BAR ── */}
      <div style={{
        background: '#0f0f0d', color: '#f5f2eb',
        display: 'flex', alignItems: 'center',
        height: 56, flexShrink: 0,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}>
        {/* Brand */}
        <div style={{
          padding: '0 18px',
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em',
          color: '#f5f2eb', borderRight: '1px solid rgba(255,255,255,0.1)',
          height: '100%', display: 'flex', alignItems: 'center', flexShrink: 0,
        }}>SETU</div>

        {/* Back */}
        {onBack && (
          <button onClick={onBack} style={{
            padding: '0 14px', height: '100%', background: 'transparent', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.1)',
            color: 'rgba(245,242,235,0.45)', cursor: 'pointer',
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            letterSpacing: '0.06em', textTransform: 'uppercase',
          }}>← back</button>
        )}

        {/* Volunteer name + need type indicator */}
        <div style={{
          padding: '0 14px', flex: 1,
          borderRight: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 8,
            color: 'rgba(245,242,235,0.3)', letterSpacing: '0.06em',
            textTransform: 'uppercase', marginBottom: 2,
          }}>volunteer</div>
          <div style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 13, color: '#f5f2eb', fontWeight: 500,
          }}>{volunteer.name}</div>
        </div>

        {/* Need type pill */}
        <div style={{
          padding: '0 14px',
          borderRight: '1px solid rgba(255,255,255,0.1)',
          display: 'flex', alignItems: 'center',
        }}>
          <span style={{
            fontFamily: "'DM Mono', monospace", fontSize: 8,
            background: needColor, color: '#fff',
            padding: '3px 8px', letterSpacing: '0.08em',
            textTransform: 'uppercase', borderRadius: 2,
          }}>{card.need_type}</span>
        </div>

        {/* Availability */}
        <div style={{
          padding: '0 14px',
          display: 'flex', alignItems: 'center', gap: 6,
          borderRight: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div
            className="vol-avail-dot"
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: volunteer.availability === 'available' ? '#2a9d70'
                : volunteer.availability === 'busy' ? '#d4a847' : '#a8a8a0',
            }}
          />
          <span style={{
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            color: 'rgba(245,242,235,0.4)', textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {volunteer.availability}
          </span>
        </div>

        <button onClick={() => logout()} style={{
          padding: '0 14px', height: '100%',
          background: 'transparent', border: 'none',
          cursor: 'pointer', fontFamily: "'DM Mono', monospace", fontSize: 9,
          color: 'rgba(245,242,235,0.35)', letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>out</button>
      </div>

      {/* ── TAB BAR ── */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid rgba(15,15,13,0.1)',
        flexShrink: 0,
        background: '#edeae2',
      }}>
        {(['mission', 'history'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="vol-tab-btn"
            style={{
              flex: 1, padding: '12px 0',
              fontFamily: "'DM Mono', monospace", fontSize: 10,
              letterSpacing: '0.07em', textTransform: 'uppercase',
              border: 'none',
              borderBottom: tab === t ? '2px solid #0f0f0d' : '2px solid transparent',
              background: 'transparent',
              color: tab === t ? '#0f0f0d' : '#a8a8a0',
              cursor: 'pointer',
              marginBottom: -1,
            }}
          >
            {t}
            {t === 'mission' && dispatch.status === 'pending' && (
              <span style={{
                marginLeft: 7, display: 'inline-block',
                width: 6, height: 6, borderRadius: '50%',
                background: '#e03d25', verticalAlign: 'middle',
              }} />
            )}
          </button>
        ))}
      </div>

      {/* ── BODY ── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {tab === 'mission' ? (
          <MissionTab
            dispatch={dispatch}
            card={card}
            onAccept={handleAccept}
            onEnRoute={handleEnRoute}
            onComplete={handleComplete}
            onCancel={handleCancel}
            actionLoading={actionLoading}
          />
        ) : (
          <HistoryTab volunteer={volunteer} history={history} />
        )}
        
      </div>
    </div>
    </div>
  )
}
