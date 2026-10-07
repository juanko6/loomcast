import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/biblioteca", async (o) => ({
  ...(await o<typeof import("@/lib/biblioteca")>()),
  cargarBiblioteca: vi.fn(),
}));

import { cargarBiblioteca, type LibItem } from "@/lib/biblioteca";
import { currentTrack, isPlaying } from "@/lib/player";
import { jobsDrenados, modo, seleccionPendiente } from "@/lib/stores";
import LibraryCard from "../biblioteca/LibraryCard.svelte";
import LibraryStudio from "../biblioteca/LibraryStudio.svelte";

const item = (extra: Partial<LibItem> = {}): LibItem => ({
  kind: "video", id: 1, titulo: "Mi vídeo", estado: "FINAL", subtipo: null,
  thumb: "/api/proyectos/1/imagenes/0", src: "/api/proyectos/1/video", destino: "videos", ...extra,
});

beforeEach(() => {
  currentTrack.set(null);
  isPlaying.set(false);
  modo.set("biblioteca");
  seleccionPendiente.set(null);
  jobsDrenados.set(0);
});

describe("LibraryCard", () => {
  it("muestra título, estado y subtipo", () => {
    render(LibraryCard, { item: item({ subtipo: "Editar", kind: "imagen" }), onopen: vi.fn(), onview: vi.fn() });
    expect(screen.getByText("Mi vídeo")).toBeInTheDocument();
    expect(screen.getByText("FINAL")).toBeInTheDocument();
    expect(screen.getByText("Editar")).toBeInTheDocument();
  });

  it("un vídeo con archivo se abre en el visor con <video>", async () => {
    const onview = vi.fn();
    render(LibraryCard, { item: item(), onopen: vi.fn(), onview });
    await userEvent.click(screen.getByRole("button", { name: "Abrir Mi vídeo" }));
    expect(onview).toHaveBeenCalledWith(expect.stringContaining('<video src="/api/proyectos/1/video"'), "Mi vídeo");
  });

  it("una imagen con archivo se abre en el visor con <img>", async () => {
    const onview = vi.fn();
    render(LibraryCard, { item: item({ kind: "imagen", src: "/api/galeria/2/final" }), onopen: vi.fn(), onview });
    await userEvent.click(screen.getAllByRole("button", { name: /Abrir/ })[0]); // la portada
    expect(onview.mock.calls[0][0]).toContain('<img src="/api/galeria/2/final"');
  });

  it("sin archivo, la portada abre el elemento en su estudio", async () => {
    const onopen = vi.fn(), onview = vi.fn();
    render(LibraryCard, { item: item({ src: null }), onopen, onview });
    await userEvent.click(screen.getByRole("button", { name: "Mi vídeo" }));
    expect(onopen).toHaveBeenCalled();
    expect(onview).not.toHaveBeenCalled();
  });

  it("'Abrir →' siempre abre en el estudio", async () => {
    const onopen = vi.fn();
    render(LibraryCard, { item: item(), onopen, onview: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: /Abrir →/ }));
    expect(onopen).toHaveBeenCalled();
  });

  it("una pista de música se reproduce en el player global (y no abre visor)", async () => {
    const onview = vi.fn();
    render(LibraryCard, {
      item: item({ kind: "musica", id: 5, titulo: "Lofi", subtipo: "Canción", src: "/api/musica/5/audio", thumb: null, destino: "musica" }),
      onopen: vi.fn(), onview,
    });
    await userEvent.click(screen.getByRole("button", { name: "Abrir Lofi" }));
    expect(onview).not.toHaveBeenCalled();
    expect(get(currentTrack)).toMatchObject({ id: 5, tipo: "cancion", src: "/api/musica/5/audio" });
  });

  it("una pista Instrumental se registra como instrumental", async () => {
    render(LibraryCard, {
      item: item({ kind: "musica", subtipo: "Instrumental", src: "/a.flac", thumb: null }), onopen: vi.fn(), onview: vi.fn(),
    });
    await userEvent.click(screen.getAllByRole("button", { name: /Abrir/ })[0]); // la portada
    expect(get(currentTrack)?.tipo).toBe("instrumental");
  });

  it("si la miniatura no carga, se oculta y queda el icono", async () => {
    const { container } = render(LibraryCard, { item: item(), onopen: vi.fn(), onview: vi.fn() });
    const img = container.querySelector("img")!;
    img.dispatchEvent(new Event("error"));
    await waitFor(() => expect(container.querySelector("img")).toBeNull());
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("sin miniatura muestra el icono según el tipo", () => {
    const { container } = render(LibraryCard, { item: item({ thumb: null, src: null }), onopen: vi.fn(), onview: vi.fn() });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  // Regresión: el visor inserta el HTML tal cual ({@html}) y el título viene del
  // LLM o del usuario; sin escapar, una comilla cortaba el atributo alt.
  it("el título con comillas o etiquetas no rompe el HTML que se manda al visor", async () => {
    const onview = vi.fn();
    render(LibraryCard, {
      item: item({ kind: "imagen", titulo: 'gato "feliz" <b>x</b>', src: "/a.png" }), onopen: vi.fn(), onview,
    });
    await userEvent.click(screen.getAllByRole("button", { name: /Abrir/ })[0]); // la portada
    const html: string = onview.mock.calls[0][0];
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.body.children).toHaveLength(1);                     // una sola <img>
    expect(doc.querySelector("img")!.getAttribute("alt")).toBe('gato "feliz" <b>x</b>');
    expect(doc.querySelector("b")).toBeNull();                      // sin inyección
  });

  it("un título que intenta cerrar el atributo no puede añadir manejadores", async () => {
    const onview = vi.fn();
    render(LibraryCard, {
      item: item({ kind: "imagen", titulo: 'x" onerror="alert(1)', src: "/a.png" }), onopen: vi.fn(), onview,
    });
    await userEvent.click(screen.getAllByRole("button", { name: /Abrir/ })[0]);
    const img = new DOMParser().parseFromString(onview.mock.calls[0][0], "text/html").querySelector("img")!;
    expect(img.hasAttribute("onerror")).toBe(false);
  });
});

describe("LibraryStudio", () => {
  const lista: LibItem[] = [
    item({ id: 1, titulo: "Cuento del bosque" }),
    item({ kind: "imagen", id: 2, titulo: "Zorro rojo", destino: "imagenes", src: null, thumb: null }),
    item({ kind: "musica", id: 3, titulo: "Lofi nocturno", destino: "musica", src: null, thumb: null }),
  ];

  it("muestra el estado de carga y luego las tarjetas", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    render(LibraryStudio);
    expect(await screen.findByText("Cuento del bosque")).toBeInTheDocument();
    expect(screen.getByText("Zorro rojo")).toBeInTheDocument();
    expect(screen.getByText("Lofi nocturno")).toBeInTheDocument();
  });

  it("las etiquetas de filtro llevan el conteo por tipo", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    expect(screen.getByRole("tab", { name: "Todo (3)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Vídeos (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Imágenes (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Música (1)" })).toBeInTheDocument();
  });

  it("filtrar por tipo oculta los demás", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    await userEvent.click(screen.getByRole("tab", { name: /Imágenes/ }));
    expect(screen.getByText("Zorro rojo")).toBeInTheDocument();
    expect(screen.queryByText("Cuento del bosque")).toBeNull();
    expect(screen.queryByText("Lofi nocturno")).toBeNull();
  });

  it("la búsqueda ignora mayúsculas y espacios alrededor", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    await userEvent.type(screen.getByLabelText("Buscar en la biblioteca"), "  ZORRO ");
    expect(screen.getByText("Zorro rojo")).toBeInTheDocument();
    expect(screen.queryByText("Cuento del bosque")).toBeNull();
  });

  it("filtro y búsqueda se combinan", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    await userEvent.click(screen.getByRole("tab", { name: /Música/ }));
    await userEvent.type(screen.getByLabelText("Buscar en la biblioteca"), "zorro");
    expect(screen.getByText("Nada coincide con la búsqueda.")).toBeInTheDocument();
  });

  it("biblioteca vacía: mensaje de que no hay nada", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue([]);
    render(LibraryStudio);
    expect(await screen.findByText("Aún no has creado nada.")).toBeInTheDocument();
  });

  it("si la carga falla muestra el error en vez de la lista", async () => {
    vi.mocked(cargarBiblioteca).mockRejectedValue(new Error("HTTP 500"));
    render(LibraryStudio);
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });

  it("'Abrir →' salta al estudio del elemento con su selección", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue([lista[1]]);
    render(LibraryStudio);
    await screen.findByText("Zorro rojo");
    await userEvent.click(screen.getByRole("button", { name: /Abrir →/ }));
    expect(get(modo)).toBe("imagenes");
    expect(get(seleccionPendiente)).toEqual({ modo: "imagenes", id: 2 });
  });

  it("recarga la lista cuando termina un job", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValueOnce([lista[0]]);
    render(LibraryStudio);
    await screen.findByText("Cuento del bosque");

    vi.mocked(cargarBiblioteca).mockResolvedValueOnce([lista[0], lista[1]]);
    jobsDrenados.update((n) => n + 1);

    expect(await screen.findByText("Zorro rojo")).toBeInTheDocument();
    expect(cargarBiblioteca).toHaveBeenCalledTimes(2);
  });

  it("abrir un vídeo muestra el visor y se cierra con Escape", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue([lista[0]]);
    const { container } = render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    await userEvent.click(screen.getByRole("button", { name: "Abrir Cuento del bosque" }));
    await waitFor(() => expect(document.querySelector(".viewer-media video")).not.toBeNull());
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(document.querySelector(".viewer-media")).toBeNull());
    expect(container).toBeTruthy();
  });

  it("reserva hueco para el player cuando hay una pista cargada", async () => {
    vi.mocked(cargarBiblioteca).mockResolvedValue(lista);
    currentTrack.set({ id: 1, tipo: "instrumental", idea: "x", seed: null, duracion_s: 1, src: "/a", cover: null });
    const { container } = render(LibraryStudio);
    await screen.findByText("Cuento del bosque");
    expect((container.firstElementChild as HTMLElement).style.paddingBottom).toBe("88px");
  });
});
