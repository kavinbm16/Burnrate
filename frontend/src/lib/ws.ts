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
}

export interface LiveClientHandlers {
  onStarted?: (sessionId: string) => void
  onMetrics?: (m: LiveMetrics) => void
  onAudio?: (pcm: ArrayBuffer) => void
  onClose?: () => void
  onError?: (e: Event) => void
}

export class LiveClient {
  private ws: WebSocket | null = null

  connect(opts: { tools_enabled: boolean; headroom_enabled: boolean }, handlers: LiveClientHandlers) {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${protocol}://${location.host}/ws/live`)
    this.ws.binaryType = 'arraybuffer'

    this.ws.onopen = () => this.ws?.send(JSON.stringify(opts))
    this.ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        handlers.onAudio?.(ev.data)
        return
      }
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'session_started') handlers.onStarted?.(msg.session_id)
        else if (msg.type === 'metrics') handlers.onMetrics?.(msg as LiveMetrics)
      } catch {
        // ignore malformed frames
      }
    }
    this.ws.onclose = () => handlers.onClose?.()
    this.ws.onerror = (e) => handlers.onError?.(e)
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
