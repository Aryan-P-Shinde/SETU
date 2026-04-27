/**
 * App.tsx
 *
 * Flow:
 *   /            → LandingPage → DashboardPage
 *   /volunteer   → VolunteerApp
 *
 * Added: page transition animation when entering dashboard from landing.
 */

import { useState, useEffect } from 'react'
import { LandingPage } from './pages/LandingPage'
import { DashboardPage } from './pages/DashboardPage'
import { VolunteerApp } from './pages/VolunteerApp'
import './index.css'

type Screen = 'landing' | 'dashboard' | 'volunteer'

function initialScreen(): Screen {
  if (window.location.pathname.startsWith('/volunteer')) return 'volunteer'
  return 'landing'
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(initialScreen)
  const [transitioning, setTransitioning] = useState(false)
  const [pendingScreen, setPendingScreen] = useState<Screen | null>(null)

  const navigateTo = (target: Screen) => {
    setTransitioning(true)
    setPendingScreen(target)
  }

  useEffect(() => {
    if (!transitioning || !pendingScreen) return
    const t = setTimeout(() => {
      setScreen(pendingScreen)
      setPendingScreen(null)
      setTransitioning(false)
    }, 280)
    return () => clearTimeout(t)
  }, [transitioning, pendingScreen])

  return (
    <>
      <style>{`
        @keyframes fadeOut {
          from { opacity: 1; transform: scale(1); }
          to   { opacity: 0; transform: scale(0.98); }
        }
        @keyframes fadeInScreen {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .screen-enter {
          animation: fadeInScreen 0.35s ease forwards;
        }
        .screen-exit {
          animation: fadeOut 0.28s ease forwards;
          pointer-events: none;
        }
      `}</style>

      <div className={transitioning ? 'screen-exit' : 'screen-enter'}>
        {screen === 'volunteer' && (
          <VolunteerApp onBack={() => navigateTo('landing')} />
        )}
        {screen === 'dashboard' && (
          <DashboardPage onBack={() => navigateTo('landing')} />
        )}
        {screen === 'landing' && (
          <LandingPage
            onEnterDashboard={() => navigateTo('dashboard')}
            onEnterVolunteer={() => navigateTo('volunteer')}
          />
        )}
      </div>
    </>
  )
}
