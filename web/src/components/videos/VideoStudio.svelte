<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../primitives/Button.svelte";
  import Field from "../primitives/Field.svelte";
  import Chip from "../primitives/Chip.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Viewer from "../primitives/Viewer.svelte";
  import IdeasView from "./IdeasView.svelte";
  import ProjectView from "./ProjectView.svelte";
  import { jobsDrenados, refrescarJobs, seleccionPendiente } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import * as API from "@/lib/proyectos";
  import type { Idea, ProyectoDetalle, Voz } from "@/lib/proyectos";
  import type { ProyectoResumen, TemaResumen } from "@/lib/types";

  // --- estado ---
  let temas = $state<TemaResumen[]>([]);
  let proyectos = $state<ProyectoResumen[]>([]);
  let voces = $state<Voz[]>([]);
  let plantillas = $state<string[]>([]);

  // Vista actual: un tema (sus ideas) o un proyecto (el pipeline).
  let vista = $state<{ tipo: "tema" | "proyecto"; id: number } | null>(null);
  let ideas = $state<Idea[]>([]);
  let proyecto = $state<ProyectoDetalle | null>(null);
  let bust = $state(0);
  let error = $state("");

  // Formulario de tema nuevo
  let temaTexto = $state("");
  let temaPlantilla = $state("");

  // Visor a pantalla completa
  let visorHtml = $state<string | null>(null);
  let visorPie = $state("");

  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");
  const ocupado = $derived((proyecto?.jobs_activos ?? 0) > 0);

  function fallo(e: unknown) {
    error = (e as Error).message;
  }

  async function refrescarListas() {
    try {
      [temas, proyectos] = await Promise.all([API.listarTemas(), API.listarProyectos()]);
    } catch (e) {
      fallo(e);
    }
  }

  async function cargarVista() {
    if (!vista) return;
    try {
      if (vista.tipo === "tema") ideas = await API.ideasDeTema(vista.id);
      else proyecto = await API.detalleProyecto(vista.id);
    } catch (e) {
      fallo(e);
    }
  }

  function irA(tipo: "tema" | "proyecto", id: number) {
    error = "";
    vista = { tipo, id };
    ideas = [];
    proyecto = null;
    cargarVista();
  }

  // --- tema e ideas ---
  async function crearTema(ev: Event) {
    ev.preventDefault();
    if (!temaTexto.trim()) return;
    try {
      const { tema_id } = await API.crearTema(temaTexto.trim(), temaPlantilla);
      temaTexto = "";
      await refrescarListas();
      irA("tema", tema_id);
      refrescarJobs();
    } catch (e) {
      fallo(e);
    }
  }

  async function borrarTema(id: number, texto: string) {
    if (!confirm(`¿Borrar el tema «${texto.slice(0, 40)}» y todas sus ideas?\n\nNo se puede deshacer.`))
      return;
    try {
      await API.borrarTema(id);
      if (vista?.tipo === "tema" && vista.id === id) vista = null;
      refrescarListas();
    } catch (e) {
      fallo(e);
    }
  }

  const accIdeas = {
    aprobar: async (id: number) => {
      try {
        const { proyecto_id } = await API.proyectoDesdeIdea(id);
        await refrescarListas();
        irA("proyecto", proyecto_id);
        refrescarJobs();
      } catch (e) {
        fallo(e);
      }
    },
    estado: async (id: number, estado: string) => {
      try {
        await API.cambiarEstadoIdea(id, estado);
        cargarVista();
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
    mas: async () => {
      if (vista?.tipo !== "tema") return;
      try {
        await API.masIdeas(vista.id);
        refrescarJobs();
      } catch (e) {
        fallo(e);
      }
    },
  };

  // --- acciones del pipeline (se inyectan en ProjectView) ---
  const pid = () => proyecto!.id;
  async function tras(promesa: Promise<unknown>) {
    try {
      await promesa;
      refrescarJobs();
      await cargarVista();
      refrescarListas();
    } catch (e) {
      fallo(e);
    }
  }

  const acciones = {
    guardarGuion: (g: API.Guion) => tras(API.guardarGuion(pid(), g)),
    regenerarGuion: () => tras(API.regenerarGuion(pid())),
    seleccionarVoz: (slug: string) => slug && tras(API.seleccionarVoz(pid(), slug)),
    generarVoz: (modo: "clon" | "design", instruct: string) =>
      tras(API.generarVoz(pid(), modo, instruct)),
    crearVoz: async (nombre: string, instruct: string) => {
      await tras(API.crearVoz(nombre, instruct));
      voces = await API.listarVoces();
    },
    clonarVoz: async (nombre: string, audio: File, inicio: number, fin: number) => {
      await tras(API.clonarVoz(nombre, audio, "", inicio, fin));
      voces = await API.listarVoces();
    },
    borrarVoz: async (slug: string, nombre: string) => {
      if (!confirm(`¿Borrar la voz «${nombre}»?\n\nLos proyectos que la usaban quedarán sin voz.`))
        return;
      await tras(API.borrarVoz(slug));
      voces = await API.listarVoces();
    },
    generarMetadatos: () => tras(API.generarMetadatos(pid())),
    generarEscenas: () => tras(API.generarEscenas(pid())),
    guardarEscenas: (e: Parameters<typeof API.guardarEscenas>[1]) =>
      tras(API.guardarEscenas(pid(), e)),
    generarImagenes: async (e: Parameters<typeof API.guardarEscenas>[1]) => {
      try {
        await API.guardarEscenas(pid(), e);
        await API.generarImagenes(pid());
        refrescarJobs();
        cargarVista();
      } catch (err) {
        fallo(err);
      }
    },
    regenerarImagen: (orden: number, nuevoSeed: boolean) =>
      tras(API.regenerarImagen(pid(), orden, nuevoSeed)),
    regenerarClip: (orden: number, modo: string) => tras(API.regenerarClip(pid(), orden, modo)),
    fijarModos: (e: { orden: number; modo: string }[]) => tras(API.fijarModos(pid(), e)),
    generarVideo: (modo: string) => tras(API.generarVideo(pid(), modo)),
    borrarVideo: async () => {
      const conVersiones = confirm(
        "¿Borrar el vídeo final?\n\nAceptar: borra también los montajes anteriores.\n" +
          "Cancelar: te pregunto solo por el vídeo final.",
      );
      if (!conVersiones && !confirm("¿Borrar solo el vídeo final?")) return;
      await tras(API.borrarVideo(pid(), conVersiones));
    },
    borrarVersion: async (nombre: string) => {
      if (!confirm(`¿Borrar la versión ${nombre}?\n\nNo se puede deshacer.`)) return;
      await tras(API.borrarVersion(pid(), nombre));
    },
    borrarProyecto: async () => {
      const t = proyecto?.idea?.titulo ?? proyecto?.slug ?? "";
      if (!confirm(`¿Borrar el proyecto «${t}» POR COMPLETO?\n\nSe pierden guion, voz, subtítulos, imágenes, clips y vídeos.\nNo se puede deshacer.`))
        return;
      if (!confirm("Confirma otra vez: se borra la carpeta entera del proyecto.")) return;
      try {
        await API.borrarProyecto(pid());
        vista = null;
        proyecto = null;
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
  };

  function abrirVisor(html: string, pie: string) {
    visorHtml = html;
    visorPie = pie;
  }

  // Al terminar un job: refrescar listas, la vista y romper caché de medios.
  let ultimoDrenaje = 0;
  $effect(() => {
    const n = $jobsDrenados;
    if (n !== ultimoDrenaje) {
      ultimoDrenaje = n;
      bust = n;
      refrescarListas();
      cargarVista();
      API.listarVoces().then((v) => (voces = v)).catch(() => {});
    }
  });

  // Salto desde la Biblioteca: abre el proyecto pedido y consume la señal.
  $effect(() => {
    const sel = $seleccionPendiente;
    if (sel?.modo === "videos") {
      seleccionPendiente.set(null);
      irA("proyecto", sel.id);
    }
  });

  onMount(async () => {
    try {
      [plantillas, voces] = await Promise.all([API.listarPlantillas(), API.listarVoces()]);
      temaPlantilla = plantillas[0] ?? "";
    } catch (e) {
      fallo(e);
    }
    refrescarListas();
  });
</script>

<div class="flex min-h-0 flex-1">
  <!-- Columna izquierda: crear tema + listas -->
  <div
    class="flex w-[320px] min-w-0 shrink-0 flex-col overflow-y-auto border-r border-line bg-surface"
    style={reservaPlayer}
  >
    <form class="space-y-3 border-b border-line p-4" onsubmit={crearTema}>
      <h2 class="text-sm font-semibold">Nuevo tema</h2>
      <textarea
        class="control"
        rows="2"
        bind:value={temaTexto}
        placeholder="¿De qué va el vídeo? Ej: misterios del océano"
      ></textarea>
      <Field label="Plantilla">
        <select class="control" bind:value={temaPlantilla}>
          {#each plantillas as pl (pl)}
            <option value={pl}>{pl}</option>
          {/each}
        </select>
      </Field>
      <Button type="submit" class="w-full" disabled={!temaTexto.trim()}>Generar ideas</Button>
    </form>

    <div class="space-y-1 p-4">
      <p class="mb-2 text-xs font-medium tracking-wide text-muted">Temas</p>
      {#each temas as t (t.id)}
        <div
          class={`group flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors
            ${vista?.tipo === "tema" && vista.id === t.id ? "bg-accent-soft" : "hover:bg-surface-2"}`}
        >
          <button type="button" class="min-w-0 flex-1 text-left" onclick={() => irA("tema", t.id)}>
            <span class="block truncate text-sm">{t.texto}</span>
            <span class="text-xs text-muted">{t.n_aprobadas}/{t.n_ideas} aprobadas</span>
          </button>
          <span class="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <IconButton
              name="x"
              label="Borrar tema"
              size={14}
              onclick={() => borrarTema(t.id, t.texto)}
              class="hover:bg-danger-soft hover:text-danger"
            />
          </span>
        </div>
      {:else}
        <p class="text-xs text-muted">Sin temas aún.</p>
      {/each}
    </div>

    <div class="space-y-1 border-t border-line p-4">
      <p class="mb-2 text-xs font-medium tracking-wide text-muted">Proyectos</p>
      {#each proyectos as pr (pr.id)}
        <button
          type="button"
          onclick={() => irA("proyecto", pr.id)}
          class={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors
            ${vista?.tipo === "proyecto" && vista.id === pr.id ? "bg-accent-soft" : "hover:bg-surface-2"}`}
        >
          <span class="min-w-0 flex-1 truncate text-sm">{pr.titulo}</span>
          <Chip>{pr.estado}</Chip>
        </button>
      {:else}
        <p class="text-xs text-muted">Sin proyectos aún.</p>
      {/each}
    </div>
  </div>

  <!-- Área de trabajo -->
  <div class="flex min-w-0 flex-1 flex-col" style={reservaPlayer}>
    {#if error}
      <div class="m-4 rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
        {error}
      </div>
    {/if}

    {#if !vista}
      <div class="grid flex-1 place-items-center p-6 text-center">
        <p class="max-w-sm text-sm text-dim">
          Crea un tema para empezar, o elige uno de la lista. De cada tema salen ideas, y de cada
          idea aprobada, un proyecto de vídeo.
        </p>
      </div>
    {:else if vista.tipo === "tema"}
      <div class="min-h-0 flex-1 overflow-y-auto p-6">
        <IdeasView
          {ideas}
          busy={false}
          onaprobar={accIdeas.aprobar}
          ondescartar={(id) => accIdeas.estado(id, "descartada")}
          onrestaurar={(id) => accIdeas.estado(id, "propuesta")}
          onabrirproyecto={(id) => irA("proyecto", id)}
          onmas={accIdeas.mas}
        />
      </div>
    {:else if proyecto}
      <ProjectView p={proyecto} {voces} {bust} {acciones} onver={abrirVisor} />
    {:else}
      <div class="grid flex-1 place-items-center">
        <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
      </div>
    {/if}
  </div>
</div>

<Viewer html={visorHtml} pie={visorPie} onclose={() => (visorHtml = null)} />
