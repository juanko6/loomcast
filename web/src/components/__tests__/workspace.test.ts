import { render, screen } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Los estudios hijos piden sus listas al montar: aquí solo importa la cabecera.
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import type { Job } from "@/lib/types";
import { jobs, modo } from "@/lib/stores";
import Workspace from "../shell/Workspace.svelte";

const job = (id: number, progreso: Job["progreso"] = null): Job => ({ id, tipo: "generar_imagenes", estado: "corriendo", progreso });
const progreso = (extra = {}) => ({ job_id: 1, transcurrido_s: 12, fase: "", hecho: 0, total: 0, pct: null, eta_s: null, ...extra });

beforeEach(() => {
  modo.set("biblioteca");
  jobs.set([]);
});

describe("Workspace: cabecera", () => {
  it.each([
    ["videos", "Vídeos"], ["imagenes", "Imágenes"], ["musica", "Música"], ["biblioteca", "Biblioteca"],
  ] as const)("el modo %s lleva su título", (m, titulo) => {
    modo.set(m);
    render(Workspace);
    expect(screen.getByRole("heading", { level: 1, name: titulo })).toBeInTheDocument();
  });

  it("sin trabajos no hay chip de cola", () => {
    render(Workspace);
    expect(screen.queryByTitle(/Trabajos en cola/)).toBeNull();
  });

  it("con trabajos pero sin progreso, el chip cuenta la cola", () => {
    jobs.set([job(1), job(2)]);
    render(Workspace);
    expect(screen.getByTitle(/Trabajos en cola/)).toHaveTextContent("2 en cola");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("etapa sin lotes: enseña el tiempo transcurrido, para distinguir 'lento' de 'colgado'", () => {
    jobs.set([job(1, progreso({ transcurrido_s: 12 }))]);
    render(Workspace);
    expect(screen.getByTitle(/Trabajos en cola/)).toHaveTextContent("1 en cola · 12s");
  });

  it.each([
    [75, "~1 min"], [45, "~45s"], [3600, "~1 h 0 min"], [7260, "~2 h 1 min"],
  ])("la estimación de %i s se lee como %s", (eta, texto) => {
    jobs.set([job(1, progreso({ fase: "imagen 2 de 4", hecho: 1, total: 4, pct: 25, eta_s: eta }))]);
    render(Workspace);
    expect(screen.getByTitle(/Trabajos en cola/)).toHaveTextContent(`imagen 2 de 4 · ${texto}`);
  });

  it("con lote muestra la fase y una barra de progreso accesible", () => {
    jobs.set([job(1, progreso({ fase: "clip 1 de 3", hecho: 0, total: 3, pct: 0 }))]);
    render(Workspace);
    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "0");
    expect(barra).toHaveAttribute("aria-valuemax", "100");
    expect(barra).toHaveTextContent("clip 1 de 3");
  });

  it("el ancho del relleno sigue el porcentaje", () => {
    jobs.set([job(1, progreso({ fase: "imagen 3 de 4", pct: 50, eta_s: 30 }))]);
    const { container } = render(Workspace);
    expect(container.querySelector('[aria-hidden="true"][style*="width: 50%"]')).not.toBeNull();
  });

  it("la fase repite el recuento de la cola solo si hay más de un trabajo", () => {
    jobs.set([job(1, progreso({ fase: "imagen 1 de 2", pct: 0 })), job(2)]);
    render(Workspace);
    expect(screen.getByTitle(/Trabajos en cola/)).toHaveTextContent("imagen 1 de 2 · 12s · 2 en cola");
  });

  it("usa el progreso del job que lo tiene, no el primero de la lista", () => {
    jobs.set([job(1), job(2, progreso({ job_id: 2, fase: "voz 1 de 1", pct: 10, eta_s: 5 }))]);
    render(Workspace);
    expect(screen.getByTitle(/Trabajos en cola/)).toHaveTextContent("voz 1 de 1");
  });
});
