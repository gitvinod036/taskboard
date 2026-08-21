import { useState } from 'react'

import api from '../services/api'

const successMessage = 'If an account exists for this email, password reset instructions have been sent.'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccess('')
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Enter a valid email address.')
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/password-reset/', { email: email.trim() })
      setSuccess(successMessage)
    } catch (requestError) {
      setError(requestError.response?.data?.email?.[0] || 'We could not process that request. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return <main className="auth-shell"><section className="auth-panel" aria-labelledby="forgot-title"><p className="eyebrow">TaskBoard</p><h1 id="forgot-title">Forgot your password?</h1><p className="auth-description">Enter your email address.</p><form onSubmit={handleSubmit} noValidate><label htmlFor="reset-email">Email<input id="reset-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" /></label>{error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}<button type="submit" disabled={loading || !email.trim()} aria-busy={loading}>{loading ? 'Sending...' : 'Send reset link'}</button></form><p className="auth-footer"><a href="/login">Back to sign in</a></p></section></main>
}