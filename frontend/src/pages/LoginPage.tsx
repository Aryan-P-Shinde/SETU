import { useState } from 'react'
import { login } from '../lib/firebase'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      onLogin()
    } catch {
      setError('Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--paper)', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <div style={{ borderTop: '2px solid var(--ink)', borderBottom: '1px solid var(--rule)', padding: '10px 48px', fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.08em', display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontWeight: 500 }}>SETU</span>
        <span style={{ color: 'var(--ink4)' }}>disaster response coordination</span>
      </div>

      {/* Login form */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 360 }}>
          <h1 style={{ fontFamily: 'var(--serif)', fontSize: 28, fontWeight: 300, letterSpacing: '-0.02em', marginBottom: 4 }}>
            NGO admin login
          </h1>
          <p style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink4)', letterSpacing: '0.06em', marginBottom: 32, textTransform: 'uppercase' }}>
            Authorised personnel only
          </p>

          <form onSubmit={submit}>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>email</div>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                style={{ width: '100%', border: 'none', borderBottom: '1px solid var(--rule-s)', background: 'transparent', fontFamily: 'var(--sans)', fontSize: 14, padding: '8px 0', outline: 'none', color: 'var(--ink)' }}
              />
            </div>

            <div style={{ marginBottom: 28 }}>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>password</div>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                style={{ width: '100%', border: 'none', borderBottom: '1px solid var(--rule-s)', background: 'transparent', fontFamily: 'var(--sans)', fontSize: 14, padding: '8px 0', outline: 'none', color: 'var(--ink)' }}
              />
            </div>

            {error && (
              <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--accent)', marginBottom: 16 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', padding: '10px 24px', border: '1px solid var(--ink)', background: loading ? 'var(--ink)' : 'transparent', color: loading ? 'var(--paper)' : 'var(--ink)', cursor: 'pointer', transition: 'all 0.15s', width: '100%' }}
            >
              {loading ? 'signing in…' : 'sign in'}
            </button>
          </form>

          {/* Demo shortcut */}
          <button
            onClick={() => { setEmail('demo@setu.org'); setPassword('demo1234') }}
            style={{ marginTop: 16, fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink4)', background: 'transparent', border: 'none', cursor: 'pointer', letterSpacing: '0.06em', textDecoration: 'underline' }}
          >
            use demo credentials
          </button>
        </div>
      </div>
    </div>
  )
}