import { AuthProvider } from './context/AuthContext'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Register from './pages/Register'
import TaskBoard from './pages/TaskBoard'
import AdminAssignments from './pages/AdminAssignments'
import AdminSubmissions from './pages/AdminSubmissions'
import AdminUsers from './pages/AdminUsers'
import ProtectedRoute from './routes/ProtectedRoute'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import OAuthCallback from './pages/OAuthCallback'

function App() {
  const path = window.location.pathname
  const resetMatch = path.match(/^\/reset-password\/([^/]+)\/([^/]+)\/?$/)
  const page = path === '/register'
    ? <Register />
    : path === '/forgot-password'
      ? <ForgotPassword />
      : path === '/oauth/callback'
        ? <OAuthCallback />
      : resetMatch
        ? <ResetPassword uid={resetMatch[1]} token={resetMatch[2]} />
    : path === '/admin/users'
      ? <ProtectedRoute adminOnly><AdminUsers /></ProtectedRoute>
      : path === '/admin/assignments'
        ? <ProtectedRoute adminOnly><AdminAssignments /></ProtectedRoute>
      : path === '/admin/submissions'
        ? <ProtectedRoute adminOnly><AdminSubmissions /></ProtectedRoute>
      : path === '/dashboard'
        ? <ProtectedRoute><Dashboard /></ProtectedRoute>
        : path === '/tasks'
      ? <ProtectedRoute><TaskBoard /></ProtectedRoute>
      : <Login />

  return <AuthProvider>{page}</AuthProvider>
}

export default App
