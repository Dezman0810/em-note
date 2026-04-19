import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, setAuthToken } from '../api/client'
import type { User } from '../api/types'

const TOKEN_KEY = 'note_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(null)
  const loaded = ref(false)

  if (token.value) setAuthToken(token.value)

  const isAuthenticated = computed(() => !!token.value)

  function persistToken(t: string | null) {
    token.value = t
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
    setAuthToken(t)
  }

  async function login(email: string, password: string) {
    const data = await authApi.login({ email, password })
    persistToken(data.access_token)
    user.value = await authApi.me()
    loaded.value = true
  }

  async function register(email: string, password: string, display_name?: string) {
    await authApi.register({ email, password, display_name })
    await login(email, password)
  }

  async function fetchMe() {
    if (!token.value) {
      loaded.value = true
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      persistToken(null)
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  function logout() {
    persistToken(null)
    user.value = null
  }

  return { token, user, loaded, isAuthenticated, login, register, fetchMe, logout }
})
