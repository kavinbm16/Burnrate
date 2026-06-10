<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import * as Card from '$lib/components/ui/card'
  import type { ComparisonRow, Session } from '$lib/api'
  import { configLabel, duration, tokens, usd } from '$lib/format'

  type Props = {
    sessions?: Session[]
    comparison?: ComparisonRow[]
    onDrilldown?: (id: string) => void
  }

  type Palette = {
    front: string
    top: string
    right: string
  }

  const BW = 30
  const BD = 18
  const BDH = 9
  const SLOT_W = 48
  const MAX_BH = 130
  const ORIGIN_X = 42
  const CANVAS_H = 240
  const ANIM_MS = 300
  const STAGGER_MS = 40

  const palettes = {
    baseline: { front: '#d97706', top: '#fbbf24', right: '#92400e' },
    tools: { front: '#ea580c', top: '#fb923c', right: '#7c2d12' },
    headroom: { front: '#dc2626', top: '#f87171', right: '#7f1d1d' },
    full: { front: '#db2777', top: '#f472b6', right: '#9d174d' },
  } satisfies Record<string, Palette>

  let {
    sessions = [],
    comparison = [],
    onDrilldown = () => {},
  }: Props = $props()

  let frame: number | null = null
  let canvas: HTMLCanvasElement
  let container: HTMLDivElement
  let resizeObserver: ResizeObserver | null = null
  let canvasW = $state(0)
  let hoveredId = $state<string | null>(null)
  let mounted = false
  let animationStart = 0
  let currentHeights = new Map<string, number>()

  const sortedSessions = $derived(
    [...sessions].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
  )
  const dataSignature = $derived(sortedSessions.map((s) => `${s.id}:${s.total_cost_usd}`).join('|'))
  const totalSpend = $derived(sessions.reduce((sum, session) => sum + session.total_cost_usd, 0))
  const peakSpend = $derived(sessions.reduce((peak, session) => Math.max(peak, session.total_cost_usd), 0))
  const avgSpend = $derived(sessions.length > 0 ? totalSpend / sessions.length : 0)

  function getPalette(session: Session): Palette {
    if (session.tools_enabled && session.headroom_enabled) return palettes.full
    if (session.tools_enabled) return palettes.tools
    if (session.headroom_enabled) return palettes.headroom
    return palettes.baseline
  }

  function easeOut(t: number): number {
    return 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3)
  }

  function setCanvasSize() {
    if (!canvas || !container) return

    const width = Math.max(320, Math.floor(container.clientWidth))
    const dpr = window.devicePixelRatio || 1
    canvasW = width
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(CANVAS_H * dpr)
    canvas.style.width = `${width}px`
    canvas.style.height = `${CANVAS_H}px`

    const ctx = canvas.getContext('2d')
    ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
    draw()
  }

  function clearCanvas(ctx: CanvasRenderingContext2D) {
    ctx.clearRect(0, 0, canvasW, CANVAS_H)
  }

  function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.lineTo(x + w - r, y)
    ctx.quadraticCurveTo(x + w, y, x + w, y + r)
    ctx.lineTo(x + w, y + h - r)
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
    ctx.lineTo(x + r, y + h)
    ctx.quadraticCurveTo(x, y + h, x, y + h - r)
    ctx.lineTo(x, y + r)
    ctx.quadraticCurveTo(x, y, x + r, y)
    ctx.closePath()
  }

  function path(ctx: CanvasRenderingContext2D, points: [number, number][]) {
    ctx.beginPath()
    points.forEach(([x, y], index) => (index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
    ctx.closePath()
  }

  function fillPath(ctx: CanvasRenderingContext2D, points: [number, number][], fill: string) {
    path(ctx, points)
    ctx.fillStyle = fill
    ctx.fill()
  }

  function strokePath(ctx: CanvasRenderingContext2D, points: [number, number][], stroke: string, width = 1) {
    path(ctx, points)
    ctx.strokeStyle = stroke
    ctx.lineWidth = width
    ctx.stroke()
  }

  function drawEmptyState(ctx: CanvasRenderingContext2D) {
    const baseline = CANVAS_H - 35
    const ghostHeights = [48, 86, 58, 112, 72]
    clearCanvas(ctx)

    ctx.save()
    ctx.setLineDash([5, 5])
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1
    ghostHeights.forEach((height, index) => {
      const x = ORIGIN_X + index * SLOT_W
      strokePath(ctx, [[x, baseline - height], [x + BW, baseline - height], [x + BW, baseline], [x, baseline]], '#1e293b')
      strokePath(ctx, [[x, baseline - height], [x + BW, baseline - height], [x + BW + BD, baseline - height - BDH], [x + BD, baseline - height - BDH]], '#1e293b')
      strokePath(ctx, [[x + BW, baseline - height], [x + BW, baseline], [x + BW + BD, baseline - BDH], [x + BW + BD, baseline - height - BDH]], '#1e293b')
    })
    ctx.restore()

    ctx.fillStyle = '#334155'
    ctx.font = '600 13px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Run a sim session to populate the city', canvasW / 2, CANVAS_H / 2)
  }

  function drawGround(ctx: CanvasRenderingContext2D, baseline: number) {
    const lastX = ORIGIN_X + (sortedSessions.length - 1) * SLOT_W
    fillPath(ctx, [[ORIGIN_X, baseline], [lastX + BW, baseline], [lastX + BW + BD, baseline - BDH], [ORIGIN_X + BD, baseline - BDH]], 'rgba(15, 23, 42, 0.76)')

    ctx.save()
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.14)'
    ctx.lineWidth = 1
    sortedSessions.forEach((_, index) => {
      const x = ORIGIN_X + index * SLOT_W
      ctx.beginPath()
      ctx.moveTo(x, baseline)
      ctx.lineTo(x + BD, baseline - BDH)
      ctx.stroke()
    })
    ctx.restore()
  }

  function drawAxis(ctx: CanvasRenderingContext2D, baseline: number, maxCost: number) {
    ctx.save()
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.22)'
    ctx.fillStyle = 'rgba(148, 163, 184, 0.78)'
    ctx.font = '10px system-ui, sans-serif'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'

    ctx.beginPath()
    ctx.moveTo(ORIGIN_X - 12, baseline - MAX_BH)
    ctx.lineTo(ORIGIN_X - 12, baseline)
    ctx.stroke()

    ;[0.05, 0.1, 0.15].forEach((value) => {
      const y = baseline - (Math.min(value / Math.max(maxCost, 0.15), 1) * MAX_BH)
      ctx.beginPath()
      ctx.moveTo(ORIGIN_X - 8, y)
      ctx.lineTo(Math.min(canvasW - 18, ORIGIN_X + sortedSessions.length * SLOT_W), y)
      ctx.stroke()
      ctx.fillText(usd(value, 2), ORIGIN_X - 16, y)
    })
    ctx.restore()
  }

  function drawBuilding(ctx: CanvasRenderingContext2D, session: Session, index: number, height: number, hovered: boolean) {
    const baseline = CANVAS_H - 35
    const x = ORIGIN_X + index * SLOT_W
    const y = baseline - height
    const palette = getPalette(session)
    const front: [number, number][] = [[x, y], [x + BW, y], [x + BW, baseline], [x, baseline]]
    const top: [number, number][] = [[x, y], [x + BW, y], [x + BW + BD, y - BDH], [x + BD, y - BDH]]
    const right: [number, number][] = [[x + BW, y], [x + BW, baseline], [x + BW + BD, baseline - BDH], [x + BW + BD, y - BDH]]

    ctx.save()
    if (hovered) {
      ctx.shadowBlur = 12
      ctx.shadowColor = palette.top
    }

    fillPath(ctx, right, palette.right)
    fillPath(ctx, front, palette.front)
    fillPath(ctx, top, palette.top)

    ctx.shadowBlur = 0
    ctx.fillStyle = 'rgba(0,0,0,0.25)'
    ctx.fillRect(x, baseline - 3, BW, 3)

    if (hovered) {
      strokePath(ctx, front, 'rgba(255,255,255,0.9)')
      strokePath(ctx, top, 'rgba(255,255,255,0.9)')
      strokePath(ctx, right, 'rgba(255,255,255,0.9)')
    }
    ctx.restore()
  }

  function drawLabels(ctx: CanvasRenderingContext2D, baseline: number) {
    ctx.save()
    ctx.fillStyle = 'rgba(148, 163, 184, 0.78)'
    ctx.font = '10px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    sortedSessions.forEach((session, index) => {
      const date = new Date(session.created_at.endsWith('Z') ? session.created_at : `${session.created_at}Z`)
      const label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      ctx.fillText(label, ORIGIN_X + index * SLOT_W + BW / 2, baseline + 18)
    })
    ctx.restore()
  }

  function drawTooltip(ctx: CanvasRenderingContext2D, session: Session, index: number, height: number) {
    const baseline = CANVAS_H - 35
    const palette = getPalette(session)
    const row = comparison.find((item) => item.session_id === session.id)
    const x = ORIGIN_X + index * SLOT_W
    const topY = baseline - height - BDH
    const topCenterX = x + BW / 2 + BD / 2
    const w = 160
    const h = 72
    const tipX = Math.min(Math.max(topCenterX + 18, 8), Math.max(8, canvasW - w - 8))
    const tipY = Math.min(Math.max(topY - h - 10, 8), CANVAS_H - h - 8)

    ctx.save()
    ctx.setLineDash([4, 4])
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.6)'
    ctx.beginPath()
    ctx.moveTo(tipX + w * 0.5, tipY + h)
    ctx.lineTo(topCenterX, topY)
    ctx.stroke()
    ctx.setLineDash([])

    roundedRect(ctx, tipX, tipY, w, h, 5)
    ctx.fillStyle = '#0f172a'
    ctx.fill()
    ctx.strokeStyle = palette.front
    ctx.lineWidth = 1
    ctx.stroke()

    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    ctx.fillStyle = 'white'
    ctx.font = '700 10px system-ui, sans-serif'
    ctx.fillText(session.scenario_name.slice(0, 24), tipX + 10, tipY + 9)
    ctx.fillStyle = palette.top
    ctx.font = '600 9px system-ui, sans-serif'
    ctx.fillText(configLabel(session.tools_enabled, session.headroom_enabled), tipX + 10, tipY + 25)
    ctx.fillStyle = '#94a3b8'
    ctx.font = '9px system-ui, sans-serif'
    ctx.fillText(`Cost ${usd(session.total_cost_usd, 2)}  · ${duration(session.duration_seconds)}`, tipX + 10, tipY + 42)
    ctx.fillText(`In ${tokens(row?.total_input_text_tokens ?? 0)} tok   Out ${tokens(row?.total_output_text_tokens ?? 0)}`, tipX + 10, tipY + 56)
    ctx.restore()
  }

  function draw(timestamp = performance.now()) {
    if (!canvas || canvasW <= 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    if (sortedSessions.length < 2) {
      drawEmptyState(ctx)
      return
    }

    const baseline = CANVAS_H - 35
    const maxCost = Math.max(...sortedSessions.map((session) => session.total_cost_usd), 0.0001)
    const elapsed = timestamp - animationStart
    const stillAnimating = sortedSessions.some((_, index) => elapsed < ANIM_MS + index * STAGGER_MS)

    clearCanvas(ctx)
    drawAxis(ctx, baseline, maxCost)
    drawGround(ctx, baseline)

    sortedSessions.forEach((session, index) => {
      const targetHeight = (session.total_cost_usd / maxCost) * MAX_BH
      const progress = easeOut((elapsed - index * STAGGER_MS) / ANIM_MS)
      const height = targetHeight * progress
      currentHeights.set(session.id, height)
      drawBuilding(ctx, session, index, height, hoveredId === session.id)
    })

    drawLabels(ctx, baseline)

    const hoveredIndex = sortedSessions.findIndex((session) => session.id === hoveredId)
    if (hoveredIndex >= 0) {
      const session = sortedSessions[hoveredIndex]
      drawTooltip(ctx, session, hoveredIndex, currentHeights.get(session.id) ?? 0)
    }

    if (stillAnimating) {
      frame = requestAnimationFrame(draw)
    } else {
      frame = null
    }
  }

  function startAnimation() {
    if (frame != null) cancelAnimationFrame(frame)
    animationStart = performance.now()
    currentHeights = new Map()
    frame = requestAnimationFrame(draw)
  }

  function hitTest(pointerX: number, pointerY: number): string | null {
    const baseline = CANVAS_H - 35

    for (let index = sortedSessions.length - 1; index >= 0; index -= 1) {
      const session = sortedSessions[index]
      const height = currentHeights.get(session.id) ?? 0
      const x = ORIGIN_X + index * SLOT_W
      if (pointerX >= x && pointerX <= x + BW && pointerY >= baseline - height && pointerY <= baseline) {
        return session.id
      }
    }

    return null
  }

  function handleMousemove(event: MouseEvent) {
    const rect = canvas.getBoundingClientRect()
    const nextHoveredId = hitTest(event.clientX - rect.left, event.clientY - rect.top)

    if (hoveredId !== nextHoveredId) {
      hoveredId = nextHoveredId
      draw()
    }

    canvas.style.cursor = nextHoveredId ? 'pointer' : 'default'
  }

  function handleMouseleave() {
    hoveredId = null
    canvas.style.cursor = 'default'
    draw()
  }

  function handleClick() {
    if (hoveredId) onDrilldown(hoveredId)
  }

  $effect(() => {
    dataSignature
    if (mounted) startAnimation()
  })

  onMount(() => {
    mounted = true
    resizeObserver = new ResizeObserver(setCanvasSize)
    resizeObserver.observe(container)
    setCanvasSize()
    startAnimation()
  })

  onDestroy(() => {
    if (frame != null) cancelAnimationFrame(frame)
    resizeObserver?.disconnect()
  })
</script>

<Card.Root class="glass overflow-hidden">
  <Card.Header class="pb-2">
    <Card.Title>Session cost city</Card.Title>
    <Card.Description>Chronological sessions mapped as spend towers</Card.Description>
  </Card.Header>
  <Card.Content class="pt-0">
    <div bind:this={container} class="w-full">
      <canvas
        bind:this={canvas}
        class="block w-full"
        onmousemove={handleMousemove}
        onmouseleave={handleMouseleave}
        onclick={handleClick}
      ></canvas>
    </div>
    <div class="grid grid-cols-2 gap-3 border-t border-border/40 pt-4 sm:grid-cols-4">
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Sessions</div>
        <div class="mt-1 font-mono text-sm font-bold tabular-nums">{sessions.length}</div>
      </div>
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Total spend</div>
        <div class="mt-1 font-mono text-sm font-bold tabular-nums text-emerald-400">{usd(totalSpend)}</div>
      </div>
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Peak session</div>
        <div class="mt-1 font-mono text-sm font-bold tabular-nums text-primary">{usd(peakSpend)}</div>
      </div>
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Avg / session</div>
        <div class="mt-1 font-mono text-sm font-bold tabular-nums text-cyan-400">{usd(avgSpend)}</div>
      </div>
    </div>
  </Card.Content>
</Card.Root>
