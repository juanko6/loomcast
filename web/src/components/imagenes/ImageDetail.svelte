<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Button from "../primitives/Button.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import {
    DURACION_MAX_S,
    DURACION_MIN_S,
    ESCALAS,
    ESTADOS_APROBADA,
    NOMBRE_ESCALA,
    N_PREVIEWS_MAX,
    rutaVideo,
    type Escala,
    type EstiloImagen,
    type GaleriaDetalle,
  } from "@/lib/galeria";

  let {
    detail,
    busy = false,
    previewSel = null,
    verGrid = false,
    bust = 0,
    estilos = [],
    onpreviews,
    onmejorar,
    onpick,
    onfinal,
    onreelegir,
    onmejorarmov = () => {},
    onanimar = () => {},
    onescalar = () => {},
    oncambiarestilo = () => {},
  }: {
    detail: GaleriaDetalle | null;
    busy?: boolean;
    previewSel?: number | null;
    verGrid?: boolean;
    bust?: number;
    estilos?: EstiloImagen[];
    onpreviews: (prompt: string, nPreviews: number) => void;
    onmejorar: () => void;
    onpick: (i: number) => void;
    onfinal: () => void;
    onreelegir: () => void;
    onmejorarmov?: (prompt: string, duracion: number) => void;
    onanimar?: (prompt: string, duracion: number) => void;
    onescalar?: (escala: Escala) => void;
    oncambiarestilo?: (estilo: string) => void;
  } = $props();

  // Borrador local del prompt, re-sincronizado al cambiar de imagen o cuando el
  // LLM lo reescribe (el padre refresca `detail`).
  let prompt = $state("");
  $effect(() => {
    prompt = detail?.prompt ?? "";
  });

  // Previews de la próxima tirada: arranca en las que pidió al crearla.
  let nPreviews = $state(4);
  $effect(() => {
    nPreviews = detail?.n_previews ?? 4;
  });

  // La escena se pliega cuando ya hay previews: a partir de ahí lo que se
  // mira son las imágenes, y se abre solo si se quiere retocar.
  let escenaAbierta = $state(true);
  let idEscena: number | null = null;
  $effect(() => {
    if (detail && detail.id !== idEscena) {
      idEscena = detail.id;
      escenaAbierta = detail.seeds.length === 0;
    }
  });

  // Borrador del movimiento de una animada; lo reescribe el LLM al pulirlo.
  let movimiento = $state("");
  let duracion = $state(12);
  $effect(() => {
    movimiento = detail?.prompt_movimiento ?? "";
    duracion = detail?.duracion_s ?? 12;
  });

  const esFondo = $derived(detail?.tipo === "quitarfondo");
  // Generar y animada nacen de un título con estilo; editar sigue con su prompt.
  const conEstilo = $derived(detail?.tipo === "generar" || detail?.tipo === "animada");
  const estiloActual = $derived(estilos.find((e) => e.id === detail?.estilo) ?? null);
  const escribiendo = $derived(busy && !detail?.prompt);
  const esAnimada = $derived(detail?.tipo === "animada");
  const aprobada = $derived(!!detail && esAnimada && ESTADOS_APROBADA.includes(detail.estado));
  const hayVideo = $derived(!!detail && detail.videos.includes("base"));

  // `?v=` para que el navegador no se quede con el bucle anterior al reanimar.
  function srcVideo(escala?: Escala) {
    const url = media(rutaVideo(detail!.id, escala));
    return `${url}${url.includes("?") ? "&" : "?"}v=${bust}`;
  }
  const tieneOrigen = $derived(detail?.tipo === "editar" || detail?.tipo === "quitarfondo");
  // Mientras sale una tirada, la rejilla tiene sus `n_previews` huecos desde
  // el principio y se van llenando; lo de antes (la final, la aprobada) no se
  // enseña porque la tirada nueva la sustituye.
  const generando = $derived(!!detail?.generando_previews);
  const mostrarGrid = $derived(
    !!detail &&
      (generando ||
        (detail.seeds.length > 0 &&
          (detail.estado === "previews" || ((detail.estado === "final" || aprobada) && verGrid)))),
  );
  const huecos = $derived(
    detail ? (generando ? Math.max(detail.n_previews, detail.seeds.length) : detail.seeds.length) : 0,
  );
  const mostrarFinal = $derived(
    !!detail && !esAnimada && detail.estado === "final" && !verGrid && !generando,
  );
  const mostrarMovimiento = $derived(aprobada && !verGrid && !generando);
</script>

<aside class="flex h-full w-[420px] min-w-0 shrink-0 flex-col border-l border-line bg-surface">
  <header class="flex items-center gap-2 border-b border-line px-5 py-4">
    <h2 class="text-sm font-semibold">Trabajo</h2>
    {#if detail && !esFondo && detail.motor_nombre}
      <span class="ml-auto rounded-full border border-line px-2 py-0.5 text-xs text-dim">
        {detail.motor_nombre}
      </span>
    {/if}
  </header>

  <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
    {#if !detail}
      <p class="mt-10 text-center text-sm text-dim">
        Selecciona una imagen o crea una nueva para empezar.
      </p>
    {:else}
      {#if busy}
        <div class="flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-4 py-3 text-dim">
          <span class="size-5 shrink-0 animate-spin rounded-full border-2 border-line border-t-accent"></span>
          <p class="text-sm">
            {esFondo ? "Quitando el fondo…" : escribiendo ? "Escribiendo la escena…" : "Trabajando… (un job en curso)"}
          </p>
        </div>
      {/if}

      {#if tieneOrigen}
        <div class="space-y-1.5">
          <p class="text-xs font-medium tracking-wide text-muted">Imagen de origen</p>
          <img src={media(`/galeria/${detail.id}/fuente`)} alt="origen" class="max-h-48 rounded-lg" />
        </div>
      {/if}

      {#if esFondo}
        {#if detail.estado === "final"}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Resultado (fondo transparente)</p>
            <div class="checker overflow-hidden rounded-lg">
              <img src={`${media(`/galeria/${detail.id}/final`)}?v=${bust}`} alt="resultado" class="block max-w-full" />
            </div>
            <a
              href={media(`/galeria/${detail.id}/final`)}
              download={`loomcast_${detail.id}.png`}
              class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
            >
              <Icon name="download" size={16} /> Descargar PNG
            </a>
          </div>
        {/if}
      {:else if conEstilo}
        <!-- generar / animada: título + estilo -> escena (la escribe el LLM al
             crear, editable) -> N previews -> final o movimiento -->
        <div class="space-y-1">
          <p class="text-sm font-medium text-text">{detail.idea}</p>
          {#if detail.detalles}
            <p class="text-xs text-dim">{detail.detalles}</p>
          {/if}
        </div>

        <label class="flex items-center gap-2 text-xs text-dim">
          <span class="shrink-0">Estilo</span>
          <select
            class="control"
            value={detail.estilo}
            disabled={busy}
            onchange={(e) => oncambiarestilo(e.currentTarget.value)}
          >
            <option value="">Libre</option>
            {#each estilos as e (e.id)}
              <option value={e.id}>{e.nombre}</option>
            {/each}
          </select>
        </label>

        <details class="rounded-lg border border-line bg-surface-2" bind:open={escenaAbierta}>
          <summary class="cursor-pointer px-3 py-2 text-xs font-medium tracking-wide text-muted">
            {estiloActual ? "Escena (inglés, editable)" : "Prompt (inglés, editable)"}
          </summary>
          <div class="space-y-2 px-3 pb-3">
            <textarea
              class="control"
              rows="5"
              bind:value={prompt}
              placeholder={escribiendo ? "El LLM está escribiendo la escena…" : "Qué se dibuja, en inglés."}
            ></textarea>
            <p class="text-xs text-muted">
              {estiloActual
                ? `Solo qué se dibuja: el estilo «${estiloActual.nombre}» se añade delante y detrás al generar.`
                : "Sin estilo, este es el prompt completo."}
            </p>
          </div>
        </details>

        <div class="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" disabled={busy} onclick={onmejorar}>
            Reescribir con el LLM
          </Button>
          <label class="flex items-center gap-1 text-xs text-dim">
            <span class="sr-only">Cuántas previews</span>
            <select class="control !w-auto !py-1" bind:value={nPreviews} disabled={busy}>
              {#each Array.from({ length: N_PREVIEWS_MAX }, (_, i) => i + 1) as n (n)}
                <option value={n}>{n}</option>
              {/each}
            </select>
          </label>
          <Button size="sm" disabled={busy || !prompt.trim()} onclick={() => onpreviews(prompt, nPreviews)}>
            {detail.seeds.length ? "Regenerar previews" : "Generar previews"}
          </Button>
          <span class="text-xs text-muted">{detail.width}×{detail.height}</span>
        </div>
      {:else}
        <!-- editar: prompt (mejorar es opcional) -> previews -> final -->
        <div class="space-y-2">
          <p class="text-xs font-medium tracking-wide text-muted">Prompt (inglés, editable)</p>
          <textarea
            class="control"
            rows="4"
            bind:value={prompt}
            placeholder="Escribe el prompt en inglés, o pulsa «Mejorar prompt con el LLM»."
          ></textarea>
          <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" disabled={busy} onclick={onmejorar}>
              Mejorar prompt con el LLM
            </Button>
            <Button size="sm" disabled={busy || !prompt.trim()} onclick={() => onpreviews(prompt, nPreviews)}>
              {detail.seeds.length ? `Regenerar ${nPreviews} previews` : `Generar ${nPreviews} previews`}
            </Button>
          </div>
        </div>
      {/if}

      {#if !esFondo}
        {#if mostrarGrid}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">
              {generando
                ? `Generando previews: ${detail.seeds.length} de ${huecos}`
                : esAnimada
                  ? "Elige la que quieres animar"
                  : "Elige la mejor (se ampliará a máxima resolución)"}
            </p>
            <div class="grid grid-cols-2 gap-2">
              {#each Array.from({ length: huecos }, (_, i) => i) as i (i)}
                {#if i < detail.seeds.length}
                  <!-- La semilla en la URL: cada tirada estrena URL, así el
                       navegador no enseña la preview_0 de la tirada anterior. -->
                  <button
                    type="button"
                    disabled={generando}
                    onclick={() => onpick(i)}
                    class={`overflow-hidden rounded-lg border-2 transition
                      ${previewSel === i ? "border-accent" : "border-line hover:border-dim"}`}
                  >
                    <img
                      src={`${media(`/galeria/${detail.id}/preview/${i}`)}?v=${detail.seeds[i]}`}
                      alt={`preview ${i + 1}`}
                      class="w-full object-cover"
                      style={`aspect-ratio: ${detail.width} / ${detail.height}`}
                    />
                  </button>
                {:else}
                  <div
                    role="img"
                    aria-label={i === detail.seeds.length ? `preview ${i + 1}: generando` : `preview ${i + 1}: en cola`}
                    class={`flex items-center justify-center rounded-lg border-2 border-line bg-surface-2 text-xs text-muted
                      ${i === detail.seeds.length ? "animate-pulse" : "opacity-60"}`}
                    style={`aspect-ratio: ${detail.width} / ${detail.height}`}
                  >
                    {i === detail.seeds.length ? "Generando…" : "En cola"}
                  </div>
                {/if}
              {/each}
            </div>
            {#if !generando}
              <Button disabled={previewSel === null || busy} onclick={onfinal}>
                {esAnimada ? "Aprobar esta imagen" : "Generar máxima resolución"}
              </Button>
            {/if}
          </div>
        {/if}

        {#if mostrarMovimiento}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Imagen aprobada</p>
            <img
              src={`${media(`/galeria/${detail.id}/final`)}?v=${bust}`}
              alt="imagen aprobada"
              class="max-h-56 rounded-lg"
            />
            <Button size="sm" variant="secondary" disabled={busy} onclick={onreelegir}>Elegir otra preview</Button>
          </div>

          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Movimiento</p>
            <label class="sr-only" for="movimiento">Prompt de movimiento</label>
            <textarea
              id="movimiento"
              class="control"
              rows="4"
              bind:value={movimiento}
              placeholder="Qué se mueve y cómo. Ej: se balancea al ritmo, da un sorbo y vuelve a apoyar el vaso."
            ></textarea>
            <div class="space-y-1">
              <label class="flex items-center justify-between text-xs text-dim" for="duracion">
                <span>Duración</span><span>{duracion} s</span>
              </label>
              <input
                id="duracion"
                type="range"
                class="w-full accent-accent"
                min={DURACION_MIN_S}
                max={DURACION_MAX_S}
                step="1"
                bind:value={duracion}
              />
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={busy || !movimiento.trim()}
                onclick={() => onmejorarmov(movimiento, duracion)}
              >
                Mejorar con IA
              </Button>
              <Button size="sm" disabled={busy || !movimiento.trim()} onclick={() => onanimar(movimiento, duracion)}>
                {hayVideo ? "Volver a animar" : "Animar"}
              </Button>
            </div>
            <p class="text-xs text-muted">
              «Mejorar con IA» es opcional: pule tu texto sin cambiar la intención y recomienda la duración.
            </p>
          </div>

          {#if hayVideo}
            <div class="space-y-2">
              <p class="text-xs font-medium tracking-wide text-muted">Bucle</p>
              <!-- svelte-ignore a11y_media_has_caption -->
              <video src={srcVideo()} autoplay loop muted playsinline class="max-w-full rounded-lg"></video>
              <div class="flex flex-wrap items-center gap-2">
                <a
                  href={media(rutaVideo(detail.id))}
                  download={`loomcast_${detail.id}.mp4`}
                  class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
                >
                  <Icon name="download" size={16} /> Descargar MP4
                </a>
                {#each ESCALAS as e (e)}
                  {#if detail.videos.includes(e)}
                    <a
                      href={media(rutaVideo(detail.id, e))}
                      download={`loomcast_${detail.id}_${e}.mp4`}
                      class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
                    >
                      <Icon name="download" size={16} /> MP4 {NOMBRE_ESCALA[e]}
                    </a>
                  {:else}
                    <Button size="sm" variant="secondary" disabled={busy} onclick={() => onescalar(e)}>
                      Escalar a {NOMBRE_ESCALA[e]}
                    </Button>
                  {/if}
                {/each}
              </div>
            </div>
          {/if}
        {/if}

        {#if mostrarFinal}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Imagen final</p>
            <img src={`${media(`/galeria/${detail.id}/final`)}?v=${bust}`} alt="final" class="max-w-full rounded-lg" />
            <div class="flex items-center gap-2">
              <a
                href={media(`/galeria/${detail.id}/final`)}
                download={`loomcast_${detail.id}.png`}
                class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
              >
                <Icon name="download" size={16} /> Descargar PNG
              </a>
              <Button size="sm" variant="secondary" onclick={onreelegir}>Elegir otra preview</Button>
            </div>
          </div>
        {/if}
      {/if}
    {/if}
  </div>
</aside>
