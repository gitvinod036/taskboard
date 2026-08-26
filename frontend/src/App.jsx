import { lazy, Suspense } from 'react'

import { AuthProvider } from './context/AuthContext'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Register from './pages/Register'
import TaskBoard from './pages/TaskBoard'
import MyTasks from './pages/MyTasks'
import AdminAssignments from './pages/AdminAssignments'
import AdminCodingProblemEdit from './pages/AdminCodingProblemEdit'
import AdminCodingProblems from './pages/AdminCodingProblems'
import AdminCodingSubmissions from './pages/AdminCodingSubmissions'
import AdminSubmissions from './pages/AdminSubmissions'
import AdminUsers from './pages/AdminUsers'
import CodingProblemDetails from './pages/CodingProblemDetails'
import CodingProblems from './pages/CodingProblems'
import ProtectedRoute from './routes/ProtectedRoute'
import SessionLoader from './components/SessionLoader'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import OAuthCallback from './pages/OAuthCallback'

// Code-split pages: Monaco (coding workspace) and admin analytics are heavy,
// so they are fetched only when their route opens.
const AdminMonitoring = lazy(() => import('./pages/AdminMonitoring'))
const CodingWorkspace = lazy(() => import('./pages/CodingWorkspace'))

function App() {
  const path = window.location.pathname
  const resetMatch = path.match(/^\/reset-password\/([^/]+)\/([^/]+)\/?$/)
  const codingEditMatch = path.match(/^\/admin\/coding\/problems\/([^/]+)\/?$/)
  const codingSolveMatch = path.match(/^\/coding\/problems\/([^/]+)\/solve\/?$/)
  const codingDetailMatch = path.match(/^\/coding\/problems\/([^/]+)\/?$/)
  const page = path === '/register'
    ? <Register />
    : path === '/forgot-password'
      ? <ForgotPassword />
    : path === '/oauth/callback'
      ? <OAuthCallback />
    : resetMatch
      ? <ResetPassword uid={resetMatch[1]} token={resetMatch[2]} />
    : path === '/coding/problems'
      ? <ProtectedRoute><CodingProblems /></ProtectedRoute>
    : codingSolveMatch
      ? <ProtectedRoute><Suspense fallback={<SessionLoader />}><CodingWorkspace problemId={codingSolveMatch[1]} /></Suspense></ProtectedRoute>
    : codingDetailMatch
      ? <ProtectedRoute><CodingProblemDetails problemId={codingDetailMatch[1]} /></ProtectedRoute>
    : path === '/admin/coding/problems'
      ? <ProtectedRoute adminOnly><AdminCodingProblems /></ProtectedRoute>
    : codingEditMatch
      ? <ProtectedRoute adminOnly><AdminCodingProblemEdit problemId={codingEditMatch[1]} /></ProtectedRoute>
    : path === '/admin/coding/submissions'
      ? <ProtectedRoute adminOnly><AdminCodingSubmissions /></ProtectedRoute>
    : path === '/admin/users'
      ? <ProtectedRoute adminOnly><AdminUsers /></ProtectedRoute>
    : path === '/admin/assignments'
      ? <ProtectedRoute adminOnly><AdminAssignments /></ProtectedRoute>
    : path === '/admin/submissions'
      ? <ProtectedRoute adminOnly><AdminSubmissions /></ProtectedRoute>
    : path === '/admin/monitoring'
      ? <ProtectedRoute adminOnly><Suspense fallback={<SessionLoader />}><AdminMonitoring /></Suspense></ProtectedRoute>
    : path === '/dashboard'
      ? <ProtectedRoute><Dashboard /></ProtectedRoute>
    : path === '/tasks'
      ? <ProtectedRoute><TaskBoard /></ProtectedRoute>
    : path === '/my-tasks'
      ? <ProtectedRoute><MyTasks /></ProtectedRoute>
    : <Login />

  return <AuthProvider>{page}</AuthProvider>
}

export default App
