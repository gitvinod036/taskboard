import { createContext, useContext, useEffect, useState } from 'react'
import api from '../services/api'

const TOKEN_KEY = 'taskflow_token'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setLoading(false)
      return
    }

    api.get('/auth/me/')
      .then(({ data }) => setUser(data))
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  async function authenticate(endpoint, credentials) {
    const { data } = await api.post(endpoint, credentials)

    if (!data?.token || !data?.user) {
      throw new Error(
        'Authentication response did not include a token and user.'
      )
    }

    localStorage.setItem(TOKEN_KEY, data.token)
    setUser(data.user)

    return data.user
  }

  async function authenticateGoogle(code) {
    return authenticate('/auth/google/exchange/', { code })
  }

  async function logoutUser() {
    try {
      await api.post('/auth/logout/')
    } finally {
      localStorage.removeItem(TOKEN_KEY)
      setUser(null)
    }
  }

  const value = {
    user,
    loading,
    isAdmin: user?.role === 'ADMIN',

    login: (credentials) =>
      authenticate('/auth/login/', credentials),

    register: (credentials) =>
      authenticate('/auth/register/', credentials),

    loginWithGoogle: authenticateGoogle,

    logout: logoutUser,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}