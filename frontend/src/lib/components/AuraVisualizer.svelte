<script lang="ts">
  import { onMount, onDestroy } from 'svelte'

  type AuraState = 'idle' | 'listening' | 'speaking' | 'muted'

  let { state = 'idle', size = 200 }: { state?: AuraState; size?: number } = $props()

  let canvas: HTMLCanvasElement
  let raf: number
  let t = 0

  const stateConfig = {
    idle: { amplitude: 6, speed: 0.006, alpha: 0.48, pulse: 0.25 },
    listening: { amplitude: 16, speed: 0.014, alpha: 0.78, pulse: 0.6 },
    speaking: { amplitude: 24, speed: 0.022, alpha: 0.95, pulse: 1 },
    muted: { amplitude: 3, speed: 0.003, alpha: 0.24, pulse: 0.1 },
  }

  const COLORS = [
    [255, 55, 18],   // hot orange
    [255, 0, 210],   // magenta
    [88, 55, 255],   // electric indigo
    [0, 190, 255],   // cyan
    [255, 178, 18],  // amber
  ]

  function color([r, g, b]: number[], alpha: number) {
    return `rgba(${r},${g},${b},${alpha})`
  }

  function ringPoint(cx: number, cy: number, baseR: number, amp: number, angle: number, phase: number, offset: number) {
    const wave =
      Math.sin(angle * 3 + phase + offset) * amp +
      Math.sin(angle * 7 - phase * 0.74 + offset * 1.7) * amp * 0.34 +
      Math.sin(angle * 11 + phase * 1.18 - offset) * amp * 0.18
    const r = baseR + wave
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    }
  }

  function traceRing(ctx: CanvasRenderingContext2D, cx: number, cy: number, baseR: number, amp: number, phase: number, offset: number) {
    const steps = 180
    ctx.beginPath()
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2
      const { x, y } = ringPoint(cx, cy, baseR, amp, angle, phase, offset)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.closePath()
  }

  function drawDottedField(ctx: CanvasRenderingContext2D, w: number, h: number) {
    ctx.save()
    ctx.fillStyle = 'rgba(255,255,255,0.045)'
    const spacing = 6
    for (let y = 3; y < h; y += spacing) {
      for (let x = 3; x < w; x += spacing) {
        ctx.fillRect(x, y, 1, 1)
      }
    }
    ctx.restore()
  }

  function drawBloom(ctx: CanvasRenderingContext2D, cx: number, cy: number, baseR: number, amp: number, phase: number, alpha: number) {
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    COLORS.forEach((c, i) => {
      const angle = phase * (0.8 + i * 0.08) + i * ((Math.PI * 2) / COLORS.length)
      const p = ringPoint(cx, cy, baseR, amp * 1.25, angle, phase, i)
      const g = ctx.createRadialGradient(p.x, p.y, 1, p.x, p.y, baseR * 0.42)
      g.addColorStop(0, color(c, alpha * 0.28))
      g.addColorStop(0.45, color(c, alpha * 0.12))
      g.addColorStop(1, color(c, 0))
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.arc(p.x, p.y, baseR * 0.44, 0, Math.PI * 2)
      ctx.fill()
    })
    ctx.restore()
  }

  function drawAuraBands(ctx: CanvasRenderingContext2D, cx: number, cy: number, baseR: number, amp: number, phase: number, alpha: number) {
    ctx.save()
    ctx.globalCompositeOperation = 'lighter'
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    for (let i = 0; i < COLORS.length; i++) {
      traceRing(ctx, cx, cy, baseR + (i - 2) * 3.4, amp * (1 - i * 0.035), phase + i * 0.82, i * 1.13)
      ctx.strokeStyle = color(COLORS[i], alpha * 0.24)
      ctx.lineWidth = 18
      ctx.filter = 'blur(9px)'
      ctx.stroke()
    }

    ctx.filter = 'blur(3px)'
    for (let i = 0; i < COLORS.length; i++) {
      traceRing(ctx, cx, cy, baseR + (i - 2) * 2.4, amp * (1 - i * 0.04), phase + i * 0.82, i * 1.13)
      ctx.strokeStyle = color(COLORS[i], alpha * 0.62)
      ctx.lineWidth = 8
      ctx.stroke()
    }

    ctx.filter = 'none'
    for (let i = 0; i < COLORS.length; i++) {
      traceRing(ctx, cx, cy, baseR + (i - 2) * 1.4, amp * (1 - i * 0.04), phase + i * 0.82, i * 1.13)
      ctx.strokeStyle = color(COLORS[i], alpha * 0.88)
      ctx.lineWidth = 2.4
      ctx.stroke()
    }

    ctx.restore()
  }

  function drawCoreCutout(ctx: CanvasRenderingContext2D, cx: number, cy: number, baseR: number) {
    const g = ctx.createRadialGradient(cx, cy, baseR * 0.58, cx, cy, baseR * 1.03)
    g.addColorStop(0, 'rgba(3,3,3,0.98)')
    g.addColorStop(0.72, 'rgba(3,3,3,0.74)')
    g.addColorStop(1, 'rgba(3,3,3,0)')
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(cx, cy, baseR * 0.95, 0, Math.PI * 2)
    ctx.fill()
  }

  function draw() {
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const cfg = stateConfig[state]
    const dpr = window.devicePixelRatio || 1
    const w = canvas.width / dpr
    const h = canvas.height / dpr

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    t += cfg.speed

    const cx = w / 2
    const cy = h / 2
    const baseR = (Math.min(w, h) / 2) * 0.62
    const pulse = 1 + Math.sin(t * 6) * cfg.pulse * 0.08
    const amp = cfg.amplitude * pulse

    drawDottedField(ctx, w, h)
    drawBloom(ctx, cx, cy, baseR, amp, t, cfg.alpha)
    drawAuraBands(ctx, cx, cy, baseR, amp, t, cfg.alpha)
    drawCoreCutout(ctx, cx, cy, baseR)

    raf = requestAnimationFrame(draw)
  }

  onMount(() => {
    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    draw()
  })

  onDestroy(() => cancelAnimationFrame(raf))
</script>

<canvas
  bind:this={canvas}
  style="width:{size}px;height:{size}px;"
  class="block"
></canvas>
