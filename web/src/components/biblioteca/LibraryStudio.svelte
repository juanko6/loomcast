<script lang="ts">
  import { onMount } from "svelte";
  import LibraryCard from "./LibraryCard.svelte";
  import Viewer from "../primitives/Viewer.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import { jobsDrenados, abrirEn } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import { cargarBiblioteca, FILTROS, type LibItem, type LibKind } from "@/lib/biblioteca";

  let items = $state<LibItem[]>([]);
  let filtro = $state<"todo" | LibKind>("todo");
  let busca = $state("");
  let cargando = $state(true);
  let error = $state("");

  let visorHtml = $state<string | null>(null);
  let visorPie = $state("");

  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");

  const visibles = $derived(
    items.filter((i) => {
      if (filtro !== "todo" && i.kind !== filtro) return false;
      const q = busca.trim().toLowerCase();
      return !q || i.titulo.toLowerCase().includes(q);
    }),
  );

  // Conteo por tipo para las etiquetas del filtro.
  const cuenta = $derived({
    todo: items.length,
    video: items.filter((i) => i.kind === "video").length,
    imagen: items.filter((i) => i.kind === "imagen").length,
    musica: items.filter((i) => i.kind === "musica").length,
  } as Record<string, number>);

  async function refrescar() {
    try {
      items = await cargarBiblioteca();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      cargando = false;
    }
  }

  // Al terminar un job puede haber material nuevo.
  let ultimoDrenaje = 0;
  $effect(() => {
    const n = $jobsDrenados;
    if (n !== ultimoDrenaje) {
      ultimoDrenaje = n;
      refrescar();
    }
  });

  onMount(refrescar);
</script>

<div class="flex min-h-0 flex-1 flex-col" style={reservaPlayer}>
  <!-- Filtros y búsqueda -->
  <div class="flex flex-wrap items-center gap-3 border-b border-line px-6 py-3">
    <div class="w-[420px] max-w-full">
      <Segmented
        options={FILTROS.map((f) => ({
          value: f.id,
          label: `${f.label} (${cuenta[f.id] ?? 0})`,
        }))}
        value={filtro}
        onchange={(v) => (filtro = v as "todo" | LibKind)}
      />
    </div>
    <input
      class="control ml-auto w-56"
      type="search"
      bind:value={busca}
      placeholder="Buscar por título…"
      aria-label="Buscar en la biblioteca"
    />
  </div>

  <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
    {#if error}
      <div class="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
        {error}
      </div>
    {:else if cargando}
      <div class="grid place-items-center py-20">
        <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
      </div>
    {:else if !visibles.length}
      <p class="py-20 text-center text-sm text-muted">
        {items.length ? "Nada coincide con la búsqueda." : "Aún no has creado nada."}
      </p>
    {:else}
      <div class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
        {#each visibles as it (it.kind + it.id)}
          <LibraryCard
            item={it}
            onopen={() => abrirEn(it.destino, it.id)}
            onview={(html, pie) => {
              visorHtml = html;
              visorPie = pie;
            }}
          />
        {/each}
      </div>
    {/if}
  </div>
</div>

<Viewer html={visorHtml} pie={visorPie} onclose={() => (visorHtml = null)} />
