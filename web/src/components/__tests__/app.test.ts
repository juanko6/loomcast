import { render, screen } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

// App arranca el polling al montar y lo para al desmontar: se vigila ese ciclo
// de vida, con los estudios hijos alimentados por un backend vacío.
const backend = async (ruta: string): Promise<any> => {
  if (ruta === "/llm/modelos") return { activo: "a", modelos: [{ id: "a", nombre: "A" }, { id: "b", nombre: "B" }] };
  if (ruta === "/salud") return { comfy: true, llm_estado: { estado: "activo", nombre: "A" } };
  return [];
};
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn() }));

import { api } from "@/lib/api";
import * as stores from "@/lib/stores";
import App from "../App.svelte";

beforeEach(() => {
  vi.mocked(api).mockImplementation(backend);
  stores.detenerPolling();
  stores.modo.set("videos");
  stores.modelos.set([]);
});

describe("App", () => {
  it("monta el rail, el área de trabajo y arranca el polling", async () => {
    const iniciar = vi.spyOn(stores, "iniciarPolling");
    render(App);
    expect(screen.getByRole("navigation", { name: "Navegación del estudio" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Vídeos" })).toBeInTheDocument();
    expect(iniciar).toHaveBeenCalledTimes(1);
  });

  it("carga los modelos de texto al arrancar", async () => {
    render(App);
    expect(await screen.findByTitle("Modelo de texto")).toBeInTheDocument();
  });

  it("si cargar los modelos falla, la app arranca igualmente", async () => {
    vi.mocked(api).mockImplementation(async (ruta: string) => {
      if (ruta === "/llm/modelos") throw new Error("HTTP 500");
      return backend(ruta);
    });
    render(App);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.queryByTitle("Modelo de texto")).toBeNull();
  });

  it("al desmontar para el polling", () => {
    const detener = vi.spyOn(stores, "detenerPolling");
    const { unmount } = render(App);
    detener.mockClear();
    unmount();
    expect(detener).toHaveBeenCalled();
  });

  it("navegar por el rail cambia el estudio mostrado", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    render(App);
    await userEvent.click(screen.getByText("Biblioteca").closest("button")!);
    expect(await screen.findByRole("heading", { level: 1, name: "Biblioteca" })).toBeInTheDocument();
  });
});
