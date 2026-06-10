// Sequential playback of 24 kHz PCM16 chunks from Gemini Live.

const SOURCE_RATE = 24_000

export class PcmPlayer {
  private ctx: AudioContext | null = null
  private nextTime = 0

  private ensureContext(): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext({ sampleRate: SOURCE_RATE })
      this.nextTime = 0
    }
    return this.ctx
  }

  play(pcm: ArrayBuffer): void {
    const ctx = this.ensureContext()
    const int16 = new Int16Array(pcm)
    if (int16.length === 0) return

    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768

    const buffer = ctx.createBuffer(1, float32.length, SOURCE_RATE)
    buffer.copyToChannel(float32, 0)

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)

    const startAt = Math.max(ctx.currentTime, this.nextTime)
    source.start(startAt)
    this.nextTime = startAt + buffer.duration
  }

  stop(): void {
    this.ctx?.close()
    this.ctx = null
    this.nextTime = 0
  }
}
