<script lang="ts">
  // El chip de la cola de la cabecera, y detrás de él el panel con lo que está
  // pasando: la etapa en curso, lo que espera, los botones de parada y los
  // últimos trabajos terminados.
  //
  // El historial es el único sitio donde se ve que un job acabó en error tras
  // varios intentos (la cola reintenta sola lo transitorio) y que otro se paró
  // a mano, que no es lo mismo que fallar.
  import BotonParar from "./BotonParar.svelte";
  import { jobs, jobsDrenados, historialJobs, lotes } from "@/lib/stores";
  import { nombreJob, resultadoJob } from "@/lib/jobs";
  import { ETAPA_VIDEO } from "@/lib/proyectos";
  import type { JobHistorial } from "@/lib/types";

  let abierto = $state(false);
  let historial = $state<JobHistorial[]>([]);

  // La cola procesa de uno en uno, así que el único job con progreso es el que
  // está corriendo ahora.
  let prog = $derived($jobs.find((j) => j.progreso)?.progreso ?? null);
  let enCurso = $derived($jobs.find((j) => j.estado === "corriendo") ?? null);
  let esperando = $derived($jobs.filter((j) => j.estado === "pendiente"));

  function reloj(s: number): string {
    if (s < 60) return `${s}s`;
    const m = Math.round(s / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  // Lo que se lee en el chip: la posición dentro del lote y lo que queda. Si la
  // etapa no va por lotes (voz, guion, armado) no hay nada que contar y se
  // enseña el tiempo que lleva, que al menos distingue "va lento" de "se colgó".
  // El lote que está produciendo ahora (solo hay uno: la línea es de uno).
  let lote = $derived($lotes.find((l) => l.actual) ?? $lotes[0] ?? null);

  let texto = $derived.by(() => {
    // Sin nada en la cola pero con un lote vivo, lo que hay que decir es que el
    // lote está esperando a una persona, no "0 en cola".
    if (!$jobs.length && lote) {
      return lote.esperando
        ? `lote: ${lote.esperando} esperando revisión`
        : `lote: ${lote.hechos} de ${lote.total}`;
    }
    const cola = `${$jobs.length} en cola`;
    const partes = [prog?.fase || cola];
    if (prog?.eta_s != null) partes.push(`~${reloj(prog.eta_s)}`);
    else if (prog) partes.push(reloj(prog.transcurrido_s));
    // El recuento solo se repite si la fase le quitó el sitio y además hay
    // más de un trabajo esperando.
    if (prog?.fase && $jobs.length > 1) partes.push(cola);
    // Con un lote en marcha, el número que de verdad importa es cuántos vídeos
    // quedan: la cola solo tiene la etapa de uno porque se producen de uno en
    // uno, así que "2 en cola" con ocho vídeos pendientes engañaría.
    if (lote?.actual) {
      partes.push(`vídeo ${lote.actual.posicion} de ${lote.total}`);
    }
    return partes.join(" · ");
  });

  async function cargarHistorial() {
    try {
      historial = await historialJobs();
    } catch {
      /* el historial es informativo: si falla, el panel sigue sirviendo para parar */
    }
  }

  function alternar() {
    abierto = !abierto;
    if (abierto) cargarHistorial();
  }

  // Cada vez que la cola se vacía un poco hay un trabajo nuevo que contar, y el
  // panel abierto se quedaría enseñando el historial de antes.
  let ultimoDrenaje = 0;
  $effect(() => {
    const n = $jobsDrenados;
    if (n !== ultimoDrenaje) {
      ultimoDrenaje = n;
      if (abierto) cargarHistorial();
    }
  });
</script>

<div class="relative shrink-0">
  <!-- El propio chip es la barra: se rellena por detrás del texto, así el
       avance y lo que se está haciendo ocupan un solo elemento. -->
  <button
    type="button"
    onclick={alternar}
    aria-expanded={abierto}
    title="Trabajos en cola (se procesan de uno en uno)"
    class="relative inline-flex cursor-pointer items-center gap-2 overflow-hidden rounded-full bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent"
  >
    {#if prog?.pct != null}
      <span
        class="absolute inset-y-0 left-0 bg-accent/30 transition-[width] duration-700 ease-out"
        style="width: {prog.pct}%"
        aria-hidden="true"
      ></span>
    {/if}
    <span class="relative size-1.5 animate-pulse rounded-full bg-accent"></span>
    <span
      class="relative"
      {...prog?.pct != null
        ? {
            role: "progressbar",
            "aria-valuenow": prog.pct,
            "aria-valuemin": 0,
            "aria-valuemax": 100,
          }
        : {}}
    >
      {texto}
    </span>
  </button>

  {#if abierto}
    <!-- Capa que cierra el panel al pulsar fuera, sin robar el foco. -->
    <button
      type="button"
      class="fixed inset-0 z-10 cursor-default"
      aria-label="Cerrar el panel de la cola"
      onclick={() => (abierto = false)}
    ></button>
    <section
      class="absolute right-0 top-full z-20 mt-2 w-[22rem] space-y-3 rounded-lg border border-line bg-surface p-4 shadow-xl"
      aria-label="Cola de trabajos"
    >
      <div class="space-y-1">
        <p class="text-xs font-medium tracking-wide text-muted">Ahora mismo</p>
        {#if enCurso}
          <p class="text-sm">
            {nombreJob(enCurso.tipo)}
            {#if prog?.fase}<span class="text-dim"> · {prog.fase}</span>{/if}
            {#if enCurso.intentos > 1}
              <span class="text-warn"> · intento {enCurso.intentos}</span>
            {/if}
          </p>
          {#if enCurso.sin_corte}
            <p class="text-xs text-warn">
              {enCurso.sin_corte} no se puede cortar a mitad: se para en cuanto termine.
            </p>
          {/if}
        {:else}
          <p class="text-sm text-dim">Nada en marcha.</p>
        {/if}
        <p class="text-xs text-muted">
          {esperando.length
            ? `${esperando.length} esperando: ${esperando.map((j) => nombreJob(j.tipo)).join(", ")}`
            : "Nada esperando."}
        </p>
      </div>

      {#if lote}
        <!-- El lote explica por qué la cola no se vacía, y es lo que se mira
             para decidir si vale la pena pararlo todo. -->
        <div class="space-y-1 border-t border-line pt-3">
          <p class="text-xs font-medium tracking-wide text-muted">Lote en marcha</p>
          <p class="text-sm">
            {lote.tema}
            <span class="text-dim">
              · {lote.hechos} de {lote.total} hechos
            </span>
          </p>
          {#if lote.actual}
            <p class="text-xs text-dim">
              Ahora: {lote.actual.titulo}
              {#if lote.actual.etapa}
                · {ETAPA_VIDEO[lote.actual.etapa] ?? nombreJob(lote.actual.etapa)}
              {/if}
            </p>
          {/if}
          <p class="text-xs text-muted">
            {lote.pendientes} por empezar{lote.esperando
              ? `, ${lote.esperando} esperando revisión`
              : ""}{lote.errores ? `, ${lote.errores} con fallo` : ""}.
          </p>
        </div>
      {/if}

      <div class="flex flex-wrap gap-2">
        <BotonParar soloCorriendo etiqueta="Detener lo actual" />
        <BotonParar etiqueta="Parar todo y vaciar la cola" />
      </div>

      <div class="space-y-1">
        <p class="text-xs font-medium tracking-wide text-muted">Últimos trabajos</p>
        {#each historial as j (j.id)}
          <div class="flex items-baseline gap-2 text-xs" title={j.log}>
            <span class="min-w-0 flex-1 truncate text-dim">{nombreJob(j.tipo)}</span>
            {#if j.intentos > 1}
              <span class="text-muted">{j.intentos} intentos</span>
            {/if}
            <span class={resultadoJob(j.estado).clase}>{resultadoJob(j.estado).texto}</span>
          </div>
        {:else}
          <p class="text-xs text-muted">Todavía no ha terminado nada.</p>
        {/each}
      </div>
    </section>
  {/if}
</div>
