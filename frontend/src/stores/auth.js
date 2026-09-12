import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import api from '../api/client'


export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const accessToken = ref(localStorage.getItem('access_token'))
  const isAuthenticated = computed(() => Boolean(accessToken.value))

  function setSession(payload) {
    user.value = payload.user
    accessToken.value = payload.access_token
    localStorage.setItem('access_token', payload.access_token)
    if (payload.refresh_token) {
      localStorage.setItem('refresh_token', payload.refresh_token)
    }
  }

  function updateUser(payload) {
    user.value = payload
  }

  async function login(credentials) {
    const response = await api.post('/auth/login', credentials)
    setSession(response.data)
    return response.data.user
  }

  async function register(form) {
    const response = await api.post('/auth/register', form)
    setSession(response.data)
    return response.data.user
  }

  async function restoreUser() {
    if (!accessToken.value || user.value) return user.value
    try {
      const response = await api.get('/users/me')
      accessToken.value = localStorage.getItem('access_token')
      user.value = response.data
      return user.value
    } catch (error) {
      clearSession()
      throw error
    }
  }

  async function logout() {
    try {
      const storedAccessToken = localStorage.getItem('access_token')
      const refreshToken = localStorage.getItem('refresh_token')
      const authorizationToken = refreshToken || storedAccessToken
      if (authorizationToken) {
        await api.post(
          '/auth/logout',
          storedAccessToken ? { access_token: storedAccessToken } : {},
          {
            headers: { Authorization: `Bearer ${authorizationToken}` },
            skipAuthRefresh: true,
          },
        )
      }
    } finally {
      clearSession()
    }
  }

  function clearSession() {
    user.value = null
    accessToken.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return {
    accessToken,
    clearSession,
    isAuthenticated,
    login,
    logout,
    register,
    restoreUser,
    setSession,
    updateUser,
    user,
  }
})
