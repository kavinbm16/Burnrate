<script lang="ts">
  import { onMount, onDestroy } from 'svelte'

  type AuraState = 'idle' | 'listening' | 'speaking' | 'muted'

  let { state = 'idle', size = 200 }: { state?: AuraState; size?: number } = $props()

  let canvas: HTMLCanvasElement
  let raf: number
  let t = 0

  const stateConfig = {
    idle:      { amplitude: 4,  speed: 0.004, alpha: 0.35, rings: 2 },
    listening: { amplitude: 14, speed: 0.012, alpha: 0.65, rings: 3 },
    speaking:  { amplitude: 28, speed: 0.022, alpha: 0.90, rings: 4 },
    muted:     { amplitude: 3,  speed: 0.002, alpha: 0.20, rings: 2 },
  }

  const COLORS = [
    [255, 140, 0],   // amber-orange
    [255, 195, 40],  // warm amber
    [255, 80, 20],   // deep orange-red
    [255, 220, 100], // yellow-gold
  ]

  function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

  function drawRing(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, amp: number, phase: number, colorA: number[], colorB: number[], alpha: number) {
    const steps = 120
    const grad = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r)
    grad.addColorStop(0,   `rgba(${colorA.join(',')},${alpha})`)
    grad.addColorStop(0.5, `rgba(${colorB.join(',')},${alpha * 0.6})`)
    grad.addColorStop(1,   `rgba(${colorA.join(',')},${alpha * 0.3})`)

    ctx.beginPath()
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2
      const noise =
        Math.sin(angle * 3 + phase) * amp +
        Math.sin(angle * 7 - phase * 1.3) * amp * 0.5 +
        Math.sin(angle * 13 + phase * 0.7) * amp * 0.25
      const rx = cx + (r + noise) * Math.cos(angle)
      const ry = cy + (r + noise) * Math.sin(angle)
      i === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry)
    }
    ctx.closePath()
    ctx.strokeStyle = grad
    ctx.lineWidth = 2.5
    ctx.stroke()
  }

  function draw() {
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const cfg = stateConfig[state]
    const dpr = window.devicePixelRatio || 1
    const w = canvas.width / dpr
    const h = canvas.height / dpr

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    t += cfg.speed

    const cx = canvas.width / 2
    const cy = canvas.height / 2
    const baseR = (Math.min(w, h) / 2) * 0.62

    // glow bloom layer
    const bloom = ctx.createRadialGradient(cx, cy, baseR * 0.4, cx, cy, baseR * 1.3)
    const [r, g, b] = COLORS[0]
    bloom.addColorStop(0, `rgba(${r},${g},${b},0)`)
    bloom.addColorStop(0.6, `rgba(${r},${g},${b},${cfg.alpha * 0.08})`)
    bloom.addColorStop(1, `rgba(${r},${g},${b},0)`)
    ctx.fillStyle = bloom
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    for (let i = 0; i < cfg.rings; i++) {
      const ringR = baseR + (i - cfg.rings / 2) * 7
      const phase = t + i * (Math.PI * 2 / cfg.rings)
      const ca = COLORS[i % COLORS.length]
      const cb = COLORS[(i + 1) % COLORS.length]
      const ringAlpha = cfg.alpha * (1 - i * 0.15)
      drawRing(ctx, cx, cy, ringR, cfg.amplitude, phase, ca, cb, ringAlpha)
    }

    raf = requestAnimationFrame(draw)
  }

  onMount(() => {
    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    draw()
  })

  onDestroy(() => cancelAnimationFrame(raf))
</script>

<canvas
  bind:this={canvas}
  style="width:{size}px;height:{size}px;"
  class="block"
></canvas>
