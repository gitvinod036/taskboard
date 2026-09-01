import axios from 'axios'

// The env var is the single source of truth (set in frontend/.env, baked at
// build time for production). The fallback only covers local development
// when the variable is missing — e.g. a dev server started before .env
// existed or after it was edited without restarting Vite, which silently
// leaves baseURL undefined and makes every API call fail in the browser.
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('taskflow_token')
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) localStorage.removeItem('taskflow_token')
    return Promise.reject(error)
  },
)

export default api
