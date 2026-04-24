/**
 * LandingPage.tsx — SETU
 * Rebuilt: big, alive, human. Photos. Real colour. Not skinny.
 */

import { useState, useEffect } from 'react'

import heroImg from '../assets/hero.jpg'
import section1Img from '../assets/section1.jpg'
import section2Img from '../assets/section2.jpg'


const NEED_COLORS: Record<string, string> = {
  rescue:    '#e03d25',
  medical:   '#e03d25',
  food:      '#b97200',
  water:     '#1a6bbf',
  shelter:   '#5b4fd4',
  logistics: '#3a3a36',
}

const SAMPLE_CARDS = [
  { type: 'rescue',  urgency: 9.2, desc: 'Three people trapped on rooftop at 45 MG Road. No food or water for 8 hours.', loc: 'Ward 3, Kolkata', time: '14 min ago' },
  { type: 'medical', urgency: 9.6, desc: 'Pregnant woman in labour, hospital road blocked by flooding. No doctor on site.', loc: 'Andheri East crossing', time: '2 min ago' },
  { type: 'water',   urgency: 7.8, desc: 'Drinking water contaminated. 55 people affected, children showing symptoms.', loc: 'Mirpur Block D', time: '31 min ago' },
  { type: 'food',    urgency: 6.9, desc: '40 families with no food for 2 days. Children and elderly badly affected.', loc: 'Ward 12, Shyamnagar', time: '1 hr ago' },
]

const TICKER = [
  'Processing voice note from Sylhet field worker...',
  'NeedCard #308 dispatched — volunteer en route',
  'Translating Hindi report from Patna district...',
  'Urgency updated: shelter in Assam → 8.1',
  'WhatsApp brief sent to Aarav S. (2.3 km away)',
  'New image intake: handwritten form, West Bengal',
]

const PIPELINE = [
  { step: '01', ch: 'RECEIVE',    desc: 'Voice notes, photos, WhatsApp messages — any language, any format' },
  { step: '02', ch: 'UNDERSTAND', desc: 'Whisper transcribes audio. Gemini Vision reads handwritten forms.' },
  { step: '03', ch: 'STRUCTURE',  desc: 'AI extracts need type, urgency score, location, contact details' },
  { step: '04', ch: 'PRIORITISE', desc: 'NeedCards ranked, deduped, and mapped across the disaster zone' },
  { step: '05', ch: 'DISPATCH',   desc: 'Nearest volunteer gets a WhatsApp brief in 30 seconds' },
  { step: '06', ch: 'CLOSE',      desc: 'Card marked resolved. Coordinator sees live status across all needs' },
]

const HERO_IMAGE = heroImg
const SECTION_IMAGE_1 = section1Img
const SECTION_IMAGE_2 = section2Img

export function LandingPage({ onEnterDashboard, onEnterVolunteer }: {
  onEnterDashboard: () => void
  onEnterVolunteer: () => void
}) {
  const [tickerIdx, setTickerIdx] = useState(0)
  const [hoveredCard, setHoveredCard] = useState<number | null>(null)

  useEffect(() => {
    const t = setInterval(() => setTickerIdx(i => (i + 1) % TICKER.length), 3000)
    return () => clearInterval(t)
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: '#f5f2eb', color: '#0f0f0d', fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,700;1,9..144,300;1,9..144,400&family=DM+Sans:wght@300;400;500;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }

        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(22px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.35; transform: scale(0.65); }
        }
        @keyframes tickIn {
          from { opacity: 0; transform: translateY(7px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        .fu  { animation: fadeUp 0.6s ease forwards; opacity: 0; }
        .fu1 { animation-delay: 0.05s }
        .fu2 { animation-delay: 0.18s }
        .fu3 { animation-delay: 0.32s }
        .fu4 { animation-delay: 0.46s }

        .dot {
          display: inline-block; width: 8px; height: 8px; border-radius: 50%;
          background: #e03d25; animation: pulseDot 1.5s ease-in-out infinite;
          flex-shrink: 0;
        }
        .tick { animation: tickIn 0.35s ease forwards; }

        .nav-btn { transition: opacity 0.15s; }
        .nav-btn:hover { opacity: 0.7; }

        .card-item { transition: transform 0.18s, box-shadow 0.18s; cursor: pointer; }
        .card-item:hover { transform: translateY(-4px); box-shadow: 0 10px 36px rgba(0,0,0,0.13); }

        .pipe-step { transition: background 0.15s, color 0.15s; }
        .pipe-step:hover { background: #0f0f0d !important; }
        .pipe-step:hover .pipe-lbl { color: #d4a847 !important; }
        .pipe-step:hover .pipe-dsc { color: rgba(245,242,235,0.65) !important; }

        .btn-gold { transition: filter 0.15s; }
        .btn-gold:hover { filter: brightness(1.08); }
        .btn-ghost { transition: background 0.15s; }
        .btn-ghost:hover { background: rgba(255,255,255,0.12) !important; }
      `}</style>

      {/* ── NAV ── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: '#0f0f0d', color: '#f5f2eb',
        display: 'flex', alignItems: 'center',
        padding: '0 32px', height: 56,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}>
        <div style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em',
          color: '#f5f2eb', marginRight: 28,
        }}>SETU</div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, flex: 1,
          fontFamily: "'DM Mono', monospace", fontSize: 11,
          color: 'rgba(245,242,235,0.45)', overflow: 'hidden',
        }}>
          <span className="dot" />
          <span key={tickerIdx} className="tick" style={{ whiteSpace: 'nowrap' }}>
            {TICKER[tickerIdx]}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button className="nav-btn" onClick={onEnterVolunteer} style={{
            padding: '8px 18px', border: '1px solid rgba(255,255,255,0.2)',
            background: 'transparent', color: 'rgba(245,242,235,0.8)',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            letterSpacing: '0.07em', textTransform: 'uppercase', cursor: 'pointer',
            borderRadius: 2,
          }}>Volunteer →</button>
          <button className="nav-btn btn-gold" onClick={onEnterDashboard} style={{
            padding: '8px 18px', border: 'none',
            background: '#d4a847', color: '#0f0f0d',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            letterSpacing: '0.07em', textTransform: 'uppercase',
            cursor: 'pointer', borderRadius: 2, fontWeight: 600,
          }}>NGO Dashboard →</button>
        </div>
      </nav>

      {/* ── HERO ── full bleed */}
      <div style={{ position: 'relative', height: '91vh', minHeight: 560, overflow: 'hidden' }}>
        <img src={HERO_IMAGE} alt="Flood rescue"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.42)' }}
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
        {/* Fallback gradient */}
        {/* <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, #1a2a3a 0%, #0a120a 100%)' }} /> */}
        {/* Vignette */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.15) 55%, transparent 100%)' }} />

        {/* Hero text — bottom left */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          padding: '0 52px 60px', maxWidth: 1100,
        }}>
          <div className="fu fu1" style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: '#d4a847', color: '#0f0f0d',
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            letterSpacing: '0.1em', textTransform: 'uppercase',
            padding: '5px 12px', marginBottom: 28, fontWeight: 600,
            borderRadius: 2,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#0f0f0d', display: 'inline-block' }} />
            SETU - Smart Extraction <em style={{textTransform: 'lowercase' }}>for</em> Task Utilization
          </div>

          <h1 className="fu fu2" style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 'clamp(46px, 7.5vw, 86px)',
            fontWeight: 300, lineHeight: 1.04, letterSpacing: '-0.025em',
            color: '#ffffff', marginBottom: 28, maxWidth: 800,
          }}>
            When the flood hits,<br />
            <em style={{ fontStyle: 'italic', fontWeight: 'bold' , color: '#e4b247' }}>every minute</em>{' '}
            is someone's life.
          </h1>

          <p className="fu fu3" style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 18, lineHeight: 1.75, fontWeight: 300,
            color: 'rgba(255,255,255,0.72)', maxWidth: 720, marginBottom: 40,
          }}>
            SETU — <em style={{fontStyle: 'italic'}}>Sanskrit for bridge </em> — exists because in 2023, help was 2 kilometers away from people who needed it, and nobody knew.
                  Hundreds of voices, messages, papers. One desperate ask, help.
                  SETU turns that chaos into a name, a location, and a volunteer — before it's too late.


          </p>

          <div className="fu fu4" style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <button className="btn-gold" onClick={onEnterDashboard} style={{
              padding: '16px 38px', background: '#f5f2eb', color: '#0f0f0d',
              border: 'none', cursor: 'pointer',
              fontFamily: "'DM Mono', monospace", fontSize: 12,
              letterSpacing: '0.07em', textTransform: 'uppercase',
              borderRadius: 2, fontWeight: 500,
            }}>Open NGO Dashboard</button>
            <button className="btn-ghost" onClick={onEnterVolunteer} style={{
              padding: '16px 38px', background: 'transparent',
              color: 'rgba(255,255,255,0.8)',
              border: '1px solid rgba(255,255,255,0.32)', cursor: 'pointer',
              fontFamily: "'DM Mono', monospace", fontSize: 12,
              letterSpacing: '0.07em', textTransform: 'uppercase', borderRadius: 2,
            }}>Volunteer View</button>
          </div>
        </div>

        {/* Stats — bottom right */}
        <div style={{
          position: 'absolute', bottom: 60, right: 52,
          display: 'flex', flexDirection: 'column', gap: 22, alignItems: 'flex-end',
        }}>
          {[{ n: '31', l: 'volunteers ready' }, { n: '9.8', l: 'highest urgency' }, { n: '50', l: 'open needs' }].map(s => (
            <div key={s.n} style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 40, fontWeight: 300, color: '#fff', lineHeight: 1 }}>{s.n}</div>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginTop: 5 }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── QUOTE STRIP ── */}
      <div style={{ background: '#d4a847', padding: '36px 52px', display: 'flex', alignItems: 'center', gap: 48 }}>
        <div style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 22, fontStyle: 'italic', fontWeight: 300,
          color: '#0f0f0d', lineHeight: 1.55, flex: 1, maxWidth: 700,
        }}>
          "Do your little bit of good where you are; it’s those little bits of 
          good put together that overwhelm the world."
        </div>
        <div style={{
          fontFamily: "'DM Mono', monospace", fontSize: 10,
          color: 'rgba(15,15,13,0.5)', letterSpacing: '0.06em',
          textTransform: 'uppercase', lineHeight: 1.8, flexShrink: 0,
        }}>
          — Desmond Tutu  
        </div>
      </div>

      {/* ── LIVE NEED CARDS ── */}
      <div style={{ padding: '80px 52px', background: '#f5f2eb' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 44 }}>
            <div>
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                color: '#999', letterSpacing: '0.1em', textTransform: 'uppercase',
                marginBottom: 14, display: 'flex', alignItems: 'center', gap: 9,
              }}>
                <span className="dot" style={{ width: 7, height: 7 }} />
                Live need cards · sorted by urgency
              </div>
              <h2 style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontSize: 'clamp(32px, 4.5vw, 52px)', fontWeight: 300,
                color: '#0f0f0d', lineHeight: 1.1, letterSpacing: '-0.02em',
              }}>
                Real needs. Real people.<br />
                <em style={{ color: '#aaa', fontStyle: 'italic' }}>Right now.</em>
              </h2>
            </div>
            <button onClick={onEnterDashboard} style={{
              fontFamily: "'DM Mono', monospace", fontSize: 10,
              color: '#0f0f0d', background: 'transparent',
              border: '1px solid #ccc', padding: '11px 22px',
              cursor: 'pointer', letterSpacing: '0.06em',
              textTransform: 'uppercase', borderRadius: 2,
            }}>View all 50 →</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
            {SAMPLE_CARDS.map((card, i) => {
              const col = NEED_COLORS[card.type]
              return (
                <div
                  key={i}
                  className="card-item"
                  onClick={onEnterDashboard}
                  onMouseEnter={() => setHoveredCard(i)}
                  onMouseLeave={() => setHoveredCard(null)}
                  style={{
                    background: '#fff', borderRadius: 4,
                    overflow: 'hidden', borderTop: `5px solid ${col}`,
                    boxShadow: '0 2px 14px rgba(0,0,0,0.07)',
                  }}
                >
                  <div style={{ padding: '24px 26px 26px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{
                          fontFamily: "'DM Mono', monospace", fontSize: 9,
                          color: '#fff', background: col,
                          padding: '3px 9px', letterSpacing: '0.09em',
                          textTransform: 'uppercase', borderRadius: 2,
                        }}>{card.type}</span>
                        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#bbb' }}>{card.time}</span>
                      </div>
                      <span style={{
                        fontFamily: "'Fraunces', Georgia, serif",
                        fontSize: 30, fontWeight: 700, color: col, lineHeight: 1,
                      }}>{card.urgency.toFixed(1)}</span>
                    </div>

                    <div style={{ height: 3, background: '#f0ede6', borderRadius: 2, marginBottom: 18 }}>
                      <div style={{ height: '100%', width: `${(card.urgency / 10) * 100}%`, background: col, borderRadius: 2 }} />
                    </div>

                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 15, fontWeight: 400, lineHeight: 1.65,
                      color: '#1a1a18', marginBottom: 16,
                    }}>{card.desc}</p>

                    <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: '#aaa' }}>
                      📍 {card.loc}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── PROBLEM SECTION — dark + photo ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: 520 , alignItems: 'stretch' }}>
        <div style={{
          background: '#0f0f0d', padding: '80px 52px',
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
        }}>
          <div style={{
            fontFamily: "'DM Mono', monospace", fontSize: 10,
            color: '#d4a847', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 24,
          }}>Why we built this</div>

          <h2 style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 'clamp(26px, 3.2vw, 42px)', fontWeight: 300,
            lineHeight: 1.2, letterSpacing: '-0.02em',
            color: '#f5f2eb', marginBottom: 24,
          }}>
            During the 2023 Sikkim floods,<br />
            <em style={{ color: 'rgba(245,242,235,0.4)' }}>no one knew who needed help first.</em>
          </h2>

          <p style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 15, lineHeight: 1.85, fontWeight: 300,
            color: 'rgba(245,242,235,0.55)', marginBottom: 48,
          }}>
            NGO coordinators received hundreds of reports across WhatsApp,
            phone calls, and handwritten slips — in three different languages —
            with no way to triage them. People waited hours for help that
            was already nearby. The technology existed. Nobody had connected it yet.
          </p>

          <div style={{ display: 'flex', gap: 40 }}>
            {[
              { n: '3–6 hrs', l: 'avg delay, report to dispatch' },
              { n: '40%', l: 'reports are duplicates' },
              { n: '7+', l: 'languages in one zone' },
            ].map(s => (
              <div key={s.n}>
                <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 30, fontWeight: 300, color: '#f5f2eb', lineHeight: 1 }}>{s.n}</div>
                <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 8, color: 'rgba(245,242,235,0.3)', letterSpacing: '0.05em', textTransform: 'uppercase', marginTop: 7, lineHeight: 1.5 }}>{s.l}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ position: 'relative', overflow: 'hidden', minHeight: 400 }}>
          <img src={SECTION_IMAGE_1} alt="Disaster relief volunteers"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.32)' }}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          {/* <div style={{ position: 'absolute', inset: 0, background: '#1c2a1c' }} /> */}
        </div>
      </div>

      {/* ── HOW IT WORKS ── */}
      <div style={{ padding: '80px 52px', background: '#edeae2' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ marginBottom: 52 }}>
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: '#999', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 18 }}>
              How it works
            </div>
            <h2 style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 'clamp(30px, 4vw, 50px)', fontWeight: 300,
              color: '#0f0f0d', lineHeight: 1.1, letterSpacing: '-0.02em',
            }}>
              From chaotic report<br />
              <em style={{ color: '#aaa' }}>to dispatched volunteer</em>
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 3 }}>
            {PIPELINE.map((s, i) => (
              <div key={i} className="pipe-step" style={{ padding: '32px 28px', background: '#f5f2eb' }}>
                <div style={{ marginBottom: 18, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: '#ccc', letterSpacing: '0.06em' }}>{s.step}</span>
                  <span className="pipe-lbl" style={{
                    fontFamily: "'DM Mono', monospace", fontSize: 10,
                    color: '#0f0f0d', letterSpacing: '0.08em', textTransform: 'uppercase',
                    fontWeight: 500, transition: 'color 0.15s',
                  }}>{s.ch}</span>
                </div>
                <p className="pipe-dsc" style={{
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 14, lineHeight: 1.72, color: '#666',
                  transition: 'color 0.15s',
                }}>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── FINAL CTA — photo bg ── */}
      <div style={{ position: 'relative', overflow: 'hidden', minHeight: 440, display: 'flex', alignItems: 'center' }}>
        <img src={SECTION_IMAGE_2} alt="Community aid"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.32)' }}
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0.2) 70%, transparent 100%)' }} />

        <div style={{ position: 'relative', padding: '80px 52px', maxWidth: 720 }}>
          <h2 style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 'clamp(30px, 4.5vw, 56px)', fontWeight: 300,
            color: '#fff', lineHeight: 1.12, letterSpacing: '-0.02em', marginBottom: 28,
          }}>
            Built by students who believe<br />
            <em style={{ color: '#d4a847' }}>technology should reach people first.</em>
          </h2>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <button className="btn-gold" onClick={onEnterDashboard} style={{
              padding: '16px 34px', background: '#d4a847', color: '#0f0f0d',
              border: 'none', cursor: 'pointer',
              fontFamily: "'DM Mono', monospace", fontSize: 11,
              letterSpacing: '0.07em', textTransform: 'uppercase',
              borderRadius: 2, fontWeight: 600,
            }}>Open NGO Dashboard →</button>
            <button className="btn-ghost" onClick={onEnterVolunteer} style={{
              padding: '16px 34px', background: 'transparent',
              color: 'rgba(255,255,255,0.8)',
              border: '1px solid rgba(255,255,255,0.38)', cursor: 'pointer',
              fontFamily: "'DM Mono', monospace", fontSize: 11,
              letterSpacing: '0.07em', textTransform: 'uppercase', borderRadius: 2,
            }}>Volunteer View →</button>
          </div>
        </div>
      </div>

      {/* ── FOOTER ── */}
      <div style={{
        background: '#0f0f0d', padding: '28px 52px',
        display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap',
      }}>
        <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 18, fontWeight: 300, color: '#f5f2eb' }}>SETU</div>
        <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: 'rgba(245,242,235,0.28)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          disaster relief coordination
        </div>
        <div style={{ display: 'flex', gap: 24, marginLeft: 16, flexWrap: 'wrap' }}>
          {['Gemini 1.5 Pro', 'Whisper', 'FastAPI', 'Cloud Run', 'Firestore', 'React'].map(t => (
            <div key={t} style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: 'rgba(245,242,235,0.28)', letterSpacing: '0.04em' }}>{t}</div>
          ))}
        </div>
      </div>

    </div>
  )
}
