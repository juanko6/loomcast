// Cliente HTTP hacia el backend de Loomcast. En dev, Vite hace de proxy de
// `/api` hacia uvicorn; en producción, FastAPI sirve el build y las rutas
// `/api` son las mismas. Un único punto para manejar JSON y errores.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

type Opts = Omit<RequestInit, "body"> & { body?: unknown };

export async function api<T = unknown>(ruta: string, opts: Opts = {}): Promise<T> {
  const { body, headers, ...rest } = opts;
  const r = await fetch(`/api${ruta}`, {
    headers: { "Content-Type": "application/json", ...headers },
    ...rest,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const texto = (await r.text().catch(() => "")).slice(0, 400);
    throw new ApiError(r.status, texto || `HTTP ${r.status}`);
  }
  // Algunos endpoints (DELETE) pueden no devolver cuerpo.
  const txt = await r.text();
  return (txt ? JSON.parse(txt) : undefined) as T;
}

// Subidas con FormData (voces, editar/quitar fondo): sin Content-Type JSON.
export async function apiForm<T = unknown>(ruta: string, form: FormData): Promise<T> {
  const r = await fetch(`/api${ruta}`, { method: "POST", body: form });
  if (!r.ok) {
    const texto = (await r.text().catch(() => "")).slice(0, 400);
    throw new ApiError(r.status, texto || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

// URL de un recurso servido por el backend (imágenes, audio, video). `bust`
// añade un query para saltar caché tras regenerar.
export function media(ruta: string, bust = false): string {
  return `/api${ruta}${bust ? `?v=${Date.now()}` : ""}`;
}
