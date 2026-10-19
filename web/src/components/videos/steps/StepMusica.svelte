<script lang="ts">
  // Paso de MÚSICA: la banda sonora de esta historia.
  //
  // La pista no es "música de fondo del vídeo": nace de la historia (el LLM lee
  // el guion y los planos) y vive en la biblioteca de Música como una pista
  // propia, así que se escucha y se descarga sola, sin la narración, para
  // reutilizarla en redes. Mezclarla bajo la voz en el vídeo final es un
  // interruptor aparte, y es lo que mira el armado.
  import { onMount } from "svelte";
  import Button from "../../primitives/Button.svelte";
  import Field from "../../primitives/Field.svelte";
  import Icon from "../../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import { listarMusica } from "@/lib/musica";
  import type { MusicaResumen } from "@/lib/types";
  import type { ProyectoDetalle } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    bust = 0,
    ongenerar,
    onfijar,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    bust?: number;
    ongenerar: () => void;
    onfijar: (musicaId: number | null, mezclar: boolean) => void;
  } = $props();

  // Pistas de la biblioteca, para poder reutilizar una que ya exista en vez de
  // generar otra. Si la lista no llega, el selector no aparece y el paso sigue
  // sirviendo para generar.
  let biblioteca = $state<MusicaResumen[]>([]);
  onMount(async () => {
    try {
      biblioteca = await listarMusica();
    } catch {
      biblioteca = [];
    }
  });

  const m = $derived(p.musica);
  const generadas = $derived(biblioteca.filter((x) => x.estado === "generada"));
  const audioUrl = $derived(m ? `${media(`/musica/${m.id}/audio`)}?v=${bust}` : "");
  const nombreDescarga = $derived(`${p.slug}-musica`);
</script>

<div class="max-w-3xl space-y-5">
  <p class="text-sm text-dim">
    El LLM lee el guion y las escenas y escribe la música de <em>esta</em> historia: estilo,
    tempo, tonalidad y secciones, con la duración de la narración. La pista queda en la
    biblioteca de Música y se descarga suelta —sin voz— para reutilizarla en redes.
  </p>

  <div class="flex flex-wrap items-center gap-3">
    <Button disabled={busy || m?.ocupado} onclick={ongenerar}>
      {m ? "Rehacer la música" : "Generar la música"}
    </Button>
    {#if m?.ocupado}
      <span class="flex items-center gap-2 text-sm text-dim">
        <span class="size-4 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        Componiendo la pista…
      </span>
    {/if}
  </div>

  {#if m}
    <div class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
      <div class="flex items-start gap-3">
        {#if m.tiene_portada}
          <img
            src={`${media(`/musica/${m.id}/portada`)}?v=${bust}`}
            alt=""
            class="size-16 shrink-0 rounded-lg object-cover"
          />
        {/if}
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium">{m.idea}</p>
          <p class="text-xs text-dim">
            {m.duracion_s}s · {m.bpm} BPM · {m.keyscale}
            {#if !m.tiene_audio}· <span class="text-warn">sin audio todavía</span>{/if}
          </p>
        </div>
      </div>

      {#if m.tiene_audio}
        <audio controls src={audioUrl} class="w-full"></audio>
        <div class="flex flex-wrap gap-2">
          <a
            href={audioUrl}
            download={nombreDescarga}
            class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-3 px-3 py-1.5 text-xs text-text transition hover:border-accent"
          >
            <Icon name="download" size={14} /> Descargar la pista sola
          </a>
        </div>
      {/if}

      {#if m.tags}
        <details class="text-xs">
          <summary class="cursor-pointer text-dim">Brief musical</summary>
          <p class="mt-2 text-muted">{m.tags}</p>
          {#if m.lyrics}
            <pre class="mt-2 whitespace-pre-wrap font-mono text-[11px] text-muted">{m.lyrics}</pre>
          {/if}
        </details>
      {/if}
    </div>

    <label
      class={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors
        ${p.musica_mezclar ? "border-accent bg-accent-soft" : "border-line bg-surface-2 hover:border-dim"}`}
    >
      <input
        type="checkbox"
        class="mt-1"
        checked={p.musica_mezclar}
        disabled={busy || !m.tiene_audio}
        onchange={(e) => onfijar(m.id, (e.currentTarget as HTMLInputElement).checked)}
      />
      <span>
        <span class="block text-sm font-medium">Mezclarla en el vídeo final</span>
        <span class="block text-xs text-dim">
          Entra por debajo de la narración y baja sola cuando se habla (ducking), con fades
          de entrada y salida. Hay que rehacer el vídeo para oírla.
        </span>
      </span>
    </label>
  {/if}

  {#if generadas.length}
    <Field
      label="O usar una pista que ya tengas"
      hint="Cualquier pista de la biblioteca de Música. Rehacer la música del proyecto reescribe la que esté enganchada aquí."
    >
      <select
        class="control"
        value={m ? String(m.id) : ""}
        onchange={(e) => {
          const v = (e.currentTarget as HTMLSelectElement).value;
          onfijar(v ? Number(v) : null, v ? p.musica_mezclar : false);
        }}
      >
        <option value="">— sin música —</option>
        {#each generadas as x (x.id)}
          <option value={String(x.id)}>{x.idea}</option>
        {/each}
      </select>
    </Field>
  {/if}
</div>
