import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, clearRequestCache, featuresApi, setAuthToken } from '../api/client'
import { clearAttachmentBlobCache } from '../utils/attachmentBlob'
import type { User } from '../api/types'
import { scheduleMindmapWarmup } from '../utils/mindmapWarmup'

const TOKEN_KEY = 'note_token'

/** Устаревший ответ fetchMe не должен сбрасывать токен после успешного login (параллельные запросы /me). */
let authEpoch = 0

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase()
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(null)
  const loaded = ref(false)
  /** Распознавание речи включено на сервере (модель Vosk есть и не отключена). */
  const audioTranscribeEnabled = ref(false)

  if (token.value) setAuthToken(token.value)

  const isAuthenticated = computed(() => !!token.value)

  function persistToken(t: string | null) {
    token.value = t
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
    setAuthToken(t)
  }

  async function login(email: string, password: string) {
    authEpoch++
    clearRequestCache()
    clearAttachmentBlobCache()
    const data = await authApi.login({ email: normalizeEmail(email), password })
    persistToken(data.access_token)
    user.value = await authApi.me()
    loaded.value = true
    if (user.value?.can_use_schemas) scheduleMindmapWarmup()
  }

  async function register(email: string, password: string, display_name?: string) {
    await authApi.register({ email: normalizeEmail(email), password, display_name })
    await login(email, password)
  }

  /** Доступно и анонимно: публичная заметка тоже прячет кнопки выключенных функций. */
  async function loadFeatures() {
    try {
      const f = await featuresApi.get()
      audioTranscribeEnabled.value = f.audio_transcribe
    } catch {
      audioTranscribeEnabled.value = false
    }
  }

  async function fetchMe() {
    const epoch = authEpoch
    void loadFeatures()
    if (!token.value) {
      loaded.value = true
      return
    }
    try {
      const me = await authApi.me()
      if (authEpoch !== epoch) return
      user.value = me
      if (me.can_use_schemas) scheduleMindmapWarmup()
    } catch {
      if (authEpoch !== epoch) return
      persistToken(null)
      user.value = null
    } finally {
      if (authEpoch === epoch) {
        loaded.value = true
      }
    }
  }

  async function changePassword(current_password: string, new_password: string) {
    const me = await authApi.changePassword({ current_password, new_password })
    user.value = me
  }

  function logout() {
    authEpoch++
    clearRequestCache()
    clearAttachmentBlobCache()
    persistToken(null)
    user.value = null
  }

  return {
    token,
    user,
    loaded,
    isAuthenticated,
    audioTranscribeEnabled,
    login,
    register,
    fetchMe,
    loadFeatures,
    changePassword,
    logout,
  }
})
