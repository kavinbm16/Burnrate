<script lang="ts">
  import { onMount } from 'svelte'
  import { toast } from 'svelte-sonner'
  import * as Card from '$lib/components/ui/card'
  import * as Table from '$lib/components/ui/table'
  import * as Chart from '$lib/components/ui/chart'
  import { Button } from '$lib/components/ui/button'
  import { Badge } from '$lib/components/ui/badge'
  import { Slider } from '$lib/components/ui/slider'
  import { Label } from '$lib/components/ui/label'
  import { Input } from '$lib/components/ui/input'
  import { BarChart, LineChart } from 'layerchart'
  import { api, type Projection } from '$lib/api'
  import { app } from '$lib/state.svelte'
  import { usd, tokens, duration, timestamp, configLabel } from '$lib/format'
  import SessionDrilldown from './SessionDrilldown.svelte'
  import DownloadIcon from '@lucide/svelte/icons/download'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import SearchIcon from '@lucide/svelte/icons/search'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import TrendingDownIcon from '@lucide/svelte/icons/trending-down'
  import WrenchIcon from '@lucide/svelte/icons/wrench'
  import WalletIcon from '@lucide/svelte/icons/wallet'
  import BotIcon from '@lucide/svelte/icons/bot'
  import SlidersHorizontalIcon from '@lucide/svelte/icons/sliders-horizontal'

  // ── Search & Filter State ──────────────────────────────────────────────────
  let searchFilter = $state('')
  let modeFilter = $state<'all' | 'live' | 'sim'>('all')
  let configFilter = $state<'all' | 'baseline' | 'tools' | 'headroom' | 'full'>('all')
  let sortBy = $state<'date_desc' | 'date_asc' | 'cost_desc' | 'cost_asc' | 'duration_desc' | 'duration_asc'>('date_desc')

  // ── Summary stats ─────────────────────────────────────────────────────────
  const totalSpend = $derived(app.sessions.reduce((a, s) => a + s.total_cost_usd, 0))
  const avgCostPerHour = $derived.by(() => {
    const rows = app.comparison.filter((r) => r.duration_seconds > 0)
    if (rows.length === 0) return 0
    return rows.reduce((a, r) => a + r.cost_per_hour_usd, 0) / rows.length
  })

  // ── Filtered & Sorted Sessions ─────────────────────────────────────────────
  const filteredComparison = $derived.by(() => {
    let items = app.comparison.filter((r) => {
      const session = app.sessions.find((s) => s.id === r.session_id)
      if (!session) return false
      
      // Mode filter
      if (modeFilter !== 'all' && session.mode !== modeFilter) return false
      
      // Config filter
      if (configFilter !== 'all') {
        if (configFilter === 'baseline' && (r.tools_enabled || r.headroom_enabled)) return false
        if (configFilter === 'tools' && (!r.tools_enabled || r.headroom_enabled)) return false
        if (configFilter === 'headroom' && (r.tools_enabled || !r.headroom_enabled)) return false
        if (configFilter === 'full' && (!r.tools_enabled || !r.headroom_enabled)) return false
      }
      
      // Search filter
      if (searchFilter && !r.scenario_name.toLowerCase().includes(searchFilter.toLowerCase())) return false
      
      return true
    })
    
    return items.sort((a, b) => {
      const sa = app.sessions.find((s) => s.id === a.session_id)
      const sb = app.sessions.find((s) => s.id === b.session_id)
      if (!sa || !sb) return 0
      
      if (sortBy === 'date_desc') return new Date(sb.created_at).getTime() - new Date(sa.created_at).getTime()
      if (sortBy === 'date_asc') return new Date(sa.created_at).getTime() - new Date(sb.created_at).getTime()
      if (sortBy === 'cost_desc') return b.total_cost_usd - a.total_cost_usd
      if (sortBy === 'cost_asc') return a.total_cost_usd - b.total_cost_usd
      if (sortBy === 'duration_desc') return b.duration_seconds - a.duration_seconds
      if (sortBy === 'duration_asc') return a.duration_seconds - b.duration_seconds
      return 0
    })
  })

  // ── Config comparison chart ───────────────────────────────────────────────
  const chartData = $derived(
    app.comparison
      .filter((r) => r.duration_seconds > 0)
      .map((r) => ({
        label: `${r.scenario_name} · ${configLabel(r.tools_enabled, r.headroom_enabled)}`,
        costPerHour: r.cost_per_hour_usd,
      }))
      .sort((a, b) => b.costPerHour - a.costPerHour),
  )

  const chartConfig = {
    costPerHour: { label: 'Cost / hour', color: 'var(--chart-1)' },
  } satisfies Chart.ChartConfig

  // ── Insights: headroom savings + tools overhead ───────────────────────────
  function meanCostPerHour(tools: boolean, headroom: boolean): number | null {
    const rows = app.comparison.filter(
      (r) => r.tools_enabled === tools && r.headroom_enabled === headroom && r.duration_seconds > 0,
    )
    if (rows.length === 0) return null
    return rows.reduce((a, r) => a + r.cost_per_hour_usd, 0) / rows.length
  }

  const headroomSavingsPct = $derived.by(() => {
    const pairs: [number | null, number | null][] = [
      [meanCostPerHour(false, false), meanCostPerHour(false, true)],
      [meanCostPerHour(true, false), meanCostPerHour(true, true)],
    ]
    const pcts = pairs
      .filter(([base, hr]) => base != null && hr != null && base > 0)
      .map(([base, hr]) => ((base! - hr!) / base!) * 100)
    if (pcts.length === 0) return null
    return pcts.reduce((a, b) => a + b, 0) / pcts.length
  })

  const toolsOverheadPerHour = $derived.by(() => {
    const pairs: [number | null, number | null][] = [
      [meanCostPerHour(false, false), meanCostPerHour(true, false)],
      [meanCostPerHour(false, true), meanCostPerHour(true, true)],
    ]
    const deltas = pairs
      .filter(([base, t]) => base != null && t != null)
      .map(([base, t]) => t! - base!)
    if (deltas.length === 0) return null
    return deltas.reduce((a, b) => a + b, 0) / deltas.length
  })

  // ── Projections (Multi-Session comparison) ──────────────────────────────────
  let selectedProjectionIds = $state<string[]>([])
  let hoursPerDay = $state(8)
  let robotsInput = $state('100')
  const robots = $derived(Math.max(1, parseInt(robotsInput, 10) || 1))

  $effect(() => {
    if (selectedProjectionIds.length === 0 && app.sessions.length > 0) {
      selectedProjectionIds = [app.sessions[0].id]
    }
  })

  // Chart data for projections: extrapolated costs for selected sessions from 1h to 24h
  const projectionChartData = $derived.by(() => {
    const data: any[] = []
    const selectedSessions = app.sessions.filter(s => selectedProjectionIds.includes(s.id))
    if (selectedSessions.length === 0) return []

    for (let h = 1; h <= 24; h++) {
      const point: any = { hour: h }
      selectedSessions.forEach(s => {
        const cost = s.duration_seconds > 0 ? (s.total_cost_usd / s.duration_seconds) * (h * 3600) : 0
        point[s.id] = cost
      })
      data.push(point)
    }
    return data
  })

  // Config mapping for projection chart keys
  const projectionChartConfig = $derived.by(() => {
    const cfg: any = {}
    app.sessions
      .filter(s => selectedProjectionIds.includes(s.id))
      .forEach((s, idx) => {
        cfg[s.id] = {
          label: `${s.scenario_name} · ${configLabel(s.tools_enabled, s.headroom_enabled)}`,
          color: `var(--chart-${(idx % 5) + 1})`
        }
      })
    return cfg
  })

  // ── Actions ───────────────────────────────────────────────────────────────
  async function remove(sessionId: string) {
    try {
      await api.deleteSession(sessionId)
      toast.success('Session deleted')
      selectedProjectionIds = selectedProjectionIds.filter(id => id !== sessionId)
      app.refreshSessions()
    } catch (e) {
      toast.error(String(e))
    }
  }

  function toggleProjectionSelection(id: string) {
    if (selectedProjectionIds.includes(id)) {
      if (selectedProjectionIds.length > 1) {
        selectedProjectionIds = selectedProjectionIds.filter(x => x !== id)
      } else {
        toast.warning('Keep at least one session selected for projection')
      }
    } else {
      if (selectedProjectionIds.length < 4) {
        selectedProjectionIds = [...selectedProjectionIds, id]
      } else {
        toast.warning('Compare up to 4 sessions at once')
      }
    }
  }

  onMount(() => {
    app.refreshSessions()
  })
</script>

<div class="flex flex-col gap-6">
  <!-- Stat cards -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
    <Card.Root class="glass glow-hover">
      <Card.Header>
        <Card.Description>Benchmark Sessions</Card.Description>
        <Card.Title class="text-3xl font-bold tracking-tight tabular-nums">{app.sessions.length}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root class="glass glow-hover">
      <Card.Header>
        <Card.Description>Total Measured Spend</Card.Description>
        <Card.Title class="text-3xl font-bold tracking-tight tabular-nums text-emerald-400">{usd(totalSpend)}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root class="glass glow-hover">
      <Card.Header>
        <Card.Description>Avg Cost / Hour</Card.Description>
        <Card.Title class="text-3xl font-bold tracking-tight tabular-nums text-cyan-400">{usd(avgCostPerHour)}</Card.Title>
      </Card.Header>
    </Card.Root>
  </div>

  <!-- Insight cards -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    <Card.Root class="glass glow-hover border-emerald-500/10">
      <Card.Content class="flex items-center gap-4 py-5">
        <div class="flex size-11 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          <TrendingDownIcon class="size-5" />
        </div>
        <div>
          <p class="text-sm font-semibold">
            {#if headroomSavingsPct != null}
              Headroom changes cost/hr by {headroomSavingsPct >= 0 ? '−' : '+'}{Math.abs(headroomSavingsPct).toFixed(1)}%
            {:else}
              Headroom savings — run configs with & without headroom
            {/if}
          </p>
          <p class="text-xs text-muted-foreground mt-0.5">Matched-pair average across configurations</p>
        </div>
      </Card.Content>
    </Card.Root>
    <Card.Root class="glass glow-hover border-amber-500/10">
      <Card.Content class="flex items-center gap-4 py-5">
        <div class="flex size-11 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.1)]">
          <WrenchIcon class="size-5" />
        </div>
        <div>
          <p class="text-sm font-semibold">
            {#if toolsOverheadPerHour != null}
              MCP tools add {usd(toolsOverheadPerHour)}/hr per robot
            {:else}
              Tool overhead — run configs with & without tools
            {/if}
          </p>
          <p class="text-xs text-muted-foreground mt-0.5">Definitions + call tokens vs baseline</p>
        </div>
      </Card.Content>
    </Card.Root>
  </div>

  <!-- Cost chart -->
  {#if chartData.length > 0}
    <Card.Root class="glass">
      <Card.Header>
        <Card.Title>Cost per hour by configuration</Card.Title>
        <Card.Description>Each bar is one completed session, normalized to one hour</Card.Description>
      </Card.Header>
      <Card.Content>
        <Chart.Container config={chartConfig} class="h-64 w-full">
          <BarChart
            data={chartData}
            x="label"
            y="costPerHour"
            yPadding={[0, 16]}
            props={{
              bars: { fill: 'var(--color-costPerHour)', radius: 6, strokeWidth: 0 },
              xAxis: { format: (v: string) => (v.length > 24 ? v.slice(0, 24) + '…' : v) },
              yAxis: { format: (v: number) => usd(v, 2) },
            }}
          >
            {#snippet tooltip()}
              <Chart.Tooltip />
            {/snippet}
          </BarChart>
        </Chart.Container>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- Projection panel -->
  <Card.Root class="glass">
    <Card.Header>
      <Card.Title>Comparative cost projections</Card.Title>
      <Card.Description>
        Select up to 4 reference sessions to compare fleet cost projection curves.
      </Card.Description>
    </Card.Header>
    <Card.Content class="grid gap-6 lg:grid-cols-5">
      <!-- Selector controls (2 columns) -->
      <div class="flex flex-col gap-5 lg:col-span-2">
        <div class="grid gap-2">
          <Label class="font-semibold text-xs text-muted-foreground uppercase tracking-wider">Reference Sessions (Select to compare)</Label>
          <div class="flex flex-col gap-1.5 max-h-48 overflow-y-auto border rounded-lg p-2 bg-card/25">
            {#each app.sessions as s (s.id)}
              <button
                class="flex items-center justify-between rounded px-2.5 py-1.5 text-left text-xs border transition-colors
                  {selectedProjectionIds.includes(s.id)
                    ? 'bg-primary/10 border-primary text-foreground font-medium'
                    : 'border-transparent hover:bg-card/60 text-muted-foreground'}"
                onclick={() => toggleProjectionSelection(s.id)}
              >
                <span class="truncate">{s.scenario_name} · {configLabel(s.tools_enabled, s.headroom_enabled)}</span>
                <span class="font-mono font-bold text-foreground text-glow-primary">{usd(s.total_cost_usd)}</span>
              </button>
            {/each}
            {#if app.sessions.length === 0}
              <p class="text-xs text-muted-foreground p-2">Run a sim session to select configs.</p>
            {/if}
          </div>
        </div>

        <div class="grid gap-2">
          <div class="flex justify-between">
            <Label class="font-medium">Active Hours / Day</Label>
            <span class="font-mono text-xs font-bold text-primary tabular-nums">{hoursPerDay}h</span>
          </div>
          <Slider value={[hoursPerDay]} onValueChange={(val) => hoursPerDay = val[0]} min={1} max={24} step={1} />
        </div>

        <div class="grid gap-2">
          <Label for="robots-input" class="font-medium">Robots in Fleet</Label>
          <Input id="robots-input" type="number" min="1" bind:value={robotsInput} class="w-32" />
        </div>
      </div>

      <!-- Projection displays / line chart (3 columns) -->
      <div class="lg:col-span-3 flex flex-col gap-4">
        {#if selectedProjectionIds.length > 0 && projectionChartData.length > 0}
          <div class="flex-1 min-h-[200px]">
            <Chart.Container config={projectionChartConfig} class="h-56 w-full">
              <LineChart
                data={projectionChartData}
                x="hour"
                series={app.sessions
                  .filter(s => selectedProjectionIds.includes(s.id))
                  .map((s) => ({
                    key: s.id,
                    label: `${s.scenario_name} (${configLabel(s.tools_enabled, s.headroom_enabled)})`,
                  }))}
                props={{
                  yAxis: { format: (v: number) => usd(v, 2) },
                  xAxis: { format: (v: number) => `${v}h` },
                  spline: { strokeWidth: 2 }
                }}
              >
                {#snippet tooltip()}
                  <Chart.Tooltip />
                {/snippet}
              </LineChart>
            </Chart.Container>
          </div>

          <!-- Comparison Grid -->
          <div class="grid grid-cols-2 gap-3 mt-2">
            {#each app.sessions.filter(s => selectedProjectionIds.includes(s.id)) as s, idx}
              {@const day_sec = hoursPerDay * 3600}
              {@const per_day = s.duration_seconds > 0 ? (s.total_cost_usd / s.duration_seconds) * day_sec : 0}
              {@const fleet_month = per_day * 30 * robots}
              <div class="rounded-lg border px-3 py-2 bg-card/20 relative overflow-hidden">
                <span class="absolute top-0 right-0 w-1.5 h-full" style="background: var(--chart-{(idx % 5) + 1})"></span>
                <div class="text-[10px] font-semibold text-muted-foreground truncate">
                  {s.scenario_name} · {configLabel(s.tools_enabled, s.headroom_enabled)}
                </div>
                <div class="mt-1 flex items-baseline justify-between gap-2">
                  <span class="text-sm font-bold tabular-nums text-foreground">{usd(per_day, 2)}<span class="text-[9px] font-normal text-muted-foreground">/day</span></span>
                  <span class="text-xs font-semibold tabular-nums text-primary">{usd(fleet_month, 2)}<span class="text-[8px] font-normal text-muted-foreground">/fleet</span></span>
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="flex-1 flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg p-6 bg-card/10">
            Select at least one reference session to compute comparative cost curves.
          </div>
        {/if}
      </div>
    </Card.Content>
  </Card.Root>

  <!-- Sessions table -->
  <Card.Root class="glass">
    <Card.Header class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
      <div>
        <Card.Title>All session metrics</Card.Title>
        <Card.Description>Replay logs, token footprint, and fleet benchmarks</Card.Description>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onclick={() => app.refreshSessions()} class="h-8">
          <RefreshCwIcon class="size-3.5" />
        </Button>
        <Button variant="outline" size="sm" href={api.exportCsvUrl} download class="h-8">
          <DownloadIcon class="size-3.5 mr-1" /> CSV
        </Button>
        <Button variant="outline" size="sm" href={api.exportJsonUrl} target="_blank" class="h-8">
          <DownloadIcon class="size-3.5 mr-1" /> JSON
        </Button>
      </div>
    </Card.Header>

    <!-- Filters Cockpit -->
    <div class="px-6 pt-4 flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-2 border rounded-lg px-2.5 py-1 bg-card/20 text-xs">
        <SearchIcon class="size-3.5 text-muted-foreground" />
        <input 
          type="text" 
          placeholder="Search scenarios..." 
          bind:value={searchFilter} 
          class="bg-transparent border-0 outline-none w-32 placeholder:text-muted-foreground text-foreground"
        />
      </div>

      <div class="flex items-center gap-2 border rounded-lg px-2.5 py-1 bg-card/20 text-xs">
        <span class="text-muted-foreground">Mode:</span>
        <select bind:value={modeFilter} class="bg-transparent border-0 outline-none text-foreground cursor-pointer font-medium">
          <option value="all">All Modes</option>
          <option value="live">Live only</option>
          <option value="sim">Sim only</option>
        </select>
      </div>

      <div class="flex items-center gap-2 border rounded-lg px-2.5 py-1 bg-card/20 text-xs">
        <span class="text-muted-foreground">Config:</span>
        <select bind:value={configFilter} class="bg-transparent border-0 outline-none text-foreground cursor-pointer font-medium">
          <option value="all">All Configs</option>
          <option value="baseline">Baseline</option>
          <option value="tools">Tools only</option>
          <option value="headroom">Headroom only</option>
          <option value="full">Full stack</option>
        </select>
      </div>

      <div class="flex items-center gap-2 border rounded-lg px-2.5 py-1 bg-card/20 text-xs ml-auto">
        <SlidersHorizontalIcon class="size-3.5 text-muted-foreground" />
        <span class="text-muted-foreground">Sort:</span>
        <select bind:value={sortBy} class="bg-transparent border-0 outline-none text-foreground cursor-pointer font-medium">
          <option value="date_desc">Newest First</option>
          <option value="date_asc">Oldest First</option>
          <option value="cost_desc">Cost (High-Low)</option>
          <option value="cost_asc">Cost (Low-High)</option>
          <option value="duration_desc">Duration (Long-Short)</option>
          <option value="duration_asc">Duration (Short-Long)</option>
        </select>
      </div>
    </div>

    <Card.Content class="pt-4">
      {#if filteredComparison.length === 0}
        <p class="py-8 text-center text-sm text-muted-foreground">
          No matching sessions found. Adjust filters or run a new benchmark.
        </p>
      {:else}
        <Table.Root>
          <Table.Header>
            <Table.Row>
              <Table.Head>Scenario / Session</Table.Head>
              <Table.Head>Config</Table.Head>
              <Table.Head class="text-right">Tokens in</Table.Head>
              <Table.Head class="text-right">Tokens out</Table.Head>
              <Table.Head class="text-right">Duration</Table.Head>
              <Table.Head class="text-right">Cost</Table.Head>
              <Table.Head class="text-right">Cost / hr</Table.Head>
              <Table.Head></Table.Head>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {#each filteredComparison as row (row.session_id)}
              {@const session = app.sessions.find((s) => s.id === row.session_id)}
              <Table.Row class="hover:bg-card/30 transition-colors">
                <Table.Cell>
                  <div class="font-semibold text-foreground">{row.scenario_name}</div>
                  {#if session}
                    <div class="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1.5">
                      <span class="capitalize px-1 rounded bg-card border border-border text-[9px] font-mono text-foreground">{session.mode}</span>
                      {timestamp(session.created_at)}
                    </div>
                  {/if}
                </Table.Cell>
                <Table.Cell>
                  <Badge variant={row.tools_enabled || row.headroom_enabled ? 'default' : 'secondary'} class="text-[10px]">
                    {configLabel(row.tools_enabled, row.headroom_enabled)}
                  </Badge>
                </Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums text-xs">
                  {tokens(row.total_input_text_tokens)}
                </Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums text-xs">
                  {tokens(row.total_output_text_tokens)}
                </Table.Cell>
                <Table.Cell class="text-right tabular-nums text-xs">{duration(row.duration_seconds)}</Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums text-xs text-emerald-400 font-semibold">{usd(row.total_cost_usd)}</Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums text-xs text-cyan-400">{usd(row.cost_per_hour_usd, 2)}</Table.Cell>
                <Table.Cell class="text-right">
                  <div class="flex items-center justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onclick={() => (app.drilldownSessionId = row.session_id)}
                      title="Inspect turns"
                      class="h-7 w-7 text-primary hover:bg-primary/10"
                    >
                      <SearchIcon class="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      class="h-7 w-7 text-destructive hover:bg-destructive/10"
                      onclick={() => remove(row.session_id)}
                      title="Delete session"
                    >
                      <Trash2Icon class="size-3.5" />
                    </Button>
                  </div>
                </Table.Cell>
              </Table.Row>
            {/each}
          </Table.Body>
        </Table.Root>
      {/if}
    </Card.Content>
  </Card.Root>
</div>

<SessionDrilldown />
