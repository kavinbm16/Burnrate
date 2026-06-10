<script lang="ts">
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import * as Card from '$lib/components/ui/card'
  import * as Select from '$lib/components/ui/select'
  import { Switch } from '$lib/components/ui/switch'
  import { Label } from '$lib/components/ui/label'
  import { Progress } from '$lib/components/ui/progress'
  import { Badge } from '$lib/components/ui/badge'
  import { api } from '$lib/api'
  import { app } from '$lib/state.svelte'
  import { usd, duration, configLabel } from '$lib/format'
  import PlayIcon from '@lucide/svelte/icons/play'
  import LayersIcon from '@lucide/svelte/icons/layers'
  import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
  import CircleXIcon from '@lucide/svelte/icons/circle-x'
  import LoaderIcon from '@lucide/svelte/icons/loader'
  import ChartColumnIcon from '@lucide/svelte/icons/chart-column'

  interface TrackedRun {
    runId: string
    label: string
    scenario: string
    status: 'running' | 'done' | 'error'
    progress: number
    total: number
    sessionId: string | null
    costUsd: number | null
    error: string | null
  }

  let scenarioPath = $state('')
  let toolsEnabled = $state(false)
  let headroomEnabled = $state(false)
  let runs = $state<TrackedRun[]>([])
  let matrixRunning = $state(false)

  const selectedScenario = $derived(app.scenarios.find((s) => s.path === scenarioPath) ?? null)

  $effect(() => {
    if (!scenarioPath && app.scenarios.length > 0) scenarioPath = app.scenarios[0].path
  })

  async function pollUntilDone(run: TrackedRun): Promise<void> {
    while (true) {
      await new Promise((r) => setTimeout(r, 1000))
      try {
        const s = await api.simStatus(run.runId)
        run.progress = s.progress ?? run.progress
        run.total = s.total ?? run.total
        if (s.status === 'done') {
          run.status = 'done'
          run.sessionId = s.session_id ?? null
          run.costUsd = s.total_cost_usd ?? null
          toast.success(`${run.label} finished — ${run.costUsd != null ? usd(run.costUsd) : 'done'}`)
          app.refreshSessions()
          return
        }
        if (s.status === 'error' || s.status === 'not_found') {
          run.status = 'error'
          run.error = s.error ?? 'Run not found'
          toast.error(`${run.label} failed: ${run.error}`)
          return
        }
      } catch {
        // transient network error — keep polling
      }
    }
  }

  async function launch(tools: boolean, headroom: boolean): Promise<TrackedRun | null> {
    if (!selectedScenario) return null
    try {
      const { run_id } = await api.startSim({
        scenario_path: scenarioPath,
        tools_enabled: tools,
        headroom_enabled: headroom,
      })
      const run: TrackedRun = {
        runId: run_id,
        label: configLabel(tools, headroom),
        scenario: selectedScenario.name,
        status: 'running',
        progress: 0,
        total: selectedScenario.turn_count,
        sessionId: null,
        costUsd: null,
        error: null,
      }
      runs.unshift(run)
      return run
    } catch (e) {
      toast.error(String(e))
      return null
    }
  }

  async function runSingle() {
    const run = await launch(toolsEnabled, headroomEnabled)
    if (run) pollUntilDone(run)
  }

  async function runFullMatrix() {
    matrixRunning = true
    const configs: [boolean, boolean][] = [
      [false, false],
      [true, false],
      [false, true],
      [true, true],
    ]
    try {
      for (const [tools, headroom] of configs) {
        const run = await launch(tools, headroom)
        if (!run) break
        await pollUntilDone(run)
        if (run.status === 'error') {
          toast.error('Matrix stopped: a run failed')
          break
        }
      }
    } finally {
      matrixRunning = false
    }
  }

  const anyRunning = $derived(runs.some((r) => r.status === 'running'))
</script>

<div class="mx-auto flex max-w-4xl flex-col gap-6">
  <!-- Config card -->
  <Card.Root>
    <Card.Header>
      <Card.Title>Run configuration</Card.Title>
      <Card.Description>
        Pick a scenario and toggle the benchmark axes. Sim mode replays text turns at full API speed
        and extrapolates audio cost from turn duration.
      </Card.Description>
    </Card.Header>
    <Card.Content class="flex flex-col gap-6">
      <div class="grid gap-2">
        <Label>Scenario</Label>
        <Select.Root type="single" bind:value={scenarioPath}>
          <Select.Trigger class="w-full">
            {selectedScenario ? selectedScenario.name : 'Select a scenario'}
          </Select.Trigger>
          <Select.Content>
            {#each app.scenarios as s (s.path)}
              <Select.Item value={s.path} label={s.name} />
            {/each}
          </Select.Content>
        </Select.Root>
        {#if selectedScenario}
          <p class="text-xs text-muted-foreground">
            {selectedScenario.description || 'No description'} ·
            {selectedScenario.turn_count} turns ·
            ~{duration(selectedScenario.estimated_duration_sec)} simulated
          </p>
        {:else if app.scenarios.length === 0}
          <p class="text-xs text-destructive">
            No scenarios found — add YAML files to <code>scenarios/</code>.
          </p>
        {/if}
      </div>

      <div class="flex gap-8">
        <div class="flex items-center gap-3">
          <Switch id="sim-tools" bind:checked={toolsEnabled} />
          <Label for="sim-tools" class="cursor-pointer">
            MCP tools
            <span class="block text-[11px] font-normal text-muted-foreground">
              inject tool definitions
            </span>
          </Label>
        </div>
        <div class="flex items-center gap-3">
          <Switch id="sim-headroom" bind:checked={headroomEnabled} />
          <Label for="sim-headroom" class="cursor-pointer">
            Headroom
            <span class="block text-[11px] font-normal text-muted-foreground">
              compress context
            </span>
          </Label>
        </div>
      </div>
    </Card.Content>
    <Card.Footer class="flex gap-3">
      <Button onclick={runSingle} disabled={!selectedScenario || matrixRunning}>
        <PlayIcon class="size-4" />
        Run {configLabel(toolsEnabled, headroomEnabled)}
      </Button>
      <Button
        variant="secondary"
        onclick={runFullMatrix}
        disabled={!selectedScenario || matrixRunning || anyRunning}
      >
        <LayersIcon class="size-4" />
        {matrixRunning ? 'Running matrix…' : 'Run full matrix (4 configs)'}
      </Button>
    </Card.Footer>
  </Card.Root>

  <!-- Runs -->
  {#if runs.length > 0}
    <Card.Root>
      <Card.Header>
        <Card.Title>Runs this session</Card.Title>
      </Card.Header>
      <Card.Content class="flex flex-col gap-4">
        {#each runs as run (run.runId)}
          <div class="flex flex-col gap-2 rounded-lg border p-4">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                {#if run.status === 'running'}
                  <LoaderIcon class="size-4 animate-spin text-muted-foreground" />
                {:else if run.status === 'done'}
                  <CircleCheckIcon class="size-4 text-emerald-500" />
                {:else}
                  <CircleXIcon class="size-4 text-destructive" />
                {/if}
                <span class="text-sm font-medium">{run.scenario}</span>
                <Badge variant="outline">{run.label}</Badge>
              </div>
              <div class="flex items-center gap-2">
                {#if run.costUsd != null}
                  <span class="font-mono text-sm">{usd(run.costUsd)}</span>
                {/if}
                {#if run.status === 'done' && run.sessionId}
                  <Button
                    variant="ghost"
                    size="sm"
                    onclick={() => app.openDrilldown(run.sessionId!)}
                  >
                    <ChartColumnIcon class="size-3.5" />
                    Analyze
                  </Button>
                {/if}
              </div>
            </div>
            {#if run.status === 'running'}
              <Progress value={run.total > 0 ? (run.progress / run.total) * 100 : 0} />
              <p class="text-xs text-muted-foreground">
                Turn {run.progress} / {run.total || '?'}
              </p>
            {:else if run.status === 'error'}
              <p class="text-xs text-destructive">{run.error}</p>
            {/if}
          </div>
        {/each}
      </Card.Content>
    </Card.Root>
  {/if}
</div>
