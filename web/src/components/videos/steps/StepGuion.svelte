<script lang="ts">
  import Field from "../../primitives/Field.svelte";
  import Button from "../../primitives/Button.svelte";
  import type { ProyectoDetalle, Guion, LineaGuion } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    onsave,
    onregen,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    onsave: (g: Guion) => void;
    onregen: () => void;
  } = $props();

  // Borrador local del guion, re-sincronizado cuando cambia el proyecto o el
  // LLM lo reescribe.
  let gancho = $state("");
  let narracion = $state("");
  let cta = $state("");
  let frases = $state<string[]>([]);
  let lineas = $state<LineaGuion[]>([]);

  // Tres formatos de guion según la plantilla: líneas atribuidas a un personaje
  // (las dice con su voz), narración continua (drama, historia) o lista de
  // frases (curiosidades).
  const esLineas = $derived(p.guion?.lineas != null);
  const esNarracion = $derived(!esLineas && p.guion?.narracion != null);

  // Las claves del reparto, para no tener que recordarlas al atribuir una
  // línea. El reparto se fija en el paso 4, así que aquí puede estar vacío: por
  // eso la clave se escribe a mano y esto solo es la ayuda.
  const claves = $derived(p.personajes.map((c) => c.clave));

  $effect(() => {
    const g = p.guion;
    gancho = g?.gancho ?? "";
    narracion = g?.narracion ?? "";
    cta = g?.cta ?? "";
    frases = [...(g?.frases ?? [])];
    lineas = (g?.lineas ?? []).map((l) => ({ ...l }));
  });

  function guardar() {
    if (esLineas) {
      onsave({
        gancho,
        cta,
        lineas: lineas
          .map((l) => ({ personaje: l.personaje.trim(), texto: l.texto.trim() }))
          .filter((l) => l.texto),
      });
      return;
    }
    onsave(
      esNarracion
        ? { gancho, narracion, cta }
        : { gancho, frases: frases.map((f) => f.trim()).filter(Boolean), cta },
    );
  }
</script>

{#if !p.guion}
  <p class="text-sm text-dim">Escribiendo el guion con el LLM…</p>
{:else}
  <div class="max-w-3xl space-y-4">
    <Field label="Gancho">
      <input class="control" bind:value={gancho} />
    </Field>

    {#if esLineas}
      <Field
        label="Narración y líneas"
        hint="Deja el personaje en blanco para el narrador. Si lleva clave del reparto ({'{ANA}'}), esa línea la dice su voz."
      >
        <div class="space-y-2">
          {#each lineas as _, i (i)}
            <div class="flex gap-2">
              <input
                class="control w-32 shrink-0 font-mono text-xs uppercase"
                list="claves-reparto"
                placeholder="narrador"
                aria-label={`Personaje de la línea ${i + 1}`}
                bind:value={lineas[i].personaje}
              />
              <textarea
                class="control min-w-0 flex-1"
                rows="2"
                aria-label={`Texto de la línea ${i + 1}`}
                bind:value={lineas[i].texto}
              ></textarea>
              <Button
                variant="ghost"
                size="sm"
                title="Quitar línea"
                onclick={() => (lineas = lineas.filter((_, j) => j !== i))}
              >
                ✕
              </Button>
            </div>
          {/each}
        </div>
      </Field>
      <datalist id="claves-reparto">
        {#each claves as clave (clave)}
          <option value={clave}></option>
        {/each}
      </datalist>
      <div class="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          onclick={() => (lineas = [...lineas, { personaje: "", texto: "" }])}
        >
          + Añadir narración
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onclick={() => (lineas = [...lineas, { personaje: claves[0] ?? "", texto: "" }])}
        >
          + Añadir línea de personaje
        </Button>
      </div>
    {:else if esNarracion}
      <Field label="Narración">
        <textarea class="control" rows="12" bind:value={narracion}></textarea>
      </Field>
    {:else}
      <Field label="Frases">
        <div class="space-y-2">
          {#each frases as _, i (i)}
            <div class="flex gap-2">
              <input class="control" bind:value={frases[i]} />
              <Button
                variant="ghost"
                size="sm"
                title="Quitar frase"
                onclick={() => (frases = frases.filter((_, j) => j !== i))}
              >
                ✕
              </Button>
            </div>
          {/each}
        </div>
      </Field>
      <Button variant="secondary" size="sm" onclick={() => (frases = [...frases, ""])}>
        + Añadir frase
      </Button>
    {/if}

    <Field label="CTA (cierre)">
      <input class="control" bind:value={cta} />
    </Field>

    <div class="flex flex-wrap gap-2 pt-1">
      <Button onclick={guardar}>Guardar guion</Button>
      <Button variant="secondary" disabled={busy} onclick={onregen}>
        Regenerar con el LLM
      </Button>
      <span class="self-center text-xs text-muted">Versión {p.guion_version}</span>
    </div>
  </div>
{/if}
