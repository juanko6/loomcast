<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../primitives/Button.svelte";
  import Field from "../primitives/Field.svelte";
  import Chip from "../primitives/Chip.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Viewer from "../primitives/Viewer.svelte";
  import IdeasView from "./IdeasView.svelte";
  import ProjectView from "./ProjectView.svelte";
  import SerieView from "./SerieView.svelte";
  import { jobs, jobsDrenados, refrescarJobs, seleccionPendiente } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import * as API from "@/lib/proyectos";
  import * as Auto from "@/lib/autopiloto";
  import * as SeriesAPI from "@/lib/series";
  import type { Idea, MiembroReparto, ProyectoDetalle, Voz } from "@/lib/proyectos";
  import type { Hilo, SerieDetalle, SerieResumen } from "@/lib/series";
  import type { OpcionesAutopiloto } from "@/lib/autopiloto";
  import type { ProyectoResumen, TemaResumen } from "@/lib/types";

  // --- estado ---
  let temas = $state<TemaResumen[]>([]);
  let series = $state<SerieResumen[]>([]);
  let proyectos = $state<ProyectoResumen[]>([]);
  let voces = $state<Voz[]>([]);
  let reparto = $state<MiembroReparto[]>([]);
  let plantillas = $state<string[]>([]);

  // Vista actual: una serie (sus episodios), un tema (sus ideas) o un proyecto
  // (el pipeline).
  let vista = $state<{ tipo: "tema" | "proyecto" | "serie"; id: number } | null>(null);
  let ideas = $state<Idea[]>([]);
  let proyecto = $state<ProyectoDetalle | null>(null);
  let serie = $state<SerieDetalle | null>(null);
  let bust = $state(0);
  let error = $state("");

  // Formulario de tema nuevo
  let temaTexto = $state("");
  let temaPlantilla = $state("");

  // Formulario de serie nueva. La plantilla por defecto es la de episodios, que
  // es la que activa el guion con líneas de personaje.
  let serieNombre = $state("");
  let seriePlantilla = $state("serie");
  // De qué va la serie y cuántos capítulos se quieren. La premisa es opcional,
  // pero con ella la serie nace ya con su hilo encolado: es la diferencia entre
  // una serie y una carpeta de capítulos.
  let seriePremisa = $state("");
  let serieEpisodios = $state(0);

  // Visor a pantalla completa
  let visorHtml = $state<string | null>(null);
  let visorPie = $state("");

  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");
  const ocupado = $derived((proyecto?.jobs_activos ?? 0) > 0);
  // La serie no produce nada por sí misma; lo que bloquea sus botones es que ya
  // haya algo en la cola (crear un episodio encola su guion).
  const hayTrabajo = $derived($jobs.length > 0);
  // El tema de una serie no se lista aparte: tiene el mismo nombre que ella y
  // se entra a sus ideas de episodio desde la propia serie.
  const temasSueltos = $derived(temas.filter((t) => !t.serie));

  // Con veinte proyectos en la lista, cuáles están ya subidos es la pregunta
  // que no se puede contestar mirando: por eso el filtro, y no solo la marca.
  let filtroPub = $state<"todos" | "sin" | "subidos">("todos");
  const proyectosVisibles = $derived(
    proyectos.filter((pr) => {
      if (filtroPub === "sin") return !pr.publicado_en;
      if (filtroPub === "subidos") return !!pr.publicado_en;
      return true;
    }),
  );
  const sinSubir = $derived(proyectos.filter((pr) => !pr.publicado_en).length);

  function fallo(e: unknown) {
    error = (e as Error).message;
  }

  async function refrescarListas() {
    try {
      [temas, proyectos, series] = await Promise.all([
        API.listarTemas(), API.listarProyectos(), SeriesAPI.listarSeries(),
      ]);
    } catch (e) {
      fallo(e);
    }
  }

  async function cargarVista() {
    if (!vista) return;
    try {
      if (vista.tipo === "tema") ideas = await API.ideasDeTema(vista.id);
      else if (vista.tipo === "serie") serie = await SeriesAPI.detalleSerie(vista.id);
      else proyecto = await API.detalleProyecto(vista.id);
    } catch (e) {
      fallo(e);
    }
  }

  function irA(tipo: "tema" | "proyecto" | "serie", id: number) {
    error = "";
    vista = { tipo, id };
    ideas = [];
    proyecto = null;
    serie = null;
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

  // --- series ---
  async function crearSerie(ev: Event) {
    ev.preventDefault();
    if (!serieNombre.trim()) return;
    try {
      const s = await SeriesAPI.crearSerie(
        serieNombre.trim(),
        seriePlantilla,
        seriePremisa.trim(),
        serieEpisodios,
      );
      serieNombre = "";
      seriePremisa = "";
      serieEpisodios = 0;
      await refrescarListas();
      irA("serie", s.id);
      // Con premisa, crear la serie encola su hilo: que se vea en la cola.
      if (s.job_id) refrescarJobs();
    } catch (e) {
      fallo(e);
    }
  }

  const accSerie = {
    // Crear el episodio ya encola su guion, así que se abre el proyecto: es
    // donde se va a seguir trabajando.
    nuevoEpisodio: async (apunte: string) => {
      if (!serie) return;
      try {
        const { proyecto_id, reparto_traido } = await SeriesAPI.crearEpisodio(serie.id, apunte);
        await refrescarListas();
        irA("proyecto", proyecto_id);
        refrescarJobs();
        if (reparto_traido.length)
          console.info(`Reparto fijo traído: ${reparto_traido.join(", ")}`);
      } catch (e) {
        fallo(e);
      }
    },
    anadirMiembro: async (slug: string) => {
      if (!serie) return;
      try {
        await SeriesAPI.anadirMiembroSerie(serie.id, slug);
        await cargarVista();
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
    quitarMiembro: async (slug: string, nombre: string) => {
      if (!serie) return;
      if (
        !confirm(
          `¿Quitar a «${nombre}» del reparto fijo de la serie?\n\n` +
            "Los episodios ya hechos se quedan con él: tienen su copia de la ficha y de la cara.",
        )
      )
        return;
      try {
        await SeriesAPI.quitarMiembroSerie(serie.id, slug);
        await cargarVista();
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
    // Las ideas de episodio son ideas del tema de la serie: mismo flujo de
    // siempre, con el prompt de ideas de la plantilla de serie.
    ideas: async () => {
      if (!serie) return;
      const temaId = serie.tema_id;
      try {
        await API.masIdeas(temaId);
        refrescarJobs();
        irA("tema", temaId);
      } catch (e) {
        fallo(e);
      }
    },
    // La cara y la voz del reparto fijo. Van aquí, en la serie, porque es
    // donde se decide una vez para todos los capítulos: hasta las series, la
    // cara solo se podía fijar dentro de un proyecto y el episodio 1 acababa
    // decidiendo por los otros cinco.
    cara: async (slug: string, tenia: boolean) => {
      try {
        // Si ya tenía cara, lo que se pide es otra distinta.
        await API.generarCaraDelReparto(slug, tenia);
        refrescarJobs();
      } catch (e) {
        fallo(e);
      }
    },
    voz: async (slug: string) => {
      try {
        await API.escribirVozDelReparto(slug);
        await cargarVista();
        refrescarJobs();
        API.listarVoces().then((v) => (voces = v)).catch(() => {});
      } catch (e) {
        fallo(e);
      }
    },
    asignarVoz: async (slug: string, voz: string) => {
      try {
        await API.asignarVozDelReparto(slug, voz);
        await cargarVista();
        API.listarReparto().then((r) => (reparto = r)).catch(() => {});
      } catch (e) {
        fallo(e);
      }
    },
    // Guardar la premisa y rehacer el hilo son dos acciones a propósito:
    // replanificar borra los tramos por los que la serie todavía no ha pasado,
    // y eso no puede salir de teclear en un campo.
    guardarPremisa: async (premisa: string, episodios: number) => {
      if (!serie) return;
      try {
        await SeriesAPI.ajustarSerie(serie.id, premisa, episodios);
        await cargarVista();
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
    escribirHilo: async () => {
      if (!serie) return;
      try {
        await SeriesAPI.escribirHilo(serie.id);
        refrescarJobs();
      } catch (e) {
        fallo(e);
      }
    },
    editarHilo: async (hilo: Hilo) => {
      if (!serie) return;
      try {
        await SeriesAPI.editarHilo(serie.id, hilo);
        await cargarVista();
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
    borrar: async () => {
      if (!serie) return;
      const nombre = serie.nombre;
      if (
        !confirm(
          `¿Disolver la serie «${nombre}»?\n\n` +
            "Sus episodios NO se borran: se quedan como vídeos sueltos, con su guion y su vídeo.",
        )
      )
        return;
      try {
        await SeriesAPI.borrarSerie(serie.id);
        vista = null;
        serie = null;
        refrescarListas();
      } catch (e) {
        fallo(e);
      }
    },
  };

  // Borrar un proyecto se puede desde su paso final y desde el listado, así que
  // la confirmación (doble: se lleva la carpeta entera) vive aquí y no en el
  // paso, que solo conoce el proyecto abierto.
  async function borrarProyecto(id: number, titulo: string) {
    if (!confirm(`¿Borrar el proyecto «${titulo}» POR COMPLETO?\n\nSe pierden guion, voz, subtítulos, imágenes, clips y vídeos.\nNo se puede deshacer.`))
      return;
    if (!confirm("Confirma otra vez: se borra la carpeta entera del proyecto.")) return;
    try {
      await API.borrarProyecto(id);
      if (vista?.tipo === "proyecto" && vista.id === id) {
        vista = null;
        proyecto = null;
      }
      refrescarListas();
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
    // Un proyecto por idea, cada uno con su autopiloto y encolados uno detrás
    // de otro. Se confirma porque son horas de GPU: con ocho ideas y el modo
    // i2v, media tarde.
    lote: async (o: OpcionesAutopiloto) => {
      if (vista?.tipo !== "tema") return;
      const sinParadas = !o.paradas?.length;
      if (
        !confirm(
          "¿Producir en lote las ideas de este tema?\n\n" +
            (sinParadas
              ? "Sin paradas de revisión: cada vídeo irá hasta el final sin preguntar nada.\n\n"
              : "Cada vídeo llegará hasta su primera parada de revisión y te esperará ahí.\n\n") +
            "Se producen de uno en uno y puedes pararlo todo cuando quieras.",
        )
      )
        return;
      try {
        const lote = await Auto.lanzarLote(vista.id, o);
        error = "";
        await refrescarListas();
        refrescarJobs();
        if (lote.actual) irA("proyecto", lote.actual.proyecto_id);
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
    // --- voz por personaje ---
    // Elegirla no encola nada (es un campo del personaje); crearla sí, y además
    // estrena voz en el banco, así que se recarga el banco en las dos.
    vozPersonaje: async (clave: string, voz: string) => {
      await tras(API.asignarVozPersonaje(pid(), clave, voz));
      voces = await API.listarVoces();
    },
    crearVozPersonaje: async (clave: string) => {
      await tras(API.crearVozPersonaje(pid(), clave));
      voces = await API.listarVoces();
    },
    // --- reparto propio ---
    // Traer y promover tocan a la vez el proyecto y el almacén, así que se
    // recargan los dos. El backend no encola nada (copiar un PNG), por eso se
    // ve el resultado sin esperar a la cola.
    traerDelReparto: async (slug: string) => {
      try {
        const { clave, renombrado } = await API.traerDelReparto(slug, pid());
        if (renombrado)
          alert(
            `Su clave ya estaba ocupada en este vídeo, así que entró como {${clave}}.\n\n` +
              "Ese es el marcador que hay que escribir en los prompts de escena.",
          );
        await cargarVista();
      } catch (e) {
        fallo(e);
      }
    },
    promoverAlReparto: async (clave: string, nombre: string) => {
      const puesto = prompt(
        "¿Con qué nombre lo guardas en el reparto propio?\n\n" +
          "Es lo que lo distinguirá en el listado.",
        nombre,
      );
      if (puesto === null || !puesto.trim()) return;
      try {
        await API.promoverAlReparto(pid(), clave, puesto.trim());
        reparto = await API.listarReparto();
        await cargarVista();
      } catch (e) {
        fallo(e);
      }
    },
    actualizarEnReparto: async (slug: string, clave: string) => {
      if (
        !confirm(
          `¿Subir la ficha y la cara de «${clave}» al reparto propio?\n\n` +
            "Los vídeos que ya lo trajeron NO cambian: cada uno tiene su copia.",
        )
      )
        return;
      try {
        await API.actualizarEnReparto(slug, pid(), clave);
        reparto = await API.listarReparto();
        await cargarVista();
      } catch (e) {
        fallo(e);
      }
    },
    borrarDelReparto: async (slug: string, nombre: string) => {
      if (
        !confirm(
          `¿Borrar a «${nombre}» del reparto propio?\n\n` +
            "Los vídeos que ya lo trajeron se quedan igual: su ficha y su cara son copias.",
        )
      )
        return;
      try {
        await API.borrarDelReparto(slug);
        reparto = await API.listarReparto();
        await cargarVista();
      } catch (e) {
        fallo(e);
      }
    },
    borrarVoz: async (slug: string, nombre: string) => {
      if (!confirm(`¿Borrar la voz «${nombre}»?\n\nLos proyectos que la usaban quedarán sin voz.`))
        return;
      await tras(API.borrarVoz(slug));
      voces = await API.listarVoces();
    },
    guardarResumen: (resumen: string) => tras(API.editarResumen(pid(), resumen)),
    generarResumen: () => tras(API.generarResumen(pid())),
    generarMetadatos: () => tras(API.generarMetadatos(pid())),
    generarCasting: () => tras(API.generarCasting(pid())),
    guardarCasting: (p: API.Personaje[]) => tras(API.guardarCasting(pid(), p)),
    generarRetrato: (clave: string, nuevoSeed: boolean) =>
      tras(API.generarRetrato(pid(), clave, nuevoSeed)),
    anadirPersonaje: (clave: string, nombre: string, ficha: string) =>
      tras(API.anadirPersonaje(pid(), clave, nombre, ficha)),
    borrarPersonaje: async (clave: string) => {
      if (!confirm(`¿Sacar a «${clave}» del reparto?\n\nSe borra también su retrato.`))
        return;
      await tras(API.borrarPersonaje(pid(), clave));
    },
    generarMusica: () => tras(API.generarMusicaProyecto(pid())),
    fijarMusica: (musicaId: number | null, mezclar: boolean) =>
      tras(API.fijarMusicaProyecto(pid(), musicaId, mezclar)),
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
    generarVideo: (modo: string, motor = "") =>
      tras(API.generarVideo(pid(), modo, motor)),
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
    borrarProyecto: () =>
      borrarProyecto(pid(), proyecto?.idea?.titulo ?? proyecto?.slug ?? ""),
    // --- publicación ---
    marcarPublicado: (fecha: string, url: string, nota: string) =>
      tras(API.marcarPublicado(pid(), fecha, url, nota)),
    quitarPublicado: async () => {
      if (
        !confirm(
          "¿Quitar la marca de publicado?\n\n" +
            "No se borra nada del disco; el vídeo vuelve a contar como pendiente de subir.",
        )
      )
        return;
      await tras(API.quitarPublicado(pid()));
    },
    liberarEspacio: async () => {
      const mb = proyecto?.disco.liberable_mb ?? 0;
      if (
        !confirm(
          `¿Liberar ${mb} MB de este proyecto?\n\n` +
            "En su carpeta queda solo el vídeo final: se borran la narración, los subtítulos, " +
            "las imágenes, los clips, los reescalados y los montajes anteriores.\n\n" +
            "El guion, los metadatos, el reparto y el enlace se quedan guardados, pero para " +
            "rehacer el vídeo habría que generarlo todo otra vez.\n\nNo se puede deshacer.",
        )
      )
        return;
      await tras(API.liberarEspacio(pid()));
    },
    // --- autopiloto ---
    lanzarAutopiloto: (o: OpcionesAutopiloto) => tras(Auto.lanzarAutopiloto(pid(), o)),
    continuarAutopiloto: () => tras(Auto.continuarAutopiloto(pid())),
    detenerAutopiloto: async () => {
      if (
        !confirm(
          "¿Apagar el autopiloto de este vídeo?\n\n" +
            "Se cancela la etapa que tenga en la cola; lo ya terminado se conserva. " +
            "Si es parte de un lote, los demás vídeos siguen su turno.",
        )
      )
        return;
      await tras(Auto.detenerAutopiloto(pid()));
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
      bust = Date.now();
      refrescarListas();
      cargarVista();
      API.listarVoces().then((v) => (voces = v)).catch(() => {});
      // El retrato de un miembro del reparto puede acabar de generarse en el
      // proyecto del que se promovió, y la miniatura del almacén lo refleja.
      API.listarReparto().then((r) => (reparto = r)).catch(() => {});
    }
  });

  // Y mientras el job corre: un lote de imágenes o clips las va dejando hechas
  // de una en una, pero la señal de arriba solo salta cuando la cola se vacía,
  // así que hasta ahora se veían once huecos vacíos durante varios minutos y
  // luego todo de golpe. Cada vez que el contador de lote avanza, se recarga.
  let ultimoAvance = -1;
  $effect(() => {
    const hecho = $jobs.find((j) => j.progreso)?.progreso?.hecho ?? -1;
    if (hecho !== ultimoAvance) {
      // El primer elemento aún no ha producido nada: recargar ahí solo gasta
      // una petición para pintar lo mismo.
      if (hecho > 0 && ultimoAvance >= 0) {
        bust = Date.now();
        cargarVista();
      }
      ultimoAvance = hecho;
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
      [plantillas, voces, reparto] = await Promise.all([
        API.listarPlantillas(), API.listarVoces(), API.listarReparto(),
      ]);
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

    <!-- Una serie se crea una vez y se saca capítulos; por eso el formulario es
         un desplegable y no compite con el de tema, que es el del día a día. -->
    <details class="border-b border-line p-4">
      <summary class="cursor-pointer text-sm font-semibold">Nueva serie</summary>
      <form class="mt-3 space-y-3" onsubmit={crearSerie}>
        <input
          class="control"
          bind:value={serieNombre}
          placeholder="Nombre de la serie. Ej: La casa de Alicia"
          aria-label="Nombre de la serie"
        />
        <Field label="Plantilla de la serie">
          <select class="control" bind:value={seriePlantilla}>
            {#each plantillas as pl (pl)}
              <option value={pl}>{pl}</option>
            {/each}
          </select>
        </Field>
        <Field
          label="Premisa (opcional)"
          hint="De qué va, en una o dos frases. De aquí sale el hilo: cómo acaba la serie y qué le toca a cada capítulo."
        >
          <textarea
            class="control"
            rows="3"
            bind:value={seriePremisa}
            placeholder="Alicia hereda la casa de su tía y descubre que alguien ya vive en ella."
            aria-label="Premisa de la serie"
          ></textarea>
        </Field>
        <Field label="Episodios (opcional)" hint="En 0 lo decide el LLM, y dice por qué ese número.">
          <input
            class="control"
            type="number"
            min="0"
            max="24"
            bind:value={serieEpisodios}
            aria-label="Episodios de la serie"
          />
        </Field>
        <p class="text-xs text-muted">
          La plantilla manda en todos los episodios: «serie» es la que escribe el guion con líneas
          de personaje, para que cada uno hable con su voz.
        </p>
        <Button type="submit" class="w-full" disabled={!serieNombre.trim()}>Crear serie</Button>
      </form>
    </details>

    {#if series.length}
      <div class="space-y-1 border-b border-line p-4">
        <p class="mb-2 text-xs font-medium tracking-wide text-muted">Series</p>
        {#each series as sr (sr.id)}
          <button
            type="button"
            onclick={() => irA("serie", sr.id)}
            class={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors
              ${vista?.tipo === "serie" && vista.id === sr.id ? "bg-accent-soft" : "hover:bg-surface-2"}`}
          >
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm">{sr.nombre}</span>
              <span class="text-xs text-muted">
                {sr.n_episodios} {sr.n_episodios === 1 ? "episodio" : "episodios"} ·
                {sr.n_miembros} fijos
              </span>
            </span>
          </button>
        {/each}
      </div>
    {/if}

    <div class="space-y-1 p-4">
      <p class="mb-2 text-xs font-medium tracking-wide text-muted">Temas</p>
      {#each temasSueltos as t (t.id)}
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
              name="trash"
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
      {#if proyectos.length > 1}
        <div class="mb-2">
          <Segmented
            options={[
              { value: "todos", label: "Todos" },
              { value: "sin", label: sinSubir ? `Sin subir ${sinSubir}` : "Sin subir" },
              { value: "subidos", label: "Subidos" },
            ]}
            value={filtroPub}
            onchange={(v) => (filtroPub = v as "todos" | "sin" | "subidos")}
          />
        </div>
      {/if}
      {#each proyectosVisibles as pr (pr.id)}
        <div
          class={`group flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors
            ${vista?.tipo === "proyecto" && vista.id === pr.id ? "bg-accent-soft" : "hover:bg-surface-2"}`}
        >
          <button
            type="button"
            onclick={() => irA("proyecto", pr.id)}
            class="flex min-w-0 flex-1 items-center gap-2 text-left"
          >
            <span class="min-w-0 flex-1 truncate text-sm">{pr.titulo}</span>
            {#if pr.serie}
              <Chip tone="accent">EP {pr.episodio}</Chip>
            {/if}
            <!-- Un proyecto en automático se reconoce desde la lista: con diez
                 en marcha, cuáles esperan que alguien los lea es la pregunta. -->
            {#if pr.autopiloto}
              <Chip tone={pr.autopiloto === "esperando" ? "warn" : "accent"}>
                {pr.autopiloto === "esperando" ? "revisar" : "auto"}
              </Chip>
            {/if}
            <!-- Un vídeo publicado está en FINAL por definición, así que la
                 marca de subido ocupa el sitio del estado en vez de añadir un
                 cuarto distintivo a una fila de 320 px. -->
            {#if pr.publicado_en}
              <Chip tone="ok">subido</Chip>
            {:else}
              <Chip>{pr.estado}</Chip>
            {/if}
          </button>
          <span class="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <IconButton
              name="trash"
              label="Borrar proyecto"
              size={14}
              onclick={() => borrarProyecto(pr.id, pr.titulo)}
              class="hover:bg-danger-soft hover:text-danger"
            />
          </span>
        </div>
      {:else}
        <p class="text-xs text-muted">
          {proyectos.length
            ? filtroPub === "sin"
              ? "Todos están subidos."
              : "Ninguno subido todavía."
            : "Sin proyectos aún."}
        </p>
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
          idea aprobada, un proyecto de vídeo. Si la historia continúa, hazla una serie: sus
          episodios comparten reparto y cada uno sabe en qué quedó el anterior.
        </p>
      </div>
    {:else if vista.tipo === "tema"}
      <div class="min-h-0 flex-1 overflow-y-auto p-6">
        <IdeasView
          {ideas}
          {voces}
          busy={hayTrabajo}
          onaprobar={accIdeas.aprobar}
          ondescartar={(id) => accIdeas.estado(id, "descartada")}
          onrestaurar={(id) => accIdeas.estado(id, "propuesta")}
          onabrirproyecto={(id) => irA("proyecto", id)}
          onmas={accIdeas.mas}
          onlote={accIdeas.lote}
        />
      </div>
    {:else if vista.tipo === "serie"}
      {#if serie}
        <SerieView
          s={serie}
          {reparto}
          {voces}
          {bust}
          busy={hayTrabajo}
          onnuevoepisodio={accSerie.nuevoEpisodio}
          onabrirepisodio={(pid) => irA("proyecto", pid)}
          onanadirmiembro={accSerie.anadirMiembro}
          onquitarmiembro={accSerie.quitarMiembro}
          onideas={accSerie.ideas}
          oncara={accSerie.cara}
          onvoz={accSerie.voz}
          onasignarvoz={accSerie.asignarVoz}
          onguardarpremisa={accSerie.guardarPremisa}
          onescribirhilo={accSerie.escribirHilo}
          oneditarhilo={accSerie.editarHilo}
          onborrarserie={accSerie.borrar}
        />
      {:else}
        <div class="grid flex-1 place-items-center">
          <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        </div>
      {/if}
    {:else if proyecto}
      <ProjectView p={proyecto} {voces} {reparto} {bust} {acciones} onver={abrirVisor} />
    {:else}
      <div class="grid flex-1 place-items-center">
        <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
      </div>
    {/if}
  </div>
</div>

<Viewer html={visorHtml} pie={visorPie} onclose={() => (visorHtml = null)} />
