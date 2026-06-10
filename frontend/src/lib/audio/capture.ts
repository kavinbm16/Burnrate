// Microphone capture: AudioWorklet → downsample to 16 kHz → PCM16 chunks.

const WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.length = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      this.buffer.push(new Float32Array(input[0]));
      this.length += input[0].length;
      // ~128ms batches at 48kHz before posting to the main thread
      if (this.length >= 6144) {
        const merged = new Float32Array(this.length);
        let off = 0;
        for (const chunk of this.buffer) {
          merged.set(chunk, off);
          off += chunk.length;
        }
        this.port.postMessage(merged, [merged.buffer]);
        this.buffer = [];
        this.length = 0;
      }
    }
    return true;
  }
}
registerProcessor('capture-processor', CaptureProcessor);
`

const TARGET_RATE = 16_000

export type MicPermission = 'unknown' | 'granted' | 'denied' | 'prompt'

/** Query microphone permission when the Permissions API is available. */
export async function queryMicPermission(): Promise<MicPermission> {
  if (!navigator.mediaDevices?.getUserMedia) return 'denied'
  try {
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName })
    return status.state as MicPermission
  } catch {
    return 'unknown'
  }
}

function micErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : ''
  const msg = err instanceof Error ? err.message : String(err)

  if (name === 'NotAllowedError' || msg.toLowerCase().includes('permission denied')) {
    return (
      'Microphone access was blocked. Click the lock/camera icon in the address bar → ' +
      'allow Microphone for this site, then try again. On macOS also check ' +
      'System Settings → Privacy & Security → Microphone and enable your browser.'
    )
  }
  if (name === 'NotFoundError') {
    return 'No microphone found. Plug in a mic or check System Settings → Sound → Input.'
  }
  if (name === 'NotReadableError') {
    return 'Microphone is in use by another app. Close other apps using the mic and try again.'
  }
  if (!window.isSecureContext && location.hostname !== 'localhost') {
    return 'Microphone requires HTTPS or localhost. Open the app at http://localhost:5173 or https://…'
  }
  return `Microphone error: ${msg}`
}

function downsampleTo16k(input: Float32Array, inputRate: number): Int16Array {
  const ratio = inputRate / TARGET_RATE
  const outLength = Math.floor(input.length / ratio)
  const out = new Int16Array(outLength)
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio
    const i0 = Math.floor(pos)
    const i1 = Math.min(i0 + 1, input.length - 1)
    const frac = pos - i0
    const sample = input[i0] * (1 - frac) + input[i1] * frac
    out[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)))
  }
  return out
}

export class MicCapture {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private node: AudioWorkletNode | null = null
  muted = false

  async start(onChunk: (pcm: ArrayBuffer) => void): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('This browser does not support microphone capture.')
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch (err) {
      throw new Error(micErrorMessage(err))
    }

    this.ctx = new AudioContext()
    // Browsers may start AudioContext suspended until a user gesture.
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume()
    }

    const workletUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: 'application/javascript' }),
    )
    try {
      await this.ctx.audioWorklet.addModule(workletUrl)
    } catch (err) {
      URL.revokeObjectURL(workletUrl)
      throw new Error(`Audio capture failed to initialize: ${err instanceof Error ? err.message : err}`)
    }
    URL.revokeObjectURL(workletUrl)

    const source = this.ctx.createMediaStreamSource(this.stream)
    this.node = new AudioWorkletNode(this.ctx, 'capture-processor')
    this.node.port.onmessage = (ev: MessageEvent<Float32Array>) => {
      if (this.muted || !this.ctx) return
      const pcm = downsampleTo16k(ev.data, this.ctx.sampleRate)
      onChunk(pcm.buffer as ArrayBuffer)
    }
    source.connect(this.node)
  }

  stop(): void {
    this.node?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.ctx?.close()
    this.node = null
    this.stream = null
    this.ctx = null
  }
}
