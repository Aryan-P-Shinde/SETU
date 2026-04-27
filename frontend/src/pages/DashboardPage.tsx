/**
 * DashboardPage.tsx — SETU NGO Command Centre
 *
 * Changes from original:
 * 1. Live Firestore reads via listOpenNeedCards() — seed data is fallback only
 * 2. Brief button calls quickDispatch() first (creates real dispatch_id), then generateBrief()
 * 3. Manual urgency decay trigger via runDecay()
 * 4. Full dark command-centre UI — not a paper form
 * 5. All stats are live (derived from actual cards)
 * 6. Three panel tabs: card detail / brief / dispatch record
 * 7. Search filter on feed
 * 8. 30s auto-refresh for live data
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { NeedCard, QuickDispatchResponse } from '../lib/api'
import { submitText, generateBrief, listOpenNeedCards, quickDispatch, runDecay } from '../lib/api'
import { SEED_NEEDCARDS } from '../lib/seedData'
import { logout } from '../lib/firebase'

type View = 'feed' | 'map'
type PanelTab = 'card' | 'brief' | 'dispatch'

const NEED_COLORS: Record<string, { bg: string; text: string }> = {
  rescue:    { bg: '#e03d25', text: '#fff' },
  medical:   { bg: '#e03d25', text: '#fff' },
  food:      { bg: '#b97200', text: '#fff' },
  water:     { bg: '#1a6bbf', text: '#fff' },
  shelter:   { bg: '#5b4fd4', text: '#fff' },
  logistics: { bg: '#3a7a5a', text: '#fff' },
  other:     { bg: '#5a5a52', text: '#fff' },
}

const TICKER_LIVE = [
  'Extraction pipeline active — Gemini 1.5 Flash ready',
  'Semantic dedup: text-embedding-004 · cosine sim threshold 0.88',
  'Urgency decay formula: U(t) = U₀ · e^(−0.05t)  half-life ≈14h',
  'Hash dedup: Layer 1 active · Semantic dedup: Layer 2 active',
  'Brief generator: WhatsApp-length · multilingual · 60–140 words',
  'Channel-agnostic intake — text / voice / image / WhatsApp',
]

const urgencyColor = (s: number) =>
  s >= 9 ? '#e03d25' : s >= 7 ? '#d4a847' : s >= 5 ? '#4a8fa8' : '#5a5a52'

const urgencyLabel = (s: number) =>
  s >= 9 ? 'CRITICAL' : s >= 7 ? 'HIGH' : s >= 5 ? 'MODERATE' : 'LOW'

const timeAgo = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function DashboardPage({ onBack }: { onBack?: () => void }) {
  const [cards, setCards] = useState<NeedCard[]>([])
  const [isLive, setIsLive] = useState(false)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<NeedCard | null>(null)
  const [panelTab, setPanelTab] = useState<PanelTab>('card')
  const [briefs, setBriefs] = useState<Record<string, string>>({})
  const [dispatches, setDispatches] = useState<Record<string, QuickDispatchResponse>>({})
  const [briefLoading, setBriefLoading] = useState<string | null>(null)
  const [reportText, setReportText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitStatus, setSubmitStatus] = useState<{ type: 'success' | 'error' | 'dup'; msg: string } | null>(null)
  const [view, setView] = useState<View>('feed')
  const [tickerIdx, setTickerIdx] = useState(0)
  const [decayRunning, setDecayRunning] = useState(false)
  const [decayResult, setDecayResult] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const mapRef = useRef<HTMLDivElement>(null)
  const mapReady = useRef(false)

  // ── Live data load ────────────────────────────────────────────────────────
  const loadCards = useCallback(async () => {
    try {
      const res = await listOpenNeedCards()
      const liveCards = res.data
      if (liveCards && liveCards.length > 0) {
        setCards(liveCards)
        setSelected(prev => prev ? (liveCards.find(c => c.id === prev.id) || liveCards[0]) : liveCards[0])
        setIsLive(true)
      } else {
        setCards(SEED_NEEDCARDS)
        setSelected(SEED_NEEDCARDS[0])
        setIsLive(false)
      }
    } catch {
      setCards(SEED_NEEDCARDS)
      setSelected(SEED_NEEDCARDS[0])
      setIsLive(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadCards() }, [loadCards])
  useEffect(() => {
    const t = setInterval(loadCards, 30000)
    return () => clearInterval(t)
  }, [loadCards])
  useEffect(() => {
    const t = setInterval(() => setTickerIdx(i => (i + 1) % TICKER_LIVE.length), 4200)
    return () => clearInterval(t)
  }, [])

  // ── Derived ───────────────────────────────────────────────────────────────
  const sorted = [...cards]
    .filter(c => !searchQuery ||
      c.description_clean.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.need_type.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => b.urgency_score_eff - a.urgency_score_eff)
  const openCount = cards.filter(c => c.status === 'open').length
  const criticalCount = cards.filter(c => c.urgency_score_eff >= 9).length
  const highCount = cards.filter(c => c.urgency_score_eff >= 7 && c.urgency_score_eff < 9).length
  const reviewCount = cards.filter(c => c.needs_review).length

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!reportText.trim() || submitting) return
    setSubmitting(true)
    setSubmitStatus(null)
    try {
      const res = await submitText(reportText)
      const result = res.data
      if (result.is_duplicate) {
        setSubmitStatus({ type: 'dup', msg: `Duplicate — merged into ${result.merged_into?.slice(0, 8)}` })
        setCards(prev => prev.map(c => c.id === result.merged_into ? { ...c, report_count: c.report_count + 1 } : c))
      } else {
        const prov: NeedCard = {
          id: result.needcard_id, need_type: result.need_type,
          description_clean: reportText.slice(0, 160),
          urgency_score_base: result.urgency_score, urgency_score_eff: result.urgency_score,
          urgency_reasoning: '', affected_count: null, skills_needed: [],
          geo_lat: 0, geo_lng: 0, geo_confidence: -1, location_text_raw: '',
          contact_name: null, contact_detail: null, report_count: 1, status: 'open',
          needs_review: result.needs_review, extraction_failed: result.extraction_failed,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }
        setCards(prev => [prov, ...prev])
        setSelected(prov)
        setSubmitStatus({ type: 'success', msg: `NeedCard ${result.needcard_id.slice(0, 8)} · urgency ${result.urgency_score.toFixed(1)}` })
      }
      setReportText('')
    } catch {
      setSubmitStatus({ type: 'error', msg: 'Failed — backend unreachable.' })
    } finally {
      setSubmitting(false)
    }
  }

  // ── Dispatch + Brief ──────────────────────────────────────────────────────
  const handleDispatchAndBrief = async (card: NeedCard) => {
    setBriefLoading(card.id)
    try {
      const dRes = await quickDispatch(card.id)
      const dispatch = dRes.data
      setDispatches(prev => ({ ...prev, [card.id]: dispatch }))
      const bRes = await generateBrief(dispatch.dispatch_id)
      setBriefs(prev => ({ ...prev, [card.id]: bRes.data.brief_text }))
      setPanelTab('brief')
    } catch {
      setBriefs(prev => ({ ...prev, [card.id]: 'Backend unreachable in this environment.\n\nIn live deployment: POST /dispatch/quick selects the nearest available volunteer by geo + skill overlap, then POST /brief/{dispatch_id} calls Gemini to generate a WhatsApp-length multilingual brief and stores it against the dispatch record.\n\nThis is a Phase 1 demo — the pipeline is built, the prompts are version-controlled, the dispatch record schema is live in Firestore.' }))
      setPanelTab('brief')
    } finally {
      setBriefLoading(null)
    }
  }

  // ── Decay ─────────────────────────────────────────────────────────────────
  const handleRunDecay = async () => {
    setDecayRunning(true)
    setDecayResult(null)
    try {
      const res = await runDecay()
      const d = res.data
      setDecayResult(`Decay complete — ${d.cards_updated} updated, ${d.cards_staled} staled`)
      await loadCards()
      setTimeout(() => setDecayResult(null), 8000)
    } catch {
      setDecayResult('Decay endpoint unavailable')
      setTimeout(() => setDecayResult(null), 5000)
    } finally {
      setDecayRunning(false)
    }
  }

  // ── Map ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (view !== 'map' || !mapRef.current || mapReady.current) return
    const key = (import.meta as any).env?.VITE_GOOGLE_MAPS_KEY
    if (!key) return
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${key}`
    script.onload = () => {
      if (!mapRef.current || mapReady.current) return
      mapReady.current = true
      const g = (window as any).google
      const map = new g.maps.Map(mapRef.current, {
        center: { lat: 22.572, lng: 88.363 }, zoom: 11,
        styles: [
          { featureType: 'all', elementType: 'geometry', stylers: [{ saturation: -90 }, { lightness: -20 }] },
          { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#1a2a3a' }] },
          { featureType: 'poi', stylers: [{ visibility: 'off' }] },
        ],
      })
      cards.filter(c => c.geo_confidence > 0.3).forEach(card => {
        const col = NEED_COLORS[card.need_type]?.bg || '#5a5a52'
        const marker = new g.maps.Marker({
          position: { lat: card.geo_lat, lng: card.geo_lng }, map,
          icon: { path: g.maps.SymbolPath.CIRCLE, scale: 10, fillColor: col, fillOpacity: 0.9, strokeColor: '#0a0a08', strokeWeight: 2 },
        })
        marker.addListener('click', () => { setSelected(card); setView('feed') })
      })
    }
    document.head.appendChild(script)
  }, [view, cards])

  const C = NEED_COLORS[selected?.need_type || ''] || NEED_COLORS.other

  return (
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      background: '#0d0d0b', color: '#e8e5de',
      fontFamily: "'DM Sans', system-ui, sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,700;1,9..144,300&family=DM+Sans:wght@300;400;500;600&display=swap');

        @keyframes pulseDot {
          0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(.6)}
        }
        @keyframes tickIn {
          from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:translateY(0)}
        }
        @keyframes fadePanel {
          from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)}
        }
        @keyframes shimmer {
          0%{background-position:-400px 0} 100%{background-position:400px 0}
        }

        .live-dot{width:6px;height:6px;border-radius:50%;background:#2a9d70;animation:pulseDot 1.4s ease-in-out infinite;flex-shrink:0}
        .live-dot.red{background:#e03d25}
        .tick-text{animation:tickIn .3s ease forwards}
        .card-row{transition:background .1s}
        .card-row:hover{background:rgba(255,255,255,.05) !important}
        .dash-btn{transition:all .15s;cursor:pointer}
        .dash-btn:hover:not(:disabled){filter:brightness(1.15)}
        .dash-btn:disabled{opacity:.35;cursor:not-allowed}
        .panel-tab{transition:color .12s,border-color .12s;cursor:pointer}
        .skeleton{
          background:linear-gradient(90deg,rgba(255,255,255,.04) 25%,rgba(255,255,255,.08) 50%,rgba(255,255,255,.04) 75%);
          background-size:400px 100%;animation:shimmer 1.4s ease infinite;border-radius:3px
        }
        .fade-panel{animation:fadePanel .2s ease forwards}
        ::-webkit-scrollbar{width:3px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:2px}
        textarea,input{caret-color:#d4a847}
        textarea:focus,input:focus{outline:none}
        textarea::placeholder,input::placeholder{color:rgba(232,229,222,.25)}
      `}</style>

      {/* ── NAV ── */}
      <nav style={{
        background: '#0a0a08',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'stretch',
        height: 50, flexShrink: 0,
      }}>
        <div style={{
          padding: '0 20px',
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', color: '#e8e5de',
          borderRight: '1px solid rgba(255,255,255,0.07)',
          display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        }}>
          SETU
          <span style={{
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            color: isLive ? '#2a9d70' : '#d4a847',
            background: isLive ? 'rgba(42,157,112,0.1)' : 'rgba(212,168,71,0.1)',
            padding: '2px 7px', borderRadius: 2, letterSpacing: '0.08em',
          }}>{isLive ? 'LIVE' : 'SEED'}</span>
        </div>

        {onBack && (
          <button onClick={onBack} className="dash-btn" style={{
            padding: '0 16px', background: 'transparent', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            color: 'rgba(232,229,222,.3)',
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            letterSpacing: '0.08em', textTransform: 'uppercase',
          }}>← back</button>
        )}

        {(['feed','map'] as View[]).map(v => (
          <button key={v} onClick={() => setView(v)} className="dash-btn" style={{
            padding: '0 16px', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            background: 'transparent',
            color: view === v ? '#d4a847' : 'rgba(232,229,222,.3)',
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            borderBottom: view === v ? '2px solid #d4a847' : '2px solid transparent',
          }}>{v}</button>
        ))}

        <button
          onClick={handleRunDecay}
          disabled={decayRunning}
          className="dash-btn"
          title="Manually trigger urgency decay (U₀ · e^(−0.05t))"
          style={{
            padding: '0 16px', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            background: 'transparent',
            color: decayRunning ? '#d4a847' : 'rgba(232,229,222,.28)',
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            letterSpacing: '0.07em', textTransform: 'uppercase',
          }}>
          {decayRunning ? '⟳ running…' : '⟳ decay'}
        </button>

        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', gap: 9,
          padding: '0 18px', overflow: 'hidden',
          fontFamily: "'DM Mono', monospace", fontSize: 10,
          color: 'rgba(232,229,222,.27)',
        }}>
          <span className="live-dot" />
          <span key={decayResult || tickerIdx} className="tick-text" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {decayResult || TICKER_LIVE[tickerIdx]}
          </span>
        </div>

        {/* Live stats */}
        <div style={{ display: 'flex', borderLeft: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}>
          {[
            { v: openCount,     label: 'open',     color: '#e8e5de' },
            { v: criticalCount, label: 'critical',  color: '#e03d25' },
            { v: highCount,     label: 'high',      color: '#d4a847' },
            { v: reviewCount,   label: 'review',    color: '#4a8fa8' },
          ].map(s => (
            <div key={s.label} style={{
              padding: '4px 13px',
              borderRight: '1px solid rgba(255,255,255,0.07)',
              textAlign: 'center',
              display: 'flex', flexDirection: 'column', justifyContent: 'center',
            }}>
              <div style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontSize: 17, fontWeight: 300, lineHeight: 1, color: s.color,
              }}>{loading ? '—' : s.v}</div>
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 7,
                color: 'rgba(232,229,222,.28)', letterSpacing: '0.07em',
                textTransform: 'uppercase', marginTop: 2,
              }}>{s.label}</div>
            </div>
          ))}
        </div>

        <button onClick={() => logout()} className="dash-btn" style={{
          padding: '0 14px', background: 'transparent', border: 'none',
          color: 'rgba(232,229,222,.22)',
          fontFamily: "'DM Mono', monospace", fontSize: 8,
          letterSpacing: '0.06em', textTransform: 'uppercase',
        }}>sign out</button>
      </nav>

      {/* ── BODY ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ── LEFT PANEL ── */}
        <div style={{
          width: 290, flexShrink: 0,
          borderRight: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          {/* Intake */}
          <div style={{
            padding: '14px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            background: '#0a0a08', flexShrink: 0,
          }}>
            <div style={{
              fontFamily: "'DM Mono', monospace", fontSize: 9,
              color: '#d4a847', letterSpacing: '0.1em', textTransform: 'uppercase',
              marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{ width: 4, height: 4, background: '#d4a847', borderRadius: '50%', display: 'inline-block' }} />
              new field report
            </div>

            <textarea
              value={reportText}
              onChange={e => setReportText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit() }}
              placeholder="Any language — Hindi, Bengali, English, Tamil…"
              rows={4}
              style={{
                width: '100%', border: 'none',
                borderBottom: '1px solid rgba(255,255,255,0.1)',
                background: 'transparent',
                fontFamily: "'DM Sans', sans-serif", fontSize: 12,
                padding: '4px 0', resize: 'none',
                color: '#e8e5de', lineHeight: 1.6,
              }}
            />

            {submitStatus && (
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 9,
                color: submitStatus.type === 'error' ? '#e03d25'
                  : submitStatus.type === 'dup' ? '#d4a847' : '#2a9d70',
                marginTop: 7, lineHeight: 1.5,
              }}>{submitStatus.msg}</div>
            )}

            <button
              onClick={handleSubmit}
              disabled={submitting || !reportText.trim()}
              className="dash-btn"
              style={{
                marginTop: 9, width: '100%',
                fontFamily: "'DM Mono', monospace", fontSize: 9,
                letterSpacing: '0.08em', textTransform: 'uppercase',
                padding: '8px 0',
                background: 'rgba(212,168,71,0.08)',
                border: `1px solid rgba(212,168,71,${submitting ? 0.4 : 0.2})`,
                color: '#d4a847', borderRadius: 2,
              }}
            >
              {submitting ? '● extracting…' : '↑ extract  ⌘↵'}
            </button>
          </div>

          {/* Search */}
          <div style={{
            padding: '7px 13px',
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            flexShrink: 0,
          }}>
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="filter cards…"
              style={{
                width: '100%', background: 'transparent', border: 'none',
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                color: 'rgba(232,229,222,.55)', letterSpacing: '0.04em', padding: '2px 0',
              }}
            />
          </div>

          {/* Feed label */}
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 8,
            color: 'rgba(232,229,222,.28)', letterSpacing: '0.08em', textTransform: 'uppercase',
            padding: '7px 13px',
            borderBottom: '1px solid rgba(255,255,255,0.04)',
            flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 7,
          }}>
            <span className="live-dot" style={{ width: 5, height: 5 }} />
            {sorted.length} need cards
          </div>

          {/* Feed */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading
              ? Array.from({ length: 7 }).map((_, i) => (
                  <div key={i} style={{ padding: '11px 13px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <div className="skeleton" style={{ height: 8, width: '40%', marginBottom: 7 }} />
                    <div className="skeleton" style={{ height: 9, width: '90%', marginBottom: 4 }} />
                    <div className="skeleton" style={{ height: 9, width: '65%' }} />
                  </div>
                ))
              : sorted.map(card => {
                  const col = NEED_COLORS[card.need_type] || NEED_COLORS.other
                  const isSel = selected?.id === card.id
                  return (
                    <div
                      key={card.id}
                      onClick={() => { setSelected(card); setPanelTab('card') }}
                      className="card-row"
                      style={{
                        padding: '10px 13px',
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                        cursor: 'pointer',
                        background: isSel ? 'rgba(255,255,255,0.05)' : 'transparent',
                        borderLeft: isSel ? `3px solid ${col.bg}` : '3px solid transparent',
                        display: 'flex', gap: 9, alignItems: 'flex-start',
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                          <span style={{
                            fontFamily: "'DM Mono', monospace", fontSize: 8,
                            background: col.bg, color: col.text,
                            padding: '1px 5px', borderRadius: 1, letterSpacing: '0.08em', textTransform: 'uppercase',
                          }}>{card.need_type}</span>
                          {card.needs_review && <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 8, color: '#4a8fa8' }}>· ⚑</span>}
                          {card.report_count > 1 && <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 8, color: 'rgba(232,229,222,.3)' }}>×{card.report_count}</span>}
                        </div>
                        <div style={{
                          fontSize: 11, color: isSel ? '#e8e5de' : 'rgba(232,229,222,.6)',
                          lineHeight: 1.5, overflow: 'hidden',
                          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                        } as any}>{card.description_clean}</div>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: 'rgba(232,229,222,.25)', marginTop: 3, letterSpacing: '0.03em',
                        }}>{timeAgo(card.created_at)}</div>
                      </div>
                      <div style={{
                        fontFamily: "'Fraunces', Georgia, serif",
                        fontSize: 19, fontWeight: 300, lineHeight: 1,
                        color: urgencyColor(card.urgency_score_eff), flexShrink: 0,
                      }}>{card.urgency_score_eff.toFixed(1)}</div>
                    </div>
                  )
                })
            }
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {view === 'map' ? (
            <div ref={mapRef} style={{ flex: 1, background: '#111310' }}>
              {!(import.meta as any).env?.VITE_GOOGLE_MAPS_KEY && (
                <div style={{
                  height: '100%', display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center', gap: 10,
                }}>
                  <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 24, fontWeight: 300, color: 'rgba(232,229,222,.18)' }}>
                    Map view
                  </div>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: 'rgba(232,229,222,.14)', letterSpacing: '0.06em' }}>
                    set VITE_GOOGLE_MAPS_KEY in .env to enable
                  </div>
                </div>
              )}
            </div>
          ) : selected ? (
            <div key={selected.id} className="fade-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

              {/* Panel header */}
              <div style={{
                padding: '16px 22px',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                flexShrink: 0, display: 'flex', alignItems: 'center', gap: 14,
              }}>
                {/* Urgency block */}
                <div style={{
                  padding: '8px 14px', flexShrink: 0,
                  background: `${urgencyColor(selected.urgency_score_eff)}12`,
                  border: `1px solid ${urgencyColor(selected.urgency_score_eff)}25`,
                  borderRadius: 4, textAlign: 'center',
                }}>
                  <div style={{
                    fontFamily: "'Fraunces', Georgia, serif",
                    fontSize: 30, fontWeight: 300, lineHeight: 1,
                    color: urgencyColor(selected.urgency_score_eff),
                  }}>{selected.urgency_score_eff.toFixed(1)}</div>
                  <div style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 7,
                    color: urgencyColor(selected.urgency_score_eff),
                    letterSpacing: '0.09em', marginTop: 4,
                  }}>{urgencyLabel(selected.urgency_score_eff)}</div>
                </div>

                {/* Title block */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, flexWrap: 'wrap' }}>
                    <span style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 9,
                      background: C.bg, color: C.text,
                      padding: '3px 8px', borderRadius: 2,
                      letterSpacing: '0.09em', textTransform: 'uppercase',
                    }}>{selected.need_type}</span>
                    {selected.needs_review && (
                      <span style={{
                        fontFamily: "'DM Mono', monospace", fontSize: 9,
                        color: '#4a8fa8', border: '1px solid rgba(74,143,168,.25)',
                        padding: '2px 7px', borderRadius: 2, letterSpacing: '0.07em',
                      }}>⚑ REVIEW</span>
                    )}
                    {selected.report_count > 1 && (
                      <span style={{
                        fontFamily: "'DM Mono', monospace", fontSize: 9,
                        color: 'rgba(232,229,222,.35)',
                      }}>×{selected.report_count} reports</span>
                    )}
                  </div>
                  <div style={{ fontSize: 13, color: '#e8e5de', lineHeight: 1.55, marginBottom: 6 }}>
                    {selected.description_clean}
                  </div>
                  <div style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 9,
                    color: 'rgba(232,229,222,.28)', letterSpacing: '0.04em',
                  }}>
                    {selected.id.slice(0, 12)} · {timeAgo(selected.created_at)}
                    {selected.location_text_raw ? ` · ${selected.location_text_raw}` : ''}
                  </div>
                </div>

                {/* Action button */}
                <button
                  onClick={() => handleDispatchAndBrief(selected)}
                  disabled={briefLoading === selected.id}
                  className="dash-btn"
                  style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 9,
                    letterSpacing: '0.08em', textTransform: 'uppercase',
                    padding: '10px 16px', flexShrink: 0,
                    background: briefLoading === selected.id ? 'rgba(42,157,112,.15)' : 'rgba(42,157,112,.1)',
                    border: `1px solid rgba(42,157,112,${briefLoading === selected.id ? .5 : .25})`,
                    color: '#2a9d70', borderRadius: 2,
                  }}
                >
                  {briefLoading === selected.id ? '⟳ generating…'
                    : dispatches[selected.id] ? '↻ regenerate brief'
                    : '→ dispatch + brief'}
                </button>
              </div>

              {/* Tabs */}
              <div style={{
                display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.06)',
                flexShrink: 0, padding: '0 22px',
              }}>
                {(['card','brief','dispatch'] as PanelTab[]).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setPanelTab(tab)}
                    className="panel-tab"
                    style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 9,
                      letterSpacing: '0.08em', textTransform: 'uppercase',
                      padding: '10px 14px', border: 'none', background: 'transparent',
                      color: panelTab === tab ? '#e8e5de' : 'rgba(232,229,222,.3)',
                      borderBottom: panelTab === tab ? '2px solid #d4a847' : '2px solid transparent',
                    }}
                  >
                    {tab}
                    {tab === 'brief' && briefs[selected.id] ? ' ●' : ''}
                    {tab === 'dispatch' && dispatches[selected.id] ? ' ●' : ''}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '22px' }}>

                {/* ── CARD TAB ── */}
                {panelTab === 'card' && (
                  <div style={{ display: 'grid', gap: 14 }}>
                    {selected.urgency_reasoning && (
                      <div style={{
                        padding: '13px 15px',
                        background: `${urgencyColor(selected.urgency_score_eff)}0c`,
                        borderLeft: `3px solid ${urgencyColor(selected.urgency_score_eff)}`,
                        borderRadius: 2,
                      }}>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: urgencyColor(selected.urgency_score_eff),
                          letterSpacing: '0.09em', textTransform: 'uppercase', marginBottom: 7,
                        }}>urgency reasoning</div>
                        <p style={{ fontSize: 13, color: 'rgba(232,229,222,.75)', lineHeight: 1.7 }}>
                          {selected.urgency_reasoning}
                        </p>
                      </div>
                    )}

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 9 }}>
                      {[
                        { label: 'Base urgency', value: selected.urgency_score_base.toFixed(1) },
                        { label: 'Eff urgency', value: selected.urgency_score_eff.toFixed(1) },
                        { label: 'Affected', value: selected.affected_count ? `${selected.affected_count}` : '—' },
                        { label: 'Reports', value: `×${selected.report_count}` },
                        { label: 'Geo confidence', value: selected.geo_confidence > 0 ? `${(selected.geo_confidence * 100).toFixed(0)}%` : '—' },
                        { label: 'Extraction', value: selected.extraction_failed ? '⚠ failed' : '✓ ok' },
                      ].map(item => (
                        <div key={item.label} style={{
                          padding: '9px 11px',
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.06)',
                          borderRadius: 3,
                        }}>
                          <div style={{
                            fontFamily: "'DM Mono', monospace", fontSize: 8,
                            color: 'rgba(232,229,222,.33)', letterSpacing: '0.07em',
                            textTransform: 'uppercase', marginBottom: 4,
                          }}>{item.label}</div>
                          <div style={{ fontSize: 14, fontWeight: 500, color: '#e8e5de' }}>{item.value}</div>
                        </div>
                      ))}
                    </div>

                    {selected.skills_needed.length > 0 && (
                      <div>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: 'rgba(232,229,222,.33)', letterSpacing: '0.09em',
                          textTransform: 'uppercase', marginBottom: 8,
                        }}>skills needed</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {selected.skills_needed.map(skill => (
                            <span key={skill} style={{
                              fontFamily: "'DM Mono', monospace", fontSize: 10,
                              padding: '3px 9px',
                              background: 'rgba(255,255,255,0.05)',
                              border: '1px solid rgba(255,255,255,0.09)',
                              borderRadius: 2, color: 'rgba(232,229,222,.65)',
                            }}>{skill.replace(/_/g, ' ')}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {(selected.contact_name || selected.contact_detail) && (
                      <div style={{
                        padding: '11px 13px',
                        background: 'rgba(42,157,112,0.06)',
                        border: '1px solid rgba(42,157,112,0.15)',
                        borderRadius: 3,
                      }}>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: '#2a9d70', letterSpacing: '0.09em',
                          textTransform: 'uppercase', marginBottom: 5,
                        }}>contact</div>
                        <div style={{ fontSize: 13, color: 'rgba(232,229,222,.75)' }}>
                          {selected.contact_name}{selected.contact_detail ? ` · ${selected.contact_detail}` : ''}
                        </div>
                      </div>
                    )}

                    {selected.geo_confidence > 0.3 && (
                      <a
                        href={`https://maps.google.com/?q=${selected.geo_lat},${selected.geo_lng}`}
                        target="_blank" rel="noopener noreferrer"
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 8,
                          fontFamily: "'DM Mono', monospace", fontSize: 9,
                          color: '#4a8fa8', letterSpacing: '0.07em', textTransform: 'uppercase',
                          textDecoration: 'none', padding: '8px 13px',
                          border: '1px solid rgba(74,143,168,0.2)', borderRadius: 2, width: 'fit-content',
                        }}
                      >
                        ↗ open in google maps
                      </a>
                    )}
                  </div>
                )}

                {/* ── BRIEF TAB ── */}
                {panelTab === 'brief' && (
                  <div>
                    {briefs[selected.id] ? (
                      <div>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: '#2a9d70', letterSpacing: '0.09em',
                          textTransform: 'uppercase', marginBottom: 13,
                          display: 'flex', alignItems: 'center', gap: 7,
                        }}>
                          <span style={{ width: 5, height: 5, background: '#2a9d70', borderRadius: '50%', display: 'inline-block' }} />
                          volunteer mission brief
                        </div>
                        <div style={{
                          padding: '18px',
                          background: 'rgba(42,157,112,0.06)',
                          border: '1px solid rgba(42,157,112,0.18)',
                          borderRadius: 4,
                          fontFamily: "'DM Sans', sans-serif",
                          fontSize: 14, lineHeight: 1.8, color: '#e8e5de',
                          whiteSpace: 'pre-wrap',
                        }}>
                          {briefs[selected.id]}
                        </div>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 9,
                          color: 'rgba(232,229,222,.25)', marginTop: 9, letterSpacing: '0.04em',
                        }}>
                          {briefs[selected.id].split(' ').length} words · WhatsApp-ready · multilingual
                          {dispatches[selected.id] ? ` · dispatch ${dispatches[selected.id].dispatch_id.slice(0, 10)}` : ''}
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, gap: 10 }}>
                        <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: 'rgba(232,229,222,.2)' }}>No brief yet</div>
                        <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: 'rgba(232,229,222,.2)', letterSpacing: '0.06em' }}>click "dispatch + brief" above</div>
                      </div>
                    )}
                  </div>
                )}

                {/* ── DISPATCH TAB ── */}
                {panelTab === 'dispatch' && (
                  <div>
                    {dispatches[selected.id] ? (
                      <div style={{ display: 'grid', gap: 14 }}>
                        <div style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 8,
                          color: '#2a9d70', letterSpacing: '0.09em', textTransform: 'uppercase',
                          display: 'flex', alignItems: 'center', gap: 7,
                        }}>
                          <span style={{ width: 5, height: 5, background: '#2a9d70', borderRadius: '50%', display: 'inline-block' }} />
                          dispatch record
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 9 }}>
                          {[
                            { label: 'Dispatch ID', value: dispatches[selected.id].dispatch_id.slice(0, 14) },
                            { label: 'Status', value: dispatches[selected.id].status.toUpperCase() },
                            { label: 'Volunteer ID', value: dispatches[selected.id].volunteer_id.slice(0, 14) },
                            { label: 'Distance', value: `${dispatches[selected.id].distance_km.toFixed(1)} km` },
                            { label: 'Match score', value: `${(dispatches[selected.id].match_score * 100).toFixed(0)}%` },
                            { label: 'Skill overlap', value: dispatches[selected.id].skill_overlap.length > 0 ? dispatches[selected.id].skill_overlap.length + ' matched' : '—' },
                          ].map(item => (
                            <div key={item.label} style={{
                              padding: '9px 11px',
                              background: 'rgba(255,255,255,0.03)',
                              border: '1px solid rgba(255,255,255,0.06)',
                              borderRadius: 3,
                            }}>
                              <div style={{
                                fontFamily: "'DM Mono', monospace", fontSize: 8,
                                color: 'rgba(232,229,222,.33)', letterSpacing: '0.07em',
                                textTransform: 'uppercase', marginBottom: 4,
                              }}>{item.label}</div>
                              <div style={{ fontSize: 13, color: '#e8e5de', wordBreak: 'break-all' }}>{item.value}</div>
                            </div>
                          ))}
                        </div>
                        {dispatches[selected.id].skill_overlap.length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {dispatches[selected.id].skill_overlap.map(s => (
                              <span key={s} style={{
                                fontFamily: "'DM Mono', monospace", fontSize: 10,
                                padding: '3px 9px',
                                background: 'rgba(42,157,112,0.1)',
                                border: '1px solid rgba(42,157,112,0.2)',
                                borderRadius: 2, color: '#2a9d70',
                              }}>{s.replace(/_/g, ' ')}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, gap: 10 }}>
                        <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: 'rgba(232,229,222,.2)' }}>No dispatch yet</div>
                        <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: 'rgba(232,229,222,.2)', letterSpacing: '0.06em' }}>click "dispatch + brief" above</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 26, fontWeight: 300, color: 'rgba(232,229,222,.15)' }}>Select a need card</div>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: 'rgba(232,229,222,.12)', letterSpacing: '0.06em' }}>← pick from the feed</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
