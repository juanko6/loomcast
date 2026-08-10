<script lang="ts">
  import Button from "../../primitives/Button.svelte";
  import Chip from "../../primitives/Chip.svelte";
  import { media } from "@/lib/api";
  import { NOMBRE_MODO, type Personaje, type ProyectoDetalle } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    bust = 0,
    ongenerar,
    onguardar,
    ongenerarcasting,
    onguardarcasting,
    ongenerarimagenes,
    onregenimagen,
    onregenclip,
    onfijarmodos,
    onver,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    bust?: number;
    ongenerar: () => void;
    onguardar: (e: { orden: number; prompt: string; prompt_movimiento: string | null }[]) => void;
    ongenerarcasting: () => void;
    onguardarcasting: (p: Personaje[]) => void;
    ongenerarimagenes: (e: { orden: number; prompt: string; prompt_movimiento: string | null }[]) => void;
    onregenimagen: (orden: number, nuevoSeed: boolean) => void;
    onregenclip: (orden: number, modo: string) => void;
    onfijarmodos: (e: { orden: number; modo: string }[]) => void;
    onver: (html: string, pie: string) => void;
  } = $props();

  const MODOS = ["estatico", "kenburns", "i2v"];

  // Borrador local de prompts y modos por escena.
  let prompts = $state<Record<number, string>>({});
  let movs = $state<Record<number, string>>({});
  let modos = $state<Record<number, string>>({});

  $effect(() => {
    const pr: Record<number, string> = {};
    const mv: Record<number, string> = {};
    const md: Record<number, string> = {};
    for (const e of p.escenas) {
      pr[e.orden] = e.prompt ?? "";
      mv[e.orden] = e.prompt_movimiento ?? "";
      md[e.orden] = e.modo ?? "kenburns";
    }
    prompts = pr;
    movs = mv;
    modos = md;
  });

  // Borrador local del reparto (mismo patrón que los prompts).
  let fichas = $state<Record<string, string>>({});
  $effect(() => {
    const f: Record<string, string> = {};
    for (const c of p.personajes) f[c.clave] = c.ficha;
    fichas = f;
  });

  // Un casting ya generado que sale vacío es una respuesta válida (el guion no
  // tiene personajes recurrentes), pero es indistinguible de "aún no generado".
  // Se resuelve mirando si ya hay escenas: si las hay, el casting ya se resolvió.
  const castingHecho = $derived(p.personajes.length > 0);

  function guardarFichas() {
    onguardarcasting(
      p.personajes.map((c) => ({
        clave: c.clave,
        nombre: c.nombre,
        ficha: (fichas[c.clave] ?? "").trim(),
      })),
    );
  }

  function recogerPrompts() {
    return p.escenas.map((e) => ({
      orden: e.orden,
      prompt: (prompts[e.orden] ?? "").trim(),
      prompt_movimiento: (movs[e.orden] ?? "").trim() || null,
    }));
  }

  function cambiarModo(orden: number, modo: string) {
    modos[orden] = modo;
    onfijarmodos([{ orden, modo }]);
  }

  function modoTodas(modo: string) {
    if (!modo) return;
    for (const e of p.escenas) modos[e.orden] = modo;
    onfijarmodos(p.escenas.map((e) => ({ orden: e.orden, modo })));
  }
</script>

<!-- Reparto: va antes de los prompts porque es lo que se inyecta en ellos. -->
<section class="mb-5 max-w-3xl rounded-xl border border-line bg-surface-2 p-4">
  <h3 class="text-sm font-semibold">Reparto</h3>
  <p class="mt-1 text-sm text-dim">
    Descripción física fija de quien sale en varias escenas. Se pega tal cual en cada prompt
    donde aparece, que es lo que hace que el generador dibuje a la misma persona y no a una
    distinta cada cuatro segundos. Un vídeo sin personajes recurrentes no necesita reparto.
  </p>

  {#if castingHecho}
    <div class="mt-3 space-y-3">
      {#each p.personajes as c (c.clave)}
        <div>
          <div class="mb-1 flex flex-wrap items-center gap-2">
            <Chip tone="accent">{"{" + c.clave + "}"}</Chip>
            <span class="text-xs text-muted">{c.nombre}</span>
          </div>
          <textarea
            class="control min-h-16 text-sm"
            bind:value={fichas[c.clave]}
            placeholder="Descripción física en inglés"
          ></textarea>
        </div>
      {/each}
    </div>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <Button size="sm" onclick={guardarFichas}>Guardar reparto</Button>
      <Button variant="secondary" size="sm" disabled={busy} onclick={ongenerarcasting}>
        Regenerar reparto
      </Button>
      {#if p.escenas.length}
        <span class="text-xs text-muted">
          Los prompts ya escritos no cambian solos: regenéralos para aplicar el reparto nuevo.
        </span>
      {/if}
    </div>
  {:else}
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <Button variant="secondary" size="sm" disabled={busy} onclick={ongenerarcasting}>
        {p.escenas.length ? "Buscar reparto en el guion" : "Generar reparto"}
      </Button>
      {#if p.escenas.length}
        <span class="text-xs text-muted">
          Este vídeo no tiene reparto fijado. Si sus escenas llevan personas, generarlo y
          regenerar los prompts hará que se parezcan entre sí.
        </span>
      {/if}
    </div>
  {/if}
</section>

{#if !p.escenas.length}
  <div class="max-w-2xl space-y-3">
    <p class="text-sm text-dim">
      El LLM propone un prompt visual por segmento de la narración, que puedes editar antes de
      gastar GPU en las imágenes.
    </p>
    <Button disabled={busy} onclick={ongenerar}>Generar prompts de escenas</Button>
  </div>
{:else}
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <Button variant="secondary" size="sm" disabled={busy} onclick={ongenerar}>
        Regenerar prompts
      </Button>
      <Button size="sm" onclick={() => onguardar(recogerPrompts())}>Guardar prompts</Button>
      <Button size="sm" disabled={busy} onclick={() => ongenerarimagenes(recogerPrompts())}>
        {p.imagenes_completas ? "Regenerar imágenes" : "Generar imágenes"}
      </Button>
      <label class="ml-auto flex items-center gap-2 text-xs text-muted">
        Modo de todas
        <select
          class="control w-auto py-1 text-xs"
          value=""
          onchange={(e) => {
            modoTodas((e.currentTarget as HTMLSelectElement).value);
            (e.currentTarget as HTMLSelectElement).value = "";
          }}
        >
          <option value="">— elegir —</option>
          {#each MODOS as m (m)}
            <option value={m}>{NOMBRE_MODO[m]}</option>
          {/each}
        </select>
      </label>
    </div>

    <div class="space-y-3">
      {#each p.escenas as e (e.orden)}
        <article class="rounded-xl border border-line bg-surface-2 p-3">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <Chip tone="accent">#{e.orden + 1}</Chip>
            <span class="text-xs tabular-nums text-muted">
              {e.t_inicio.toFixed(1)}–{e.t_fin.toFixed(1)}s
            </span>
            <span class="min-w-0 flex-1 truncate text-xs text-dim">{e.texto}</span>
            {#if e.en_cola}
              <Chip tone="accent">⏳ {e.en_cola} en cola</Chip>
            {/if}
            {#if e.clip_viejo}
              <Chip tone="warn">clip desactualizado</Chip>
            {/if}
          </div>

          <div class="flex gap-3">
            <!-- Miniatura de la escena -->
            {#if e.imagen}
              <button
                type="button"
                class="shrink-0 cursor-zoom-in"
                onclick={() =>
                  onver(
                    `<img src="${media(`/proyectos/${p.id}/imagenes/${e.orden}`)}?v=${bust}" alt="escena ${e.orden + 1}">`,
                    `Escena ${e.orden + 1} · imagen`,
                  )}
              >
                <img
                  src={`${media(`/proyectos/${p.id}/imagenes/${e.orden}`)}?v=${bust}`}
                  alt={`escena ${e.orden + 1}`}
                  class="w-14 rounded-md object-cover"
                  style="aspect-ratio:9/16"
                />
              </button>
            {:else}
              <div
                class="grid w-14 shrink-0 place-items-center rounded-md bg-surface-3 text-xs text-muted"
                style="aspect-ratio:9/16"
              >
                {e.orden + 1}
              </div>
            {/if}

            <div class="min-w-0 flex-1 space-y-2">
              <textarea
                class="control text-xs"
                rows="2"
                bind:value={prompts[e.orden]}
                placeholder="Prompt visual (imagen)"
              ></textarea>
              <textarea
                class="control text-xs"
                rows="2"
                bind:value={movs[e.orden]}
                placeholder="Prompt de movimiento (solo modo i2v)"
              ></textarea>

              <div class="flex flex-wrap items-center gap-1.5">
                <Button size="sm" variant="secondary" disabled={!!e.en_cola}
                  onclick={() => onregenimagen(e.orden, true)}
                  title="Genera otra imagen distinta (seed nuevo)">Otra imagen</Button>
                <Button size="sm" variant="ghost" disabled={!!e.en_cola}
                  onclick={() => onregenimagen(e.orden, false)}
                  title="Rehace la imagen con el mismo seed: solo cambia si editaste el prompt">Mismo seed</Button>
                <select
                  class="control w-auto py-1 text-xs"
                  value={modos[e.orden]}
                  onchange={(ev) => cambiarModo(e.orden, (ev.currentTarget as HTMLSelectElement).value)}
                >
                  {#each MODOS as m (m)}
                    <option value={m}>{NOMBRE_MODO[m]}</option>
                  {/each}
                </select>
                <Button size="sm" variant="secondary" disabled={!!e.en_cola || !e.imagen}
                  onclick={() => onregenclip(e.orden, modos[e.orden])}
                  title={e.imagen ? "Regenera el clip de esta escena" : "Genera antes la imagen"}>Clip</Button>
                {#if e.clip}
                  <Button size="sm" variant="ghost"
                    onclick={() =>
                      onver(
                        `<video src="${media(`/proyectos/${p.id}/clips/${e.orden}`)}?v=${bust}" controls autoplay loop muted playsinline></video>`,
                        `Escena ${e.orden + 1} · clip ${NOMBRE_MODO[e.clip_modo ?? ""] ?? ""}`,
                      )}>Ver clip</Button>
                {/if}
                <span class="text-[11px] text-muted">
                  {#if e.imagen_s}img {e.imagen_s}s{/if}
                  {#if e.clip}
                    · clip {e.clip_modo ? NOMBRE_MODO[e.clip_modo] : "(modo sin registrar)"}{#if e.clip_s} · {e.clip_s}s{/if}
                  {/if}
                </span>
              </div>
            </div>
          </div>
        </article>
      {/each}
    </div>
  </div>
{/if}
