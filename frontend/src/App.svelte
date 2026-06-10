<script lang="ts">
  import { onMount } from 'svelte'
  import { ModeWatcher } from 'mode-watcher'
  import { Toaster } from '$lib/components/ui/sonner'
  import { Badge } from '$lib/components/ui/badge'
  import { Separator } from '$lib/components/ui/separator'
  import { app, type Tab } from '$lib/state.svelte'
  import FlameIcon from '@lucide/svelte/icons/flame'
  import MicIcon from '@lucide/svelte/icons/mic'
  import PlayIcon from '@lucide/svelte/icons/play'
  import ChartColumnIcon from '@lucide/svelte/icons/chart-column'
  import ServerIcon from '@lucide/svelte/icons/server'
  import LiveView from '$lib/views/LiveView.svelte'
  import SimView from '$lib/views/SimView.svelte'
  import AnalyticsView from '$lib/views/AnalyticsView.svelte'

  const navItems: { id: Tab; label: string; icon: typeof MicIcon; hint: string }[] = [
    { id: 'live', label: 'Live', icon: MicIcon, hint: 'Mic session' },
    { id: 'sim', label: 'Sim', icon: PlayIcon, hint: 'Scenario replay' },
    { id: 'analytics', label: 'Analytics', icon: ChartColumnIcon, hint: 'Compare & project' },
  ]

  const titles: Record<Tab, { title: string; sub: string }> = {
    live: { title: 'Live Session', sub: 'Microphone → Gemini Live → speaker, with real-time cost' },
    sim: { title: 'Sim Runner', sub: 'Replay YAML scenarios at full API speed' },
    analytics: { title: 'Analytics', sub: 'Compare configs, project fleet costs, export' },
  }

  onMount(() => {
    app.loadStatic()
    app.refreshSessions()
  })
</script>

<ModeWatcher defaultMode="dark" />
<Toaster richColors position="top-right" />

<div class="flex h-screen overflow-hidden bg-background text-foreground">
  <!-- Sidebar -->
  <aside class="flex w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
    <div class="flex items-center gap-2.5 px-5 py-5">
      <div class="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <FlameIcon class="size-5" />
      </div>
      <div>
        <div class="text-sm font-bold tracking-widest">BURNRATE</div>
        <div class="text-[11px] text-muted-foreground">Gemini Live cost lab</div>
      </div>
    </div>

    <Separator />

    <nav class="flex flex-1 flex-col gap-1 p-3">
      {#each navItems as item (item.id)}
        <button
          class="flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors
            {app.tab === item.id
              ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
              : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground'}"
          onclick={() => (app.tab = item.id)}
        >
          <item.icon class="size-4" />
          <span class="flex-1">{item.label}</span>
          <span class="text-[10px] text-muted-foreground">{item.hint}</span>
        </button>
      {/each}
    </nav>

    <Separator />

    <div class="space-y-2 p-4 text-xs text-muted-foreground">
      {#if app.config}
        <div class="flex items-center gap-2 truncate">
          <span class="size-1.5 shrink-0 rounded-full {app.backendUp ? 'bg-emerald-500' : 'bg-red-500'}"></span>
          <span class="truncate font-mono">{app.config.model}</span>
        </div>
        <div class="flex items-center gap-2">
          <ServerIcon class="size-3" />
          {app.config.mcp_servers.length} MCP server{app.config.mcp_servers.length === 1 ? '' : 's'} configured
        </div>
      {:else}
        <div class="flex items-center gap-2">
          <span class="size-1.5 rounded-full bg-red-500"></span>
          backend unreachable
        </div>
      {/if}
    </div>
  </aside>

  <!-- Main -->
  <div class="flex min-w-0 flex-1 flex-col">
    <header class="flex items-center justify-between border-b px-6 py-4">
      <div>
        <h1 class="text-lg font-semibold">{titles[app.tab].title}</h1>
        <p class="text-xs text-muted-foreground">{titles[app.tab].sub}</p>
      </div>
      {#if app.config}
        <div class="flex items-center gap-1.5">
          <Badge variant="outline" class="font-mono text-[10px]">
            audio in ${app.config.pricing.audio_input_per_min}/min
          </Badge>
          <Badge variant="outline" class="font-mono text-[10px]">
            audio out ${app.config.pricing.audio_output_per_min}/min
          </Badge>
          <Badge variant="outline" class="font-mono text-[10px]">
            txt in ${app.config.pricing.text_input_per_mtok}/Mtok
          </Badge>
          <Badge variant="outline" class="font-mono text-[10px]">
            txt out ${app.config.pricing.text_output_per_mtok}/Mtok
          </Badge>
        </div>
      {/if}
    </header>

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
