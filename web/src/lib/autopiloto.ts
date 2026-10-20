// Cliente del autopiloto y de los lotes. Refleja backend/routers/lotes.py y los
// endpoints de autopiloto de backend/routers/proyectos.py.
import { api } from "./api";

// Las tres paradas de revisión humana, en el orden en que llegan. El texto es lo
// que se lee en los interruptores al lanzar, así que dice **qué se revisa** y no
// cómo se llama la clave.
export const PARADAS = [
  {
    id: "idea",
    nombre: "Elegir las ideas",
    desc: "En un lote solo se producen las ideas que hayas aprobado. Sin esta parada entran también las propuestas.",
  },
  {
    id: "guion",
    nombre: "Revisar el guion",
    desc: "El guion lo decide todo: un texto malo son veinte minutos de GPU tirados en imágenes, clips y montaje.",
  },
  {
    id: "escenas",
    nombre: "Revisar los prompts de escena",
    desc: "Justo antes de gastar GPU en las imágenes, que es la etapa cara.",
  },
];

export const PARADAS_DEFECTO = PARADAS.map((p) => p.id);

export interface Autopiloto {
  id: number;
  proyecto_id: number;
  lote_id: number | null;
  // pendiente | corriendo | esperando | hecho | error | parado
  estado: string;
  modo_video: string;
  motor: string;
  paradas: string[];
  // Última etapa que terminó bien (tipo de job).
  etapa: string;
  // Por qué está donde está, ya escrito para leerlo.
  motivo: string;
  // Clave de la parada en la que espera, o "" si no espera a nadie.
  parada: string;
}

export interface LoteProyecto {
  proyecto_id: number;
  estado: string;
  etapa: string;
  motivo: string;
}

export interface Lote {
  id: number;
  tema_id: number;
  tema: string;
  total: number;
  pendientes: number;
  esperando: number;
  hechos: number;
  errores: number;
  parados: number;
  // El proyecto que está produciendo ahora, o null si ninguno.
  actual: { proyecto_id: number; titulo: string; etapa: string; posicion: number } | null;
  proyectos: LoteProyecto[];
}

export interface OpcionesAutopiloto {
  modo: string;
  motor?: string;
  voz?: string;
  // null = las paradas de config.toml; [] = producción sin manos. Son dos cosas
  // distintas y la API las distingue.
  paradas?: string[] | null;
}

export const lanzarAutopiloto = (pid: number, o: OpcionesAutopiloto) =>
  api<Autopiloto>(`/proyectos/${pid}/autopiloto`, { method: "POST", body: o });

export const continuarAutopiloto = (pid: number) =>
  api<Autopiloto>(`/proyectos/${pid}/autopiloto/continuar`, { method: "POST" });

export const detenerAutopiloto = (pid: number) =>
  api<{ parado: boolean }>(`/proyectos/${pid}/autopiloto`, { method: "DELETE" });

export const lanzarLote = (tema_id: number, o: OpcionesAutopiloto) =>
  api<Lote>("/lotes", { method: "POST", body: { tema_id, ...o } });

export const listarLotes = () => api<Lote[]>("/lotes");

// Qué se lee del estado de una tirada. "esperando" no es un problema: es el
// autopiloto haciendo lo que se le pidió, así que no se pinta como un aviso.
export const ESTADO_AUTOPILOTO: Record<string, { texto: string; clase: string }> = {
  pendiente: { texto: "En cola del lote", clase: "text-dim" },
  corriendo: { texto: "En automático", clase: "text-accent" },
  esperando: { texto: "Esperando tu revisión", clase: "text-warn" },
  hecho: { texto: "Terminado", clase: "text-ok" },
  error: { texto: "Detenido por un fallo", clase: "text-danger" },
  parado: { texto: "Parado", clase: "text-warn" },
};

export function estadoAutopiloto(estado: string) {
  return ESTADO_AUTOPILOTO[estado] ?? { texto: estado, clase: "text-dim" };
}

/** Si esa tirada sigue viva (produciendo, esperando turno o esperando revisión). */
export function viva(a: Autopiloto | null | undefined): boolean {
  return !!a && ["pendiente", "corriendo", "esperando"].includes(a.estado);
}

/** Si al lote le queda algo por hacer: es lo que decide si la cabecera lo cuenta. */
export function loteVivo(l: Lote): boolean {
  return l.pendientes > 0 || l.actual !== null;
}
