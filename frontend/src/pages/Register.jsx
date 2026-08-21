import { useState } from 'react'

import { AuthForm } from './Login'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { register } = useAuth()
  const [form, setForm] = useState({ username: '', email: '', password: '', password_confirm: '' })
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    try {
      await register(form)
    } catch (requestError) {
      const data = requestError.response?.data || {}
      const validationMessage = data.detail || data.password_confirm?.[0] || data.password?.[0] || data.username?.[0] || data.email?.[0]
      setError(validationMessage || requestError.message || 'Unable to create your account.')
      return
    }
    window.location.replace('/dashboard')
  }

  return <AuthForm title="Create your account" submitLabel="Register" form={form} setForm={setForm} error={error} onSubmit={handleSubmit} footer="Already registered?" link="/login" linkLabel="Sign in" includeConfirmation />
}