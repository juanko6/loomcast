<script lang="ts">
  // Vista de una serie: su hilo, su reparto fijo, sus episodios y el botón que
  // de verdad se usa a diario, "Nuevo episodio".
  //
  // El orden de la pantalla es el orden en que se produce una serie: primero se
  // decide de qué va y a dónde llega (el hilo), después quién sale siempre, y a
  // partir de ahí todo es sacar capítulos. El hilo va primero porque es el que
  // reparte el sitio de cada episodio: el apunte es opcional justamente porque,
  // con hilo, el capítulo que toca ya está decidido.
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import Field from "../primitives/Field.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import { media } from "@/lib/api";
  import type { MiembroReparto } from "@/lib/proyectos";
  import type { Hilo, SerieDetalle, Tramo } from "@/lib/series";

  let {
    s,
    reparto = [],
    busy = false,
    onnuevoepisodio,
    onabrirepisodio,
    onanadirmiembro,
    onquitarmiembro,
    onideas,
    onguardarpremisa,
    onescribirhilo,
    oneditarhilo,
    onborrarserie,
  }: {
    s: SerieDetalle;
    reparto?: MiembroReparto[];
    busy?: boolean;
    onnuevoepisodio: (apunte: string) => void;
    onabrirepisodio: (pid: number) => void;
    onanadirmiembro: (slug: string) => void;
    onquitarmiembro: (slug: string, nombre: string) => void;
    onideas: () => void;
    // Guardar la premisa no reescribe el hilo: son dos acciones porque rehacer
    // el hilo replanifica los capítulos que no se han escrito.
    onguardarpremisa: (premisa: string, episodios: number) => void;
    onescribirhilo: () => void;
    oneditarhilo: (hilo: Hilo) => void;
    onborrarserie: () => void;
  } = $props();

  let apunte = $state("");
  let aFichar = $state("");

  // La premisa y los episodios pedidos, con el mismo patrón que el resto de los
  // editores: lo guardado es la fuente, y se recarga al cambiar por fuera salvo
  // que haya algo a medio escribir.
  let premisa = $state("");
  let episodios = $state(0);
  let premisaGuardada = $state("");
  let episodiosGuardados = $state(0);
  $effect(() => {
    if (s.premisa !== premisaGuardada) {
      if (premisa === premisaGuardada) premisa = s.premisa;
      premisaGuardada = s.premisa;
    }
    if (s.episodios_objetivo !== episodiosGuardados) {
      if (episodios === episodiosGuardados) episodios = s.episodios_objetivo;
      episodiosGuardados = s.episodios_objetivo;
    }
  });
  const premisaSucia = $derived(
    premisa.trim() !== premisaGuardada.trim() || episodios !== episodiosGuardados,
  );

  // Borrador del hilo: null = no se está editando a mano. Se copia al abrir el
  // editor, así que lo que el LLM reescriba entretanto no pisa lo que se esté
  // tecleando.
  let borrador = $state<Hilo | null>(null);
  let fueraTexto = $state("");

  function editar() {
    if (!s.hilo) return;
    borrador = { ...s.hilo, tramos: s.hilo.tramos.map((t) => ({ ...t })) };
    fueraTexto = s.hilo.fuera.join("\n");
  }

  function guardarHilo() {
    if (!borrador) return;
    oneditarhilo({
      ...borrador,
      fuera: fueraTexto.split("\n").map((x) => x.trim()).filter(Boolean),
    });
    borrador = null;
  }

  const vacio: Tramo = { numero: 0, titulo: "", pasa: "", cambia: "" };

  // Los del reparto propio que todavía no salen en la serie: lo que queda por
  // elegir en el selector.
  const disponibles = $derived(
    reparto.filter((m) => !s.miembros.some((x) => x.slug === m.slug)),
  );
  const ultimo = $derived(s.episodios[s.episodios.length - 1] ?? null);
  const siguiente = $derived((ultimo?.episodio ?? 0) + 1);
  // Qué episodio cubre cada tramo: con esto el mapa de la serie se lee de un
  // vistazo, y se ve en qué capítulo se torció.
  const porNumero = $derived(
    new Map(s.episodios.map((e) => [e.episodio, e])),
  );
  const tramoSiguiente = $derived(
    s.hilo?.tramos.find((t) => t.numero === siguiente) ?? null,
  );

  function nuevo() {
    onnuevoepisodio(apunte.trim());
    apunte = "";
  }
</script>

<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
  <div class="max-w-3xl space-y-6">
    <header class="flex flex-wrap items-center gap-3">
      <h2 class="text-lg font-semibold tracking-tight text-balance">{s.nombre}</h2>
      <Chip tone="accent">{s.plantilla}</Chip>
      <Chip>
        {#if s.n_tramos}
          {s.n_episodios} de {s.n_tramos} episodios
        {:else}
          {s.n_episodios} {s.n_episodios === 1 ? "episodio" : "episodios"}
        {/if}
      </Chip>
    </header>

    <!-- El hilo: de qué va la serie y a dónde llega -->
    <section class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
      <div>
        <h3 class="text-sm font-semibold">El hilo</h3>
        <p class="text-xs text-dim">
          La continuidad de siempre mira atrás: impide contradecir lo que pasó. El hilo mira
          adelante, que es otra cosa: dice cómo acaba la serie y le da a cada episodio el sitio que
          ocupa. Es lo que impide que el capítulo seis sea de otra historia.
        </p>
      </div>

      <Field label="Premisa" hint="Una o dos frases: de aquí sale el hilo.">
        <textarea
          class="control"
          rows="2"
          bind:value={premisa}
          placeholder="Alicia hereda la casa de su tía y descubre que alguien ya vive en ella."
          aria-label="Premisa de la serie"
        ></textarea>
      </Field>

      <div class="flex flex-wrap items-end gap-2">
        <div class="w-36">
          <Field label="Episodios" hint="0 = lo decide el LLM">
            <input
              class="control"
              type="number"
              min="0"
              max="24"
              bind:value={episodios}
              aria-label="Episodios de la serie"
            />
          </Field>
        </div>
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || !premisaSucia}
          onclick={() => onguardarpremisa(premisa.trim(), episodios)}
        >
          Guardar
        </Button>
        <Button size="sm" disabled={busy || !premisa.trim()} onclick={onescribirhilo}>
          {s.tiene_hilo ? "Replanificar lo que queda" : "Escribir el hilo"}
        </Button>
      </div>

      {#if !s.hilo}
        <p class="text-xs text-muted">
          Sin hilo la serie funciona como antes: cada capítulo solo sabe lo que pasó en el
          anterior, y nada dice a dónde va. Escribe la premisa y pide el hilo.
        </p>
      {:else}
        <dl class="space-y-1 rounded-lg bg-surface p-3 text-xs">
          <div>
            <dt class="inline font-semibold">La pregunta de la serie: </dt>
            <dd class="inline text-dim">{s.hilo.pregunta}</dd>
          </div>
          <div>
            <dt class="inline font-semibold">Cómo acaba: </dt>
            <dd class="inline text-dim">{s.hilo.destino}</dd>
          </div>
          {#if s.hilo.fuera.length}
            <div>
              <dt class="inline font-semibold">Nunca: </dt>
              <dd class="inline text-dim">{s.hilo.fuera.join(" · ")}</dd>
            </div>
          {/if}
          <div>
            <dt class="inline font-semibold">Recomendaba {s.hilo.episodios_recomendados}: </dt>
            <dd class="inline text-dim">{s.hilo.por_que}</dd>
          </div>
        </dl>

        <!-- El mapa: un tramo por episodio, y qué capítulo cubre cada uno. -->
        <ol class="space-y-1">
          {#each s.hilo.tramos as t (t.numero)}
            {@const ep = porNumero.get(t.numero)}
            <li
              class={`rounded-lg border p-2.5 text-xs
                ${t.numero === siguiente ? "border-accent/50 bg-accent-soft/30" : "border-line"}`}
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-semibold tabular-nums text-accent">EP {t.numero}</span>
                <span class="min-w-0 flex-1 truncate font-medium">{t.titulo}</span>
                {#if ep}
                  <Chip tone="ok">rodado</Chip>
                {:else if t.numero === siguiente}
                  <Chip tone="accent">el siguiente</Chip>
                {:else}
                  <Chip>por rodar</Chip>
                {/if}
                {#if t.numero === s.hilo.tramos.length}
                  <Chip tone="accent">cierra</Chip>
                {/if}
              </div>
              <p class="mt-1 text-dim">{t.pasa}</p>
              {#if ep?.desvio}
                <p class="mt-1 text-warn">Se desvió: {ep.desvio}</p>
              {/if}
            </li>
          {/each}
        </ol>

        {#if s.n_episodios > s.hilo.tramos.length}
          <p class="text-xs text-warn">
            Hay {s.n_episodios} episodios y el hilo llega al {s.hilo.tramos.length}: los de más allá
            se escriben sin tramo. Replanifica, o dala por acabada.
          </p>
        {/if}

        <div class="flex flex-wrap items-center gap-2">
          {#if borrador}
            <Button size="sm" disabled={busy} onclick={guardarHilo}>Guardar el hilo</Button>
            <Button size="sm" variant="ghost" onclick={() => (borrador = null)}>Cancelar</Button>
          {:else}
            <Button size="sm" variant="ghost" onclick={editar}>Corregir a mano</Button>
            <span class="text-xs text-muted">Versión {s.hilo_version}</span>
          {/if}
        </div>

        {#if borrador}
          <div class="space-y-3 rounded-lg border border-line p-3">
            <p class="text-xs text-dim">
              Los tramos ya rodados se pueden tocar, pero lo que cambie no reescribe sus capítulos:
              aquí se replanifica lo que queda.
            </p>
            <Field label="Premisa del hilo">
              <textarea
                class="control"
                rows="2"
                aria-label="Premisa del hilo"
                bind:value={borrador.premisa}
              ></textarea>
            </Field>
            <Field label="La pregunta de la serie">
              <input
                class="control"
                aria-label="La pregunta de la serie"
                bind:value={borrador.pregunta}
              />
            </Field>
            <Field label="Cómo acaba">
              <textarea
                class="control"
                rows="2"
                aria-label="Cómo acaba"
                bind:value={borrador.destino}
              ></textarea>
            </Field>
            <Field label="Lo que esta serie nunca hace" hint="Una por línea.">
              <textarea
                class="control"
                rows="3"
                aria-label="Lo que esta serie nunca hace"
                bind:value={fueraTexto}
              ></textarea>
            </Field>

            <Field label="Tramos" hint="Vacía uno para borrarlo; se renumeran al guardar.">
              <div class="space-y-2">
                {#each borrador.tramos as _, i (i)}
                  <div class="space-y-1 rounded-lg bg-surface p-2">
                    <div class="flex items-center gap-2">
                      <span class="w-12 shrink-0 text-xs font-semibold tabular-nums text-accent">
                        EP {i + 1}
                      </span>
                      <input
                        class="control min-w-0 flex-1"
                        placeholder="Título del tramo"
                        aria-label={`Título del tramo ${i + 1}`}
                        bind:value={borrador.tramos[i].titulo}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Quitar tramo"
                        onclick={() =>
                          (borrador = borrador && {
                            ...borrador,
                            tramos: borrador.tramos.filter((_, j) => j !== i),
                          })}
                      >
                        ✕
                      </Button>
                    </div>
                    <input
                      class="control"
                      placeholder="Qué pasa en este episodio"
                      aria-label={`Qué pasa en el tramo ${i + 1}`}
                      bind:value={borrador.tramos[i].pasa}
                    />
                    <input
                      class="control"
                      placeholder="Qué ha cambiado al terminarlo"
                      aria-label={`Qué cambia en el tramo ${i + 1}`}
                      bind:value={borrador.tramos[i].cambia}
                    />
                  </div>
                {/each}
              </div>
            </Field>
            <Button
              variant="secondary"
              size="sm"
              onclick={() =>
                (borrador = borrador && {
                  ...borrador,
                  tramos: [...borrador.tramos, { ...vacio }],
                })}
            >
              + Añadir tramo
            </Button>
          </div>
        {/if}
      {/if}
    </section>

    <!-- Reparto fijo -->
    <section class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
      <div>
        <h3 class="text-sm font-semibold">Reparto fijo</h3>
        <p class="text-xs text-dim">
          Sale en todos los episodios. Cada capítulo nuevo se los trae del reparto propio con su
          ficha, su cara y su voz ya puestas, así que no hay que volver a describirlos.
        </p>
      </div>

      {#if s.miembros.length}
        <ul class="space-y-2">
          {#each s.miembros as m (m.slug)}
            <li class="flex items-center gap-3 rounded-lg bg-surface p-2">
              <Thumbnail
                src={m.retrato ? media(`/reparto/${m.slug}/retrato`) : null}
                alt={`Retrato de ${m.nombre}`}
                size={40}
                icon="clapper"
              />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium">{m.nombre}</span>
                <span class="block truncate text-xs text-muted">
                  {`{${m.clave}}`}{m.voz ? ` · voz ${m.voz}` : " · sin voz"}
                </span>
              </span>
              <IconButton
                name="trash"
                label={`Quitar a ${m.nombre} de la serie`}
                size={14}
                onclick={() => onquitarmiembro(m.slug, m.nombre)}
                class="hover:bg-danger-soft hover:text-danger"
              />
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-sm text-dim">
          Todavía no hay nadie fijo. Promueve a un personaje al reparto propio desde el paso de
          escenas de un vídeo y añádelo aquí: es lo que hace que no cambie de cara entre capítulos.
        </p>
      {/if}

      {#if disponibles.length}
        <div class="flex flex-wrap items-end gap-2">
          <div class="min-w-[220px] flex-1">
            <Field label="Añadir del reparto propio">
              <select class="control" bind:value={aFichar}>
                <option value="">Elige a alguien…</option>
                {#each disponibles as m (m.slug)}
                  <option value={m.slug}>{m.nombre} · {`{${m.clave}}`}</option>
                {/each}
              </select>
            </Field>
          </div>
          <Button
            size="sm"
            variant="secondary"
            disabled={!aFichar}
            onclick={() => {
              onanadirmiembro(aFichar);
              aFichar = "";
            }}
          >
            Añadir
          </Button>
        </div>
      {/if}
    </section>

    <!-- Nuevo episodio -->
    <section class="space-y-3 rounded-xl border border-accent/40 bg-accent-soft/40 p-4">
      <div>
        <h3 class="text-sm font-semibold">Episodio {siguiente}</h3>
        <p class="text-xs text-dim">
          {#if tramoSiguiente}
            Su tramo: {tramoSiguiente.pasa}
          {:else if s.tiene_hilo}
            El hilo no llega hasta aquí: este capítulo se escribiría sin tramo. Replanifica el
            hilo, o da la serie por acabada.
          {:else if ultimo?.resumen}
            Continúa el episodio {ultimo.episodio}: el guion sale con su canon como contexto.
          {:else if ultimo}
            El episodio {ultimo.episodio} no está cerrado todavía (no tiene canon), así que este no
            podrá continuarlo. Aprueba su guion o escríbele el resumen a mano.
          {:else}
            El primero planta la situación y deja algo abierto para el siguiente.
          {/if}
        </p>
      </div>
      <Field
        label="Apunte (opcional)"
        hint="Una línea de dirección: «Ana encuentra la llave». En blanco, lo propone el LLM desde donde quedó el anterior."
      >
        <input class="control" bind:value={apunte} placeholder="Qué pasa en este capítulo" />
      </Field>
      <div class="flex flex-wrap items-center gap-2">
        <Button disabled={busy} onclick={nuevo}>Nuevo episodio</Button>
        <Button variant="secondary" size="sm" disabled={busy} onclick={onideas}>
          Pedir ideas de episodio
        </Button>
      </div>
    </section>

    <!-- Episodios -->
    <section class="space-y-2">
      <h3 class="text-sm font-semibold">Episodios</h3>
      {#if s.episodios.length}
        <ul class="space-y-1">
          {#each s.episodios as e (e.proyecto_id)}
            <li>
              <button
                type="button"
                aria-label={`Abrir episodio ${e.episodio}: ${e.titulo}`}
                class="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-2"
                onclick={() => onabrirepisodio(e.proyecto_id)}
              >
                <span class="w-12 shrink-0 text-xs font-semibold tabular-nums text-accent">
                  EP {e.episodio}
                </span>
                <span class="min-w-0 flex-1 truncate text-sm">{e.titulo}</span>
                {#if e.ocupado}
                  <Chip tone="warn">en marcha</Chip>
                {/if}
                {#if e.desvio}
                  <Chip tone="warn">fuera de tramo</Chip>
                {/if}
                {#if e.continuidad_rota}
                  <Chip tone="warn">canon cambiado</Chip>
                {/if}
                {#if e.resumen}
                  <Chip tone="ok">cerrado</Chip>
                {/if}
                <Chip>{e.estado}</Chip>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-sm text-dim">Ningún episodio todavía.</p>
      {/if}
    </section>

    <div class="flex items-center gap-3 border-t border-line pt-4">
      <Button variant="danger" size="sm" disabled={busy} onclick={onborrarserie}>
        Disolver la serie
      </Button>
      <span class="text-xs text-muted">
        Los episodios no se borran: se quedan como vídeos sueltos, con su guion y su vídeo.
      </span>
    </div>
  </div>
</div>
