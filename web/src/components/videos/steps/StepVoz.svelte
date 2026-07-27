<script lang="ts">
  import Field from "../../primitives/Field.svelte";
  import Button from "../../primitives/Button.svelte";
  import IconButton from "../../primitives/IconButton.svelte";
  import Segmented from "../../primitives/Segmented.svelte";
  import { media } from "@/lib/api";
  import type { ProyectoDetalle, Voz } from "@/lib/proyectos";

  // Tope del fragmento a clonar (debe coincidir con MAX_REF_S del backend).
  const MAX_CLIP_S = 15;

  let {
    p,
    voces,
    busy = false,
    onselectvoz,
    ongenerar,
    oncrearvoz,
    onclonarvoz,
    onborrarvoz,
  }: {
    p: ProyectoDetalle;
    voces: Voz[];
    busy?: boolean;
    onselectvoz: (slug: string) => void;
    ongenerar: (modo: "clon" | "design", instruct: string) => void;
    oncrearvoz: (nombre: string, instruct: string) => void;
    onclonarvoz: (nombre: string, audio: File, inicio: number, fin: number) => void;
    onborrarvoz: (slug: string, nombre: string) => void;
  } = $props();

  const disponibles = $derived(voces.filter((v) => v.disponible));
  const vozSel = $derived(disponibles.find((v) => v.slug === p.voz));

  // Instrucción de la narración expresiva (borrador de sesión).
  let instruct = $state("");
  $effect(() => {
    instruct = p.voz_instruct ?? "";
  });

  // --- crear voz nueva ---
  let abrirCrear = $state(false);
  let modoNueva = $state<"design" | "clon">("design");
  let nombreNueva = $state("");
  let instructNueva = $state("");
  let audioFile = $state<File | null>(null);
  let audioUrl = $state<string | null>(null);
  let dur = $state(0);
  let inicio = $state(0);
  let fin = $state(MAX_CLIP_S);
  let player = $state<HTMLAudioElement>();

  function elegirAudio(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0] ?? null;
    audioFile = f;
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = f ? URL.createObjectURL(f) : null;
    inicio = 0;
    fin = MAX_CLIP_S;
  }

  function marcarInicio() {
    if (!player) return;
    inicio = Math.max(0, player.currentTime);
    if (fin <= inicio) fin = Math.min(dur, inicio + MAX_CLIP_S);
    if (fin - inicio > MAX_CLIP_S) fin = inicio + MAX_CLIP_S;
  }

  function marcarFin() {
    if (!player) return;
    fin = Math.min(Math.max(player.currentTime, inicio + 0.5), inicio + MAX_CLIP_S);
  }

  function oirSeleccion() {
    if (!player) return;
    player.currentTime = inicio;
    player.play().catch(() => {});
  }
</script>

<div class="max-w-3xl space-y-5">
  <!-- Elegir voz del banco -->
  <Field label="Voz del banco">
    <select
      class="control"
      value={p.voz ?? ""}
      onchange={(e) => onselectvoz((e.currentTarget as HTMLSelectElement).value)}
    >
      <option value="">— sin elegir —</option>
      {#each disponibles as v (v.slug)}
        <option value={v.slug}>{v.nombre}</option>
      {/each}
    </select>
  </Field>

  {#if vozSel}
    <div class="space-y-2 rounded-lg border border-line bg-surface-2 p-3">
      <audio controls src={media(`/voces/${vozSel.slug}/audio`)}></audio>
      <p class="text-xs text-dim">{vozSel.instruct}</p>
    </div>
  {/if}

  <!-- Generar la narración -->
  <div class="flex flex-wrap gap-2">
    <Button disabled={busy || !p.voz} onclick={() => ongenerar("clon", "")}>
      {p.voz_disponible ? "Regenerar narración" : "Generar narración"}
    </Button>
    <Button
      variant="secondary"
      disabled={busy}
      onclick={() => ongenerar("design", instruct)}
      title="Narra el guion con VoiceDesign usando el estilo de abajo. No usa la voz del banco."
    >
      Narración expresiva
    </Button>
  </div>

  <Field
    label="Estilo de la narración expresiva"
    hint="El LLM lo sugiere según la historia; puedes retocarlo. Se envía a VoiceDesign y sobrescribe la narración."
  >
    <textarea class="control" rows="3" bind:value={instruct}
      placeholder="Cómo debe contar: tono, ritmo, emoción, pausas…"></textarea>
  </Field>

  {#if p.voz_disponible}
    <Field label="Narración generada">
      <audio controls src={`${media(`/proyectos/${p.id}/audio`)}?v=${p.guion_version}`}></audio>
    </Field>
  {/if}

  {#if p.subtitulos}
    <details class="rounded-lg border border-line bg-surface-2 p-3">
      <summary class="cursor-pointer text-sm text-dim">Ver subtítulos (.srt)</summary>
      <pre class="mt-2 max-h-60 overflow-auto text-xs leading-relaxed text-dim">{p.subtitulos}</pre>
    </details>
  {/if}

  <!-- Banco de voces -->
  <details class="rounded-lg border border-line bg-surface-2 p-3" bind:open={abrirCrear}>
    <summary class="cursor-pointer text-sm text-dim">Banco de voces ({voces.length})</summary>
    <div class="mt-3 space-y-3">
      {#each voces as v (v.slug)}
        <div class="flex items-center justify-between gap-2 text-sm">
          <span>
            {v.nombre}
            {#if v.estado !== "lista"}<span class="text-xs text-muted">({v.estado})</span>{/if}
          </span>
          <IconButton
            name="x"
            label="Borrar voz"
            size={16}
            onclick={() => onborrarvoz(v.slug, v.nombre)}
            class="hover:bg-danger-soft hover:text-danger"
          />
        </div>
      {/each}

      <div class="space-y-3 border-t border-line pt-3">
        <p class="text-xs font-medium tracking-wide text-muted">Crear una voz nueva</p>
        <Segmented
          options={[
            { value: "design", label: "Describir" },
            { value: "clon", label: "Clonar de un audio" },
          ]}
          value={modoNueva}
          onchange={(v) => (modoNueva = v as "design" | "clon")}
        />
        <input class="control" bind:value={nombreNueva} placeholder="Nombre (ej: Narrador Épico)" />

        {#if modoNueva === "design"}
          <textarea class="control" rows="2" bind:value={instructNueva}
            placeholder="Describe cómo suena: voz masculina grave, tono misterioso, ritmo pausado…"></textarea>
          <Button
            variant="secondary"
            size="sm"
            disabled={!nombreNueva.trim() || !instructNueva.trim()}
            onclick={() => oncrearvoz(nombreNueva.trim(), instructNueva.trim())}
          >
            Crear voz (VoiceDesign)
          </Button>
        {:else}
          <input class="control" type="file" accept="audio/*" onchange={elegirAudio} />
          {#if audioUrl}
            <div class="space-y-2">
              <audio
                bind:this={player}
                controls
                src={audioUrl}
                onloadedmetadata={() => {
                  dur = player?.duration ?? 0;
                  fin = Math.min(dur, MAX_CLIP_S);
                }}
                ontimeupdate={() => {
                  if (player && !player.paused && player.currentTime >= fin) player.pause();
                }}
              ></audio>
              <div class="flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" onclick={marcarInicio}>Inicio aquí</Button>
                <Button variant="secondary" size="sm" onclick={marcarFin}>Fin aquí</Button>
                <Button variant="secondary" size="sm" onclick={oirSeleccion}>Oír selección</Button>
              </div>
              <p class="text-xs text-muted">
                Fragmento a clonar: {inicio.toFixed(1)}s → {fin.toFixed(1)}s ({(fin - inicio).toFixed(1)}s).
                Máximo {MAX_CLIP_S}s.
              </p>
            </div>
          {/if}
          <Button
            variant="secondary"
            size="sm"
            disabled={!nombreNueva.trim() || !audioFile}
            onclick={() => audioFile && onclonarvoz(nombreNueva.trim(), audioFile, inicio, fin)}
          >
            Clonar voz del fragmento
          </Button>
        {/if}
      </div>
    </div>
  </details>
</div>
