// Global app state via Svelte 5 runes.
import { api, type AppConfig, type Session, type ComparisonRow, type Scenario } from './api'

export type Tab = 'live' | 'sim' | 'analytics'

class AppState {
  tab = $state<Tab>('sim')
  config = $state<AppConfig | null>(null)
  scenarios = $state<Scenario[]>([])
  sessions = $state<Session[]>([])
  comparison = $state<ComparisonRow[]>([])
  backendUp = $state(true)
  /** Session to open in the analytics drill-down. */
  drilldownSessionId = $state<string | null>(null)

  async loadStatic() {
    try {
      const [config, scenarios] = await Promise.all([api.config(), api.scenarios()])
      this.config = config
      this.scenarios = scenarios
      this.backendUp = true
    } catch {
      this.backendUp = false
    }
  }

  async refreshSessions() {
    try {
      const [sessions, comparison] = await Promise.all([api.sessions(), api.comparison()])
      this.sessions = sessions
      this.comparison = comparison
      this.backendUp = true
    } catch {
      this.backendUp = false
    }
  }

  openDrilldown(sessionId: string) {
    this.drilldownSessionId = sessionId
    this.tab = 'analytics'
  }
}

export const app = new AppState()
