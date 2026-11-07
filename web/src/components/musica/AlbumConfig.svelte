<script lang="ts">
  import Field from "../primitives/Field.svelte";
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import { mmss, type AlbumDetalle } from "@/lib/albumes";

  // Panel izquierdo del modo álbum: crear uno nuevo desde una idea, o el ADN
  // del álbum abierto (lo que no cambia entre pistas) y sus acciones.
  let {
    album = null,
    oncreate,
    onsave,
    onproduce,
    onreplan,
    ondelete,
  }: {
    album?: AlbumDetalle | null;
    oncreate: (p: { idea: string; num_pistas: number }) => void;
    onsave: (p: { titulo: string; firma: string }) => void;
    onproduce: () => void;
    onreplan: () => void;
    ondelete: () => void;
  } = $props();

  let idea = $state("");
  let num = $state(12);
  let titulo = $state("");
  let firma = $state("");

  $effect(() => {
    titulo = album?.titulo ?? "";
    firma = album?.firma ?? "";
  });

  const pendientes = $derived(album ? album.pistas.filter((p) => p.estado !== "generada").length : 0);
  const sinEscribir = $derived(album ? album.pistas.filter((p) => !p.escrita).length : 0);
  const cambiado = $derived(!!album && (titulo !== album.titulo || firma !== album.firma));
</script>

<div class="flex h-full flex-col">
  <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
    {#if !album}
      <h2 class="text-sm font-semibold text-text">Nuevo álbum</h2>
      <p class="text-xs leading-relaxed text-muted">
        El LLM fija el sonido del disco (género, banda y producción) y escribe una intención
        distinta para cada pista. Todas usan la misma semilla: lo que cambia es lo que cuentan.
        También puedes crearlo desde una pista que te guste, en su panel de resultado.
      </p>
      <Field label="¿Cómo es el álbum?">
        <textarea
          class="control"
          rows="4"
          bind:value={idea}
          placeholder="Ej: jazz noir de madrugada con saxo tenor y piano, ciudad mojada, detectives cansados"
        ></textarea>
      </Field>
      <Field label="Pistas" hint="La duración de cada una la decide su intención.">
        <input class="control" type="number" min="2" max="20" bind:value={num} />
      </Field>
    {:else}
      <div class="space-y-1">
        <p class="text-xs font-medium tracking-wide text-muted">Álbum</p>
        <input class="control text-sm font-semibold" bind:value={titulo} />
      </div>
      <div class="flex flex-wrap gap-1.5">
        <Chip tone="accent">{album.estado}</Chip>
        <Chip>{album.pistas.length} pistas</Chip>
        {#if album.duracion_total_s}<Chip>{mmss(album.duracion_total_s)}</Chip>{/if}
        <Chip>seed {album.seed}</Chip>
      </div>
      {#if album.genero}
        <div class="space-y-1.5">
          <p class="text-xs font-medium tracking-wide text-muted">Género</p>
          <p class="text-sm text-dim">{album.genero}</p>
        </div>
        <div class="space-y-1.5">
          <p class="text-xs font-medium tracking-wide text-muted">La banda</p>
          <div class="flex flex-wrap gap-1.5">
            {#each album.banda as b}<Chip>{b}</Chip>{/each}
          </div>
        </div>
        {#if album.arco}
          <div class="space-y-1.5">
            <p class="text-xs font-medium tracking-wide text-muted">Arco</p>
            <p class="text-sm leading-relaxed text-dim">{album.arco}</p>
          </div>
        {/if}
        <Field
          label="Firma de producción (inglés)"
          hint="Se pega igual al final del estilo de cada pista: es lo que hace que suenen al mismo disco."
        >
          <textarea class="control" rows="6" bind:value={firma}></textarea>
        </Field>
      {:else}
        <p class="text-sm text-dim">El LLM está planificando el álbum…</p>
      {/if}
    {/if}
  </div>

  <div class="border-t border-line bg-surface p-4">
    {#if !album}
      <Button
        class="w-full"
        disabled={!idea.trim()}
        onclick={() => oncreate({ idea: idea.trim(), num_pistas: num })}
      >
        Planificar álbum
      </Button>
    {:else}
      <div class="flex flex-col gap-2">
        {#if cambiado}
          <Button variant="secondary" onclick={() => onsave({ titulo, firma })}>Guardar cambios</Button>
        {/if}
        <Button
          class="w-full"
          disabled={album.ocupado || sinEscribir > 0 || pendientes === 0}
          onclick={onproduce}
          title={sinEscribir > 0 ? "Aún faltan pistas por escribir" : ""}
        >
          {pendientes === 0 && album.pistas.length
            ? "Álbum producido"
            : `Producir ${pendientes} ${pendientes === 1 ? "pista" : "pistas"}`}
        </Button>
        <div class="flex gap-2">
          <Button variant="ghost" size="sm" class="flex-1" disabled={album.ocupado} onclick={onreplan}>
            Replanificar
          </Button>
          <Button variant="danger" size="sm" class="flex-1" onclick={ondelete}>Borrar álbum</Button>
        </div>
      </div>
    {/if}
  </div>
</div>
