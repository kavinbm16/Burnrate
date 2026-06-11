<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import { toast } from 'svelte-sonner'
  import * as Card from '$lib/components/ui/card'
  import * as Chart from '$lib/components/ui/chart'
  import { Button } from '$lib/components/ui/button'
  import { Switch } from '$lib/components/ui/switch'
  import { Label } from '$lib/components/ui/label'
  import { Badge } from '$lib/components/ui/badge'
  import { Slider } from '$lib/components/ui/slider'
  import { AreaChart } from 'layerchart'
  import { LiveClient, type LiveMetrics } from '$lib/ws'
  import { MicCapture, queryMicPermission, type MicPermission } from '$lib/audio/capture'
  import { PcmPlayer } from '$lib/audio/playback'
  import { app } from '$lib/state.svelte'
  import { usd, duration, tokens } from '$lib/format'
  import MicIcon from '@lucide/svelte/icons/mic'
  import MicOffIcon from '@lucide/svelte/icons/mic-off'
  import SquareIcon from '@lucide/svelte/icons/square'
  import RadioIcon from '@lucide/svelte/icons/radio'
  import AlertTriangleIcon from '@lucide/svelte/icons/alert-triangle'
  import AuraVisualizer from '$lib/components/AuraVisualizer.svelte'

  let toolsEnabled = $state(false)
  let headroomEnabled = $state(false)

  let running = $state(false)
  let muted = $state(false)
  let sessionId = $state<string | null>(null)
  let startedAt = $state(0)
  let elapsed = $state(0)
  let totalCost = $state(0)
  let feed = $state<LiveMetrics[]>([])

  let budget = $state(0.50)
  let budgetLimitEnabled = $state(true)

  let client: LiveClient | null = null
  let mic: MicCapture | null = null
  let player: PcmPlayer | null = null
  let ticker: ReturnType<typeof setInterval> | null = null
  let micPermission = $state<MicPermission>('unknown')


  onMount(async () => {
    micPermission = await queryMicPermission()
  })

  const costPerMin = $derived(elapsed > 10 ? totalCost / (elapsed / 60) : 0)
  const costPerHour = $derived(costPerMin * 60)
  const costBreakdown = $derived.by(() => {
    let audio_input = 0, audio_output = 0, text_input = 0, text_output = 0
    for (const m of feed) {
      if (m.cost_breakdown) {
        audio_input += m.cost_breakdown.audio_input_usd
        audio_output += m.cost_breakdown.audio_output_usd
        text_input += m.cost_breakdown.text_input_usd
        text_output += m.cost_breakdown.text_output_usd
      }
    }
    return { audio_input, audio_output, text_input, text_output }
  })
  const sparkline = $derived.by(() => {
    let acc = 0
    return feed
      .slice()
      .reverse()
      .map((m) => {
        acc += m.cost_usd
        return { turn: m.turn_index, cumulative: acc }
      })
  })

  const sparkConfig = {
    cumulative: { label: 'Cost', color: 'var(--chart-1)' },
  } satisfies Chart.ChartConfig

  async function start() {
    feed = []
    totalCost = 0
    elapsed = 0
    sessionId = null

    mic = new MicCapture()
    player = new PcmPlayer()
    client = new LiveClient()

    try {
      await mic.start((chunk) => client?.sendAudio(chunk))
      micPermission = 'granted'

      await client.connect(
        { tools_enabled: toolsEnabled, headroom_enabled: headroomEnabled },
        {
          onStarted: (id) => {
            sessionId = id
            toast.success('Live session started — speak into the mic')
          },
          onMetrics: (m) => {
            totalCost = m.total_cost_usd
            feed.unshift(m)
            if (feed.length > 200) feed.pop()

            if (budgetLimitEnabled && totalCost >= budget) {
              toast.error(`Budget limit of ${usd(budget, 2)} exceeded! Auto-stopping session.`)
              stop(true)
            }
          },
          onAudio: (pcm) => player?.play(pcm),
          onError: (message) => {
            toast.error(message, { duration: 12_000 })
            if (running) stop(false)
          },
          onClose: () => {
            if (running) stop(false)
          },
        },
      )

      running = true
      startedAt = Date.now()
      ticker = setInterval(() => (elapsed = (Date.now() - startedAt) / 1000), 500)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      toast.error(message, { duration: 12_000 })
      if (message.toLowerCase().includes('microphone')) micPermission = 'denied'
      cleanup()
    }
  }

  function cleanup() {
    mic?.stop()
    player?.stop()
    client?.close()
    mic = null
    player = null
    client = null
    if (ticker) clearInterval(ticker)
    ticker = null
  }

  function stop(notify = true) {
    running = false
    muted = false
    cleanup()
    if (notify) toast.info(`Session ended — ${usd(totalCost)}`)
    app.refreshSessions()
  }

  function toggleMute() {
    muted = !muted
    if (mic) {
      mic.muted = muted
    }
  }

  onDestroy(() => {
    if (running) stop(false)
  })
</script>

<div class="w-full flex flex-col gap-5 live-command-surface">
  {#if micPermission === 'denied'}
    <Card.Root class="border-amber-500/40 bg-amber-500/5">
      <Card.Content class="py-4 text-sm">
        <p class="font-medium text-amber-200">Microphone blocked</p>
        <p class="mt-1 text-muted-foreground">
          Allow microphone access: click lock icon → Site settings → Microphone → Allow. macOS: System Settings → Privacy & Security → Microphone.
        </p>
      </Card.Content>
    </Card.Root>
  {/if}

  {#if running && budgetLimitEnabled && totalCost >= budget * 0.8}
    <Card.Root class="border-amber-500/40 bg-amber-500/10 text-amber-200 animate-pulse glow-primary">
      <Card.Content class="py-4 text-sm flex items-center gap-3">
        <AlertTriangleIcon class="size-5 text-amber-500 shrink-0" />
        <div>
          <p class="font-semibold">Budget Warning</p>
          <p class="text-xs text-muted-foreground mt-0.5">
            At <span class="font-mono text-amber-400 font-bold">{usd(totalCost)}</span> of <span class="font-mono text-amber-400 font-bold">{usd(budget, 2)}</span> ({Math.round(totalCost / budget * 100)}%).
          </p>
        </div>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- HEADER: Session Controls -->
  <Card.Root class="console-panel glow-primary border-primary/30">
    <Card.Content class="py-4">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-6">
          <div class="flex items-center gap-3">
            <Switch id="live-tools" bind:checked={toolsEnabled} disabled={running} />
            <Label for="live-tools" class="cursor-pointer font-semibold text-sm">MCP tools</Label>
          </div>
          <div class="flex items-center gap-3">
            <Switch id="live-headroom" bind:checked={headroomEnabled} disabled={running} />
            <Label for="live-headroom" class="cursor-pointer font-semibold text-sm">Headroom</Label>
          </div>
        </div>

        <div class="flex items-center gap-2">
          {#if running}
            <Button variant="outline" size="sm" onclick={toggleMute}>
              {#if muted}<MicOffIcon class="size-4 mr-1.5" /> Unmute{:else}<MicIcon class="size-4 mr-1.5" /> Mute{/if}
            </Button>
            <Button variant="destructive" size="sm" onclick={() => stop()}>
              <SquareIcon class="size-4 mr-1.5" /> End session
            </Button>
          {:else}
            <Button onclick={start} class="glow-primary">
              <MicIcon class="size-4 mr-1.5" /> Start live session
            </Button>
          {/if}
        </div>
      </div>
    </Card.Content>
  </Card.Root>

  <!-- KEY METRICS BAR: 4 Cards -->
  <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
    <!-- Duration -->
    <Card.Root class="console-panel">
      <Card.Content class="pt-4">
        <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Duration</div>
        <div class="mt-3 text-2xl font-bold tabular-nums text-foreground">{duration(elapsed)}</div>
      </Card.Content>
    </Card.Root>

    <!-- Session Cost -->
    <Card.Root class="console-panel">
      <Card.Content class="pt-4">
        <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Session Cost</div>
        <div class="mt-3 text-2xl font-bold tabular-nums text-emerald-400">{usd(totalCost)}</div>
      </Card.Content>
    </Card.Root>

    <!-- Burn Rate -->
    <Card.Root class="console-panel">
      <Card.Content class="pt-4">
        <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Burn Rate</div>
        <div class="mt-3 text-2xl font-bold tabular-nums text-orange-400">{usd(costPerHour, 2)}/h</div>
        <div class="mt-1 text-xs text-muted-foreground">{usd(costPerMin, 4)}/min</div>
      </Card.Content>
    </Card.Root>

    <!-- Budget Status -->
    <Card.Root class="console-panel">
      <Card.Content class="pt-4">
        <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Budget</div>
        <div class="mt-3 text-2xl font-bold tabular-nums {totalCost >= budget * 0.9 ? 'text-red-400' : totalCost >= budget * 0.7 ? 'text-amber-400' : 'text-cyan-400'}">{usd(budget, 2)}</div>
        {#if budgetLimitEnabled}
          <div class="mt-2 h-1 bg-card/50 rounded-full overflow-hidden">
            <div
              class="h-full {totalCost / budget > 1 ? 'bg-red-500' : totalCost / budget > 0.7 ? 'bg-amber-500' : 'bg-cyan-500'} transition-all"
              style="width: {Math.min(100, (totalCost / budget) * 100)}%"
            ></div>
          </div>
        {/if}
      </Card.Content>
    </Card.Root>
  </div>

  <!-- MAIN CONTENT: 2-Column Layout -->
  <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">

    <!-- LEFT: Stream Log (Primary, takes 2/3) -->
    <div class="lg:col-span-2 flex flex-col">
      <Card.Root class="console-panel flex-1 flex flex-col min-h-[600px]">
        <Card.Header class="border-b">
          <div class="data-label text-xs">Stream Log</div>
          <Card.Title class="text-lg">Real-Time Turn Feed</Card.Title>
        </Card.Header>
        <Card.Content class="flex-1 flex flex-col pr-2 overflow-hidden">
          {#if feed.length === 0}
            <div class="flex-grow flex flex-col items-center justify-center text-sm text-muted-foreground">
              <RadioIcon class="size-10 mb-3 opacity-40 {running && !muted ? 'animate-ping' : ''}" />
              {running ? 'Speak now — turns will appear here.' : 'Start a session to see turn metrics.'}
            </div>
          {:else}
            <div class="flex-grow flex flex-col gap-2 overflow-y-auto pr-1">
              {#each feed as m (m.turn_index)}
                <div class="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-xs bg-card/40 hover:bg-card/70 border-border/60 hover:border-primary/40 transition-all">
                  <div class="flex items-center gap-2 min-w-0">
                    <Badge variant="secondary" class="font-mono text-xs shrink-0">#{m.turn_index}</Badge>
                    <span class="text-muted-foreground truncate">
                      <span class="font-semibold text-foreground">{tokens(m.input_tokens)}</span>in / <span class="font-semibold text-foreground">{tokens(m.output_tokens)}</span>out
                      {#if m.audio_input_sec || m.audio_output_sec}
                        / {m.audio_input_sec}→{m.audio_output_sec}s
                      {/if}
                    </span>
                  </div>
                  <span class="font-mono font-bold tabular-nums text-foreground shrink-0">{usd(m.cost_usd)}</span>
                </div>
              {/each}
            </div>
          {/if}
        </Card.Content>
      </Card.Root>
    </div>

    <!-- RIGHT: Visualizations & Metrics (takes 1/3) -->
    <div class="flex flex-col gap-5">

      <!-- Audio Visualizer -->
      <Card.Root class="audio-wave-card signal-panel glow-hover flex flex-col items-center overflow-hidden">
        <Card.Header class="w-full border-b">
          <div class="data-label text-xs">Signal Monitor</div>
          <Card.Title class="text-base">Audio wave</Card.Title>
        </Card.Header>
        <Card.Content class="flex flex-col items-center gap-2 py-6">
          <AuraVisualizer
            state={running && muted ? 'muted' : running ? 'speaking' : 'idle'}
            size={160}
          />
          <p class="text-xs text-muted-foreground">
            {#if running && muted}
              <span class="text-amber-400 font-semibold">Muted</span>
            {:else if running}
              <span class="text-cyan-400 font-semibold">Streaming</span>
            {:else}
              <span>Inactive</span>
            {/if}
          </p>
        </Card.Content>
      </Card.Root>

      <!-- Cost Composition -->
      {#if feed.length > 0}
        <Card.Root class="console-panel">
          <Card.Header class="border-b pb-3">
            <div class="data-label text-xs">Cost Composition</div>
            <Card.Title class="text-base">Where the $ goes</Card.Title>
          </Card.Header>
          <Card.Content class="pt-3 space-y-3">
            <div class="space-y-1.5 text-xs">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-blue-500"></div>
                  <span class="text-muted-foreground">Audio In</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.audio_input)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-cyan-500"></div>
                  <span class="text-muted-foreground">Audio Out</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.audio_output)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-amber-500"></div>
                  <span class="text-muted-foreground">Text In</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.text_input)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-rose-500"></div>
                  <span class="text-muted-foreground">Text Out</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.text_output)}</span>
              </div>
            </div>
            {#if totalCost > 0}
              <div class="mt-3 h-2 rounded-full flex overflow-hidden bg-card/50 border border-border/40">
                {#if costBreakdown.audio_input > 0}
                  <div class="bg-blue-500/80" style="width: {100 * costBreakdown.audio_input / totalCost}%"></div>
                {/if}
                {#if costBreakdown.audio_output > 0}
                  <div class="bg-cyan-500/80" style="width: {100 * costBreakdown.audio_output / totalCost}%"></div>
                {/if}
                {#if costBreakdown.text_input > 0}
                  <div class="bg-amber-500/80" style="width: {100 * costBreakdown.text_input / totalCost}%"></div>
                {/if}
                {#if costBreakdown.text_output > 0}
                  <div class="bg-rose-500/80" style="width: {100 * costBreakdown.text_output / totalCost}%"></div>
                {/if}
              </div>
            {/if}
          </Card.Content>
        </Card.Root>
      {/if}

      <!-- Budget Controls -->
      <Card.Root class="console-panel">
        <Card.Header class="border-b pb-3">
          <div class="data-label text-xs">Safety Rail</div>
          <Card.Title class="text-base">Budget limits</Card.Title>
        </Card.Header>
        <Card.Content class="pt-3 space-y-3">
          <div class="flex items-center justify-between">
            <Label for="live-budget" class="font-semibold text-xs">Limit</Label>
            <span class="font-mono text-sm font-bold text-primary">{usd(budget, 2)}</span>
          </div>
          <Slider value={[budget]} onValueChange={(val) => budget = val[0]} min={0.05} max={5.0} step={0.05} disabled={running} />
          <div class="flex items-center gap-2">
            <Switch id="budget-auto-stop" bind:checked={budgetLimitEnabled} disabled={running} />
            <Label for="budget-auto-stop" class="text-xs text-muted-foreground">Auto-stop</Label>
          </div>
        </Card.Content>
      </Card.Root>
    </div>
  </div>

  <!-- FOOTER: Cost Trace Chart (Full Width) -->
  {#if sparkline.length > 1}
    <Card.Root class="console-panel">
      <Card.Header class="border-b">
        <div class="data-label text-xs">Cost Trace</div>
        <Card.Title class="text-base">Session cost accumulation</Card.Title>
      </Card.Header>
      <Card.Content class="pt-4">
        <Chart.Container config={sparkConfig} class="h-40 w-full">
          <AreaChart
            data={sparkline}
            x="turn"
            y="cumulative"
            props={{
              area: { fill: 'var(--color-cumulative)', 'fill-opacity': 0.15 },
              yAxis: { format: (v: number) => usd(v) },
            }}
          />
        </Chart.Container>
      </Card.Content>
    </Card.Root>
  {/if}

</div>

<style>
  :global(.audio-wave-card) {
    background-image:
      radial-gradient(circle, rgba(255, 255, 255, 0.07) 1px, transparent 1px),
      radial-gradient(circle at 50% 48%, rgba(236, 72, 153, 0.12), transparent 32%),
      radial-gradient(circle at 50% 58%, rgba(14, 165, 233, 0.1), transparent 34%);
    background-position: 0 0, center, center;
    background-size: 6px 6px, 100% 100%, 100% 100%;
    background-color: rgba(3, 3, 3, 0.42);
  }
</style>
