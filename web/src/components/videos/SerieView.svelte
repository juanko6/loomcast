<script lang="ts">
  // Vista de una serie: su reparto fijo, sus episodios y el botón que de verdad
  // se usa a diario, "Nuevo episodio".
  //
  // El orden de la pantalla es el orden en que se produce una serie: primero se
  // fija quién sale siempre (una vez), y a partir de ahí todo es sacar
  // capítulos. El apunte es opcional porque en una serie que va sola lo normal
  // es dejar que el episodio salga de donde quedó el anterior.
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import Field from "../primitives/Field.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import { media } from "@/lib/api";
  import type { MiembroReparto } from "@/lib/proyectos";
  import type { SerieDetalle } from "@/lib/series";

  let {
    s,
    reparto = [],
    busy = false,
    onnuevoepisodio,
    onabrirepisodio,
    onanadirmiembro,
    onquitarmiembro,
    onideas,
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
    onborrarserie: () => void;
  } = $props();

  let apunte = $state("");
  let aFichar = $state("");

  // Los del reparto propio que todavía no salen en la serie: lo que queda por
  // elegir en el selector.
  const disponibles = $derived(
    reparto.filter((m) => !s.miembros.some((x) => x.slug === m.slug)),
  );
  const ultimo = $derived(s.episodios[s.episodios.length - 1] ?? null);
  const siguiente = $derived((ultimo?.episodio ?? 0) + 1);

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
      <Chip>{s.n_episodios} {s.n_episodios === 1 ? "episodio" : "episodios"}</Chip>
    </header>

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
          {#if ultimo?.resumen}
            Continúa el episodio {ultimo.episodio}: el guion sale con su resumen como contexto.
          {:else if ultimo}
            El episodio {ultimo.episodio} no está cerrado todavía (no tiene resumen), así que este
            no podrá continuarlo. Arma su vídeo o escríbele el resumen a mano.
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
