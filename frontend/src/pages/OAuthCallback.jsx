import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'

export default function OAuthCallback() {
  const { loginWithGoogle } = useAuth()
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const oauthError = params.get('oauth_error')
    if (oauthError || !code) {
      setError(oauthError || 'Google login could not be completed.')
      return
    }
    loginWithGoogle(code)
      .then(() => window.location.replace('/dashboard'))
      .catch(() => setError('Google login could not be completed.'))
  }, [])

  return <main className="auth-shell"><section className="auth-panel" aria-labelledby="oauth-title"><p className="eyebrow">TaskBoard</p><h1 id="oauth-title">Signing you in</h1>{error ? <><p className="form-error" role="alert">{error}</p><a className="auth-primary-link" href="/login">Back to sign in</a></> : <p className="auth-description">Completing Google authentication...</p>}</section></main>
}