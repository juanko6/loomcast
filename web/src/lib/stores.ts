// Estado global de la app (dentro de la isla raíz): salud del sistema, cola de
// jobs y modelo de texto activo. Usa stores de Svelte para que cualquier
// componente se suscriba sin pasar props en cadena.
import { writable, get } from "svelte/store";
import { api } from "./api";
import type { Salud, ModeloLLM, Job, StudioMode } from "./types";

export const modo = writable<StudioMode>("videos");

// Salto entre modos con un elemento ya elegido: la Biblioteca lo fija y el
// estudio de destino lo consume al montarse/reaccionar (y lo limpia).
export const seleccionPendiente = writable<{ modo: StudioMode; id: number } | null>(null);

export function abrirEn(destino: StudioMode, id: number): void {
  seleccionPendiente.set({ modo: destino, id });
  modo.set(destino);
}

export const salud = writable<Salud | null>(null);
export const modelos = writable<ModeloLLM[]>([]);
export const modeloActivo = writable<string>("");
export const jobs = writable<Job[]>([]);

// Señal que se incrementa cada vez que la cola se vacía un poco (un job
// terminó): las vistas se suscriben para refrescarse solas, como hacía el
// polling del app.js original.
export const jobsDrenados = writable<number>(0);

let jobsPrevios = 0;

export async function refrescarSalud(): Promise<void> {
  try {
    salud.set(await api<Salud>("/salud"));
  } catch {
    /* backend caído: dejamos el último estado conocido */
  }
}

export async function cargarModelos(): Promise<void> {
  const { activo, modelos: lista } = await api<{ activo: string; modelos: ModeloLLM[] }>(
    "/llm/modelos",
  );
  modelos.set(lista);
  modeloActivo.set(activo);
}

export async function cambiarModelo(id: string): Promise<void> {
  await api("/llm/modelo", { method: "POST", body: { id } });
  modeloActivo.set(id);
  refrescarSalud();
}

export async function refrescarJobs(): Promise<void> {
  try {
    const lista = await api<Job[]>("/jobs");
    jobs.set(lista);
    if (jobsPrevios > 0 && lista.length < jobsPrevios) {
      jobsDrenados.update((n) => n + 1);
    }
    jobsPrevios = lista.length;
  } catch {
    /* ignorar caídas puntuales del polling */
  }
}

let timerSalud: ReturnType<typeof setInterval> | null = null;
let timerJobs: ReturnType<typeof setTimeout> | null = null;
// Cada arranque estrena número: un ciclo que estaba esperando su petición
// cuando se paró el polling se encuentra el número cambiado y no reprograma,
// así que rearrancar no deja dos cadenas consultando a la vez.
let generacion = 0;

// La cola se consulta encadenando timeouts en vez de con un intervalo fijo
// para poder cambiar la cadencia: con trabajo en marcha hace falta ritmo para
// que la barra de progreso avance de forma legible, pero en reposo eso serían
// 3.600 peticiones por hora para no ver nada.
async function cicloJobs(gen: number): Promise<void> {
  await refrescarJobs();
  if (gen !== generacion) return;
  timerJobs = setTimeout(() => cicloJobs(gen), get(jobs).length ? 1000 : 2500);
}

// Arranca el polling de salud (15s) y de la cola (1s trabajando, 2.5s en
// reposo). Idempotente.
export function iniciarPolling(): void {
  detenerPolling();
  refrescarSalud();
  timerSalud = setInterval(refrescarSalud, 15000);
  cicloJobs(generacion);
}

export function detenerPolling(): void {
  generacion += 1;
  if (timerSalud) clearInterval(timerSalud);
  if (timerJobs) clearTimeout(timerJobs);
  timerSalud = timerJobs = null;
}

export function hayCola(): boolean {
  return get(jobs).length > 0;
}
