<script lang="ts">
  import Field from "../primitives/Field.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Button from "../primitives/Button.svelte";
  import { IDIOMAS, KEYSCALES, TIMESIGS, type Musical, type MusicaDetalle } from "@/lib/musica";
  import type { TipoMusica } from "@/lib/types";

  type Campos = { tags: string; lyrics: string; duracion_s: number } & Musical;

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
    onsuggest: (p: Campos) => void;
    ongenerate: (p: Campos) => void;
  } = $props();

  // Borrador local; se re-sincroniza cuando cambia la pista seleccionada (o al
  // volver a "nueva pista"). Tras un job del LLM, el padre refresca `detail` y
  // el borrador recoge las etiquetas/letra sugeridas.
  let tipo = $state<TipoMusica>("instrumental");
  let idea = $state("");
  let tags = $state("");
  let lyrics = $state("");
  let duracion = $state(30);
  let bpm = $state(120);
  let keyscale = $state("C major");
  let timesig = $state("4");
  let idioma = $state("es");

  $effect(() => {
    const d = detail;
    tipo = d?.tipo ?? "instrumental";
    idea = d?.idea ?? "";
    tags = d?.tags ?? "";
    lyrics = d?.lyrics ?? "";
    duracion = d?.duracion_s ?? 30;
    bpm = d?.bpm ?? 120;
    keyscale = d?.keyscale ?? "C major";
    timesig = d?.timesig ?? "4";
    idioma = d?.idioma ?? "es";
  });

  const esCancion = $derived((detail ? detail.tipo : tipo) === "cancion");
  const nuevo = $derived(detail === null);
  const campos = (): Campos => ({
    tags,
    lyrics,
    duracion_s: duracion,
    bpm,
    keyscale,
    timesig,
    idioma,
  });
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
      <Field
        label="Descripción de estilo (inglés)"
        hint="ACE-Step 1.5 espera prosa, no etiquetas: di qué instrumentos hay y qué papel tiene cada uno en la mezcla."
      >
        <textarea
          class="control"
          rows="6"
          bind:value={tags}
          placeholder="Ej: A warm lofi hip hop track built on a mellow upright piano and a lazy, brushed drum groove. A soft sub-bass anchors the track without intruding, and rain and vinyl crackle sit far back in the mix, leaving generous space around the piano."
        ></textarea>
      </Field>
      {#if esCancion}
        <Field label="Letra" hint="Marcadores con indicación dentro: [Verse 1 - voz susurrada sobre guitarra].">
          <textarea
            class="control"
            rows="8"
            bind:value={lyrics}
            placeholder={"[Intro - piano y batería con escobillas]\n[Verse 1 - voz femenina cercana]\n...\n[Chorus - armonías apiladas]\n..."}
          ></textarea>
        </Field>
      {/if}
    {/if}

    <Field label="Duración (segundos)">
      <input class="control" type="number" min="5" max="600" step="5" bind:value={duracion} />
    </Field>

    {#if !nuevo}
      <!-- Conditioning musical de 1.5. Fijar tempo, tonalidad y compás es lo que
           evita que el arreglo derive y los instrumentos se tapen entre sí. -->
      <div class="grid grid-cols-2 gap-3">
        <Field label="Tempo (BPM)">
          <input class="control" type="number" min="10" max="300" bind:value={bpm} />
        </Field>
        <Field label="Compás">
          <select class="control" bind:value={timesig}>
            {#each TIMESIGS as t}<option value={t}>{t}/4</option>{/each}
          </select>
        </Field>
        <Field label="Tonalidad">
          <select class="control" bind:value={keyscale}>
            {#each KEYSCALES as k}<option value={k}>{k}</option>{/each}
          </select>
        </Field>
        {#if esCancion}
          <Field label="Idioma de la letra">
            <select class="control" bind:value={idioma}>
              {#each IDIOMAS as i}<option value={i.value}>{i.label}</option>{/each}
            </select>
          </Field>
        {/if}
      </div>
    {/if}
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
          onclick={() => onsuggest(campos())}
          title="El LLM sugiere la descripción, el tempo y la tonalidad{esCancion
            ? ' y la letra'
            : ''} a partir de tu idea"
        >
          Sugerir con LLM
        </Button>
        <Button
          class="w-full"
          disabled={busy || !tags.trim()}
          onclick={() => ongenerate(campos())}
        >
          {detail?.tiene_audio ? "Regenerar (otra distinta)" : "Generar música"}
        </Button>
      </div>
    {/if}
  </div>
</div>
