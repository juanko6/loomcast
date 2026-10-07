import { describe, expect, it } from "vitest";
import { escaparHtml } from "../html";

describe("escaparHtml", () => {
  it.each([
    ["texto normal", "texto normal"],
    ["", ""],
    ["a & b", "a &amp; b"],
    ["<b>x</b>", "&lt;b&gt;x&lt;/b&gt;"],
    ['di "hola"', "di &quot;hola&quot;"],
    ["it's", "it&#39;s"],
    ["&lt;", "&amp;lt;"],   // no doble-interpreta lo que ya parece una entidad
    ["acentos áéí ñ — ¿?", "acentos áéí ñ — ¿?"],
  ])("%j → %j", (entrada, esperado) => {
    expect(escaparHtml(entrada)).toBe(esperado);
  });

  it("el resultado, insertado como HTML, vuelve a dar el texto original", () => {
    const original = `<img src=x onerror="alert('x')"> & "comillas"`;
    const div = document.createElement("div");
    div.innerHTML = escaparHtml(original);
    expect(div.textContent).toBe(original);
    expect(div.querySelector("img")).toBeNull();
  });
});
