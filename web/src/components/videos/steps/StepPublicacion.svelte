<script lang="ts">
  import Button from "../../primitives/Button.svelte";
  import Field from "../../primitives/Field.svelte";
  import Icon from "../../primitives/Icon.svelte";
  import MetadatosRedes from "../MetadatosRedes.svelte";
  import { enlaceYoutube, fechaEnEspanol, type ProyectoDetalle } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    onmarcar,
    onquitar,
    onliberar,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    onmarcar: (fecha: string, url: string, nota: string) => void;
    onquitar: () => void;
    onliberar: () => void;
  } = $props();

  const pub = $derived(p.publicacion);
  const enlace = $derived(enlaceYoutube(pub?.url ?? ""));

  let fecha = $state("");
  let url = $state("");
  let nota = $state("");
  let editando = $state(false);

  const hoy = new Date().toISOString().slice(0, 10);

  // El formulario arranca con lo que ya hay apuntado (o con hoy, si es la
  // primera vez). Se rehace cada vez que cambia la publicación del proyecto:
  // marcarla recarga la ficha, y el formulario no puede quedarse con lo de
  // antes.
  $effect(() => {
    const actual = p.publicacion;
    fecha = actual?.fecha || hoy;
    url = actual?.url ?? "";
    nota = actual?.nota ?? "";
    editando = false;
  });

  // Lo que se puede tirar sin perder el vídeo. Por debajo de 1 MB no hay nada
  // que liberar (o ya se liberó).
  const liberable = $derived(p.disco.liberable_mb >= 1);
</script>

<div class="max-w-3xl space-y-5">
  {#if !p.video_disponible}
    <p class="rounded-xl border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
      Este proyecto no tiene vídeo montado ahora mismo. Puedes marcarlo igual si ya lo subiste y
      después liberaste el material.
    </p>
  {/if}

  <!-- Estado de la publicación -->
  {#if pub && !editando}
    <section class="space-y-3 rounded-xl border border-ok/30 bg-ok-soft p-4">
      <div class="flex flex-wrap items-center gap-2">
        <Icon name="check" size={16} class="text-ok" />
        <h3 class="text-sm font-semibold text-ok">
          Publicado el {fechaEnEspanol(pub.fecha)}
        </h3>
      </div>
      {#if enlace}
        <a
          href={enlace}
          target="_blank"
          rel="noreferrer"
          class="inline-flex items-center gap-2 text-sm text-accent underline-offset-2 hover:underline"
        >
          <Icon name="link" size={14} />
          {pub.url}
        </a>
      {:else}
        <p class="text-xs text-muted">Sin enlace apuntado.</p>
      {/if}
      {#if pub.nota}
        <p class="whitespace-pre-wrap text-sm text-dim">{pub.nota}</p>
      {/if}
      <div class="flex flex-wrap gap-2 pt-1">
        <Button size="sm" variant="secondary" onclick={() => (editando = true)}>
          Editar los datos
        </Button>
        <Button size="sm" variant="ghost" onclick={onquitar}>Quitar la marca</Button>
      </div>
    </section>
  {:else}
    <section class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
      <h3 class="text-sm font-semibold">
        {pub ? "Editar la publicación" : "Marcar como publicado"}
      </h3>
      <p class="text-xs text-dim">
        Lo que hay en YouTube no se ve desde aquí: esto es lo único que distingue un vídeo ya
        subido de uno que sigue esperando.
      </p>
      <div class="flex flex-wrap gap-3">
        <div class="w-40">
          <Field label="Fecha de subida">
            <input class="control" type="date" bind:value={fecha} aria-label="Fecha de subida" />
          </Field>
        </div>
        <div class="min-w-56 flex-1">
          <Field label="Enlace o id del vídeo" hint="Vale la URL entera o solo el id.">
            <input
              class="control"
              bind:value={url}
              placeholder="https://youtu.be/…"
              aria-label="Enlace o id del vídeo"
            />
          </Field>
        </div>
      </div>
      <Field label="Nota (opcional)" hint="Para ti: en qué canal, con qué título, qué cambiaste.">
        <textarea class="control" rows="2" bind:value={nota} aria-label="Nota"></textarea>
      </Field>
      <div class="flex flex-wrap gap-2">
        <Button disabled={busy} onclick={() => onmarcar(fecha, url, nota)}>
          {pub ? "Guardar" : "Marcar como publicado"}
        </Button>
        {#if pub}
          <Button variant="ghost" onclick={() => (editando = false)}>Cancelar</Button>
        {/if}
      </div>
    </section>
  {/if}

  <!-- Los textos, aquí mismo: este es el paso en el que se suben -->
  {#if p.metadatos}
    <details class="rounded-xl border border-line bg-surface p-3" open={!pub}>
      <summary class="cursor-pointer text-sm font-medium">Textos para subirlo</summary>
      <div class="mt-3 space-y-4">
        <MetadatosRedes m={p.metadatos} />
      </div>
    </details>
  {:else}
    <p class="text-sm text-dim">
      Este vídeo no tiene metadatos todavía: el título, la descripción y las etiquetas se generan
      en el paso de Metadatos.
    </p>
  {/if}

  <!-- Espacio en disco -->
  <section class="space-y-2 rounded-xl border border-line bg-surface-2 p-4">
    <h3 class="text-sm font-semibold">Espacio en disco</h3>
    {#if p.liberado}
      <p class="text-sm text-dim">
        De este proyecto ya solo queda el vídeo final
        (<span class="tabular-nums text-text">{p.disco.total_mb} MB</span>). El guion, los
        metadatos, el reparto y este enlace siguen guardados.
      </p>
    {:else}
      <p class="text-sm text-dim">
        Este proyecto ocupa <span class="tabular-nums text-text">{p.disco.total_mb} MB</span>, de
        los que <span class="tabular-nums text-text">{p.disco.liberable_mb} MB</span> es todo lo
        que no es el vídeo final: la narración, las imágenes, los clips, los reescalados y los
        montajes anteriores.
      </p>
      <p class="text-xs text-muted">
        Liberarlo deja solo el montaje. El guion, los metadatos, el reparto y el enlace no están en
        disco sino guardados, así que se quedan; lo que se pierde es lo que habría que volver a
        generar para rehacer el vídeo.
      </p>
    {/if}
    <div class="flex flex-wrap items-center gap-3 pt-1">
      <Button
        variant="secondary"
        size="sm"
        disabled={busy || !pub || !liberable}
        onclick={onliberar}
      >
        Liberar {p.disco.liberable_mb} MB
      </Button>
      {#if !pub}
        <span class="text-xs text-muted">
          Solo de vídeos ya publicados: hasta entonces este material es el que rehace el montaje.
        </span>
      {:else if !liberable}
        <span class="text-xs text-muted">No queda material intermedio que tirar.</span>
      {/if}
    </div>
  </section>
</div>
