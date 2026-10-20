<script lang="ts">
  // El autopiloto dentro de un proyecto: o lo que está haciendo, o el formulario
  // para lanzarlo.
  //
  // Vive arriba, encima del stepper, porque cuando una tirada está en marcha es
  // lo primero que hay que saber: en qué etapa va, si se ha parado a que
  // revises algo y por qué se detuvo si se detuvo. El stepper sigue estando y
  // sigue funcionando a mano: lo que se pulse adelanta en la cola a lo que esté
  // encolando el autopiloto.
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import AutopilotoForm from "./AutopilotoForm.svelte";
  import { ETAPA_VIDEO, type ProyectoDetalle, type Voz } from "@/lib/proyectos";
  import {
    estadoAutopiloto,
    viva,
    type OpcionesAutopiloto,
  } from "@/lib/autopiloto";

  let {
    p,
    voces = [],
    busy = false,
    onlanzar,
    oncontinuar,
    ondetener,
  }: {
    p: ProyectoDetalle;
    voces?: Voz[];
    busy?: boolean;
    onlanzar: (o: OpcionesAutopiloto) => void;
    oncontinuar: () => void;
    ondetener: () => void;
  } = $props();

  const a = $derived(p.autopiloto);
  const enMarcha = $derived(viva(a));
  const estado = $derived(a ? estadoAutopiloto(a.estado) : null);
  // La etapa en gerundio, la misma que enseña la cabecera del proyecto.
  const etapa = $derived(a?.etapa ? ETAPA_VIDEO[a.etapa] : null);
  let abierto = $state(false);
</script>

<section
  class="mx-6 mt-3 rounded-xl border border-line bg-surface-2 p-3"
  aria-label="Autopiloto"
>
  {#if enMarcha && a}
    <!-- Los botones a la derecha y el texto en su propia línea: el motivo es lo
         que hay que poder leer entero ("Esperando que revises el guion"), y
         compartiendo fila con dos botones se quedaba en tres letras. -->
    <div class="flex flex-wrap items-center gap-3">
      <Chip tone={a.estado === "esperando" ? "warn" : "accent"}>Autopiloto</Chip>
      <span class={`text-sm font-medium ${estado!.clase}`}>{estado!.texto}</span>
      <span class="ml-auto flex flex-wrap gap-2">
        {#if a.estado === "esperando"}
          <Button size="sm" onclick={oncontinuar}>Visto, continuar</Button>
        {/if}
        <Button size="sm" variant="danger" onclick={ondetener}>Detener autopiloto</Button>
      </span>
    </div>
    {#if a.motivo || etapa}
      <p class="mt-1.5 text-sm text-dim">{a.motivo || etapa}</p>
    {/if}
    {#if a.lote_id !== null}
      <p class="mt-1 text-xs text-muted">
        Este vídeo es parte de un lote; los demás siguen su turno aunque pares este.
      </p>
    {/if}
  {:else}
    <div class="flex flex-wrap items-center gap-3">
      <Chip>Autopiloto</Chip>
      <span class="min-w-0 flex-1 text-sm text-dim">
        {#if a}
          {estado!.texto}{a.motivo ? ` · ${a.motivo}` : ""}
        {:else}
          De donde esté el proyecto hasta el vídeo final, sin pulsar cada paso.
        {/if}
      </span>
      <Button size="sm" variant="secondary" onclick={() => (abierto = !abierto)}>
        {abierto ? "Cerrar" : a ? "Volver a lanzarlo" : "Lanzar…"}
      </Button>
    </div>
    {#if abierto}
      <div class="mt-3 border-t border-line pt-3">
        <AutopilotoForm
          {voces}
          vozActual={p.voz}
          {busy}
          onlanzar={(o) => {
            abierto = false;
            onlanzar(o);
          }}
        />
      </div>
    {/if}
  {/if}
</section>
