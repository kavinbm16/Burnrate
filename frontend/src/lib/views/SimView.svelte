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
  import ListTodoIcon from '@lucide/svelte/icons/list-todo'
  import InfoIcon from '@lucide/svelte/icons/info'

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

<div class="w-full flex flex-col gap-6">
  {#if geminiHealthMsg}
    <Card.Root class="border-destructive/40 bg-destructive/5 animate-pulse">
      <Card.Content class="py-4 text-sm">
        <p class="font-medium text-destructive">Gemini Live not reachable</p>
        <p class="mt-1 text-muted-foreground">{geminiHealthMsg}</p>
      </Card.Content>
    </Card.Root>
  {/if}

  <!-- Premium Two Column Dashboard Cockpit Grid -->
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-5 items-start">
    
    <!-- LEFT PANEL: Main Sim controller & Logs Timeline (3/5 width) -->
    <div class="flex flex-col gap-6 lg:col-span-3">
      
      <!-- Config card -->
      <Card.Root class="glass glow-primary">
        <Card.Header>
          <Card.Title>Simulation Runner</Card.Title>
          <Card.Description>
            Select a workload scenario to mock sequential robot operations at maximum speed.
          </Card.Description>
        </Card.Header>
        <Card.Content class="flex flex-col gap-6">
          <div class="grid gap-2">
            <Label class="font-semibold text-sm">Target Scenario</Label>
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
          </div>

          <div class="flex flex-wrap gap-8 py-2">
            <div class="flex items-center gap-3">
              <Switch id="sim-tools" bind:checked={toolsEnabled} />
              <Label for="sim-tools" class="cursor-pointer font-semibold text-sm">
                MCP tools
                <span class="block text-[11px] font-normal text-muted-foreground mt-0.5">
                  inject tool definitions
                </span>
              </Label>
            </div>
            <div class="flex items-center gap-3">
              <Switch id="sim-headroom" bind:checked={headroomEnabled} />
              <Label for="sim-headroom" class="cursor-pointer font-semibold text-sm">
                Headroom
                <span class="block text-[11px] font-normal text-muted-foreground mt-0.5">
                  compress context
                </span>
              </Label>
            </div>
          </div>
        </Card.Content>
        <Card.Footer class="flex gap-3 border-t pt-4">
          <Button onclick={runSingle} disabled={!selectedScenario || matrixRunning} class="glow-primary px-5">
            <PlayIcon class="size-4 mr-1.5" />
            Run {configLabel(toolsEnabled, headroomEnabled)}
          </Button>
          <Button
            variant="secondary"
            onclick={runFullMatrix}
            disabled={!selectedScenario || matrixRunning || anyRunning}
          >
            <LayersIcon class="size-4 mr-1.5" />
            {matrixRunning ? 'Running matrix…' : 'Run full matrix (4 configs)'}
          </Button>
        </Card.Footer>
      </Card.Root>

      <!-- Active Simulation Runs Replays -->
      {#if runs.length > 0}
        <Card.Root class="glass flex-grow min-h-[400px]">
          <Card.Header>
            <Card.Title>Runs this session</Card.Title>
            <Card.Description>Simulated runs history and conversational metrics feed.</Card.Description>
          </Card.Header>
          <Card.Content class="flex flex-col gap-4">
            {#each runs as run (run.runId)}
              <div class="flex flex-col gap-3 rounded-xl border p-4 bg-card/30 border-border/60 hover:border-primary/20 transition-all duration-200">
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-2">
                    {#if run.status === 'running'}
                      <LoaderIcon class="size-4 animate-spin text-primary" />
                    {:else if run.status === 'done'}
                      <CircleCheckIcon class="size-4 text-emerald-500" />
                    {:else}
                      <CircleXIcon class="size-4 text-destructive" />
                    {/if}
                    <span class="text-sm font-bold">{run.scenario}</span>
                    <Badge variant="outline" class="text-[10px] bg-primary/5">{run.label}</Badge>
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
                        class="h-7 px-2.5 text-xs text-primary"
                      >
                        <ChartColumnIcon class="size-3.5 mr-1" />
                        Analyze
                      </Button>
                    {/if}
                  </div>
                </div>
                {#if run.status === 'running'}
                  <Progress value={run.total > 0 ? (run.progress / run.total) * 100 : 0} />
                  <p class="text-xs text-muted-foreground">
                    Replaying turn {run.progress} / {run.total || '?'}
                  </p>
                {:else if run.status === 'error'}
                  <p class="text-xs text-destructive">{run.error}</p>
                {/if}

                <!-- Real-Time Replay Timeline -->
                {#if run.turns && run.turns.length > 0}
                  <div class="mt-2 border-t pt-3 flex flex-col gap-2">
                    <p class="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Simulation Timeline</p>
                    <div class="flex flex-col gap-1.5 max-h-52 overflow-y-auto pr-1">
                      {#each run.turns as turn (turn.turn_index)}
                        <div class="flex items-center justify-between rounded border bg-card/45 px-3 py-2 text-xs border-border/40 hover:border-primary/20 transition-all duration-150">
                          <div class="flex items-center gap-2">
                            <Badge variant="secondary" class="font-mono text-[9px] h-4">#{turn.turn_index + 1}</Badge>
                            <span class="text-muted-foreground">
                              <span class="text-foreground font-semibold">{tokens(turn.input_text_tokens)}</span> in · <span class="text-foreground font-semibold">{tokens(turn.output_text_tokens)}</span> out
                              {#if turn.tool_call_tokens > 0}
                                · <span class="text-primary font-bold">{tokens(turn.tool_call_tokens)} tool</span>
                              {/if}
                            </span>
                          </div>
                          <span class="font-mono font-bold text-foreground text-glow-primary">{usd(turn.cost_usd)}</span>
                        </div>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            {/each}
          </Card.Content>
        </Card.Root>
      {/if}
      
    </div>

    <!-- RIGHT PANEL: Workload Details & Guides (2/5 width) -->
    <div class="flex flex-col gap-6 lg:col-span-2">
      
      <!-- Scenario Prompt Previews -->
      {#if selectedScenario}
        <Card.Root class="glass glow-hover">
          <Card.Header class="flex flex-row items-center gap-3">
            <div class="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ListTodoIcon class="size-4" />
            </div>
            <div>
              <Card.Title>Workload Details</Card.Title>
              <Card.Description>Static operations in the "{selectedScenario.name}" scenario.</Card.Description>
            </div>
          </Card.Header>
          <Card.Content class="flex flex-col gap-4">
            <!-- Metadata grid -->
            <div class="grid grid-cols-2 gap-2 text-xs border-b pb-3 border-border/40">
              <div class="flex flex-col">
                <span class="text-muted-foreground">Total Turns</span>
                <span class="font-semibold text-sm text-foreground mt-0.5">{selectedScenario.turn_count}</span>
              </div>
              <div class="flex flex-col">
                <span class="text-muted-foreground">Est. Duration</span>
                <span class="font-semibold text-sm text-foreground mt-0.5">{duration(selectedScenario.estimated_duration_sec)}</span>
              </div>
            </div>

            <!-- List of prompt text -->
            <div class="flex flex-col gap-2">
              <span class="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Workload Sequence</span>
              <div class="flex flex-col gap-1.5 max-h-64 overflow-y-auto pr-1">
                {#each selectedScenario.turns as turnPrompt, idx}
                  <div class="px-3 py-2 rounded bg-card/30 border text-xs text-muted-foreground truncate hover:text-foreground hover:bg-card/50 transition-colors">
                    <span class="font-mono text-[10px] text-primary mr-1.5">#{idx + 1}</span>
                    {turnPrompt}
                  </div>
                {/each}
              </div>
            </div>
          </Card.Content>
        </Card.Root>
      {/if}

      <!-- Simulation Matrix Guide -->
      <Card.Root class="glass glow-hover">
        <Card.Header class="flex flex-row items-center gap-3">
          <div class="flex size-9 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400">
            <InfoIcon class="size-4" />
          </div>
          <div>
            <Card.Title>Matrix Configs Guide</Card.Title>
            <Card.Description>Understand the benchmark dimensions.</Card.Description>
          </div>
        </Card.Header>
        <Card.Content class="flex flex-col gap-3.5 text-xs">
          <div class="flex gap-2">
            <Badge variant="outline" class="h-5 shrink-0 text-[9px] font-mono">Baseline</Badge>
            <p class="text-muted-foreground">Standard Gemini Live connection without headroom optimization or tool calls. Represents raw API pricing.</p>
          </div>
          <div class="flex gap-2 border-t pt-2 border-border/30">
            <Badge variant="outline" class="h-5 shrink-0 text-[9px] font-mono bg-cyan-500/5 border-cyan-500/20 text-cyan-400">Headroom only</Badge>
            <p class="text-muted-foreground">Runs the workload with headroom-ai context compression active. Saves input tokens across turns.</p>
          </div>
          <div class="flex gap-2 border-t pt-2 border-border/30">
            <Badge variant="outline" class="h-5 shrink-0 text-[9px] font-mono">Tools only</Badge>
            <p class="text-muted-foreground">Injects MCP tool definitions into the connection. Increases input token count due to JSON schema payload.</p>
          </div>
          <div class="flex gap-2 border-t pt-2 border-border/30">
            <Badge variant="default" class="h-5 shrink-0 text-[9px] font-mono">Full stack</Badge>
            <p class="text-muted-foreground">Enables both MCP tools and Headroom. Tests context compression on functional tool payloads to offset schema costs.</p>
          </div>
        </Card.Content>
      </Card.Root>

    </div>
  </div>
</div>
