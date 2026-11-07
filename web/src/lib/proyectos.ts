// Cliente del modo Vídeos: temas, ideas, proyectos, voces y reparto propio.
// Refleja backend/routers/{temas,ideas,proyectos,voces,reparto,sistema}.py
import { api, apiForm } from "./api";
import type { Autopiloto } from "./autopiloto";
import type { ProyectoResumen, TemaResumen } from "./types";

export interface Idea {
  id: number;
  titulo: string;
  gancho: string;
  resumen: string;
  estado: string;
  proyecto_id: number | null;
}

export interface Escena {
  orden: number;
  texto: string;
  prompt: string;
  prompt_movimiento: string | null;
  t_inicio: number;
  t_fin: number;
  imagen: boolean;
  imagen_s: number | null;
  clip: boolean;
  clip_s: number | null;
  clip_modo: string | null;
  clip_viejo: boolean;
  modo: string | null;
  en_cola: string | null;
  // Claves de los personajes que salen en la escena. Si tienen retrato, su
  // imagen se genera a partir de esas caras y no solo del texto.
  personajes: string[];
}

// Personaje recurrente del vídeo. La `ficha` es la descripción física en
// inglés que se pega literal en cada prompt donde sale, para que el generador
// dibuje a la misma persona en todas sus escenas.
export interface Personaje {
  clave: string;
  nombre: string;
  ficha: string;
  // "persona" | "objeto". El reparto admite objetos recurrentes (un barco, un
  // mapa) y su imagen de referencia se encuadra sin pedir cara.
  tipo?: string;
  // Si ya tiene retrato de referencia generado: es la cara con la que se
  // generarán sus escenas.
  retrato: boolean;
  // Slug del miembro del reparto propio del que se trajo, o "" si nació en este
  // proyecto. No es una referencia viva: su ficha y su retrato son copias.
  reparto_slug?: string;
  // Slug de la voz del banco con la que dice sus líneas ("" = ninguna, y sus
  // líneas las narra la voz del proyecto).
  voz?: string;
}

// Alguien guardado en el reparto propio: una ficha y una cara que sobreviven al
// vídeo y se traen a cualquier proyecto nuevo.
export interface MiembroReparto {
  slug: string;
  nombre: string;
  // Marcador que propone al traerlo. Si en el proyecto ya está ocupado, entra
  // con la siguiente libre (ANA_2) en vez de pisar al que estaba.
  clave: string;
  ficha: string;
  tipo: string;
  // Su voz del banco, que viaja con él al vídeo al que se le traiga. No se
  // copia como el retrato: una voz del banco ya es compartida entre vídeos.
  voz?: string;
  retrato: boolean;
}

// Un tramo del cuerpo del guion en el formato de líneas atribuidas: quién lo
// dice (clave del reparto; "" = narrador) y qué dice.
export interface LineaGuion {
  personaje: string;
  texto: string;
}

export interface Guion {
  gancho: string;
  narracion?: string;
  frases?: string[];
  // Solo en las plantillas con formato_guion "lineas": el narrador lleva la
  // historia y los personajes dicen líneas puntuales, cada uno con su voz.
  lineas?: LineaGuion[];
  cta: string;
}

export interface Metadatos {
  youtube: { titulo: string; descripcion: string; etiquetas: string[] };
  tiktok: { descripcion: string };
}

// La pista de música del proyecto. Es una fila de la biblioteca de Música
// (misma tabla que las pistas sueltas), así que se escucha y se descarga sola,
// sin la narración: es el audio reutilizable en redes.
export interface MusicaProyecto {
  id: number;
  idea: string;
  tags: string | null;
  lyrics: string | null;
  duracion_s: number;
  bpm: number;
  keyscale: string;
  estado: string;
  tiene_audio: boolean;
  tiene_portada: boolean;
  // Hay un job de esta pista en la cola (brief, síntesis o portada).
  ocupado: boolean;
}

// Dónde quedó el vídeo una vez subido. null en el detalle = sin publicar.
export interface Publicacion {
  // ISO corta ("2026-10-29"): la pone quien lo marca, porque subir y apuntarlo
  // no pasan el mismo día.
  fecha: string;
  // Enlace o id del vídeo en YouTube, tal y como se pegó.
  url: string;
  nota: string;
}

// Lo apuntado puede ser el enlace entero o solo el id del vídeo (es lo que se
// tiene a mano según de dónde se copie); para abrirlo hace falta una URL.
// Devuelve "" si no hay nada apuntado.
export function enlaceYoutube(url: string): string {
  const v = url.trim();
  if (!v) return "";
  return /^https?:\/\//i.test(v) ? v : `https://youtu.be/${v}`;
}

// La fecha se guarda en ISO corta (que es como la manda el <input type=date>)
// pero aquí se lee en español, como las de los montajes. Lo que no sea una ISO
// se devuelve tal cual: mejor enseñar lo que hay que inventarse una fecha.
export function fechaEnEspanol(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

// Cuánto ocupa el proyecto en disco y cuánto de eso es material intermedio que
// se puede tirar una vez publicado.
export interface Disco {
  total_mb: number;
  liberable_mb: number;
}

export interface Version {
  nombre: string;
  fecha: string;
  mb: number;
}

// De qué serie es episodio un proyecto. null = vídeo suelto, que es lo que son
// todos los proyectos que no nacen de una serie.
export interface SerieDelProyecto {
  id: number;
  nombre: string;
  slug: string;
  episodio: number;
  // El episodio anterior y en qué quedó: es el contexto que el LLM ya está
  // usando para escribir este guion, así que es donde se corrige si está mal.
  anterior: { episodio: number; resumen: string } | null;
  // Cuántos tramos tiene el hilo de la serie (0 = serie sin hilo).
  tramos: number;
  // El sitio que ocupa este capítulo en la historia. Es lo otro que el LLM
  // tiene delante al escribir el guion, así que es lo que hace falta para
  // juzgarlo: sin el tramo, "se fue del tema" no se puede comprobar.
  tramo: { numero: number; titulo: string; pasa: string; cambia: string } | null;
  // Si es el último del hilo: el único episodio que cierra la serie.
  es_final: boolean;
  // Qué hizo en vez de lo que su tramo pedía. Vacío = lo cumplió.
  desvio: string;
  // De qué versión del guion salió el resumen. Distinta de `guion_version` =
  // el canon cuenta una versión que ya no existe.
  resumen_version: number;
  // Se escribió sobre un canon que después cambió.
  continuidad_rota: boolean;
}

export interface ProyectoDetalle {
  id: number;
  slug: string;
  estado: string;
  plantilla: string;
  // De qué está hecho el vídeo, según la plantilla: "imagen" (un prompt y un
  // PNG por escena) o "motion" (una ficha de composición dibujada por código).
  montaje: string;
  serie: SerieDelProyecto | null;
  // En qué quedó ESTE episodio, para el guion del siguiente. Vacío = sin cerrar
  // (o proyecto suelto).
  resumen_episodio: string;
  voz: string | null;
  voz_instruct: string;
  idea: { titulo: string; gancho: string; resumen: string } | null;
  guion: Guion | null;
  guion_version: number;
  metadatos: Metadatos | null;
  voz_disponible: boolean;
  // mtime del voz.mp3: bust del player de narración tras cada regeneración.
  voz_version: number;
  subtitulos: string | null;
  escenas: Escena[];
  personajes: Personaje[];
  imagenes_completas: boolean;
  // null = el proyecto no tiene música todavía.
  musica: MusicaProyecto | null;
  // Si el armado mezcla la pista bajo la narración. Tener música y mezclarla
  // son dos decisiones distintas.
  musica_mezclar: boolean;
  video_disponible: boolean;
  versiones: Version[];
  // null = el vídeo no está subido todavía.
  publicacion: Publicacion | null;
  disco: Disco;
  // De este proyecto ya solo queda el vídeo final: se publicó y se liberó su
  // material. No es que le falte trabajo, es que se tiró a propósito.
  liberado: boolean;
  jobs_activos: number;
  job_activo: string | null;
  // Su última tirada automática, viva o terminada; null si nunca tuvo una. Va
  // la última y no solo la viva porque cómo acabó la anterior —un fallo, una
  // parada— es lo que hay que leer antes de relanzarla.
  autopiloto: Autopiloto | null;
}

// Un paso del pipeline en el stepper de la vista de proyecto.
export interface Paso {
  id: string;
  label: string;
  hecho: boolean;
  bloqueado: boolean;
}

export interface Voz {
  slug: string;
  nombre: string;
  instruct: string;
  estado: string;
  disponible: boolean;
}

// --- temas e ideas ---
export const listarTemas = () => api<TemaResumen[]>("/temas");
export const crearTema = (texto: string, plantilla: string) =>
  api<{ tema_id: number }>("/temas", { method: "POST", body: { texto, plantilla } });
export const ideasDeTema = (id: number) => api<Idea[]>(`/temas/${id}/ideas`);
export const masIdeas = (id: number) =>
  api<{ job_id: number }>(`/temas/${id}/ideas`, { method: "POST" });
export const borrarTema = (id: number) =>
  api<{ ideas: number }>(`/temas/${id}`, { method: "DELETE" });

export const cambiarEstadoIdea = (id: number, estado: string) =>
  api(`/ideas/${id}/estado`, { method: "POST", body: { estado } });
export const proyectoDesdeIdea = (id: number) =>
  api<{ proyecto_id: number }>(`/ideas/${id}/proyecto`, { method: "POST" });

// --- proyectos ---
export const listarProyectos = () => api<ProyectoResumen[]>("/proyectos");
export const detalleProyecto = (id: number) => api<ProyectoDetalle>(`/proyectos/${id}`);

export const guardarGuion = (id: number, body: Guion) =>
  api<{ version: number }>(`/proyectos/${id}/guion`, { method: "PUT", body });
export const regenerarGuion = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/guion/regenerar`, { method: "POST" });

export const seleccionarVoz = (id: number, voz: string) =>
  api(`/proyectos/${id}/voz`, { method: "PUT", body: { voz } });
export const generarVoz = (id: number, modo: "clon" | "design", instruct?: string) =>
  api<{ job_id: number }>(`/proyectos/${id}/voz`, {
    method: "POST",
    body: { modo, instruct },
  });

// Corrige a mano en qué quedó el episodio: es lo que el guion del siguiente
// dará por cierto, así que no puede depender de un texto que nadie revisa.
export const editarResumen = (id: number, resumen: string) =>
  api<{ resumen: string }>(`/proyectos/${id}/resumen`, {
    method: "PUT",
    body: { resumen },
  });

// Lo reescribe el LLM. Sale solo al armar el vídeo del episodio; esto es para
// rehacerlo tras cambiar el guion.
export const generarResumen = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/resumen`, { method: "POST" });

export const generarMetadatos = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/metadatos`, { method: "POST" });

// --- publicación ---
export const marcarPublicado = (
  id: number,
  fecha: string,
  url: string,
  nota: string,
) =>
  api<Publicacion>(`/proyectos/${id}/publicacion`, {
    method: "PUT",
    body: { fecha, url, nota },
  });
export const quitarPublicado = (id: number) =>
  api<{ publicado: boolean }>(`/proyectos/${id}/publicacion`, { method: "DELETE" });
// Tira el material intermedio de un proyecto ya publicado; devuelve lo liberado.
export const liberarEspacio = (id: number) =>
  api<{ mb: number; archivos: number }>(`/proyectos/${id}/liberar`, { method: "POST" });

export const generarCasting = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/casting`, { method: "POST" });
export const guardarCasting = (id: number, personajes: Personaje[]) =>
  api<{ actualizados: number }>(`/proyectos/${id}/casting`, {
    method: "PUT",
    body: { personajes },
  });

export const anadirPersonaje = (id: number, clave: string, nombre: string, ficha: string) =>
  api<{ clave: string }>(`/proyectos/${id}/personajes`, {
    method: "POST",
    body: { clave, nombre, ficha },
  });
export const borrarPersonaje = (id: number, clave: string) =>
  api<{ borrado: string }>(`/proyectos/${id}/personajes/${clave}`, { method: "DELETE" });

// Con qué voz del banco dice sus líneas un personaje ("" = la del proyecto).
export const asignarVozPersonaje = (id: number, clave: string, voz: string) =>
  api<{ ok: boolean }>(`/proyectos/${id}/personajes/${clave}/voz`, {
    method: "PUT",
    body: { voz },
  });

// Le crea una voz en el banco desde su propia ficha (VoiceDesign) y se la
// asigna. Queda asignada al encolar, así que la UI ya dice de quién es.
export const crearVozPersonaje = (id: number, clave: string) =>
  api<{ voz_id: number; slug: string; job_id: number }>(
    `/proyectos/${id}/personajes/${clave}/voz`,
    { method: "POST" },
  );

export const generarRetrato = (id: number, clave: string, nuevo_seed: boolean) =>
  api<{ job_id: number }>(`/proyectos/${id}/personajes/${clave}/retrato`, {
    method: "POST",
    body: { nuevo_seed },
  });

// Escribe el brief musical desde la historia y encola la pista.
export const generarMusicaProyecto = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/musica`, { method: "POST" });

// Engancha una pista de la biblioteca (o la suelta con musica_id = null) y
// decide si el armado la mezcla.
export const fijarMusicaProyecto = (
  id: number,
  musica_id: number | null,
  mezclar: boolean,
) =>
  api<{ ok: boolean }>(`/proyectos/${id}/musica`, {
    method: "PUT",
    body: { musica_id, mezclar },
  });

export const generarEscenas = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/escenas`, { method: "POST" });
export const guardarEscenas = (
  id: number,
  escenas: { orden: number; prompt: string; prompt_movimiento: string | null }[],
) => api<{ actualizadas: number }>(`/proyectos/${id}/escenas`, { method: "PUT", body: { escenas } });
export const fijarModos = (id: number, escenas: { orden: number; modo: string }[]) =>
  api(`/proyectos/${id}/escenas/modos`, { method: "PUT", body: { escenas } });

export const generarImagenes = (id: number) =>
  api<{ job_id: number }>(`/proyectos/${id}/imagenes`, { method: "POST" });
export const regenerarImagen = (id: number, orden: number, nuevo_seed: boolean) =>
  api<{ job_id: number }>(`/proyectos/${id}/escenas/${orden}/imagen`, {
    method: "POST",
    body: { nuevo_seed },
  });
export const regenerarClip = (id: number, orden: number, modo: string) =>
  api<{ job_id: number }>(`/proyectos/${id}/escenas/${orden}/clip`, {
    method: "POST",
    body: { modo },
  });

// `motor` solo lo miran los modos que animan con i2v; vacío = el de
// [i2v].motor en config.toml.
export const generarVideo = (id: number, modo: string, motor = "") =>
  api<{ job_id: number }>(`/proyectos/${id}/video`, {
    method: "POST",
    body: { modo, motor },
  });

// Un motor de [i2v.motores] de config.toml.
export type MotorI2V = {
  id: string;
  nombre: string;
  frames: number;
  fps_origen: number;
  defecto: boolean;
};

export const listarMotoresI2V = () =>
  api<MotorI2V[]>("/proyectos/motores-i2v");
export const borrarVideo = (id: number, conVersiones: boolean) =>
  api<{ final: number; versiones: number }>(
    `/proyectos/${id}/video?con_versiones=${conVersiones}`,
    { method: "DELETE" },
  );
export const borrarVersion = (id: number, nombre: string) =>
  api(`/proyectos/${id}/versiones/${nombre}`, { method: "DELETE" });
export const borrarProyecto = (id: number) =>
  api<{ slug: string; archivos: number }>(`/proyectos/${id}`, { method: "DELETE" });

// --- voces y plantillas ---
export const listarVoces = () => api<Voz[]>("/voces");
export const crearVoz = (nombre: string, instruct: string) =>
  api<{ job_id: number }>("/voces", { method: "POST", body: { nombre, instruct } });
export function clonarVoz(nombre: string, audio: File, descripcion: string, inicio?: number, fin?: number) {
  const fd = new FormData();
  fd.append("nombre", nombre);
  fd.append("audio", audio);
  fd.append("descripcion", descripcion);
  if (inicio != null) fd.append("inicio", String(inicio));
  if (fin != null) fd.append("fin", String(fin));
  return apiForm<{ job_id: number }>("/voces/clonar", fd);
}
export const borrarVoz = (slug: string) => api(`/voces/${slug}`, { method: "DELETE" });

export const listarPlantillas = () => api<string[]>("/plantillas");

// --- reparto propio ---
export const listarReparto = () => api<MiembroReparto[]>("/reparto");

// Guarda en el reparto a un personaje que ya quedó bien en este proyecto: se
// promueve, no se rellena un formulario en blanco.
export const promoverAlReparto = (proyecto_id: number, clave: string, nombre: string) =>
  api<{ slug: string; nombre: string; retrato: boolean }>("/reparto", {
    method: "POST",
    body: { proyecto_id, clave, nombre },
  });

// Pisa al miembro con la versión de este proyecto. Hace falta porque editar la
// ficha dentro del proyecto NO toca al original.
export const actualizarEnReparto = (slug: string, proyecto_id: number, clave: string) =>
  api<{ slug: string; nombre: string; retrato: boolean }>(`/reparto/${slug}`, {
    method: "PUT",
    body: { proyecto_id, clave },
  });

// `renombrado` = su clave estaba ocupada y entró con otra, que es la que hay
// que escribir en los prompts.
export const traerDelReparto = (slug: string, proyecto_id: number) =>
  api<{ clave: string; renombrado: boolean; retrato: boolean; voz: string }>(
    `/reparto/${slug}/traer`,
    { method: "POST", body: { proyecto_id } },
  );

export const borrarDelReparto = (slug: string) =>
  api<{ slug: string; personajes_desvinculados: number }>(`/reparto/${slug}`, {
    method: "DELETE",
  });

// Le hace la cara sin pasar por ningún proyecto. Es lo que una serie necesita:
// el hilo dice quiénes son antes del primer capítulo, y la cara hay que fijarla
// antes para que todos los episodios se traigan la misma. `nuevo_seed` da otra
// persona distinta, para cuando la que salió no convence.
export const generarCaraDelReparto = (slug: string, nuevo_seed = false) =>
  api<{ slug: string; job_id: number }>(
    `/reparto/${slug}/retrato?nuevo_seed=${nuevo_seed}`,
    { method: "POST" },
  );

// Le escribe una voz desde su ficha (los cuatro bloques de VoiceDesign) y la
// encola en el banco, donde queda como cualquier otra: si no convence, se borra.
export const escribirVozDelReparto = (slug: string) =>
  api<{ slug: string; voz: string; job_id: number }>(`/reparto/${slug}/voz`, {
    method: "POST",
  });

// Le pone una voz que ya está en el banco; "" se la quita.
export const asignarVozDelReparto = (slug: string, voz: string) =>
  api<{ slug: string; voz: string }>(`/reparto/${slug}/voz`, {
    method: "PUT",
    body: { voz },
  });

// Modos de generación de vídeo (los describe la UI, los ejecuta el backend).
export const MODOS_VIDEO = [
  {
    id: "estatico",
    nombre: "Estático (rápido)",
    desc: "Imágenes fijas + subtítulos + voz. ~30s. Ideal para iterar guion, voz y prompts.",
  },
  {
    id: "kenburns",
    nombre: "Ken Burns (con movimiento)",
    desc: "ESRGAN + zoom/paneo a 60fps. Más nítido y vistoso. ~2-3 min.",
  },
  {
    id: "i2v",
    nombre: "Image-to-video (movimiento IA)",
    desc: "Anima cada escena con el motor i2v elegido + RIFE a 60fps. Lo más vistoso y lo más lento.",
  },
  {
    id: "mixto",
    nombre: "Mixto (modo por escena)",
    desc: "Usa el modo elegido en cada escena. Salta las que ya tengan su clip hecho con ese modo.",
  },
];

export const NOMBRE_MODO: Record<string, string> = {
  estatico: "Estático",
  kenburns: "Ken Burns",
  i2v: "i2v",
  motion: "Motion",
};

// Etiquetas legibles de la etapa en curso (job activo del proyecto).
export const ETAPA_VIDEO: Record<string, string> = {
  generar_guion: "Escribiendo el guion…",
  generar_voz: "Generando la narración…",
  generar_subtitulos: "Transcribiendo subtítulos…",
  generar_metadatos: "Escribiendo los metadatos…",
  generar_casting: "Fijando el reparto…",
  generar_retrato: "Retratando al personaje…",
  generar_escenas: "Proponiendo las escenas…",
  generar_musica_proyecto: "Escribiendo la música de la historia…",
  sintetizar_musica_proyecto: "Generando la pista de música…",
  generar_imagenes: "Generando las imágenes…",
  armar_estatico: "Armando vídeo estático…",
  generar_upscale: "Reescalando imágenes (ESRGAN)…",
  generar_clips: "Generando movimiento (Ken Burns 60fps)…",
  generar_i2v: "Animando escenas (i2v) + RIFE…",
  generar_clips_mixto: "Generando clips (modo por escena)…",
  regenerar_imagen: "Regenerando una imagen…",
  regenerar_clip: "Regenerando un clip…",
  armar_video: "Armando el vídeo final (subtítulos + voz)…",
  generar_resumen_episodio: "Cerrando el episodio (resumen para el siguiente)…",
  generar_retratos: "Retratando al reparto…",
};
