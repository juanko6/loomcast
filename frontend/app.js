/* Loomcast — UI Fase 1: temas → ideas → guion → metadatos */
const $ = (sel) => document.querySelector(sel);
const panel = $("#panel");

const api = async (ruta, opts = {}) => {
  const r = await fetch(`/api${ruta}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
};

const esc = (t) =>
  String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- estado global ----------
let vista = null; // {tipo: "tema"|"proyecto", id}
let jobsPrevios = 0;

// ---------- salud y jobs ----------
async function refrescarSalud() {
  try {
    const s = await api("/salud");
    $("#dot-llm").className = `dot ${s.llm ? "on" : "off"}`;
    $("#dot-comfy").className = `dot ${s.comfy ? "on" : "off"}`;
  } catch { /* servidor caído; los dots quedan como estén */ }
}

async function refrescarJobs() {
  try {
    const jobs = await api("/jobs");
    const badge = $("#jobs-badge");
    badge.classList.toggle("oculto", jobs.length === 0);
    if (jobs.length) badge.textContent = `${jobs.length} job(s) en cola`;
    // si un job terminó, recargar la vista actual y las listas
    if (jobsPrevios > 0 && jobs.length < jobsPrevios) {
      cargarListas();
      renderVista();
    }
    jobsPrevios = jobs.length;
  } catch { /* ignorar */ }
}

// ---------- listas laterales ----------
async function cargarListas() {
  const [temas, proyectos] = await Promise.all([
    api("/temas"), api("/proyectos"),
  ]);
  $("#lista-temas").innerHTML = temas.map((t) => `
    <li data-tema="${t.id}" class="${vista?.tipo === "tema" && vista.id === t.id ? "activo" : ""}">
      <span>${esc(t.texto.slice(0, 40))}</span>
      <span class="meta">${t.n_aprobadas}/${t.n_ideas} ✓</span>
    </li>`).join("") || `<li class="meta">Sin temas aún</li>`;
  $("#lista-proyectos").innerHTML = proyectos.map((p) => `
    <li data-proyecto="${p.id}" class="${vista?.tipo === "proyecto" && vista.id === p.id ? "activo" : ""}">
      <span>${esc(p.titulo.slice(0, 40))}</span>
      <span class="meta">${esc(p.estado)}</span>
    </li>`).join("") || `<li class="meta">Sin proyectos aún</li>`;
}

// ---------- vista: ideas de un tema ----------
async function renderTema(id) {
  const ideas = await api(`/temas/${id}/ideas`);
  if (!ideas.length) {
    panel.innerHTML = `<p class="spinner">Generando ideas con el LLM… la lista aparecerá aquí.</p>`;
    return;
  }
  panel.innerHTML = `
    <h2>Ideas (aprueba las buenas, descarta el resto)</h2>
    ${ideas.map((i) => `
      <div class="card ${i.estado}">
        <h3>${esc(i.titulo)}</h3>
        <div class="gancho">“${esc(i.gancho)}”</div>
        <div class="resumen">${esc(i.resumen)}</div>
        <div class="acciones">
          ${i.proyecto_id
            ? `<button data-ir-proyecto="${i.proyecto_id}">Ver proyecto →</button>`
            : `
          <button data-proyecto-de="${i.id}">✓ Aprobar y crear proyecto</button>
          ${i.estado !== "descartada"
            ? `<button class="peligro" data-descartar="${i.id}">Descartar</button>`
            : `<button class="sec" data-restaurar="${i.id}">Restaurar</button>`}`}
        </div>
      </div>`).join("")}
    <button class="sec" id="mas-ideas">＋ Generar más ideas</button>`;
}

// ---------- vista: detalle de proyecto ----------
async function renderProyecto(id) {
  const p = await api(`/proyectos/${id}`);
  const g = p.guion;
  const m = p.metadatos;
  const ocupado = p.jobs_activos > 0;

  panel.innerHTML = `
    <div class="bloque">
      <span class="estado-chip">${esc(p.estado)}</span>
      <h2 style="margin-top:8px">${esc(p.idea?.titulo ?? p.slug)}</h2>
      ${ocupado ? `<p class="spinner">Trabajando… (guion o metadatos en curso)</p>` : ""}
    </div>

    <div class="bloque">
      <h2>Guion ${g ? `(v${p.guion_version})` : ""}</h2>
      ${!g ? `<p class="vacio">Aún no hay guion.</p>` : `
        <form id="form-guion">
          <label>Gancho</label>
          <input id="g-gancho" value="${esc(g.gancho)}">
          <label>Frases</label>
          <div id="g-frases">
            ${g.frases.map((f) => `
              <div class="frase-row">
                <input value="${esc(f)}">
                <button type="button" class="sec quitar-frase">✕</button>
              </div>`).join("")}
          </div>
          <button type="button" class="sec" id="agregar-frase">＋ frase</button>
          <label>CTA (cierre)</label>
          <input id="g-cta" value="${esc(g.cta)}">
          <div class="acciones" style="margin-top:10px">
            <button type="submit">Guardar guion editado</button>
            <button type="button" class="sec" id="regenerar-guion" ${ocupado ? "disabled" : ""}>↻ Regenerar con LLM</button>
            <button type="button" id="gen-meta" ${ocupado ? "disabled" : ""}>Generar metadatos →</button>
          </div>
        </form>`}
    </div>

    <div class="bloque">
      <h2>Voz y subtítulos</h2>
      ${!g ? `<p class="vacio">Primero el guion.</p>` : `
        <div class="acciones" style="margin-bottom:12px">
          <button id="gen-voz" ${ocupado ? "disabled" : ""}>
            ${p.voz_disponible ? "↻ Regenerar voz (nueva voz)" : "🎙 Generar voz"}
          </button>
        </div>
        ${p.voz_disponible ? `
          <audio controls src="/api/proyectos/${p.id}/audio?v=${Date.now()}"
                 style="width:100%;margin-bottom:12px"></audio>` : ""}
        ${p.subtitulos ? `
          <details>
            <summary style="cursor:pointer;color:var(--dim)">Ver subtítulos (.srt)</summary>
            <pre class="meta-desc" style="max-height:260px;overflow:auto;background:var(--panel);
                 padding:10px;border-radius:8px;margin-top:8px">${esc(p.subtitulos)}</pre>
          </details>` : ""}`}
    </div>

    <div class="bloque">
      <h2>Metadatos</h2>
      ${!m ? `<p class="vacio">Genera el guion primero y luego los metadatos.</p>` : `
        <div class="card">
          <h3>YouTube</h3>
          <p><b>${esc(m.youtube.titulo)}</b></p>
          <pre class="meta-desc">${esc(m.youtube.descripcion)}</pre>
          <div class="etiquetas">${m.youtube.etiquetas.map((e) => `<span>${esc(e)}</span>`).join("")}</div>
        </div>
        <div class="card">
          <h3>TikTok</h3>
          <pre class="meta-desc">${esc(m.tiktok.descripcion)}</pre>
        </div>`}
    </div>`;
}

// ---------- render según vista ----------
async function renderVista() {
  if (!vista) return;
  try {
    if (vista.tipo === "tema") await renderTema(vista.id);
    else await renderProyecto(vista.id);
  } catch (e) {
    panel.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

function irA(tipo, id) {
  vista = { tipo, id };
  cargarListas();
  renderVista();
}

// ---------- eventos ----------
$("#form-tema").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const texto = $("#tema-texto").value.trim();
  if (!texto) return;
  const r = await api("/temas", {
    method: "POST",
    body: { texto, plantilla: $("#tema-plantilla").value },
  });
  $("#tema-texto").value = "";
  irA("tema", r.tema_id);
  refrescarJobs();
});

document.addEventListener("click", async (ev) => {
  const b = ev.target;
  const li = b.closest?.("[data-tema]");
  if (li) return irA("tema", +li.dataset.tema);
  const lp = b.closest?.("[data-proyecto]");
  if (lp) return irA("proyecto", +lp.dataset.proyecto);

  try {
    if (b.dataset?.descartar) {
      await api(`/ideas/${b.dataset.descartar}/estado`, { method: "POST", body: { estado: "descartada" } });
      renderVista(); cargarListas();
    } else if (b.dataset?.restaurar) {
      await api(`/ideas/${b.dataset.restaurar}/estado`, { method: "POST", body: { estado: "propuesta" } });
      renderVista(); cargarListas();
    } else if (b.dataset?.proyectoDe) {
      const r = await api(`/ideas/${b.dataset.proyectoDe}/proyecto`, { method: "POST" });
      irA("proyecto", r.proyecto_id);
      refrescarJobs();
    } else if (b.dataset?.irProyecto) {
      irA("proyecto", +b.dataset.irProyecto);
    } else if (b.id === "mas-ideas" && vista?.tipo === "tema") {
      await api(`/temas/${vista.id}/ideas`, { method: "POST" });
      refrescarJobs();
      b.textContent = "Generando más ideas…"; b.disabled = true;
    } else if (b.id === "regenerar-guion" && vista?.tipo === "proyecto") {
      await api(`/proyectos/${vista.id}/guion/regenerar`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-meta" && vista?.tipo === "proyecto") {
      await api(`/proyectos/${vista.id}/metadatos`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-voz" && vista?.tipo === "proyecto") {
      await api(`/proyectos/${vista.id}/voz`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "agregar-frase") {
      const div = document.createElement("div");
      div.className = "frase-row";
      div.innerHTML = `<input value=""><button type="button" class="sec quitar-frase">✕</button>`;
      $("#g-frases").appendChild(div);
    } else if (b.classList?.contains("quitar-frase")) {
      b.closest(".frase-row").remove();
    }
  } catch (e) {
    panel.insertAdjacentHTML("afterbegin", `<div class="error-box">${esc(e.message)}</div>`);
  }
});

document.addEventListener("submit", async (ev) => {
  if (ev.target.id !== "form-guion") return;
  ev.preventDefault();
  const frases = [...document.querySelectorAll("#g-frases input")]
    .map((i) => i.value.trim()).filter(Boolean);
  await api(`/proyectos/${vista.id}/guion`, {
    method: "PUT",
    body: { gancho: $("#g-gancho").value.trim(), frases, cta: $("#g-cta").value.trim() },
  });
  renderVista();
});

// ---------- arranque ----------
(async function init() {
  const plantillas = await api("/plantillas");
  $("#tema-plantilla").innerHTML =
    plantillas.map((p) => `<option>${esc(p)}</option>`).join("");
  cargarListas();
  refrescarSalud();
  refrescarJobs();
  setInterval(refrescarSalud, 15000);
  setInterval(refrescarJobs, 2500);
})();
