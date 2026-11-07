<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Button from "../primitives/Button.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import { media } from "@/lib/api";
  import { portadaUrl, KEYSCALES, TIMESIGS } from "@/lib/musica";
  import { currentTrack, isPlaying, playTrack } from "@/lib/player";
  import { mmss, type AlbumDetalle, type CambiosPista, type PistaAlbum } from "@/lib/albumes";

  // El tracklist del álbum: la revisión antes de gastar GPU. Cada pista se
  // edita aquí (título, intención, tempo, tonalidad) y se puede reescribir su
  // brief, moverla o quitarla. La duración no se edita: sale del guion.
  let {
    album,
    selectedId = null,
    onselect,
    onedit,
    onrewrite,
    onmove,
    onremove,
  }: {
    album: AlbumDetalle;
    selectedId?: number | null;
    onselect: (id: number) => void;
    onedit: (id: number, cambios: CambiosPista) => void;
    onrewrite: (id: number) => void;
    onmove: (id: number, delta: number) => void;
    onremove: (p: PistaAlbum) => void;
  } = $props();

  let abierta = $state<number | null>(null);
  let borrador = $state<CambiosPista>({});

  function abrir(p: PistaAlbum) {
    onselect(p.id);
    if (abierta === p.id) return;
    abierta = p.id;
    borrador = {
      titulo: p.titulo,
      intencion: p.intencion,
      bpm: p.bpm,
      keyscale: p.keyscale,
      timesig: p.timesig,
    };
  }

  function reproducir(p: PistaAlbum) {
    playTrack({
      id: p.id,
      tipo: "instrumental",
      idea: p.titulo,
      seed: p.seed,
      duracion_s: p.duracion_s,
      src: media(`/musica/${p.id}/audio`),
      cover: p.tiene_portada ? portadaUrl(p.id) : null,
    });
  }

  function cambios(p: PistaAlbum): CambiosPista {
    const c: CambiosPista = {};
    for (const k of ["titulo", "intencion", "bpm", "keyscale", "timesig"] as const) {
      if (borrador[k] !== undefined && borrador[k] !== p[k]) (c as Record<string, unknown>)[k] = borrador[k];
    }
    return c;
  }
</script>

<div class="space-y-2">
  {#if album.pistas.length === 0}
    <div class="mt-10 flex flex-col items-center gap-3 text-dim">
      <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
      <p class="text-sm">Planificando el álbum: sonido, banda y una intención por pista…</p>
    </div>
  {/if}

  {#each album.pistas as p, i (p.id)}
    {@const sonando = $currentTrack?.id === p.id && $isPlaying}
    {@const c = abierta === p.id ? cambios(p) : {}}
    <div
      class={`rounded-lg border transition-colors ${
        p.id === selectedId ? "border-accent/40 bg-accent-soft" : "border-line-soft bg-surface-2"
      }`}
    >
      <div class="flex items-center gap-3 px-3 py-2.5">
        <span class="w-6 shrink-0 text-right text-xs tabular-nums text-muted">{p.pista_n}</span>
        {#if p.tiene_audio}
          <Thumbnail
            src={p.tiene_portada ? portadaUrl(p.id) : null}
            alt=""
            icon="music"
            size={40}
            playing={sonando}
            onplay={() => reproducir(p)}
          />
        {:else}
          <Thumbnail src={null} alt="" icon="music" size={40} />
        {/if}
        <button type="button" class="flex min-w-0 flex-1 flex-col items-start gap-1.5 text-left" onclick={() => abrir(p)}>
          <span class="w-full truncate text-sm font-medium text-text">{p.titulo || "(sin título)"}</span>
          <span class="line-clamp-1 w-full text-xs text-dim">{p.intencion.split("\n")[0]}</span>
          <span class="flex flex-wrap items-center gap-1">
            {#if p.origen}<Chip tone="accent">origen</Chip>{/if}
            <Chip>{p.bpm} BPM</Chip>
            <Chip>{p.keyscale}</Chip>
            {#if p.escrita}
              <Chip>{mmss(p.duracion_s)}{p.compases ? ` · ${p.compases} c.` : ""}</Chip>
            {:else}
              <Chip>sin escribir</Chip>
            {/if}
            {#if p.ocupado}
              <span class="size-3.5 animate-spin rounded-full border-2 border-line border-t-accent"></span>
            {:else}
              <Chip>{p.estado}</Chip>
            {/if}
          </span>
        </button>
      </div>

      {#if abierta === p.id}
        <div class="space-y-3 border-t border-line-soft px-4 py-3">
          <input class="control text-sm" bind:value={borrador.titulo} placeholder="Título" />
          <textarea
            class="control text-sm"
            rows="4"
            bind:value={borrador.intencion}
            placeholder="Qué cuenta esta pista, su papel, quién lleva la melodía, su forma"
          ></textarea>
          <div class="grid grid-cols-3 gap-2">
            <input class="control" type="number" min="10" max="300" bind:value={borrador.bpm} title="Tempo (BPM)" />
            <select class="control" bind:value={borrador.keyscale} title="Tonalidad">
              {#each KEYSCALES as k}<option value={k}>{k}</option>{/each}
            </select>
            <select class="control" bind:value={borrador.timesig} title="Compás">
              {#each TIMESIGS as t}<option value={t}>{t}/4</option>{/each}
            </select>
          </div>
          {#if p.lyrics}
            <details class="text-xs text-dim">
              <summary class="cursor-pointer text-muted">Guion ({p.compases} compases)</summary>
              <pre class="mt-2 whitespace-pre-wrap font-sans leading-relaxed">{p.lyrics}</pre>
            </details>
          {/if}
          <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" disabled={Object.keys(c).length === 0} onclick={() => onedit(p.id, c)}>
              Guardar
            </Button>
            {#if !p.origen}
              <Button
                size="sm"
                variant="secondary"
                disabled={p.ocupado || album.ocupado}
                title="El LLM vuelve a escribir el estilo y el guion desde la intención guardada"
                onclick={() => onrewrite(p.id)}
              >
                Reescribir con LLM
              </Button>
            {/if}
            <span class="flex-1"></span>
            <Button size="sm" variant="ghost" disabled={i === 0} onclick={() => onmove(p.id, -1)} title="Subir">↑</Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={i === album.pistas.length - 1}
              onclick={() => onmove(p.id, 1)}
              title="Bajar">↓</Button>
            <Button size="sm" variant="danger" onclick={() => onremove(p)}>Quitar</Button>
          </div>
        </div>
      {/if}
    </div>
  {/each}
</div>
