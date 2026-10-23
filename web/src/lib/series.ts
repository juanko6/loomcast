// Cliente del área de Series (dentro del modo Vídeos): refleja
// backend/routers/series.py.
//
// Una serie es un nombre, una plantilla, un reparto fijo y un hilo. Lo que la
// UI tiene que dejar hacer en un clic es lo que más se repite al producir una
// serie de verdad: el episodio siguiente.
import { api } from "./api";
import type { MiembroReparto } from "./proyectos";

// Un tramo del hilo: el sitio que ocupa un episodio en la historia. El
// `numero` lo pone el backend por la posición en la lista (es el episodio al
// que le toca), así que al editar no se manda.
export interface Tramo {
  numero: number;
  titulo: string;
  pasa: string;
  cambia: string;
}

// Hacia dónde va la serie. Lo escribe el LLM desde la premisa y se edita como
// el guion: es un plan, y un plan que nadie puede corregir deriva igual que un
// resumen que nadie puede corregir.
export interface Hilo {
  premisa: string;
  pregunta: string;
  destino: string;
  // Lo que esta serie NO es. Frena la deriva mejor que diez reglas de estilo:
  // un capítulo que se desvía casi nunca cambia de tono, cambia de género.
  fuera: string[];
  episodios_recomendados: number;
  por_que: string;
  tramos: Tramo[];
}

export interface SerieResumen {
  id: number;
  slug: string;
  nombre: string;
  plantilla: string;
  // De qué va la serie, en palabras del usuario: de aquí sale el hilo.
  premisa: string;
  // Cuántos episodios se pidieron; 0 = lo decide el LLM. Los que la serie tiene
  // de verdad son `n_tramos`.
  episodios_objetivo: number;
  n_tramos: number;
  tiene_hilo: boolean;
  // Tema del que cuelgan las ideas de episodio: con él se reutiliza el "generar
  // más ideas" de siempre, solo que con el prompt de ideas de la plantilla de
  // serie, que piensa en episodios.
  tema_id: number;
  n_episodios: number;
  n_miembros: number;
}

export interface EpisodioResumen {
  proyecto_id: number;
  episodio: number;
  titulo: string;
  slug: string;
  estado: string;
  // Vacío = sin cerrar. Cuando lo tiene, es lo que el episodio siguiente usará
  // como contexto al escribir su guion. Se escribe al aprobar el guion, no al
  // armar el vídeo: la historia queda cerrada cuando está escrita.
  resumen: string;
  // El tramo del hilo que le tocaba (null si la serie no tiene hilo, o si este
  // episodio se sale del mapa).
  tramo: Tramo | null;
  // Qué hizo en vez de lo que su tramo pedía. Vacío = lo cumplió.
  desvio: string;
  // Se escribió sobre un canon que después cambió (se reescribió el guion de
  // un episodio anterior, o se corrigió su resumen a mano).
  continuidad_rota: boolean;
  ocupado: boolean;
}

export interface SerieDetalle extends SerieResumen {
  // El reparto fijo, tal como está en el reparto propio: cada episodio nuevo se
  // los trae con su ficha, su cara y su voz.
  miembros: MiembroReparto[];
  // null = serie sin hilo: funciona como antes, solo con continuidad hacia
  // atrás.
  hilo: Hilo | null;
  hilo_version: number;
  episodios: EpisodioResumen[];
}

export const listarSeries = () => api<SerieResumen[]>("/series");

// `premisa` es opcional pero es lo que convierte esto en una serie y no en una
// carpeta de capítulos: con ella, crear la serie encola su hilo (`job_id`).
// `episodios` en 0 significa que lo decide el LLM, que además dirá por qué.
export const crearSerie = (
  nombre: string,
  plantilla: string,
  premisa = "",
  episodios = 0,
) =>
  api<SerieResumen & { job_id: number | null }>("/series", {
    method: "POST",
    body: { nombre, plantilla, premisa, episodios },
  });

// Guardar la premisa no reescribe el hilo: eso es `escribirHilo`, porque en una
// serie a medias replanifica los capítulos que aún no se han escrito.
export const ajustarSerie = (id: number, premisa: string, episodios: number) =>
  api<SerieResumen>(`/series/${id}`, {
    method: "PUT",
    body: { premisa, episodios },
  });

// Escribe el hilo, o replanifica lo que falta si ya hay capítulos rodados (lo
// decide la etapa: los tramos rodados no se tocan).
export const escribirHilo = (id: number) =>
  api<{ job_id: number }>(`/series/${id}/hilo`, { method: "POST" });

export const editarHilo = (id: number, hilo: Omit<Hilo, "tramos"> & {
  tramos: { titulo: string; pasa: string; cambia: string }[];
}) =>
  api<{ version: number; tramos: number }>(`/series/${id}/hilo`, {
    method: "PUT",
    body: hilo,
  });
export const detalleSerie = (id: number) => api<SerieDetalle>(`/series/${id}`);
export const borrarSerie = (id: number) =>
  api<{ episodios_sueltos: number }>(`/series/${id}`, { method: "DELETE" });

export const anadirMiembroSerie = (id: number, reparto_slug: string) =>
  api<{ slug: string }>(`/series/${id}/miembros`, {
    method: "POST",
    body: { reparto_slug },
  });
export const quitarMiembroSerie = (id: number, slug: string) =>
  api<{ slug: string }>(`/series/${id}/miembros/${slug}`, { method: "DELETE" });

// `apunte` es opcional: vacío, el episodio lo propone el LLM desde el resumen
// del anterior. `reparto_traido` dice con qué clave entró cada personaje fijo,
// que es el marcador que acabará en los prompts de escena.
export const crearEpisodio = (id: number, apunte = "") =>
  api<{
    proyecto_id: number;
    episodio: number;
    idea_id: number;
    job_id?: number;
    reparto_traido: string[];
  }>(`/series/${id}/episodios`, { method: "POST", body: { apunte } });
