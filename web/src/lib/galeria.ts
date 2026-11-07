// Cliente del modo Imágenes. Refleja backend/routers/galeria.py.
import { api, apiForm } from "./api";
import type { GaleriaResumen, TipoGaleria } from "./types";

export interface GaleriaDetalle {
  id: number;
  tipo: TipoGaleria;
  motor: string;
  motor_nombre: string;
  idea: string;
  prompt: string | null;
  width: number;
  height: number;
  estado: string;
  seeds: number[];
  seed_elegido: number | null;
  // Solo en las animadas: el movimiento, su duración y qué vídeos hay.
  prompt_movimiento: string;
  duracion_s: number;
  seed_video: number | null;
  escala: Escala | null;
  videos: ("base" | Escala)[];
  ocupado: boolean;
}

export type Escala = "2k" | "4k";

// Duración del bucle de una animada, en segundos (backend: [animada]).
export const DURACION_MIN_S = 10;
export const DURACION_MAX_S = 15;

// Estados de una animada que ya tiene la preview aprobada.
export const ESTADOS_APROBADA = ["final", "movimiento", "animada", "escalada"];
// Estados en los que ya hay bucle en disco.
export const ESTADOS_CON_VIDEO = ["animada", "escalada"];

// Un modelo de [imagen.motores] de config.toml. `modos` son los que sabe hacer
// y `defecto_en` aquellos en los que va preseleccionado.
export interface MotorImagen {
  id: string;
  nombre: string;
  modos: ("generar" | "editar")[];
  defecto_en: ("generar" | "editar")[];
}

// Presets de tamaño (solo aplican al modo "generar"; al editar, el tamaño de
// salida lo marca la imagen de origen y el workflow).
export const TAMANOS: { label: string; w: number; h: number }[] = [
  { label: "9:16 vertical", w: 768, h: 1344 },
  { label: "1:1 cuadrado", w: 1024, h: 1024 },
  { label: "16:9 horizontal", w: 1344, h: 768 },
  { label: "2:3 retrato", w: 896, h: 1344 },
  { label: "3:2 paisaje", w: 1344, h: 896 },
];

export const listarGaleria = () => api<GaleriaResumen[]>("/galeria");
export const detalleGaleria = (id: number) => api<GaleriaDetalle>(`/galeria/${id}`);

export const listarMotores = () => api<MotorImagen[]>("/galeria/motores");

export const crearGenerar = (body: {
  idea: string;
  width: number;
  height: number;
  motor: string;
}) => api<{ id: number }>("/galeria", { method: "POST", body });

export const crearAnimada = (body: { idea: string; width: number; height: number }) =>
  api<{ id: number }>("/galeria/animada", { method: "POST", body });

export function crearEditar(idea: string, file: File, motor: string) {
  const fd = new FormData();
  fd.append("idea", idea);
  fd.append("imagen", file);
  fd.append("motor", motor);
  return apiForm<{ id: number }>("/galeria/editar", fd);
}

// Mejora el prompt con el LLM a demanda (paso opcional).
export const mejorarPrompt = (id: number) =>
  api<{ job_id: number }>(`/galeria/${id}/mejorar`, { method: "POST" });

export function crearQuitarFondo(file: File) {
  const fd = new FormData();
  fd.append("imagen", file);
  return apiForm<{ id: number; job_id: number }>("/galeria/quitarfondo", fd);
}

export const editarPrompt = (id: number, prompt: string) =>
  api<{ ok: boolean }>(`/galeria/${id}/prompt`, { method: "PUT", body: { prompt } });

export const lanzarPreviews = (id: number, width?: number, height?: number) =>
  api<{ job_id: number }>(`/galeria/${id}/previews`, {
    method: "POST",
    body: width && height ? { width, height } : {},
  });

// Aprueba una preview. En generar/editar encola el ESRGAN; en una animada es
// inmediato y no encola nada (job_id null).
export const lanzarFinal = (id: number, indice: number) =>
  api<{ job_id: number | null }>(`/galeria/${id}/final`, { method: "POST", body: { indice } });

export const guardarMovimiento = (id: number, prompt: string, duracion_s: number) =>
  api<{ ok: boolean }>(`/galeria/${id}/movimiento`, {
    method: "PUT",
    body: { prompt, duracion_s },
  });

export const mejorarMovimiento = (id: number) =>
  api<{ job_id: number }>(`/galeria/${id}/movimiento/mejorar`, { method: "POST" });

export const animar = (id: number) =>
  api<{ job_id: number }>(`/galeria/${id}/animar`, { method: "POST" });

export const escalar = (id: number, escala: Escala) =>
  api<{ job_id: number }>(`/galeria/${id}/escalar`, { method: "POST", body: { escala } });

// Ruta (para `media`) del bucle, o de su versión escalada.
export const rutaVideo = (id: number, escala?: Escala | null) =>
  `/galeria/${id}/video${escala ? `?escala=${escala}` : ""}`;

export const borrarGaleria = (id: number) =>
  api<{ borrada: number; archivos: number }>(`/galeria/${id}`, { method: "DELETE" });
