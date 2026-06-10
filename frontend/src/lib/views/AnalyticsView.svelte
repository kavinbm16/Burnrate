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
  import { BarChart } from 'layerchart'
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

  // ── Summary stats ─────────────────────────────────────────────────────────
  const totalSpend = $derived(app.sessions.reduce((a, s) => a + s.total_cost_usd, 0))
  const avgCostPerHour = $derived.by(() => {
    const rows = app.comparison.filter((r) => r.duration_seconds > 0)
    if (rows.length === 0) return 0
    return rows.reduce((a, r) => a + r.cost_per_hour_usd, 0) / rows.length
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
    // Compare matched pairs: (tools off) baseline vs headroom-only, (tools on) tools-only vs full
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

  // ── Projections ───────────────────────────────────────────────────────────
  let projectionSessionId = $state<string | null>(null)
  let hoursPerDay = $state(8)
  let robots = $state(100)
  let projection = $state<Projection | null>(null)

  $effect(() => {
    if (!projectionSessionId && app.sessions.length > 0) {
      projectionSessionId = app.sessions[0].id
    }
  })

  $effect(() => {
    const id = projectionSessionId
    const h = hoursPerDay
    const r = robots
    if (!id) return
    api
      .projection(id, h, r)
      .then((p) => (projection = p))
      .catch(() => (projection = null))
  })

  // ── Actions ───────────────────────────────────────────────────────────────
  async function remove(sessionId: string) {
    try {
      await api.deleteSession(sessionId)
      toast.success('Session deleted')
      if (projectionSessionId === sessionId) projectionSessionId = null
      app.refreshSessions()
    } catch (e) {
      toast.error(String(e))
    }
  }

  onMount(() => {
    app.refreshSessions()
  })
</script>

<div class="flex flex-col gap-6">
  <!-- Stat cards -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
    <Card.Root>
      <Card.Header>
        <Card.Description>Benchmark sessions</Card.Description>
        <Card.Title class="text-2xl tabular-nums">{app.sessions.length}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root>
      <Card.Header>
        <Card.Description>Total measured spend</Card.Description>
        <Card.Title class="text-2xl tabular-nums">{usd(totalSpend)}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root>
      <Card.Header>
        <Card.Description>Avg cost / hour</Card.Description>
        <Card.Title class="text-2xl tabular-nums">{usd(avgCostPerHour)}</Card.Title>
      </Card.Header>
    </Card.Root>
  </div>

  <!-- Insight cards -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    <Card.Root>
      <Card.Content class="flex items-center gap-4">
        <div class="flex size-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
          <TrendingDownIcon class="size-5" />
        </div>
        <div>
          <p class="text-sm font-medium">
            {#if headroomSavingsPct != null}
              Headroom changes cost/hr by {headroomSavingsPct >= 0 ? '−' : '+'}{Math.abs(headroomSavingsPct).toFixed(1)}%
            {:else}
              Headroom savings — needs runs with and without headroom
            {/if}
          </p>
          <p class="text-xs text-muted-foreground">Matched-pair average across configurations</p>
        </div>
      </Card.Content>
    </Card.Root>
    <Card.Root>
      <Card.Content class="flex items-center gap-4">
        <div class="flex size-10 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500">
          <WrenchIcon class="size-5" />
        </div>
        <div>
          <p class="text-sm font-medium">
            {#if toolsOverheadPerHour != null}
              MCP tools add {usd(toolsOverheadPerHour)}/hr per robot
            {:else}
              Tool overhead — needs runs with and without tools
            {/if}
          </p>
          <p class="text-xs text-muted-foreground">Definitions + call tokens vs baseline</p>
        </div>
      </Card.Content>
    </Card.Root>
  </div>

  <!-- Cost chart -->
  {#if chartData.length > 0}
    <Card.Root>
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
  <Card.Root>
    <Card.Header>
      <Card.Title>Fleet cost projection</Card.Title>
      <Card.Description>
        Extrapolates the selected session to daily, monthly, and fleet scale
      </Card.Description>
    </Card.Header>
    <Card.Content class="grid gap-6 lg:grid-cols-2">
      <div class="flex flex-col gap-5">
        <div class="grid gap-2">
          <Label>Reference session</Label>
          <select
            bind:value={projectionSessionId}
            class="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
          >
            {#each app.sessions as s (s.id)}
              <option value={s.id}>
                {s.scenario_name} · {configLabel(s.tools_enabled, s.headroom_enabled)} · {usd(s.total_cost_usd)}
              </option>
            {/each}
          </select>
        </div>
        <div class="grid gap-2">
          <div class="flex justify-between">
            <Label>Active hours / day</Label>
            <span class="font-mono text-sm tabular-nums">{hoursPerDay}h</span>
          </div>
          <Slider type="single" bind:value={hoursPerDay} min={1} max={24} step={1} />
        </div>
        <div class="grid gap-2">
          <Label for="robots-input">Robots in fleet</Label>
          <Input id="robots-input" type="number" min="1" bind:value={robots} class="w-32" />
        </div>
      </div>

      {#if projection}
        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-lg border p-4">
            <div class="flex items-center gap-2 text-xs text-muted-foreground">
              <WalletIcon class="size-3.5" /> Per robot / day
            </div>
            <div class="mt-1 text-xl font-semibold tabular-nums">{usd(projection.per_day_usd, 2)}</div>
          </div>
          <div class="rounded-lg border p-4">
            <div class="flex items-center gap-2 text-xs text-muted-foreground">
              <WalletIcon class="size-3.5" /> Per robot / month
            </div>
            <div class="mt-1 text-xl font-semibold tabular-nums">{usd(projection.per_month_usd, 2)}</div>
          </div>
          <div class="rounded-lg border p-4">
            <div class="flex items-center gap-2 text-xs text-muted-foreground">
              <BotIcon class="size-3.5" /> Fleet / day ({robots})
            </div>
            <div class="mt-1 text-xl font-semibold tabular-nums">{usd(projection.fleet_per_day_usd, 2)}</div>
          </div>
          <div class="rounded-lg border bg-primary/5 p-4">
            <div class="flex items-center gap-2 text-xs text-muted-foreground">
              <BotIcon class="size-3.5" /> Fleet / month ({robots})
            </div>
            <div class="mt-1 text-xl font-semibold tabular-nums">{usd(projection.fleet_per_month_usd, 2)}</div>
          </div>
        </div>
      {:else}
        <div class="flex items-center justify-center text-sm text-muted-foreground">
          Run a benchmark to project costs
        </div>
      {/if}
    </Card.Content>
  </Card.Root>

  <!-- Sessions table -->
  <Card.Root>
    <Card.Header class="flex flex-row items-center justify-between">
      <div>
        <Card.Title>All sessions</Card.Title>
        <Card.Description>Every benchmark run, live and simulated</Card.Description>
      </div>
      <div class="flex gap-2">
        <Button variant="ghost" size="sm" onclick={() => app.refreshSessions()}>
          <RefreshCwIcon class="size-3.5" />
        </Button>
        <Button variant="outline" size="sm" href={api.exportCsvUrl} download>
          <DownloadIcon class="size-3.5" /> CSV
        </Button>
        <Button variant="outline" size="sm" href={api.exportJsonUrl} target="_blank">
          <DownloadIcon class="size-3.5" /> JSON
        </Button>
      </div>
    </Card.Header>
    <Card.Content>
      {#if app.comparison.length === 0}
        <p class="py-8 text-center text-sm text-muted-foreground">
          No sessions yet — run a sim or start a live session.
        </p>
      {:else}
        <Table.Root>
          <Table.Header>
            <Table.Row>
              <Table.Head>Scenario</Table.Head>
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
            {#each app.comparison as row (row.session_id)}
              {@const session = app.sessions.find((s) => s.id === row.session_id)}
              <Table.Row>
                <Table.Cell>
                  <div class="font-medium">{row.scenario_name}</div>
                  {#if session}
                    <div class="text-xs text-muted-foreground">{timestamp(session.created_at)}</div>
                  {/if}
                </Table.Cell>
                <Table.Cell>
                  <Badge variant={row.tools_enabled || row.headroom_enabled ? 'default' : 'secondary'}>
                    {configLabel(row.tools_enabled, row.headroom_enabled)}
                  </Badge>
                </Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums">
                  {tokens(row.total_input_text_tokens)}
                </Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums">
                  {tokens(row.total_output_text_tokens)}
                </Table.Cell>
                <Table.Cell class="text-right tabular-nums">{duration(row.duration_seconds)}</Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums">{usd(row.total_cost_usd)}</Table.Cell>
                <Table.Cell class="text-right font-mono tabular-nums">{usd(row.cost_per_hour_usd, 2)}</Table.Cell>
                <Table.Cell class="text-right">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onclick={() => (app.drilldownSessionId = row.session_id)}
                    title="Inspect turns"
                  >
                    <SearchIcon class="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    class="text-destructive"
                    onclick={() => remove(row.session_id)}
                    title="Delete session"
                  >
                    <Trash2Icon class="size-3.5" />
                  </Button>
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
