<script lang="ts">
  import { onMount } from 'svelte'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import * as Card from '$lib/components/ui/card'
  import * as Select from '$lib/components/ui/select'
  import { Switch } from '$lib/components/ui/switch'
  import { Label } from '$lib/components/ui/label'
  import { Progress } from '$lib/components/ui/progress'
  import { Badge } from '$lib/components/ui/badge'
  import { api, type Turn } from '$lib/api'
  import { app } from '$lib/state.svelte'
  import { usd, duration, configLabel, tokens } from '$lib/format'
  import PlayIcon from '@lucide/svelte/icons/play'
  import LayersIcon from '@lucide/svelte/icons/layers'
  import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
  import CircleXIcon from '@lucide/svelte/icons/circle-x'
  import LoaderIcon from '@lucide/svelte/icons/loader'
  import ChartColumnIcon from '@lucide/svelte/icons/chart-column'
  import InfoIcon from '@lucide/svelte/icons/info'
  import ListTodoIcon from '@lucide/svelte/icons/list-todo'

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
    turns?: Turn[]
  }

  let scenarioPath = $state('')
  let toolsEnabled = $state(false)
  let headroomEnabled = $state(false)
  let runs = $state<TrackedRun[]>([])
  let matrixRunning = $state(false)
  let geminiHealthMsg = $state<string | null>(null)

  onMount(async () => {
    try {
      const h = await api.geminiHealth()
      geminiHealthMsg = h.status === 'error' ? (h.message ?? 'Gemini unreachable') : null
    } catch {
      geminiHealthMsg = 'Backend unreachable — is uvicorn running on :8000?'
    }
  })

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

        if (s.session_id) {
          run.sessionId = s.session_id
          try {
            run.turns = await api.turns(s.session_id)
          } catch {
            // ignore
          }
        }

        if (s.status === 'done') {
          run.status = 'done'
          run.sessionId = s.session_id ?? null
          run.costUsd = s.total_cost_usd ?? null
          if (s.session_id) {
            try {
              run.turns = await api.turns(s.session_id)
            } catch {
              // ignore
            }
          }
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
        // transient
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
        turns: []
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

<div class="w-full flex flex-col gap-5">
  {#if geminiHealthMsg}
    <Card.Root class="border-destructive/40 bg-destructive/5 animate-pulse">
      <Card.Content class="py-4 text-sm">
        <p class="font-medium text-destructive">Gemini Live not reachable</p>
        <p class="mt-1 text-muted-foreground">{geminiHealthMsg}</p>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- HEADER: Scenario + Launch Controls -->
  <Card.Root class="console-panel glow-primary border-primary/30">
    <Card.Content class="py-4">
      <div class="flex flex-col gap-4 md:gap-6">
        <!-- Scenario selector -->
        <div class="grid gap-2 md:gap-3">
          <Label class="font-semibold text-sm">Target Scenario</Label>
          <Select.Root type="single" bind:value={scenarioPath}>
            <Select.Trigger class="w-full md:w-64">
              {selectedScenario ? selectedScenario.name : 'Select a scenario'}
            </Select.Trigger>
            <Select.Content>
              {#each app.scenarios as s (s.path)}
                <Select.Item value={s.path} label={s.name} />
              {/each}
            </Select.Content>
          </Select.Root>
        </div>

        <!-- Config toggles + Buttons -->
        <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div class="flex flex-wrap gap-6">
            <div class="flex items-center gap-3">
              <Switch id="sim-tools" bind:checked={toolsEnabled} disabled={anyRunning} />
              <Label for="sim-tools" class="cursor-pointer font-semibold text-sm">
                MCP tools
                <span class="block text-[11px] font-normal text-muted-foreground mt-0.5">Inject definitions</span>
              </Label>
            </div>
            <div class="flex items-center gap-3">
              <Switch id="sim-headroom" bind:checked={headroomEnabled} disabled={anyRunning} />
              <Label for="sim-headroom" class="cursor-pointer font-semibold text-sm">
                Headroom
                <span class="block text-[11px] font-normal text-muted-foreground mt-0.5">Compress context</span>
              </Label>
            </div>
          </div>

          <div class="flex gap-2">
            <Button onclick={runSingle} disabled={!selectedScenario || matrixRunning} class="glow-primary">
              <PlayIcon class="size-4 mr-1.5" />
              Run {configLabel(toolsEnabled, headroomEnabled)}
            </Button>
            <Button
              variant="secondary"
              onclick={runFullMatrix}
              disabled={!selectedScenario || matrixRunning || anyRunning}
              class="hidden sm:flex"
            >
              <LayersIcon class="size-4 mr-1.5" />
              {matrixRunning ? 'Running…' : 'Run matrix'}
            </Button>
          </div>
        </div>
      </div>
    </Card.Content>
  </Card.Root>

  <!-- MAIN: 2-Column Layout -->
  <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">

    <!-- LEFT: Active Runs (2/3) -->
    <div class="lg:col-span-2">
      {#if runs.length === 0}
        <Card.Root class="console-panel h-64 flex items-center justify-center">
          <div class="text-center text-muted-foreground">
            <p class="text-sm">No simulations running</p>
            <p class="text-xs mt-1">Launch a run above to see progress and results</p>
          </div>
        </Card.Root>
      {:else}
        <Card.Root class="console-panel">
          <Card.Header class="border-b">
            <div class="data-label text-xs">Simulation Runs</div>
            <Card.Title class="text-lg">Benchmark Results</Card.Title>
          </Card.Header>
          <Card.Content class="pt-4">
            <div class="flex flex-col gap-4">
              {#each runs as run (run.runId)}
                <div class="rounded-lg border p-4 bg-card/40 border-border/60 hover:border-primary/40 transition-all">

                  <!-- Run Header: Status + Title + Cost -->
                  <div class="flex items-center justify-between gap-3 mb-3">
                    <div class="flex items-center gap-3">
                      {#if run.status === 'running'}
                        <LoaderIcon class="size-5 animate-spin text-primary shrink-0" />
                      {:else if run.status === 'done'}
                        <CircleCheckIcon class="size-5 text-emerald-500 shrink-0" />
                      {:else}
                        <CircleXIcon class="size-5 text-destructive shrink-0" />
                      {/if}
                      <div>
                        <p class="text-sm font-semibold">{run.scenario}</p>
                        <Badge variant="outline" class="text-xs mt-1">{run.label}</Badge>
                      </div>
                    </div>
                    <div class="flex items-center gap-2">
                      {#if run.costUsd != null}
                        <span class="font-mono text-sm font-bold text-emerald-400">{usd(run.costUsd)}</span>
                      {/if}
                      {#if run.status === 'done' && run.sessionId}
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => app.openDrilldown(run.sessionId!)}
                          class="h-8 px-3 text-xs text-primary"
                        >
                          <ChartColumnIcon class="size-4 mr-1" />
                          Analyze
                        </Button>
                      {/if}
                    </div>
                  </div>

                  <!-- Progress or Status -->
                  {#if run.status === 'running'}
                    <div class="mb-3">
                      <Progress value={run.total > 0 ? (run.progress / run.total) * 100 : 0} />
                      <p class="text-xs text-muted-foreground mt-2">
                        Turn {run.progress} / {run.total}
                      </p>
                    </div>
                  {:else if run.status === 'error'}
                    <p class="text-xs text-destructive mb-3">{run.error}</p>
                  {/if}

                  <!-- Timeline: Turns -->
                  {#if run.turns && run.turns.length > 0}
                    <div class="border-t pt-3">
                      <p class="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Turn Timeline</p>
                      <div class="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                        {#each run.turns as turn (turn.turn_index)}
                          <div class="flex items-center justify-between text-xs rounded px-2 py-1.5 bg-card/50 border border-border/40">
                            <div class="flex items-center gap-2 min-w-0">
                              <Badge variant="secondary" class="font-mono text-[9px] shrink-0">#{turn.turn_index + 1}</Badge>
                              <span class="text-muted-foreground truncate">
                                <span class="font-semibold text-foreground">{tokens(turn.input_text_tokens)}</span>in / <span class="font-semibold text-foreground">{tokens(turn.output_text_tokens)}</span>out
                                {#if turn.tool_call_tokens > 0}
                                  / <span class="text-primary font-bold">{tokens(turn.tool_call_tokens)}tool</span>
                                {/if}
                              </span>
                            </div>
                            <span class="font-mono font-bold text-foreground shrink-0">{usd(turn.cost_usd)}</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          </Card.Content>
        </Card.Root>
      {/if}
    </div>

    <!-- RIGHT: Details + Guide (1/3) -->
    <div class="flex flex-col gap-5">

      <!-- Scenario Details -->
      {#if selectedScenario}
        <Card.Root class="console-panel">
          <Card.Header class="border-b pb-3">
            <div class="flex items-center gap-2">
              <ListTodoIcon class="size-4 text-primary" />
              <div>
                <div class="data-label text-xs">Workload Details</div>
                <Card.Title class="text-base">{selectedScenario.name}</Card.Title>
              </div>
            </div>
          </Card.Header>
          <Card.Content class="pt-3 space-y-3 text-xs">
            <!-- Stats -->
            <div class="grid grid-cols-2 gap-3 pb-3 border-b">
              <div>
                <p class="text-muted-foreground mb-1">Total Turns</p>
                <p class="font-semibold text-foreground">{selectedScenario.turn_count}</p>
              </div>
              <div>
                <p class="text-muted-foreground mb-1">Est. Duration</p>
                <p class="font-semibold text-foreground">{duration(selectedScenario.estimated_duration_sec)}</p>
              </div>
            </div>

            <!-- Turns preview -->
            <div>
              <p class="font-semibold text-foreground mb-2 uppercase tracking-wider text-[9px]">Sequence</p>
              <div class="flex flex-col gap-3 max-h-40 overflow-y-auto pr-1">
                {#each selectedScenario.turns as turnPrompt, idx}
                  <div class="px-2 py-3 rounded bg-card/30 border border-border/40 text-foreground leading-snug hover:bg-card/50 transition-colors">
                    <span class="font-mono text-[9px] text-primary"># {idx + 1}</span>
                    <span class="text-[10px] ml-1 break-words block">{turnPrompt}</span>
                  </div>
                {/each}
              </div>
            </div>
          </Card.Content>
        </Card.Root>
      {/if}

      <!-- Config Matrix Guide -->
      <Card.Root class="console-panel">
        <Card.Header class="border-b pb-3">
          <div class="flex items-center gap-2">
            <InfoIcon class="size-4 text-cyan-400" />
            <div>
              <div class="data-label text-xs">Benchmark Guide</div>
              <Card.Title class="text-base">Matrix configs</Card.Title>
            </div>
          </div>
        </Card.Header>
        <Card.Content class="pt-3 space-y-2 text-xs">
          <div class="pb-2 border-b">
            <Badge variant="outline" class="text-[9px] mb-1">Baseline</Badge>
            <p class="text-foreground">Raw Gemini Live without optimization.</p>
          </div>
          <div class="pb-2 border-b">
            <Badge variant="outline" class="text-[9px] bg-cyan-500/5 border-cyan-500/20 text-cyan-400 mb-1">Headroom</Badge>
            <p class="text-foreground">Context compression to reduce input tokens.</p>
          </div>
          <div class="pb-2 border-b">
            <Badge variant="outline" class="text-[9px] mb-1">Tools</Badge>
            <p class="text-foreground">MCP definitions increase input token count.</p>
          </div>
          <div>
            <Badge variant="default" class="text-[9px] mb-1">Full stack</Badge>
            <p class="text-foreground">Both tools + headroom compression together.</p>
          </div>
        </Card.Content>
      </Card.Root>
    </div>

  </div>

</div>
