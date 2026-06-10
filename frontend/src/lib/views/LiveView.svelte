<script lang="ts">
  import { onDestroy } from 'svelte'
  import { toast } from 'svelte-sonner'
  import * as Card from '$lib/components/ui/card'
  import * as Chart from '$lib/components/ui/chart'
  import { Button } from '$lib/components/ui/button'
  import { Switch } from '$lib/components/ui/switch'
  import { Label } from '$lib/components/ui/label'
  import { Badge } from '$lib/components/ui/badge'
  import { AreaChart } from 'layerchart'
  import { LiveClient, type LiveMetrics } from '$lib/ws'
  import { MicCapture } from '$lib/audio/capture'
  import { PcmPlayer } from '$lib/audio/playback'
  import { app } from '$lib/state.svelte'
  import { usd, duration } from '$lib/format'
  import MicIcon from '@lucide/svelte/icons/mic'
  import MicOffIcon from '@lucide/svelte/icons/mic-off'
  import SquareIcon from '@lucide/svelte/icons/square'
  import RadioIcon from '@lucide/svelte/icons/radio'

  let toolsEnabled = $state(false)
  let headroomEnabled = $state(false)

  let running = $state(false)
  let muted = $state(false)
  let sessionId = $state<string | null>(null)
  let startedAt = $state(0)
  let elapsed = $state(0)
  let totalCost = $state(0)
  let feed = $state<LiveMetrics[]>([])

  let client: LiveClient | null = null
  let mic: MicCapture | null = null
  let player: PcmPlayer | null = null
  let ticker: ReturnType<typeof setInterval> | null = null

  const costPerMin = $derived(elapsed > 10 ? totalCost / (elapsed / 60) : 0)
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
      client.connect(
        { tools_enabled: toolsEnabled, headroom_enabled: headroomEnabled },
        {
          onStarted: (id) => {
            sessionId = id
            toast.success('Live session started')
          },
          onMetrics: (m) => {
            totalCost = m.total_cost_usd
            feed.unshift(m)
            if (feed.length > 200) feed.pop()
          },
          onAudio: (pcm) => player?.play(pcm),
          onClose: () => {
            if (running) stop(false)
          },
          onError: () => toast.error('WebSocket error — is the backend running?'),
        },
      )

      await mic.start((chunk) => client?.sendAudio(chunk))

      running = true
      startedAt = Date.now()
      ticker = setInterval(() => (elapsed = (Date.now() - startedAt) / 1000), 500)
    } catch (e) {
      toast.error(`Could not start: ${e instanceof Error ? e.message : e}`)
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
    if (mic) mic.muted = muted
  }

  onDestroy(() => {
    if (running) stop(false)
  })
</script>

<div class="mx-auto flex max-w-4xl flex-col gap-6">
  <!-- Controls -->
  <Card.Root>
    <Card.Content class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-3">
          <Switch id="live-tools" bind:checked={toolsEnabled} disabled={running} />
          <Label for="live-tools" class="cursor-pointer">MCP tools</Label>
        </div>
        <div class="flex items-center gap-3">
          <Switch id="live-headroom" bind:checked={headroomEnabled} disabled={running} />
          <Label for="live-headroom" class="cursor-pointer">Headroom</Label>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {#if running}
          <Button variant="outline" onclick={toggleMute}>
            {#if muted}<MicOffIcon class="size-4" /> Unmute{:else}<MicIcon class="size-4" /> Mute{/if}
          </Button>
          <Button variant="destructive" onclick={() => stop()}>
            <SquareIcon class="size-4" /> End session
          </Button>
        {:else}
          <Button onclick={start}>
            <MicIcon class="size-4" /> Start live session
          </Button>
        {/if}
      </div>
    </Card.Content>
  </Card.Root>

  <!-- Status / gauges -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
    <Card.Root>
      <Card.Header>
        <Card.Description class="flex items-center gap-2">
          {#if running}
            <RadioIcon class="size-3.5 animate-pulse text-red-500" /> Live
          {:else}
            Session
          {/if}
        </Card.Description>
        <Card.Title class="text-2xl tabular-nums">{duration(elapsed)}</Card.Title>
        {#if sessionId}
          <Card.Description class="truncate font-mono text-[10px]">{sessionId}</Card.Description>
        {/if}
      </Card.Header>
    </Card.Root>
    <Card.Root>
      <Card.Header>
        <Card.Description>Running total</Card.Description>
        <Card.Title class="text-2xl tabular-nums">{usd(totalCost)}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root>
      <Card.Header>
        <Card.Description>Burn rate</Card.Description>
        <Card.Title class="text-2xl tabular-nums">{usd(costPerMin)}/min</Card.Title>
      </Card.Header>
    </Card.Root>
  </div>

  <!-- Cost sparkline -->
  {#if sparkline.length > 1}
    <Card.Root>
      <Card.Header>
        <Card.Title>Cumulative cost</Card.Title>
      </Card.Header>
      <Card.Content>
        <Chart.Container config={sparkConfig} class="h-36 w-full">
          <AreaChart
            data={sparkline}
            x="turn"
            y="cumulative"
            props={{
              area: { fill: 'var(--color-cumulative)', 'fill-opacity': 0.25 },
              yAxis: { format: (v: number) => usd(v) },
            }}
          />
        </Chart.Container>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- Turn feed -->
  <Card.Root>
    <Card.Header>
      <Card.Title>Turn feed</Card.Title>
      <Card.Description>Per-turn usage from Gemini Live usageMetadata</Card.Description>
    </Card.Header>
    <Card.Content>
      {#if feed.length === 0}
        <p class="py-6 text-center text-sm text-muted-foreground">
          {running ? 'Speak — turns will appear here as the model responds.' : 'Start a session to capture turns.'}
        </p>
      {:else}
        <div class="flex max-h-80 flex-col gap-2 overflow-y-auto">
          {#each feed as m (m.turn_index)}
            <div class="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
              <div class="flex items-center gap-3">
                <Badge variant="secondary" class="font-mono">#{m.turn_index}</Badge>
                <span class="text-xs text-muted-foreground">
                  {m.input_tokens} in · {m.output_tokens} out
                  {#if m.audio_input_sec || m.audio_output_sec}
                    · {m.audio_input_sec}s mic / {m.audio_output_sec}s audio
                  {/if}
                </span>
              </div>
              <span class="font-mono text-xs tabular-nums">{usd(m.cost_usd)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </Card.Content>
  </Card.Root>
</div>
