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
      // Request mic first while we're still in the button-click user gesture.
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

<div class="w-full flex flex-col gap-6 live-command-surface">
  {#if micPermission === 'denied'}
    <Card.Root class="border-amber-500/40 bg-amber-500/5">
      <Card.Content class="py-4 text-sm">
        <p class="font-medium text-amber-200">Microphone blocked</p>
        <p class="mt-1 text-muted-foreground">
          Allow microphone access for this site: click the <strong>lock icon</strong> in the address
          bar → Site settings → Microphone → Allow. On macOS also enable your browser under
          <strong>System Settings → Privacy & Security → Microphone</strong>, then reload and try
          again.
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
            Approaching limit: currently at <span class="font-mono text-amber-400 font-bold">{usd(totalCost)}</span> of <span class="font-mono text-amber-400 font-bold">{usd(budget, 2)}</span> ({Math.round(totalCost / budget * 100)}%).
          </p>
        </div>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- Premium Two Column Dashboard Cockpit Grid -->
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-5 items-start">
    
    <!-- LEFT PANEL: Main Controls & Scrollable Timeline (3/5 width) -->
    <div class="flex flex-col gap-6 lg:col-span-3">
      
      <!-- Session controls -->
      <Card.Root class="console-panel glow-primary">
        <Card.Header>
          <div class="data-label">Run Console</div>
          <Card.Title>Live Session Controls</Card.Title>
          <Card.Description>Configure tools and headroom compression, then start streaming live.</Card.Description>
        </Card.Header>
        <Card.Content class="flex flex-wrap items-center justify-between gap-4 py-3">
          <div class="flex items-center gap-8">
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
              <Button variant="outline" onclick={toggleMute}>
                {#if muted}<MicOffIcon class="size-4 mr-1.5" /> Unmute{:else}<MicIcon class="size-4 mr-1.5" /> Mute{/if}
              </Button>
              <Button variant="destructive" onclick={() => stop()}>
                <SquareIcon class="size-4 mr-1.5" /> End session
              </Button>
            {:else}
              <Button onclick={start} class="glow-primary px-5 py-2.5">
                <MicIcon class="size-4 mr-1.5" /> Start live session
              </Button>
            {/if}
          </div>
        </Card.Content>
      </Card.Root>

      <!-- Scrollable Turn Feed -->
      <Card.Root class="console-panel flex-1 flex flex-col min-h-[500px]">
        <Card.Header>
          <div class="data-label">Stream Log</div>
          <Card.Title>Real-Time Turn Feed</Card.Title>
          <Card.Description>Interactive timeline showing Gemini Live token pricing, usage metadata, and stream records.</Card.Description>
        </Card.Header>
        <Card.Content class="flex-1 flex flex-col pr-2">
          {#if feed.length === 0}
            <div class="telemetry-grid flex-grow flex flex-col items-center justify-center py-20 text-sm text-muted-foreground border border-dashed rounded-lg bg-card/10">
              <RadioIcon class="size-8 text-muted-foreground mb-3 opacity-60 {running && !muted ? 'animate-ping' : ''}" />
              {running ? 'Speak now — turns will record here as the model answers.' : 'Initialize a live session to display turn metrics.'}
            </div>
          {:else}
            <div class="flex-grow flex flex-col gap-2 max-h-[520px] overflow-y-auto pr-1">
              {#each feed as m (m.turn_index)}
                <div class="flex items-center justify-between rounded-md border px-3.5 py-3 text-sm bg-card/40 hover:bg-card/70 border-border/70 hover:border-primary/35 transition-all duration-200">
                  <div class="flex items-center gap-3">
                    <Badge variant="secondary" class="font-mono bg-primary/10 border-primary/20 text-primary">#{m.turn_index}</Badge>
                    <span class="text-xs text-muted-foreground">
                      <span class="text-foreground font-semibold">{tokens(m.input_tokens)}</span> in · <span class="text-foreground font-semibold">{tokens(m.output_tokens)}</span> out
                      {#if m.audio_input_sec || m.audio_output_sec}
                        · {m.audio_input_sec}s mic / {m.audio_output_sec}s audio
                      {/if}
                    </span>
                  </div>
                  <span class="font-mono text-xs font-bold tabular-nums text-foreground">{usd(m.cost_usd)}</span>
                </div>
              {/each}
            </div>
          {/if}
        </Card.Content>
      </Card.Root>

    </div>

    <!-- RIGHT PANEL: Analytics & Visual gauges (2/5 width) -->
    <div class="flex flex-col gap-6 lg:col-span-2">
      
      <!-- Audio Visualizer Card -->
      <Card.Root class="audio-wave-card signal-panel glow-hover flex flex-col items-center overflow-hidden">
        <Card.Header class="w-full">
          <div class="data-label">Signal Monitor</div>
          <Card.Title>Live audio wave</Card.Title>
          <Card.Description>Visual feedback of microphone input streaming to Gemini.</Card.Description>
        </Card.Header>
        <Card.Content class="flex flex-col items-center gap-3 pb-6">
          <AuraVisualizer
            state={running && muted ? 'muted' : running ? 'speaking' : 'idle'}
            size={220}
          />
          <p class="text-xs text-muted-foreground">
            {#if running && muted}
              <span class="text-amber-400 font-semibold">Microphone muted</span>
            {:else if running}
              <span class="text-cyan-400 font-semibold">Streaming to Gemini</span>
            {:else}
              <span>Session inactive</span>
            {/if}
          </p>
        </Card.Content>
      </Card.Root>

      <!-- Cost Thresholds -->
      <Card.Root class="console-panel glow-hover">
        <Card.Header>
          <div class="data-label">Safety Rail</div>
          <Card.Title>Budget limits & Safety</Card.Title>
          <Card.Description>Set a budget ceiling to automatically pause or warn on high token spend.</Card.Description>
        </Card.Header>
        <Card.Content class="flex flex-col gap-4">
          <div class="flex items-center justify-between">
            <Label for="live-budget" class="font-semibold text-sm">Session Limit</Label>
            <span class="font-mono text-sm font-bold text-primary text-glow-primary">{usd(budget, 2)}</span>
          </div>
          <div class="px-1 py-1">
            <Slider value={[budget]} onValueChange={(val) => budget = val[0]} min={0.05} max={5.0} step={0.05} disabled={running} />
          </div>
          <div class="flex items-center gap-3">
            <Switch id="budget-auto-stop" bind:checked={budgetLimitEnabled} disabled={running} />
            <Label for="budget-auto-stop" class="cursor-pointer text-xs text-muted-foreground select-none">
              Auto-stop session once budget is exceeded
            </Label>
          </div>
        </Card.Content>
      </Card.Root>

      <!-- Gauges -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="console-panel p-4">
          <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Duration</div>
          <div class="mt-2 text-xl font-bold tabular-nums text-foreground">{duration(elapsed)}</div>
        </div>
        <div class="console-panel p-4">
          <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Session Cost</div>
          <div class="mt-2 text-xl font-bold tabular-nums text-emerald-400">{usd(totalCost)}</div>
        </div>
        <div class="console-panel p-4 col-span-1 sm:col-span-2">
          <div class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Burn Rate</div>
          <div class="mt-2 text-xl font-bold tabular-nums text-orange-400">{usd(costPerHour, 2)}/hour</div>
          <div class="mt-1 text-xs text-muted-foreground">{usd(costPerMin, 4)}/min</div>
        </div>
      </div>

      <!-- Cost Breakdown -->
      {#if feed.length > 0}
        <Card.Root class="console-panel">
          <Card.Header>
            <div class="data-label">Cost Composition</div>
            <Card.Title>Where the $ goes</Card.Title>
          </Card.Header>
          <Card.Content class="space-y-4">
            <div class="space-y-2 text-sm">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-blue-500"></div>
                  <span class="text-muted-foreground">Audio Input</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.audio_input)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-cyan-500"></div>
                  <span class="text-muted-foreground">Audio Output</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.audio_output)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-amber-500"></div>
                  <span class="text-muted-foreground">Text Input</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.text_input)}</span>
              </div>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="size-2 rounded-full bg-rose-500"></div>
                  <span class="text-muted-foreground">Text Output</span>
                </div>
                <span class="font-mono font-bold">{usd(costBreakdown.text_output)}</span>
              </div>
            </div>
            <!-- Stacked bar -->
            {#if totalCost > 0}
              <div class="mt-4 h-2 rounded-full flex overflow-hidden bg-card/50 border border-border/50">
                {#if costBreakdown.audio_input > 0}
                  <div
                    class="bg-blue-500/80"
                    style="width: {100 * costBreakdown.audio_input / totalCost}%"
                  ></div>
                {/if}
                {#if costBreakdown.audio_output > 0}
                  <div
                    class="bg-cyan-500/80"
                    style="width: {100 * costBreakdown.audio_output / totalCost}%"
                  ></div>
                {/if}
                {#if costBreakdown.text_input > 0}
                  <div
                    class="bg-amber-500/80"
                    style="width: {100 * costBreakdown.text_input / totalCost}%"
                  ></div>
                {/if}
                {#if costBreakdown.text_output > 0}
                  <div
                    class="bg-rose-500/80"
                    style="width: {100 * costBreakdown.text_output / totalCost}%"
                  ></div>
                {/if}
              </div>
            {/if}
          </Card.Content>
        </Card.Root>
      {/if}

      <!-- Cost progression sparkline -->
      {#if sparkline.length > 1}
        <Card.Root class="console-panel flex-grow">
          <Card.Header>
            <div class="data-label">Cost Trace</div>
            <Card.Title>Session cost accumulation</Card.Title>
          </Card.Header>
          <Card.Content>
            <Chart.Container config={sparkConfig} class="h-32 w-full">
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
  </div>
</div>

<style>
  :global(.audio-wave-card) {
    background-image:
      radial-gradient(circle, rgba(255, 255, 255, 0.07) 1px, transparent 1px),
      radial-gradient(circle at 50% 48%, rgba(236, 72, 153, 0.12), transparent 32%),
      radial-gradient(circle at 50% 58%, rgba(14, 165, 233, 0.1), transparent 34%);
    background-position:
      0 0,
      center,
      center;
    background-size:
      6px 6px,
      100% 100%,
      100% 100%;
    background-color: rgba(3, 3, 3, 0.42);
  }
</style>
