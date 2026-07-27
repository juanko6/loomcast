<script lang="ts">
  import Field from "../primitives/Field.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Button from "../primitives/Button.svelte";
  import type { MusicaDetalle } from "@/lib/musica";
  import type { TipoMusica } from "@/lib/types";

  let {
    detail = null,
    busy = false,
    oncreate,
    onsuggest,
    ongenerate,
  }: {
    detail?: MusicaDetalle | null;
    busy?: boolean;
    oncreate: (p: { tipo: TipoMusica; idea: string; duracion_s: number }) => void;
    onsuggest: (p: { tags: string; lyrics: string; duracion_s: number }) => void;
    ongenerate: (p: { tags: string; lyrics: string; duracion_s: number }) => void;
  } = $props();

  // Borrador local; se re-sincroniza cuando cambia la pista seleccionada (o al
  // volver a "nueva pista"). Tras un job del LLM, el padre refresca `detail` y
  // el borrador recoge las etiquetas/letra sugeridas.
  let tipo = $state<TipoMusica>("instrumental");
  let idea = $state("");
  let tags = $state("");
  let lyrics = $state("");
  let duracion = $state(30);

  $effect(() => {
    const d = detail;
    tipo = d?.tipo ?? "instrumental";
    idea = d?.idea ?? "";
    tags = d?.tags ?? "";
    lyrics = d?.lyrics ?? "";
    duracion = d?.duracion_s ?? 30;
  });

  const esCancion = $derived((detail ? detail.tipo : tipo) === "cancion");
  const nuevo = $derived(detail === null);
</script>

<div class="flex h-full flex-col">
  <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
    {#if nuevo}
      <h2 class="text-sm font-semibold text-text">Nueva pista</h2>
      <Segmented
        options={[
          { value: "instrumental", label: "Instrumental" },
          { value: "cancion", label: "Canción" },
        ]}
        value={tipo}
        onchange={(v) => (tipo = v as TipoMusica)}
      />
      <Field
        label={esCancion ? "¿De qué va la canción?" : "¿Qué música quieres?"}
        hint="Luego afinas las etiquetas y la letra, o se las pides al LLM."
      >
        <textarea
          class="control"
          rows="3"
          bind:value={idea}
          placeholder={esCancion
            ? "Ej: una balada esperanzadora sobre volver a empezar, voz femenina"
            : "Ej: lofi triste con piano y lluvia para un storytime"}
        ></textarea>
      </Field>
    {:else}
      <div class="space-y-1">
        <p class="text-xs font-medium tracking-wide text-muted">Editando pista</p>
        <h2 class="line-clamp-2 text-sm font-semibold break-words text-text">{idea || "(pista sin título)"}</h2>
      </div>
      <Field label="Etiquetas de estilo (inglés, coma-separadas)">
        <textarea
          class="control"
          rows="3"
          bind:value={tags}
          placeholder="Ej: lofi hip hop, warm piano, rain, mellow, slow ~70 BPM, instrumental"
        ></textarea>
      </Field>
      {#if esCancion}
        <Field label="Letra" hint="Usa marcadores [verse] / [chorus].">
          <textarea class="control" rows="8" bind:value={lyrics} placeholder="[verse]\n...\n[chorus]\n..."
          ></textarea>
        </Field>
      {/if}
    {/if}

    <Field label="Duración (segundos)">
      <input class="control" type="number" min="5" max="600" step="5" bind:value={duracion} />
    </Field>
  </div>

  <!-- Barra de acción fija abajo (patrón Mureka) -->
  <div class="border-t border-line bg-surface p-4">
    {#if nuevo}
      <Button
        class="w-full"
        disabled={!idea.trim()}
        onclick={() => oncreate({ tipo, idea: idea.trim(), duracion_s: duracion })}
      >
        Crear pista
      </Button>
    {:else}
      <div class="flex flex-col gap-2">
        <Button
          variant="secondary"
          disabled={busy}
          onclick={() => onsuggest({ tags, lyrics, duracion_s: duracion })}
          title="El LLM sugiere las etiquetas{esCancion ? ' y la letra' : ''} a partir de tu idea"
        >
          Sugerir con LLM
        </Button>
        <Button
          class="w-full"
          disabled={busy || !tags.trim()}
          onclick={() => ongenerate({ tags, lyrics, duracion_s: duracion })}
        >
          {detail?.tiene_audio ? "Regenerar (otra distinta)" : "Generar música"}
        </Button>
      </div>
    {/if}
  </div>
</div>
