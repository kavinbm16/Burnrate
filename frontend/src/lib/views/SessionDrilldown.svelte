<script lang="ts">
  import * as Sheet from '$lib/components/ui/sheet'
  import * as Chart from '$lib/components/ui/chart'
  import { Badge } from '$lib/components/ui/badge'
  import { Separator } from '$lib/components/ui/separator'
  import { AreaChart, LineChart, PieChart } from 'layerchart'
  import { api, type Turn } from '$lib/api'
  import { app } from '$lib/state.svelte'
  import { usd, tokens, duration, configLabel } from '$lib/format'

  let turns = $state<Turn[]>([])
  let loading = $state(false)

  const session = $derived(app.sessions.find((s) => s.id === app.drilldownSessionId) ?? null)
  const open = $derived(app.drilldownSessionId != null)

  $effect(() => {
    const id = app.drilldownSessionId
    if (!id) {
      turns = []
      return
    }
    loading = true
    api
      .turns(id)
      .then((t) => (turns = t))
      .catch(() => (turns = []))
      .finally(() => (loading = false))
  })

  // ── Per-turn token series ─────────────────────────────────────────────────
  const tokenData = $derived(
    turns.map((t) => ({
      turn: t.turn_index,
      input: t.input_text_tokens,
      output: t.output_text_tokens,
    })),
  )

  const tokenConfig = {
    input: { label: 'Input tokens', color: 'var(--chart-2)' },
    output: { label: 'Output tokens', color: 'var(--chart-5)' },
  } satisfies Chart.ChartConfig

  // ── Cumulative cost ───────────────────────────────────────────────────────
  const costData = $derived.by(() => {
    let acc = 0
    return turns.map((t) => {
      acc += t.cost_usd
      return { turn: t.turn_index, cumulative: acc }
    })
  })

  const costConfig = {
    cumulative: { label: 'Cumulative cost', color: 'var(--chart-1)' },
  } satisfies Chart.ChartConfig

  // ── Cost buckets (derived from pricing) ───────────────────────────────────
  const buckets = $derived.by(() => {
    const pricing = app.config?.pricing
    if (!pricing || turns.length === 0) return []
    const textIn = turns.reduce(
      (a, t) => a + ((t.input_text_tokens + t.tool_call_tokens) / 1_000_000) * pricing.text_input_per_mtok,
      0,
    )
    const textOut = turns.reduce(
      (a, t) => a + (t.output_text_tokens / 1_000_000) * pricing.text_output_per_mtok,
      0,
    )
    const total = turns.reduce((a, t) => a + t.cost_usd, 0)
    const audio = Math.max(0, total - textIn - textOut)
    return [
      { bucket: 'Text input', value: textIn, color: 'var(--chart-2)' },
      { bucket: 'Text output', value: textOut, color: 'var(--chart-5)' },
      { bucket: 'Audio I/O', value: audio, color: 'var(--chart-1)' },
    ].filter((b) => b.value > 0)
  })

  const bucketConfig = {
    value: { label: 'Cost' },
    'Text input': { label: 'Text input', color: 'var(--chart-2)' },
    'Text output': { label: 'Text output', color: 'var(--chart-5)' },
    'Audio I/O': { label: 'Audio I/O', color: 'var(--chart-1)' },
  } satisfies Chart.ChartConfig

  const totalTokensIn = $derived(turns.reduce((a, t) => a + t.input_text_tokens, 0))
  const totalTokensOut = $derived(turns.reduce((a, t) => a + t.output_text_tokens, 0))
</script>

<Sheet.Root
  {open}
  onOpenChange={(v) => {
    if (!v) app.drilldownSessionId = null
  }}
>
  <Sheet.Content side="right" class="w-full overflow-y-auto sm:max-w-xl">
    <Sheet.Header>
      <Sheet.Title>
        {session?.scenario_name ?? 'Session'}
        {#if session}
          <Badge variant="outline" class="ml-2">
            {configLabel(session.tools_enabled, session.headroom_enabled)}
          </Badge>
        {/if}
      </Sheet.Title>
      <Sheet.Description>
        {#if session}
          {session.mode} session · {duration(session.duration_seconds)} ·
          {usd(session.total_cost_usd)} total
        {/if}
      </Sheet.Description>
    </Sheet.Header>

    <div class="flex flex-col gap-6 px-4 pb-8">
      {#if loading}
        <p class="text-sm text-muted-foreground">Loading turns…</p>
      {:else if turns.length === 0}
        <p class="text-sm text-muted-foreground">No turn data recorded for this session.</p>
      {:else}
        <div class="grid grid-cols-3 gap-3 text-center">
          <div class="rounded-lg border p-3">
            <div class="text-lg font-semibold tabular-nums">{turns.length}</div>
            <div class="text-xs text-muted-foreground">turns</div>
          </div>
          <div class="rounded-lg border p-3">
            <div class="text-lg font-semibold tabular-nums">{tokens(totalTokensIn)}</div>
            <div class="text-xs text-muted-foreground">tokens in</div>
          </div>
          <div class="rounded-lg border p-3">
            <div class="text-lg font-semibold tabular-nums">{tokens(totalTokensOut)}</div>
            <div class="text-xs text-muted-foreground">tokens out</div>
          </div>
        </div>

        <div>
          <h3 class="mb-2 text-sm font-medium">Tokens per turn</h3>
          <Chart.Container config={tokenConfig} class="h-44 w-full">
            <AreaChart
              data={tokenData}
              x="turn"
              series={[
                { key: 'input', label: 'Input', color: 'var(--color-input)' },
                { key: 'output', label: 'Output', color: 'var(--color-output)' },
              ]}
              props={{ area: { 'fill-opacity': 0.3 } }}
            >
              {#snippet tooltip()}
                <Chart.Tooltip />
              {/snippet}
            </AreaChart>
          </Chart.Container>
        </div>

        <Separator />

        <div>
          <h3 class="mb-2 text-sm font-medium">Cumulative cost</h3>
          <Chart.Container config={costConfig} class="h-44 w-full">
            <LineChart
              data={costData}
              x="turn"
              y="cumulative"
              props={{
                spline: { stroke: 'var(--color-cumulative)', 'stroke-width': 2 },
                yAxis: { format: (v: number) => usd(v) },
              }}
            >
              {#snippet tooltip()}
                <Chart.Tooltip />
              {/snippet}
            </LineChart>
          </Chart.Container>
        </div>

        {#if buckets.length > 0}
          <Separator />
          <div>
            <h3 class="mb-2 text-sm font-medium">Cost split</h3>
            <Chart.Container config={bucketConfig} class="mx-auto h-48 w-full">
              <PieChart
                data={buckets}
                key="bucket"
                value="value"
                cRange={buckets.map((b) => b.color)}
                innerRadius={-20}
                padding={8}
              >
                {#snippet tooltip()}
                  <Chart.Tooltip />
                {/snippet}
              </PieChart>
            </Chart.Container>
            <div class="mt-2 flex justify-center gap-4 text-xs text-muted-foreground">
              {#each buckets as b (b.bucket)}
                <span class="flex items-center gap-1.5">
                  <span class="size-2 rounded-full" style="background: {b.color}"></span>
                  {b.bucket} {usd(b.value)}
                </span>
              {/each}
            </div>
          </div>
        {/if}
      {/if}
    </div>
  </Sheet.Content>
</Sheet.Root>
