<script lang="ts">
  import Stepper from "./Stepper.svelte";
  import StepGuion from "./steps/StepGuion.svelte";
  import StepVoz from "./steps/StepVoz.svelte";
  import StepMetadatos from "./steps/StepMetadatos.svelte";
  import StepEscenas from "./steps/StepEscenas.svelte";
  import StepMusica from "./steps/StepMusica.svelte";
  import StepVideo from "./steps/StepVideo.svelte";
  import Chip from "../primitives/Chip.svelte";
  import BotonParar from "../shell/BotonParar.svelte";
  import {
    ETAPA_VIDEO,
    type MiembroReparto,
    type Paso,
    type ProyectoDetalle,
    type Voz,
    type Guion,
  } from "@/lib/proyectos";

  let {
    p,
    voces,
    reparto = [],
    bust = 0,
    acciones,
    onver,
  }: {
    p: ProyectoDetalle;
    voces: Voz[];
    reparto?: MiembroReparto[];
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
    {
      id: "musica",
      label: "Música",
      hecho: !!p.musica?.tiene_audio,
      // La música se escribe desde la historia, así que basta con tener guion;
      // la duración sale de la narración si ya está hecha.
      bloqueado: !p.guion,
    },
    { id: "video", label: "Vídeo final", hecho: p.video_disponible, bloqueado: !p.imagenes_completas },
  ]);

  // Primer paso pendiente (o el último si está todo hecho).
  // La música es opcional: no se sugiere sola, se entra a mano. Si no, un
  // proyecto con todo hecho menos la música abriría siempre ahí.
  const sugerido = $derived(
    pasos.find((s) => s.id !== "musica" && !s.hecho && !s.bloqueado)?.id ?? "video",
  );
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
    <!-- Un episodio se reconoce antes que nada por de qué serie es. -->
    {#if p.serie}
      <Chip tone="accent">{p.serie.nombre} · EP {p.serie.episodio}</Chip>
    {/if}
    <Chip>{p.estado}</Chip>
    {#if etapa}
      <span class="flex items-center gap-2 text-sm text-dim">
        <span class="size-4 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        {etapa}
      </span>
      <!-- Junto a la etapa en curso: es lo que se está mirando cuando un lote
           de doce escenas lleva veinte minutos y uno decide que ya no. -->
      <BotonParar />
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
        onvozpersonaje={acciones.vozPersonaje}
        oncrearvozpersonaje={acciones.crearVozPersonaje}
      />
    {:else if activo === "metadatos"}
      <StepMetadatos {p} {busy} ongenerar={acciones.generarMetadatos} />
    {:else if activo === "escenas"}
      <StepEscenas
        {p}
        {reparto}
        {busy}
        {bust}
        ongenerar={acciones.generarEscenas}
        onguardar={acciones.guardarEscenas}
        ongenerarcasting={acciones.generarCasting}
        onguardarcasting={acciones.guardarCasting}
        ongenerarretrato={acciones.generarRetrato}
        onanadirpersonaje={acciones.anadirPersonaje}
        onborrarpersonaje={acciones.borrarPersonaje}
        ontraerdelreparto={acciones.traerDelReparto}
        onpromoveralreparto={acciones.promoverAlReparto}
        onactualizarenreparto={acciones.actualizarEnReparto}
        onborrardelreparto={acciones.borrarDelReparto}
        ongenerarimagenes={acciones.generarImagenes}
        onregenimagen={acciones.regenerarImagen}
        onregenclip={acciones.regenerarClip}
        onfijarmodos={acciones.fijarModos}
        {onver}
      />
    {:else if activo === "musica"}
      <StepMusica
        {p}
        {busy}
        {bust}
        ongenerar={acciones.generarMusica}
        onfijar={acciones.fijarMusica}
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
        onguardarresumen={acciones.guardarResumen}
        ongenerarresumen={acciones.generarResumen}
        {onver}
      />
    {/if}
  </div>
</div>
