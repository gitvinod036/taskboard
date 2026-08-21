import { useAuth } from '../context/AuthContext'
import SessionLoader from '../components/SessionLoader'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, isAdmin } = useAuth()

  if (loading) return <SessionLoader />
  if (!user) {
    window.location.replace('/login')
    return null
  }
  if (adminOnly && !isAdmin) {
    window.location.replace('/dashboard')
    return null
  }
  return children
}