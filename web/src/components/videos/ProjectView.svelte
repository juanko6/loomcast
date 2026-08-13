<script lang="ts">
  import Stepper from "./Stepper.svelte";
  import StepGuion from "./steps/StepGuion.svelte";
  import StepVoz from "./steps/StepVoz.svelte";
  import StepMetadatos from "./steps/StepMetadatos.svelte";
  import StepEscenas from "./steps/StepEscenas.svelte";
  import StepVideo from "./steps/StepVideo.svelte";
  import Chip from "../primitives/Chip.svelte";
  import {
    ETAPA_VIDEO,
    type Paso,
    type ProyectoDetalle,
    type Voz,
    type Guion,
  } from "@/lib/proyectos";

  let {
    p,
    voces,
    bust = 0,
    acciones,
    onver,
  }: {
    p: ProyectoDetalle;
    voces: Voz[];
    bust?: number;
    // Todas las acciones del pipeline, inyectadas por el orquestador.
    acciones: Record<string, any>;
    onver: (html: string, pie: string) => void;
  } = $props();

  const busy = $derived(p.jobs_activos > 0);
  const etapa = $derived(p.job_activo ? ETAPA_VIDEO[p.job_activo] : null);

  // El paso activo lo elige el usuario; por defecto, el primero sin completar.
  let elegido = $state<string | null>(null);

  const pasos = $derived<Paso[]>([
    { id: "guion", label: "Guion", hecho: !!p.guion, bloqueado: false },
    { id: "voz", label: "Voz", hecho: p.voz_disponible, bloqueado: !p.guion },
    { id: "metadatos", label: "Metadatos", hecho: !!p.metadatos, bloqueado: !p.voz_disponible },
    {
      id: "escenas",
      label: "Escenas e imágenes",
      hecho: p.imagenes_completas,
      bloqueado: !p.subtitulos,
    },
    { id: "video", label: "Vídeo final", hecho: p.video_disponible, bloqueado: !p.imagenes_completas },
  ]);

  // Primer paso pendiente (o el último si está todo hecho).
  const sugerido = $derived(pasos.find((s) => !s.hecho && !s.bloqueado)?.id ?? "video");
  const activo = $derived(
    elegido && !pasos.find((s) => s.id === elegido)?.bloqueado ? elegido : sugerido,
  );
</script>

<div class="flex min-h-0 flex-1 flex-col">
  <!-- Cabecera del proyecto -->
  <header class="flex flex-wrap items-center gap-3 px-6 pt-5 pb-1">
    <h2 class="text-lg font-semibold tracking-tight text-balance">
      {p.idea?.titulo ?? p.slug}
    </h2>
    <Chip>{p.estado}</Chip>
    {#if etapa}
      <span class="flex items-center gap-2 text-sm text-dim">
        <span class="size-4 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        {etapa}
      </span>
    {/if}
  </header>

  <Stepper {pasos} {activo} onselect={(id) => (elegido = id)} />

  <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
    {#if activo === "guion"}
      <StepGuion {p} {busy} onsave={(g: Guion) => acciones.guardarGuion(g)} onregen={acciones.regenerarGuion} />
    {:else if activo === "voz"}
      <StepVoz
        {p}
        {voces}
        {busy}
        onselectvoz={acciones.seleccionarVoz}
        ongenerar={acciones.generarVoz}
        oncrearvoz={acciones.crearVoz}
        onclonarvoz={acciones.clonarVoz}
        onborrarvoz={acciones.borrarVoz}
      />
    {:else if activo === "metadatos"}
      <StepMetadatos {p} {busy} ongenerar={acciones.generarMetadatos} />
    {:else if activo === "escenas"}
      <StepEscenas
        {p}
        {busy}
        {bust}
        ongenerar={acciones.generarEscenas}
        onguardar={acciones.guardarEscenas}
        ongenerarcasting={acciones.generarCasting}
        onguardarcasting={acciones.guardarCasting}
        ongenerarretrato={acciones.generarRetrato}
        onanadirpersonaje={acciones.anadirPersonaje}
        onborrarpersonaje={acciones.borrarPersonaje}
        ongenerarimagenes={acciones.generarImagenes}
        onregenimagen={acciones.regenerarImagen}
        onregenclip={acciones.regenerarClip}
        onfijarmodos={acciones.fijarModos}
        {onver}
      />
    {:else}
      <StepVideo
        {p}
        {busy}
        {bust}
        ongenerar={acciones.generarVideo}
        onborrarvideo={acciones.borrarVideo}
        onborrarversion={acciones.borrarVersion}
        onborrarproyecto={acciones.borrarProyecto}
        {onver}
      />
    {/if}
  </div>
</div>
