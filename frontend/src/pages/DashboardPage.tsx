/**
 * DashboardPage.tsx — SETU
 * Rethemed to match LandingPage: dark nav, Fraunces headings, gold accents, warm paper.
 */

import { useState, useEffect, useRef } from 'react'
import type { NeedCard } from '../lib/api'
import { submitText, generateBrief } from '../lib/api'
import { SEED_NEEDCARDS } from '../lib/seedData'
import { NeedCardComponent } from '../components/NeedCardComponent'
import { logout } from '../lib/firebase'

type View = 'feed' | 'map'

const NEED_COLORS: Record<string, string> = {
  rescue:    '#e03d25',
  medical:   '#e03d25',
  food:      '#b97200',
  water:     '#1a6bbf',
  shelter:   '#5b4fd4',
  logistics: '#3a3a36',
  other:     '#3a3a36',
}

const TICKER = [
  'Processing voice note from Sylhet field worker...',
  'NeedCard #308 dispatched — volunteer en route',
  'Translating Hindi report from Patna district...',
  'Urgency updated: shelter in Assam → 8.1',
  'WhatsApp brief sent to Aarav S. (2.3 km away)',
  'New image intake: handwritten form, West Bengal',
]

export function DashboardPage({ onBack }: { onBack?: () => void }) {
  const [cards, setCards] = useState<NeedCard[]>(SEED_NEEDCARDS)
  const [selected, setSelected] = useState<NeedCard | null>(SEED_NEEDCARDS[0])
  const [briefs, setBriefs] = useState<Record<string, string>>({})
  const [briefLoading, setBriefLoading] = useState<string | null>(null)
  const [reportText, setReportText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submitSuccess, setSubmitSuccess] = useState('')
  const [view, setView] = useState<View>('feed')
  const [tickerIdx, setTickerIdx] = useState(0)
  const mapRef = useRef<HTMLDivElement>(null)
  const mapReady = useRef(false)

  const openCount = cards.filter(c => c.status === 'open').length
  const reviewCount = cards.filter(c => c.needs_review).length
  const fulfilledCount = cards.filter(c => c.status === 'fulfilled').length
  const sorted = [...cards].sort((a, b) => b.urgency_score_eff - a.urgency_score_eff)

  useEffect(() => {
    const t = setInterval(() => setTickerIdx(i => (i + 1) % TICKER.length), 3000)
    return () => clearInterval(t)
  }, [])

  const handleSubmit = async () => {
    if (!reportText.trim() || submitting) return
    setSubmitting(true)
    setSubmitError('')
    setSubmitSuccess('')
    try {
      const res = await submitText(reportText)
      const result = res.data
      if (result.is_duplicate) {
        setSubmitSuccess(`Duplicate — merged into ${result.merged_into?.slice(0, 8)}`)
        setCards(prev => prev.map(c => c.id === result.merged_into ? { ...c, report_count: c.report_count + 1 } : c))
      } else {
        const provisional: NeedCard = {
          id: result.needcard_id, need_type: result.need_type,
          description_clean: reportText.slice(0, 120),
          urgency_score_base: result.urgency_score, urgency_score_eff: result.urgency_score,
          urgency_reasoning: '', affected_count: null, skills_needed: [],
          geo_lat: 0, geo_lng: 0, geo_confidence: 0, location_text_raw: '',
          contact_name: null, contact_detail: null, report_count: 1,
          status: 'open', needs_review: result.needs_review, extraction_failed: result.extraction_failed,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }
        setCards(prev => [provisional, ...prev])
        setSelected(provisional)
        setSubmitSuccess(`NeedCard created · urgency ${result.urgency_score.toFixed(1)}`)
      }
      setReportText('')
    } catch {
      setSubmitError('Submission failed — check connection.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleGenerateBrief = async (card: NeedCard) => {
    setBriefLoading(card.id)
    try {
      const res = await generateBrief(`demo_dispatch_${card.id}`)
      setBriefs(prev => ({ ...prev, [card.id]: res.data.brief_text }))
    } catch {
      setBriefs(prev => ({ ...prev, [card.id]: '[Brief requires live backend with GEMINI_API_KEY configured]' }))
    } finally {
      setBriefLoading(null)
    }
  }

  useEffect(() => {
    if (view !== 'map' || !mapRef.current || mapReady.current) return
    const key = import.meta.env.VITE_GOOGLE_MAPS_KEY
    if (!key) return

    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${key}`
    script.onload = () => {
      if (!mapRef.current || mapReady.current) return
      mapReady.current = true
      const g = (window as any).google
      const map = new g.maps.Map(mapRef.current, {
        center: { lat: 22.572, lng: 88.363 }, zoom: 12,
        styles: [
          { featureType: 'all', elementType: 'geometry', stylers: [{ saturation: -80 }] },
          { featureType: 'poi', stylers: [{ visibility: 'off' }] },
        ],
      })
      cards.filter(c => c.geo_confidence > 0.3).forEach(card => {
        const color = card.urgency_score_eff >= 9 ? '#e03d25' : card.urgency_score_eff >= 7 ? '#b97200' : '#3a3a36'
        const marker = new g.maps.Marker({
          position: { lat: card.geo_lat, lng: card.geo_lng }, map,
          icon: { path: g.maps.SymbolPath.CIRCLE, scale: 8, fillColor: color, fillOpacity: 1, strokeColor: '#f5f2eb', strokeWeight: 2 },
        })
        marker.addListener('click', () => { setSelected(card); setView('feed') })
      })
    }
    document.head.appendChild(script)
  }, [view])

  const urgencyColor = (s: number) =>
    s >= 9 ? '#e03d25' : s >= 7 ? '#b97200' : '#6b6b65'

  return (
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      background: '#f5f2eb', color: '#0f0f0d',
      fontFamily: "'DM Sans', system-ui, sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,700;1,9..144,300;1,9..144,400&family=DM+Sans:wght@300;400;500;600&display=swap');

        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.35; transform: scale(0.65); }
        }
        @keyframes tickIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        .dash-dot {
          display: inline-block; width: 7px; height: 7px; border-radius: 50%;
          background: #e03d25; animation: pulseDot 1.5s ease-in-out infinite;
          flex-shrink: 0;
        }
        .dash-tick { animation: tickIn 0.35s ease forwards; }

        .dash-card-row { transition: background 0.12s; }
        .dash-card-row:hover { background: #edeae2 !important; }

        .dash-submit-btn { transition: all 0.15s; }
        .dash-submit-btn:hover:not(:disabled) {
          background: #0f0f0d !important;
          color: #f5f2eb !important;
        }

        .dash-view-btn { transition: all 0.15s; }

        .dash-nav-ghost { transition: opacity 0.15s; }
        .dash-nav-ghost:hover { opacity: 0.65; }

        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #edeae2; }
        ::-webkit-scrollbar-thumb { background: #a8a8a0; }
      `}</style>

      {/* ── NAV ── */}
      <nav style={{
        background: '#0f0f0d', color: '#f5f2eb',
        display: 'flex', alignItems: 'center',
        height: 56, flexShrink: 0,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}>
        {/* Brand */}
        <div style={{
          padding: '0 24px',
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em',
          color: '#f5f2eb', borderRight: '1px solid rgba(255,255,255,0.1)',
          height: '100%', display: 'flex', alignItems: 'center', flexShrink: 0,
        }}>SETU</div>

        {/* Back */}
        {onBack && (
          <button onClick={onBack} className="dash-nav-ghost" style={{
            padding: '0 18px', height: '100%', background: 'transparent', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.1)',
            color: 'rgba(245,242,235,0.5)', cursor: 'pointer',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            letterSpacing: '0.06em', textTransform: 'uppercase',
          }}>← back</button>
        )}

        {/* View toggles */}
        {(['feed', 'map'] as View[]).map(v => (
          <button key={v} onClick={() => setView(v)} className="dash-view-btn" style={{
            padding: '0 18px', height: '100%', border: 'none',
            borderRight: '1px solid rgba(255,255,255,0.1)',
            background: view === v ? '#d4a847' : 'transparent',
            color: view === v ? '#0f0f0d' : 'rgba(245,242,235,0.45)',
            cursor: 'pointer',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            letterSpacing: '0.07em', textTransform: 'uppercase',
            fontWeight: view === v ? 600 : 400,
          }}>{v}</button>
        ))}

        {/* Ticker */}
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 20px', overflow: 'hidden',
          fontFamily: "'DM Mono', monospace", fontSize: 10,
          color: 'rgba(245,242,235,0.38)',
        }}>
          <span className="dash-dot" />
          <span key={tickerIdx} className="dash-tick" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {TICKER[tickerIdx]}
          </span>
        </div>

        {/* Stats */}
        <div style={{ display: 'flex', borderLeft: '1px solid rgba(255,255,255,0.1)', flexShrink: 0 }}>
          {[
            { value: openCount,      label: 'open',      color: '#e03d25' },
            { value: 31,             label: 'volunteers', color: undefined },
            { value: fulfilledCount, label: 'fulfilled',  color: '#2a9d70' },
            { value: reviewCount,    label: 'review',     color: '#d4a847' },
          ].map(s => (
            <div key={s.label} style={{
              padding: '6px 16px', borderRight: '1px solid rgba(255,255,255,0.1)',
              textAlign: 'center',
            }}>
              <div style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontSize: 20, fontWeight: 300, lineHeight: 1,
                color: s.color || '#f5f2eb',
              }}>{s.value}</div>
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 8,
                color: 'rgba(245,242,235,0.3)', letterSpacing: '0.06em',
                textTransform: 'uppercase', marginTop: 3,
              }}>{s.label}</div>
            </div>
          ))}
        </div>

        <button onClick={() => logout()} className="dash-nav-ghost" style={{
          padding: '0 18px', height: '100%', background: 'transparent', border: 'none',
          color: 'rgba(245,242,235,0.4)', cursor: 'pointer',
          fontFamily: "'DM Mono', monospace", fontSize: 9,
          letterSpacing: '0.06em', textTransform: 'uppercase',
        }}>sign out</button>
      </nav>

      {/* ── BODY ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ── LEFT PANEL ── */}
        <div style={{
          width: 320, borderRight: '1px solid rgba(15,15,13,0.1)',
          display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden',
          background: '#f5f2eb',
        }}>

          {/* Submit form */}
          <div style={{
            padding: '18px 18px 16px',
            borderBottom: '1px solid rgba(15,15,13,0.1)', flexShrink: 0,
            background: '#edeae2',
          }}>
            <div style={{
              fontFamily: "'DM Mono', monospace", fontSize: 9,
              color: '#d4a847', letterSpacing: '0.1em',
              textTransform: 'uppercase', marginBottom: 10,
              display: 'flex', alignItems: 'center', gap: 7,
            }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%',
                background: '#d4a847', display: 'inline-block', flexShrink: 0,
              }} />
              submit field report
            </div>

            <textarea
              value={reportText}
              onChange={e => setReportText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) handleSubmit() }}
              placeholder="Paste or type raw field report in any language — Hindi, Bengali, English…"
              rows={5}
              style={{
                width: '100%', border: 'none',
                borderBottom: '1px solid rgba(15,15,13,0.18)',
                background: 'transparent',
                fontFamily: "'DM Sans', sans-serif", fontSize: 13,
                padding: '6px 0', outline: 'none', resize: 'vertical',
                color: '#0f0f0d', lineHeight: 1.6,
              }}
            />

            {submitError && (
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                color: '#e03d25', marginTop: 6,
              }}>{submitError}</div>
            )}
            {submitSuccess && (
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                color: '#2a9d70', marginTop: 6,
              }}>{submitSuccess}</div>
            )}

            <button
              onClick={handleSubmit}
              disabled={submitting || !reportText.trim()}
              className="dash-submit-btn"
              style={{
                marginTop: 12,
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                letterSpacing: '0.07em', textTransform: 'uppercase',
                padding: '10px 0', width: '100%',
                border: `1px solid ${submitting ? 'transparent' : '#0f0f0d'}`,
                background: submitting ? '#0f0f0d' : 'transparent',
                color: submitting ? '#f5f2eb' : '#0f0f0d',
                cursor: submitting || !reportText.trim() ? 'not-allowed' : 'pointer',
                opacity: !reportText.trim() ? 0.35 : 1,
                borderRadius: 2,
              }}
            >
              {submitting ? 'extracting…' : 'extract + create needcard'}
            </button>
          </div>

          {/* Feed header */}
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 9,
            color: '#a8a8a0', letterSpacing: '0.08em',
            textTransform: 'uppercase',
            padding: '10px 18px',
            borderBottom: '1px solid rgba(15,15,13,0.08)',
            flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span className="dash-dot" style={{ width: 6, height: 6 }} />
            need cards · {openCount} open
          </div>

          {/* Feed list */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {sorted.map(card => {
              const col = NEED_COLORS[card.need_type] || '#3a3a36'
              const isSelected = selected?.id === card.id
              return (
                <div
                  key={card.id}
                  onClick={() => setSelected(card)}
                  className="dash-card-row"
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 16px',
                    borderBottom: '1px solid rgba(15,15,13,0.06)',
                    cursor: 'pointer',
                    background: isSelected ? '#edeae2' : 'transparent',
                    borderLeft: isSelected ? `3px solid ${col}` : '3px solid transparent',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 9,
                      color: isSelected ? col : '#a8a8a0',
                      textTransform: 'uppercase', marginBottom: 3,
                      letterSpacing: '0.07em',
                    }}>
                      {card.need_type}
                      {card.needs_review && (
                        <span style={{ marginLeft: 6, color: '#e03d25' }}>· review</span>
                      )}
                      {card.report_count > 1 && (
                        <span style={{ marginLeft: 6, color: '#a8a8a0' }}>· ×{card.report_count}</span>
                      )}
                    </div>
                    <div style={{
                      fontSize: 12, color: '#1a1a18',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      fontFamily: "'DM Sans', sans-serif",
                    }}>{card.description_clean}</div>
                  </div>
                  <div style={{
                    fontFamily: "'Fraunces', Georgia, serif",
                    fontSize: 18, fontWeight: 300,
                    color: urgencyColor(card.urgency_score_eff), flexShrink: 0,
                    lineHeight: 1,
                  }}>
                    {card.urgency_score_eff.toFixed(1)}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#f5f2eb' }}>
          {view === 'map' ? (
            <div ref={mapRef} style={{ flex: 1, background: '#edeae2' }}>
              {!import.meta.env.VITE_GOOGLE_MAPS_KEY && (
                <div style={{
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  height: '100%', gap: 12,
                }}>
                  <div style={{
                    fontFamily: "'Fraunces', Georgia, serif",
                    fontSize: 28, fontWeight: 300, color: '#a8a8a0',
                    letterSpacing: '-0.02em',
                  }}>Map view</div>
                  <div style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 10,
                    color: '#c0bdb6', letterSpacing: '0.06em',
                  }}>set VITE_GOOGLE_MAPS_KEY in .env to enable</div>
                </div>
              )}
            </div>
          ) : selected ? (
            <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px' }}>
              <div style={{ maxWidth: 680, margin: '0 auto' }}>

                {/* Card ID header */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20,
                }}>
                  <span style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 9,
                    color: '#a8a8a0', letterSpacing: '0.07em', textTransform: 'uppercase',
                  }}>
                    {selected.id.slice(0, 8)} · selected needcard
                  </span>
                  <div style={{
                    flex: 1, height: '0.5px', background: 'rgba(15,15,13,0.1)',
                  }} />
                  <span style={{
                    display: 'inline-block',
                    fontFamily: "'DM Mono', monospace", fontSize: 9,
                    background: NEED_COLORS[selected.need_type] || '#3a3a36',
                    color: '#fff', padding: '3px 9px',
                    letterSpacing: '0.09em', textTransform: 'uppercase', borderRadius: 2,
                  }}>{selected.need_type}</span>
                </div>

                <NeedCardComponent
                  card={selected}
                  selected
                  brief={briefs[selected.id]}
                  onGenerateBrief={() => handleGenerateBrief(selected)}
                  briefLoading={briefLoading === selected.id}
                />

                {selected.urgency_reasoning && (
                  <div style={{
                    marginTop: 20,
                    padding: '16px 18px',
                    background: '#edeae2',
                    borderLeft: '3px solid #d4a847',
                    borderRadius: 2,
                  }}>
                    <div style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 9,
                      color: '#d4a847', letterSpacing: '0.08em',
                      textTransform: 'uppercase', marginBottom: 8,
                    }}>urgency reasoning</div>
                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 13, color: '#3a3a36', lineHeight: 1.7,
                    }}>{selected.urgency_reasoning}</p>
                  </div>
                )}

                {selected.geo_confidence > 0.3 && (
                  <div style={{ marginTop: 16 }}>
                    <a
                      href={`https://maps.google.com/?q=${selected.geo_lat},${selected.geo_lng}&zoom=17`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 8,
                        fontFamily: "'DM Mono', monospace", fontSize: 10,
                        color: '#2a9d70', letterSpacing: '0.06em',
                        textTransform: 'uppercase', textDecoration: 'none',
                        padding: '9px 16px',
                        border: '1px solid rgba(42,157,112,0.4)',
                        borderRadius: 2,
                        transition: 'border-color 0.15s',
                      }}
                    >
                      📍 open in google maps →
                    </a>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 12,
            }}>
              <div style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontSize: 32, fontWeight: 300, color: '#c0bdb6',
                letterSpacing: '-0.02em',
              }}>No card selected</div>
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                color: '#c0bdb6', letterSpacing: '0.06em',
              }}>select a need card from the feed →</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
