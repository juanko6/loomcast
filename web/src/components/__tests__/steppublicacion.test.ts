import { render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ProyectoDetalle, Publicacion } from "@/lib/proyectos";
import StepPublicacion from "../videos/steps/StepPublicacion.svelte";

const METADATOS = {
  youtube: { titulo: "Título YT", descripcion: "Descripción larga", etiquetas: ["a", "b"] },
  tiktok: { descripcion: "Texto TikTok" },
};

function proyecto(extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle {
  return {
    id: 1, slug: "demo", estado: "FINAL", plantilla: "curiosidades", voz: null, voz_instruct: "",
    idea: { titulo: "Un título", gancho: "g", resumen: "r" },
    guion: null, guion_version: 0, metadatos: METADATOS, voz_disponible: true, voz_version: 0,
    subtitulos: null, escenas: [], personajes: [], imagenes_completas: true,
    video_disponible: true, versiones: [], jobs_activos: 0, job_activo: null,
    musica: null, musica_mezclar: false, serie: null, resumen_episodio: "",
    publicacion: null, disco: { total_mb: 400, liberable_mb: 300 }, liberado: false, ...extra,
  } as ProyectoDetalle;
}

const PUBLICADO: Publicacion = {
  fecha: "2026-10-20",
  url: "abc123",
  nota: "Subido al canal nuevo",
};

const props = (p: ProyectoDetalle) => ({
  p, onmarcar: vi.fn(), onquitar: vi.fn(), onliberar: vi.fn(),
});

describe("StepPublicacion: marcar", () => {
  it("sin publicar, el formulario viene con la fecha de hoy", () => {
    render(StepPublicacion, props(proyecto()));
    const hoy = new Date().toISOString().slice(0, 10);
    expect((screen.getByLabelText("Fecha de subida") as HTMLInputElement).value).toBe(hoy);
    expect(screen.getByRole("button", { name: "Marcar como publicado" })).toBeEnabled();
  });

  it("marca con la fecha, el enlace y la nota que se teclean", async () => {
    const p = props(proyecto());
    render(StepPublicacion, p);
    await userEvent.clear(screen.getByLabelText("Enlace o id del vídeo"));
    await userEvent.type(screen.getByLabelText("Enlace o id del vídeo"), "abc123");
    await userEvent.type(screen.getByLabelText("Nota"), "canal nuevo");
    await userEvent.click(screen.getByRole("button", { name: "Marcar como publicado" }));
    const hoy = new Date().toISOString().slice(0, 10);
    expect(p.onmarcar).toHaveBeenCalledWith(hoy, "abc123", "canal nuevo");
  });

  it("ya publicado: dice cuándo, enlaza el vídeo y enseña la nota", () => {
    render(StepPublicacion, props(proyecto({ publicacion: PUBLICADO })));
    expect(screen.getByText("Publicado el 20/10/2026")).toBeInTheDocument();
    // Lo apuntado era solo el id: el enlace se compone para poder abrirlo.
    expect(screen.getByRole("link", { name: /abc123/ })).toHaveAttribute(
      "href",
      "https://youtu.be/abc123",
    );
    expect(screen.getByText("Subido al canal nuevo")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Marcar como publicado" })).toBeNull();
  });

  it("se pueden corregir los datos, y el formulario trae los de antes", async () => {
    render(StepPublicacion, props(proyecto({ publicacion: PUBLICADO })));
    await userEvent.click(screen.getByRole("button", { name: "Editar los datos" }));
    expect((screen.getByLabelText("Fecha de subida") as HTMLInputElement).value).toBe("2026-10-20");
    expect((screen.getByLabelText("Enlace o id del vídeo") as HTMLInputElement).value).toBe("abc123");
  });

  it("quitar la marca lo pide fuera", async () => {
    const p = props(proyecto({ publicacion: PUBLICADO }));
    render(StepPublicacion, p);
    await userEvent.click(screen.getByRole("button", { name: "Quitar la marca" }));
    expect(p.onquitar).toHaveBeenCalled();
  });

  it("sin vídeo montado avisa, pero deja marcarlo igual", () => {
    render(StepPublicacion, props(proyecto({ video_disponible: false })));
    expect(screen.getByText(/no tiene vídeo montado/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marcar como publicado" })).toBeEnabled();
  });
});

describe("StepPublicacion: espacio en disco", () => {
  const liberar = () => screen.getByRole("button", { name: /Liberar/ });

  it("dice cuánto ocupa y cuánto se puede tirar", () => {
    render(StepPublicacion, props(proyecto({ publicacion: PUBLICADO })));
    expect(screen.getByText("400 MB")).toBeInTheDocument();
    expect(screen.getByText("300 MB")).toBeInTheDocument();
  });

  it("no se libera lo que aún no está publicado, y lo explica", () => {
    render(StepPublicacion, props(proyecto()));
    expect(liberar()).toBeDisabled();
    expect(screen.getByText(/Solo de vídeos ya publicados/)).toBeInTheDocument();
  });

  it("publicado, libera lo que haya", async () => {
    const p = props(proyecto({ publicacion: PUBLICADO }));
    render(StepPublicacion, p);
    await userEvent.click(liberar());
    expect(p.onliberar).toHaveBeenCalled();
  });

  it("liberado, dice que ya solo queda el vídeo y no ofrece liberar más", () => {
    render(StepPublicacion, props(proyecto({
      publicacion: PUBLICADO, liberado: true,
      disco: { total_mb: 120, liberable_mb: 0 },
    })));
    expect(screen.getByText(/ya solo queda el vídeo final/)).toBeInTheDocument();
    expect(screen.getByText(/siguen guardados/)).toBeInTheDocument();
    expect(liberar()).toBeDisabled();
  });

  it("sin material intermedio no hay nada que liberar", () => {
    render(StepPublicacion, props(proyecto({
      publicacion: PUBLICADO, disco: { total_mb: 100, liberable_mb: 0 },
    })));
    expect(liberar()).toBeDisabled();
    expect(screen.getByText("No queda material intermedio que tirar.")).toBeInTheDocument();
  });
});

describe("StepPublicacion: los textos para subirlo", () => {
  it("trae los metadatos con sus botones de copiar", () => {
    render(StepPublicacion, props(proyecto()));
    expect(screen.getByDisplayValue("Título YT")).toBeInTheDocument();
    expect(screen.getByDisplayValue("a, b")).toBeInTheDocument();
    expect(screen.getByDisplayValue("#a #b")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar título" })).toBeInTheDocument();
  });

  it("sin metadatos manda al paso donde se escriben", () => {
    render(StepPublicacion, props(proyecto({ metadatos: null })));
    expect(screen.getByText(/se generan\s+en el paso de Metadatos/)).toBeInTheDocument();
  });
});
