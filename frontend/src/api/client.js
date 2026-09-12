import axios from 'axios'


const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
const api = axios.create({
  baseURL,
  timeout: 15000,
})
const refreshClient = axios.create({ baseURL, timeout: 15000 })
let refreshPromise = null

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function clearStoredSession() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) throw new Error('登录状态已失效')
  const response = await refreshClient.post('/auth/refresh', null, {
    headers: { Authorization: `Bearer ${refreshToken}` },
  })
  const session = response.data.data
  localStorage.setItem('access_token', session.access_token)
  localStorage.setItem('refresh_token', session.refresh_token)
  return session.access_token
}

api.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const original = error.config
    const isAuthEndpoint = ['/auth/login', '/auth/register', '/auth/refresh'].some((path) =>
      String(original?.url || '').includes(path),
    )
    if (
      error.response?.status === 401
      && original
      && !original._retry
      && !original.skipAuthRefresh
      && !isAuthEndpoint
      && localStorage.getItem('refresh_token')
    ) {
      original._retry = true
      try {
        refreshPromise ||= refreshAccessToken().finally(() => {
          refreshPromise = null
        })
        const accessToken = await refreshPromise
        original.headers.Authorization = `Bearer ${accessToken}`
        return api(original)
      } catch {
        clearStoredSession()
      }
    }
    if (!error.response) {
      const message = error.code === 'ECONNABORTED'
        ? '请求超时，请检查网络后重试'
        : '网络连接失败，请检查网络或服务状态'
      return Promise.reject({ message })
    }
    return Promise.reject(error.response?.data || error)
  },
)

export default api
