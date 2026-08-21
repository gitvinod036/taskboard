import { useState } from 'react'

import api from '../services/api'

export default function ResetPassword({ uid, token }) {
  const [form, setForm] = useState({ new_password: '', new_password_confirm: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    if (form.new_password !== form.new_password_confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/password-reset-confirm/', { uid, token, ...form })
      setSuccess(true)
    } catch (requestError) {
      const data = requestError.response?.data || {}
      setError(data.token?.[0] || data.new_password_confirm?.[0] || data.new_password?.[0] || 'This password reset link is invalid or expired.')
    } finally {
      setLoading(false)
    }
  }

  return <main className="auth-shell"><section className="auth-panel" aria-labelledby="reset-title"><p className="eyebrow">TaskBoard</p>{success ? <><h1 id="reset-title">Password reset successfully.</h1><p className="auth-description">You can now sign in with your new password.</p><a className="auth-primary-link" href="/login">Sign in</a></> : <><h1 id="reset-title">Reset your password</h1><form onSubmit={handleSubmit} noValidate><label htmlFor="new-password">New password<input id="new-password" required type="password" value={form.new_password} onChange={(event) => setForm({ ...form, new_password: event.target.value })} autoComplete="new-password" /></label><label htmlFor="confirm-password">Confirm password<input id="confirm-password" required type="password" value={form.new_password_confirm} onChange={(event) => setForm({ ...form, new_password_confirm: event.target.value })} autoComplete="new-password" /></label>{error && <p className="form-error" role="alert">{error}</p>}<button type="submit" disabled={loading || !form.new_password || !form.new_password_confirm} aria-busy={loading}>{loading ? 'Resetting...' : 'Reset password'}</button></form></>}</section></main>
}