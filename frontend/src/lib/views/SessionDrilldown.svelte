<script lang="ts">
  import * as Sheet from '$lib/components/ui/sheet'
  import * as Chart from '$lib/components/ui/chart'
  import { Badge } from '$lib/components/ui/badge'
  import { Separator } from '$lib/components/ui/separator'
  import { AreaChart, LineChart, PieChart } from 'layerchart'
  import { api, type Turn } from '$lib/api'
  import { app } from '$lib/state.svelte'
  import { usd, tokens, duration, configLabel, timestamp } from '$lib/format'
  import ZapIcon from '@lucide/svelte/icons/zap'
  import MessageSquareIcon from '@lucide/svelte/icons/message-square'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import WrenchIcon from '@lucide/svelte/icons/wrench'

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
  const totalCost = $derived(turns.reduce((a, t) => a + t.cost_usd, 0))
  const totalToolCalls = $derived(turns.reduce((a, t) => a + t.tool_call_tokens, 0))

  // Costliest turn
  const costliestTurn = $derived(turns.reduce<Turn | null>((max, t) => (!max || t.cost_usd > max.cost_usd) ? t : max, null))
</script>

<Sheet.Root
  {open}
  onOpenChange={(v) => {
    if (!v) app.drilldownSessionId = null
  }}
>
  <Sheet.Content side="right" class="w-full overflow-y-auto sm:max-w-2xl p-0">
    <!-- Hero header -->
    <div class="sticky top-0 z-10 border-b border-border/50 bg-background/95 backdrop-blur-md px-5 pt-5 pb-4">
      <Sheet.Header>
        <Sheet.Title class="text-lg font-bold flex flex-wrap items-center gap-2">
          <span>{session?.scenario_name ?? 'Session'}</span>
          {#if session}
            <Badge variant="outline" class="text-[10px] font-mono">
              {configLabel(session.tools_enabled, session.headroom_enabled)}
            </Badge>
            <Badge variant="secondary" class="text-[10px] capitalize">{session.mode}</Badge>
          {/if}
        </Sheet.Title>
        <Sheet.Description class="text-xs text-muted-foreground mt-1">
          {#if session}
            {duration(session.duration_seconds)} session · {turns.length} turns · recorded {timestamp(session.created_at)}
          {/if}
        </Sheet.Description>
      </Sheet.Header>
    </div>

    <div class="flex flex-col gap-5 px-5 pb-8 pt-4">
      {#if loading}
        <div class="flex items-center justify-center py-16">
          <div class="flex flex-col items-center gap-3">
            <div class="size-8 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
            <p class="text-sm text-muted-foreground">Loading turn data…</p>
          </div>
        </div>
      {:else if turns.length === 0}
        <div class="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <MessageSquareIcon class="size-10 text-muted-foreground/30" />
          <p class="text-sm text-muted-foreground">No turn data recorded for this session.</p>
        </div>
      {:else}
        <!-- Summary stat cards -->
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-xl border border-border/50 bg-card/40 p-3 flex flex-col gap-1">
            <span class="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Turns</span>
            <span class="text-2xl font-bold tabular-nums text-foreground">{turns.length}</span>
          </div>
          <div class="rounded-xl border border-primary/20 bg-primary/5 p-3 flex flex-col gap-1">
            <span class="text-[10px] uppercase tracking-wider text-primary/70 font-semibold">Total Cost</span>
            <span class="text-2xl font-bold tabular-nums text-primary">{usd(totalCost)}</span>
          </div>
          <div class="rounded-xl border border-border/50 bg-card/40 p-3 flex flex-col gap-1">
            <span class="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1">
              <ArrowUpIcon class="size-3" />Tokens in
            </span>
            <span class="text-2xl font-bold tabular-nums text-chart-2">{tokens(totalTokensIn)}</span>
          </div>
          <div class="rounded-xl border border-border/50 bg-card/40 p-3 flex flex-col gap-1">
            <span class="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1">
              <ArrowDownIcon class="size-3" />Tokens out
            </span>
            <span class="text-2xl font-bold tabular-nums text-chart-5">{tokens(totalTokensOut)}</span>
          </div>
        </div>

        {#if costliestTurn}
          <div class="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
            <ZapIcon class="size-4 text-amber-400 shrink-0" />
            <div class="min-w-0">
              <p class="text-xs font-semibold text-amber-300">Costliest turn: #{ costliestTurn.turn_index}</p>
              <p class="text-[11px] text-muted-foreground">
                {usd(costliestTurn.cost_usd)} · {tokens(costliestTurn.input_text_tokens)} in / {tokens(costliestTurn.output_text_tokens)} out
                {#if costliestTurn.tool_call_tokens > 0}
                  · {tokens(costliestTurn.tool_call_tokens)} tool tokens
                {/if}
              </p>
            </div>
          </div>
        {/if}

        <!-- Tokens per turn area chart -->
        <div>
          <h3 class="mb-3 text-sm font-semibold">Tokens per turn</h3>
          <Chart.Container config={tokenConfig} class="h-44 w-full">
            <AreaChart
              data={tokenData}
              x="turn"
              series={[
                { key: 'input', label: 'Input', color: 'var(--color-input)' },
                { key: 'output', label: 'Output', color: 'var(--color-output)' },
              ]}
              props={{ area: { 'fill-opacity': 0.25 } }}
            >
              {#snippet tooltip()}
                <Chart.Tooltip />
              {/snippet}
            </AreaChart>
          </Chart.Container>
        </div>

        <Separator class="opacity-30" />

        <!-- Cumulative cost line chart -->
        <div>
          <h3 class="mb-3 text-sm font-semibold">Cumulative cost</h3>
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
          <Separator class="opacity-30" />
          <!-- Cost split pie -->
          <div>
            <h3 class="mb-3 text-sm font-semibold">Cost split by type</h3>
            <div class="grid grid-cols-2 gap-4 items-center">
              <Chart.Container config={bucketConfig} class="h-44 w-full">
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
              <div class="flex flex-col gap-2">
                {#each buckets as b (b.bucket)}
                  <div class="flex items-center justify-between gap-3 text-xs">
                    <span class="flex items-center gap-2 text-muted-foreground">
                      <span class="size-2.5 rounded-sm shrink-0" style="background: {b.color}"></span>
                      {b.bucket}
                    </span>
                    <span class="font-mono font-semibold tabular-nums text-foreground">{usd(b.value)}</span>
                  </div>
                {/each}
              </div>
            </div>
          </div>
        {/if}

        <Separator class="opacity-30" />

        <!-- Per-turn breakdown table -->
        <div>
          <h3 class="mb-3 text-sm font-semibold">Turn-by-turn breakdown</h3>
          <div class="rounded-xl border border-border/40 overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="border-b border-border/40 bg-card/40">
                    <th class="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">#</th>
                    <th class="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Tok in</th>
                    <th class="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Tok out</th>
                    <th class="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Tools</th>
                    <th class="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {#each turns as t (t.turn_index)}
                    <tr class="border-b border-border/20 hover:bg-card/30 transition-colors {t === costliestTurn ? 'bg-amber-500/5' : ''}">
                      <td class="px-3 py-2 font-mono text-muted-foreground">{t.turn_index}</td>
                      <td class="px-3 py-2 text-right font-mono tabular-nums text-chart-2">{tokens(t.input_text_tokens)}</td>
                      <td class="px-3 py-2 text-right font-mono tabular-nums text-chart-5">{tokens(t.output_text_tokens)}</td>
                      <td class="px-3 py-2 text-right font-mono tabular-nums text-amber-400">
                        {#if t.tool_call_tokens > 0}
                          <span class="flex items-center justify-end gap-1">
                            <WrenchIcon class="size-3" />{tokens(t.tool_call_tokens)}
                          </span>
                        {:else}
                          <span class="text-muted-foreground/30">—</span>
                        {/if}
                      </td>
                      <td class="px-3 py-2 text-right font-mono tabular-nums font-semibold text-primary">{usd(t.cost_usd)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      {/if}
    </div>
  </Sheet.Content>
</Sheet.Root>
