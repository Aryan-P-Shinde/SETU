/**
 * App.tsx
 *
 * Flow:
 *   /            → LandingPage → DashboardPage
 *   /volunteer   → VolunteerApp
 *
 * Auth bypassed for Phase 1 demo. Firebase code kept in firebase.ts
 * for when you want to re-enable it.
 */

import { useState } from 'react'
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

  if (screen === 'volunteer') {
    return <VolunteerApp onBack={() => setScreen('landing')} />
  }

  if (screen === 'dashboard') {
    return <DashboardPage onBack={() => setScreen('landing')} />
  }

  return (
    <LandingPage
      onEnterDashboard={() => setScreen('dashboard')}
      onEnterVolunteer={() => setScreen('volunteer')}
    />
  )
}
