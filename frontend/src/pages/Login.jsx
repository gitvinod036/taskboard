import { useState } from 'react'

import { useAuth } from '../context/AuthContext'
import { ThemeToggle } from '../theme'

export default function Login() {
  const { login } = useAuth()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    try {
      await login(form)
      window.location.replace('/dashboard')
    } catch (requestError) {
      setError(requestError.response?.data?.non_field_errors?.[0] || 'Unable to sign in with those details.')
    }
  }

  return (
    <>
      <div className="auth-theme-slot">
        <ThemeToggle />
      </div>
      <AuthForm title="Welcome back" submitLabel="Sign in" form={form} setForm={setForm} error={error} onSubmit={handleSubmit} footer="Need an account?" link="/register" linkLabel="Register" />
    </>
  )
}

function AuthForm({ title, submitLabel, form, setForm, error, onSubmit, footer, link, linkLabel, includeConfirmation = false }) {
  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <p className="eyebrow">TaskBoard</p>
        <h1 id="auth-title">{title}</h1>
        <form onSubmit={onSubmit} noValidate>
          <label htmlFor="auth-username">Username<input id="auth-username" required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} autoComplete="username" /></label>
          {includeConfirmation && <label htmlFor="auth-email">Email<input id="auth-email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} autoComplete="email" /></label>}
          <label htmlFor="auth-password">Password<input id="auth-password" required type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} autoComplete={includeConfirmation ? 'new-password' : 'current-password'} /></label>
          {!includeConfirmation && <a className="auth-secondary-link" href="/forgot-password">Forgot password?</a>}
          {includeConfirmation && <label htmlFor="auth-confirm-password">Confirm password<input id="auth-confirm-password" required type="password" value={form.password_confirm} onChange={(event) => setForm({ ...form, password_confirm: event.target.value })} autoComplete="new-password" /></label>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" disabled={form.username.length === 0 || form.password.length === 0}>{submitLabel}</button>
        </form>
        {!includeConfirmation && <><div className="auth-divider"><span>OR</span></div><a className="google-login-button" href={`${import.meta.env.VITE_API_BASE_URL}/auth/google/`}><span aria-hidden="true">G</span>Continue with Google</a></>}
        <p className="auth-footer">{footer} <a href={link}>{linkLabel}</a></p>
      </section>
    </main>
  )
}

export { AuthForm }