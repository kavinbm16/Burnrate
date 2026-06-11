// WebSocket client for the live audio session (/ws/live).

export interface LiveMetrics {
  type: 'metrics'
  turn_index: number
  input_tokens: number
  output_tokens: number
  audio_input_sec: number
  audio_output_sec: number
  cost_usd: number
  total_cost_usd: number
  cost_breakdown?: {
    audio_input_usd: number
    audio_output_usd: number
    text_input_usd: number
    text_output_usd: number
  }
  cost_rate_per_hour_usd?: number
  elapsed_seconds?: number
}

export interface LiveClientHandlers {
  onStarted?: (sessionId: string) => void
  onMetrics?: (m: LiveMetrics) => void
  onAudio?: (pcm: ArrayBuffer) => void
  onError?: (message: string) => void
  onClose?: () => void
}

export class LiveClient {
  private ws: WebSocket | null = null

  connect(
    opts: { tools_enabled: boolean; headroom_enabled: boolean },
    handlers: LiveClientHandlers,
  ): Promise<void> {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${protocol}://${location.host}/ws/live`)
    this.ws.binaryType = 'arraybuffer'

    return new Promise((resolve, reject) => {
      if (!this.ws) {
        reject(new Error('WebSocket failed to initialize'))
        return
      }

      this.ws.onopen = () => {
        this.ws?.send(JSON.stringify(opts))
        resolve()
      }

      this.ws.onerror = () => {
        handlers.onError?.('WebSocket connection error')
        reject(new Error('WebSocket connection error'))
      }

      this.ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          handlers.onAudio?.(ev.data)
          return
        }
        try {
          const msg = JSON.parse(ev.data) as Record<string, unknown>
          if (msg?.type === 'session_started') handlers.onStarted?.(msg.session_id as string)
          else if (msg?.type === 'metrics') handlers.onMetrics?.(msg as LiveMetrics)
          else if (msg?.type === 'error') handlers.onError?.((msg.message as string) ?? 'Unknown error')
        } catch {
          // ignore malformed frames
        }
      }

      this.ws.onclose = () => handlers.onClose?.()
    })
  }

  sendAudio(chunk: ArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(chunk)
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  close() {
    this.ws?.close()
    this.ws = null
  }
}
