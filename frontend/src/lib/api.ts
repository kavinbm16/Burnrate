// Typed client for the Burnrate REST API.

export interface AppConfig {
  model: string
  pricing: {
    audio_input_per_min: number
    audio_output_per_min: number
    text_input_per_mtok: number
    text_output_per_mtok: number
  }
  mcp_servers: { name: string; type: string }[]
}

export interface Scenario {
  path: string
  name: string
  description: string
  turn_count: number
  avg_turn_duration_sec: number
  repeat: number
  estimated_duration_sec: number
  error?: string
}

export interface Session {
  id: string
  mode: string
  scenario_name: string
  tools_enabled: boolean
  headroom_enabled: boolean
  created_at: string
  duration_seconds: number
  total_cost_usd: number
}

export interface Turn {
  session_id: string
  turn_index: number
  input_audio_tokens: number
  input_text_tokens: number
  output_audio_tokens: number
  output_text_tokens: number
  tool_call_tokens: number
  audio_duration_seconds: number
  cost_usd: number
}

export interface ComparisonRow {
  session_id: string
  scenario_name: string
  tools_enabled: boolean
  headroom_enabled: boolean
  duration_seconds: number
  total_cost_usd: number
  total_input_text_tokens: number
  total_output_text_tokens: number
  total_tool_tokens: number
  cost_per_hour_usd: number
}

export interface Projection {
  session_id: string
  session_cost_usd: number
  session_duration_seconds: number
  hours_per_day: number
  robots: number
  per_hour_usd: number
  per_day_usd: number
  per_month_usd: number
  fleet_per_day_usd: number
  fleet_per_month_usd: number
}

export interface SimRunStatus {
  status: 'running' | 'done' | 'error' | 'not_found'
  progress?: number
  total?: number
  session_id?: string | null
  total_cost_usd?: number
  error?: string | null
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  config: () => get<AppConfig>('/api/config'),
  scenarios: () => get<Scenario[]>('/api/scenarios'),
  sessions: () => get<Session[]>('/api/sessions'),
  turns: (sessionId: string) => get<Turn[]>(`/api/sessions/${sessionId}/turns`),
  comparison: () => get<ComparisonRow[]>('/api/comparison'),
  projection: (sessionId: string, hoursPerDay: number, robots: number) =>
    get<Projection>(
      `/api/sessions/${sessionId}/projection?hours_per_day=${hoursPerDay}&robots=${robots}`,
    ),

  async deleteSession(sessionId: string): Promise<void> {
    const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`DELETE failed: ${res.status}`)
  },

  async startSim(body: {
    scenario_path: string
    tools_enabled: boolean
    headroom_enabled: boolean
  }): Promise<{ run_id: string }> {
    const res = await fetch('/api/sim/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Sim start failed: ${res.status}: ${await res.text()}`)
    return res.json()
  },

  simStatus: (runId: string) => get<SimRunStatus>(`/api/sim/status/${runId}`),

  exportCsvUrl: '/api/export/csv',
  exportJsonUrl: '/api/export/json',
}
