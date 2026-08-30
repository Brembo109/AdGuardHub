import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api/client'
import type { AuthState } from './api/types'

interface AuthContextValue {
  state: AuthState | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  setup: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setState(await api.authState())
    } catch {
      setState({
        authenticated: false,
        username: null,
        setup_required: false,
        ephemeral_secret: false,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      loading,
      refresh,
      login: async (username, password) => {
        await api.login(username, password)
        await refresh()
      },
      setup: async (username, password) => {
        await api.setup(username, password)
        await refresh()
      },
      logout: async () => {
        await api.logout()
        await refresh()
      },
    }),
    [state, loading, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
