import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, apiForm, media } from "../api";

function respuesta(cuerpo: string, status = 200) {
  return new Response(cuerpo, { status });
}

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

afterEach(() => fetchMock.mockReset());

describe("api", () => {
  it("antepone /api, manda JSON y devuelve el cuerpo parseado", async () => {
    fetchMock.mockResolvedValue(respuesta('{"ok":true}'));
    const r = await api<{ ok: boolean }>("/temas", { method: "POST", body: { texto: "x" } });

    expect(r).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/temas");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"texto":"x"}');
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("sin body no envía cuerpo; body falsy pero definido sí", async () => {
    fetchMock.mockImplementation(async () => respuesta("{}"));  // un Response nuevo por llamada
    await api("/a");
    expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
    await api("/a", { method: "POST", body: 0 });
    await api("/a", { method: "POST", body: "" });
    await api("/a", { method: "POST", body: false });
    expect(fetchMock.mock.calls.slice(1).map((c) => c[1].body)).toEqual(["0", '""', "false"]);
  });

  it("permite añadir cabeceras sin perder el Content-Type", async () => {
    fetchMock.mockResolvedValue(respuesta("{}"));
    await api("/a", { headers: { "X-Test": "1" } });
    expect(fetchMock.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
      "X-Test": "1",
    });
  });

  it("respuesta sin cuerpo (DELETE) devuelve undefined", async () => {
    fetchMock.mockResolvedValue(respuesta("", 200));
    expect(await api("/a", { method: "DELETE" })).toBeUndefined();
  });

  it("error HTTP: ApiError con status y el texto del servidor", async () => {
    fetchMock.mockResolvedValue(respuesta('{"detail":"Tema no existe"}', 404));
    const e = await api("/temas/9").catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("ApiError");
    expect(e.status).toBe(404);
    expect(e.message).toContain("Tema no existe");
  });

  it("error HTTP sin cuerpo cae a 'HTTP <status>'", async () => {
    fetchMock.mockResolvedValue(respuesta("", 500));
    await expect(api("/a")).rejects.toMatchObject({ status: 500, message: "HTTP 500" });
  });

  it("recorta cuerpos de error enormes a 400 caracteres", async () => {
    fetchMock.mockResolvedValue(respuesta("x".repeat(5000), 500));
    const e = await api("/a").catch((x) => x);
    expect(e.message).toHaveLength(400);
  });

  it("si ni siquiera se puede leer el cuerpo del error, igualmente lanza ApiError", async () => {
    const rota = respuesta("", 502);
    vi.spyOn(rota, "text").mockRejectedValue(new Error("stream roto"));
    fetchMock.mockResolvedValue(rota);
    await expect(api("/a")).rejects.toMatchObject({ status: 502, message: "HTTP 502" });
  });

  it("un fallo de red se propaga tal cual", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/a")).rejects.toThrow("Failed to fetch");
  });

  it("JSON inválido en una respuesta OK lanza error de parseo", async () => {
    fetchMock.mockResolvedValue(respuesta("<html>"));
    await expect(api("/a")).rejects.toThrow(SyntaxError);
  });
});

describe("apiForm", () => {
  it("hace POST con el FormData y sin Content-Type (lo pone el navegador)", async () => {
    fetchMock.mockResolvedValue(respuesta('{"id":3}'));
    const fd = new FormData();
    fd.append("idea", "x");
    expect(await apiForm("/galeria/editar", fd)).toEqual({ id: 3 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/galeria/editar");
    expect(init).toEqual({ method: "POST", body: fd });
    expect(init.headers).toBeUndefined();
  });

  it("error HTTP: ApiError con status y texto", async () => {
    fetchMock.mockResolvedValue(respuesta("Formato no soportado", 400));
    await expect(apiForm("/voces/clonar", new FormData())).rejects.toMatchObject({
      status: 400,
      message: "Formato no soportado",
    });
  });
});

describe("media", () => {
  afterEach(() => vi.useRealTimers());

  it("construye la URL del recurso", () => {
    expect(media("/proyectos/1/video")).toBe("/api/proyectos/1/video");
  });

  it("con bust añade la marca de tiempo para saltar la caché", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_700_000_000_000);
    expect(media("/galeria/2/final", true)).toBe("/api/galeria/2/final?v=1700000000000");
  });
});
