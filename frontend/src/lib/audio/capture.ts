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
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    this.ctx = new AudioContext()
    const workletUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: 'application/javascript' }),
    )
    await this.ctx.audioWorklet.addModule(workletUrl)
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
