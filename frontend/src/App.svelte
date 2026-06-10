<script lang="ts">
  import { onMount } from 'svelte'
  import { ModeWatcher } from 'mode-watcher'
  import { Toaster } from '$lib/components/ui/sonner'
  import { Badge } from '$lib/components/ui/badge'
  import { app, type Tab } from '$lib/state.svelte'
  import FlameIcon from '@lucide/svelte/icons/flame'
  import MicIcon from '@lucide/svelte/icons/mic'
  import PlayIcon from '@lucide/svelte/icons/play'
  import ChartColumnIcon from '@lucide/svelte/icons/chart-column'
  import ServerIcon from '@lucide/svelte/icons/server'
  import CircleDotIcon from '@lucide/svelte/icons/circle-dot'
  import ActivityIcon from '@lucide/svelte/icons/activity'
  import LiveView from '$lib/views/LiveView.svelte'
  import SimView from '$lib/views/SimView.svelte'
  import AnalyticsView from '$lib/views/AnalyticsView.svelte'
  import { usd } from '$lib/format'

  const navItems: { id: Tab; label: string; icon: typeof MicIcon; hint: string }[] = [
    { id: 'live', label: 'Live', icon: MicIcon, hint: 'Mic session' },
    { id: 'sim', label: 'Sim', icon: PlayIcon, hint: 'Scenario replay' },
    { id: 'analytics', label: 'Analytics', icon: ChartColumnIcon, hint: 'Compare & project' },
  ]

  const titles: Record<Tab, { title: string; sub: string }> = {
    live: { title: 'Live Session', sub: 'Microphone → Gemini Live → speaker, with real-time cost tracking' },
    sim: { title: 'Sim Runner', sub: 'Replay YAML scenarios at full API speed and benchmark configs' },
    analytics: { title: 'Analytics', sub: 'Compare configurations, project fleet costs, and export metrics' },
  }

  const totalSessions = $derived(app.sessions.length)
  const totalSpend = $derived(app.sessions.reduce((a, s) => a + s.total_cost_usd, 0))

  onMount(() => {
    app.loadStatic()
    app.refreshSessions()
  })
</script>

<ModeWatcher defaultMode="dark" />
<Toaster richColors position="top-right" />

<div class="flex h-screen overflow-hidden bg-background text-foreground">
  <!-- Sidebar -->
  <aside class="telemetry-grid flex w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground relative overflow-hidden">
    <div class="absolute inset-x-0 top-0 h-40 pointer-events-none"
      style="background: radial-gradient(ellipse at 50% 0%, color-mix(in srgb, var(--primary) 16%, transparent), transparent 70%);">
    </div>
    <div class="absolute inset-y-0 right-0 w-px bg-gradient-to-b from-transparent via-primary/35 to-transparent"></div>

    <!-- Brand -->
    <div class="flex items-center gap-3 px-4 py-4 relative z-10">
      <div class="flex size-9 shrink-0 items-center justify-center rounded-lg border border-primary/35 bg-primary/15 text-primary shadow-[0_0_22px_color-mix(in_srgb,var(--primary)_28%,transparent)]">
        <FlameIcon class="size-4.5" />
      </div>
      <div>
        <div class="text-sm font-extrabold tracking-widest text-foreground">BURNRATE</div>
        <div class="font-mono text-[10px] text-muted-foreground">CONTROL ROOM</div>
      </div>
    </div>

    <!-- Divider -->
    <div class="h-px bg-sidebar-border mx-4 mb-1"></div>

    <!-- Nav -->
    <nav class="flex flex-1 flex-col gap-0.5 p-2 relative z-10">
      {#each navItems as item (item.id)}
        <button
          class="flex items-center gap-3 rounded-md border px-3 py-2.5 text-left text-sm transition-all duration-200 group relative
            {app.tab === item.id
              ? 'border-primary/35 bg-primary/10 text-primary font-semibold shadow-[inset_0_0_16px_color-mix(in_srgb,var(--primary)_7%,transparent)]'
              : 'border-transparent text-muted-foreground hover:border-border/70 hover:bg-sidebar-accent/60 hover:text-foreground'}"
          onclick={() => (app.tab = item.id)}
        >
          {#if app.tab === item.id}
            <div class="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-full shadow-[0_0_8px_var(--primary)]"></div>
          {/if}
          <item.icon class="size-4 shrink-0 {app.tab === item.id ? 'text-primary' : ''}" />
          <span class="flex-1 text-[13px]">{item.label}</span>
          <span class="text-[9px] text-muted-foreground font-medium hidden group-hover:block {app.tab === item.id ? 'block opacity-60' : ''}">{item.hint}</span>
        </button>
      {/each}
    </nav>

    <!-- Divider -->
    <div class="h-px bg-sidebar-border mx-4"></div>

    <!-- Session summary mini-stats -->
    {#if app.sessions.length > 0}
      <div class="px-4 py-3 relative z-10">
        <div class="console-panel p-3 flex flex-col gap-2">
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-muted-foreground flex items-center gap-1.5">
              <ActivityIcon class="size-3" />
              Sessions
            </span>
            <span class="font-bold text-foreground tabular-nums">{totalSessions}</span>
          </div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-muted-foreground flex items-center gap-1.5">
              <span class="size-1.5 rounded-full bg-emerald-400"></span>
              Total spend
            </span>
            <span class="font-bold text-emerald-400 tabular-nums font-mono">{usd(totalSpend)}</span>
          </div>
        </div>
      </div>

      <div class="h-px bg-sidebar-border mx-4"></div>
    {/if}

    <!-- Model & MCP status -->
    <div class="p-3 text-xs relative z-10">
      {#if app.config}
        <div class="flex flex-col gap-1.5 px-1">
          <div class="flex items-center gap-2 min-w-0">
            <span class="size-1.5 shrink-0 rounded-full {app.backendUp ? 'bg-emerald-400 shadow-[0_0_6px_rgb(52,211,153)]' : 'bg-red-400'}"></span>
            <span class="truncate font-mono text-[10px] text-muted-foreground">{app.config.model}</span>
          </div>
          <div class="flex items-center gap-1.5 text-muted-foreground">
            <ServerIcon class="size-3 shrink-0" />
            <span class="text-[10px]">{app.config.mcp_servers.length} MCP server{app.config.mcp_servers.length === 1 ? '' : 's'}</span>
          </div>
        </div>
      {:else}
        <div class="flex items-center gap-2 px-1">
          <span class="size-1.5 rounded-full bg-red-400"></span>
          <span class="text-[10px] text-muted-foreground">backend unreachable</span>
        </div>
      {/if}
    </div>
  </aside>

  <!-- Main -->
  <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
    <!-- Header -->
    <header class="flex shrink-0 items-center justify-between border-b border-border/60 px-6 py-3.5 bg-background/82 backdrop-blur-sm">
      <div>
        <div class="data-label">Mission Surface</div>
        <h1 class="mt-0.5 text-base font-bold text-foreground">{titles[app.tab].title}</h1>
        <p class="text-[11px] text-muted-foreground mt-0.5">{titles[app.tab].sub}</p>
      </div>
      {#if app.config}
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" class="font-mono text-[9px] h-5 bg-primary/5 border-primary/20 text-primary">
            🎤 ${app.config.pricing.audio_input_per_min}/min
          </Badge>
          <Badge variant="outline" class="font-mono text-[9px] h-5 bg-primary/5 border-primary/20 text-primary">
            🔊 ${app.config.pricing.audio_output_per_min}/min
          </Badge>
          <Badge variant="outline" class="font-mono text-[9px] h-5 border-border/50 text-muted-foreground">
            txt ${app.config.pricing.text_input_per_mtok}/M in
          </Badge>
          <Badge variant="outline" class="font-mono text-[9px] h-5 border-border/50 text-muted-foreground">
            txt ${app.config.pricing.text_output_per_mtok}/M out
          </Badge>
        </div>
      {/if}
    </header>

    <!-- Content -->
    <main class="flex-1 overflow-y-auto p-6">
      {#if app.tab === 'live'}
        <LiveView />
      {:else if app.tab === 'sim'}
        <SimView />
      {:else}
        <AnalyticsView />
      {/if}
    </main>
  </div>
</div>
