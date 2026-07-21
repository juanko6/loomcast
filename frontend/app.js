/* Loomcast — UI: tema → ideas → guion → voz → metadatos → escenas → video */
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
let voces = []; // banco de voces cacheado

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
    if (jobsPrevios > 0 && jobs.length < jobsPrevios) {
      voces = await api("/voces");
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

// ---------- bloques del proyecto ----------
function bloqueGuion(p, ocupado) {
  const g = p.guion;
  return `
    <div class="bloque">
      <h2>1 · Guion ${g ? `(v${p.guion_version})` : ""}</h2>
      ${!g ? `<p class="vacio">Generando el guion…</p>` : `
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
          </div>
        </form>`}
    </div>`;
}

function bloqueVoz(p, ocupado) {
  if (!p.guion) return "";
  const listas = voces.filter((v) => v.disponible);
  const opciones = listas.map((v) =>
    `<option value="${esc(v.slug)}" ${p.voz === v.slug ? "selected" : ""}>${esc(v.nombre)}</option>`
  ).join("");
  const vozSel = listas.find((v) => v.slug === p.voz);
  return `
    <div class="bloque">
      <h2>2 · Voz</h2>
      <label>Elige una voz del banco</label>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <select id="sel-voz" style="margin:0;flex:1">
          <option value="">— sin elegir —</option>
          ${opciones}
        </select>
        <button type="button" class="sec" id="preview-voz" ${vozSel ? "" : "disabled"}>▶ Escuchar</button>
      </div>
      ${vozSel ? `<audio id="audio-preview-voz" src="/api/voces/${vozSel.slug}/audio" style="display:none"></audio>
        <p class="resumen" style="margin-bottom:8px">${esc(vozSel.instruct)}</p>` : ""}
      <details style="margin-bottom:12px">
        <summary style="cursor:pointer;color:var(--dim)">＋ Crear una voz nueva</summary>
        <div style="margin-top:8px">
          <input id="voz-nombre" placeholder="Nombre (ej: Narrador Épico)">
          <textarea id="voz-instruct" rows="2"
            placeholder="Describe cómo suena: voz masculina grave, tono misterioso, ritmo pausado…"></textarea>
          <button type="button" class="sec" id="crear-voz">Crear voz (VoiceDesign)</button>
        </div>
      </details>
      <div class="acciones" style="margin-bottom:12px">
        <button id="gen-voz" ${ocupado || !p.voz ? "disabled" : ""}>
          ${p.voz_disponible ? "↻ Regenerar narración" : "🎙 Generar narración"}
        </button>
      </div>
      ${p.voz_disponible ? `
        <audio controls src="/api/proyectos/${p.id}/audio?v=${Date.now()}"
               style="width:100%;margin-bottom:12px"></audio>` : ""}
      ${p.subtitulos ? `
        <details>
          <summary style="cursor:pointer;color:var(--dim)">Ver subtítulos (.srt)</summary>
          <pre class="meta-desc" style="max-height:240px;overflow:auto;background:var(--panel);
               padding:10px;border-radius:8px;margin-top:8px">${esc(p.subtitulos)}</pre>
        </details>` : ""}
    </div>`;
}

function bloqueMetadatos(p, ocupado) {
  if (!p.voz_disponible) return "";
  const m = p.metadatos;
  return `
    <div class="bloque">
      <h2>3 · Metadatos</h2>
      <div class="acciones" style="margin-bottom:12px">
        <button id="gen-meta" ${ocupado ? "disabled" : ""}>
          ${m ? "↻ Regenerar metadatos" : "🏷 Generar título, descripción y etiquetas"}
        </button>
      </div>
      ${!m ? `<p class="vacio">Genera los metadatos cuando la narración esté lista.</p>` : `
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

function bloqueEscenas(p, ocupado) {
  if (!p.subtitulos) return "";
  const hayEscenas = p.escenas.length > 0;
  const hayImagenes = p.imagenes_completas;
  return `
    <div class="bloque">
      <h2>4 · Escenas e imágenes</h2>
      <div class="acciones" style="margin-bottom:12px">
        <button id="gen-escenas" class="${hayEscenas ? "sec" : ""}" ${ocupado ? "disabled" : ""}>
          ${hayEscenas ? "↻ Regenerar prompts de escenas" : "🎞 Generar prompts de escenas"}
        </button>
      </div>
      ${!hayEscenas ? `<p class="vacio">Genera las escenas: el LLM propone un prompt visual por segmento, que puedes editar antes de crear las imágenes.</p>` : `
        <form id="form-escenas">
          <p class="resumen">Revisa y edita cada prompt visual. Cuando estés conforme, genera las imágenes.</p>
          ${p.escenas.map((e) => `
            <div class="escena-row">
              <div class="escena-cab">
                <span class="estado-chip">#${e.orden + 1} · ${e.t_inicio.toFixed(1)}–${e.t_fin.toFixed(1)}s</span>
                <span class="meta">${esc(e.texto)}</span>
              </div>
              <div style="display:flex;gap:8px;align-items:flex-start">
                ${e.imagen
                  ? `<img src="/api/proyectos/${p.id}/imagenes/${e.orden}?v=${Date.now()}"
                         style="width:54px;border-radius:6px;aspect-ratio:9/16;object-fit:cover;flex-shrink:0">`
                  : `<div style="width:54px;aspect-ratio:9/16;border-radius:6px;flex-shrink:0;
                         background:var(--panel2);display:flex;align-items:center;justify-content:center;
                         color:var(--dim);font-size:11px">${e.orden + 1}</div>`}
                <textarea class="escena-prompt" data-orden="${e.orden}" rows="3">${esc(e.prompt)}</textarea>
              </div>
            </div>`).join("")}
          <div class="acciones" style="margin-top:10px">
            <button type="submit" class="sec">Guardar prompts editados</button>
            <button type="button" id="gen-imagenes" ${ocupado ? "disabled" : ""}>
              ${hayImagenes ? "↻ Regenerar imágenes" : "✓ Aceptar y generar imágenes"}
            </button>
          </div>
        </form>`}
    </div>`;
}

const ETAPA_VIDEO = {
  armar_estatico: "Armando video estático…",
  generar_upscale: "Reescalando imágenes (ESRGAN)…",
  generar_clips: "Generando movimiento (Ken Burns 60fps)…",
  generar_i2v: "Animando escenas (i2v) + RIFE…",
  armar_video: "Armando video final (subtítulos + voz)…",
};

const MODOS_VIDEO = [
  { id: "estatico", nombre: "Estático (rápido)",
    desc: "Imágenes fijas + subtítulos + voz. ~30s. Ideal para iterar guion/voz/prompts." },
  { id: "kenburns", nombre: "Ken Burns (con movimiento)",
    desc: "ESRGAN + zoom/paneo a 60fps. Más nítido y vistoso. ~2-3 min." },
  { id: "i2v", nombre: "Image-to-video (movimiento IA)",
    desc: "Anima cada escena con tu workflow i2v de ComfyUI + RIFE a 60fps. Lo más vistoso, lo más lento." },
];

function bloqueVideo(p, ocupado) {
  if (!p.imagenes_completas) return "";
  const enVideo = ETAPA_VIDEO[p.job_activo];
  const modoSel = window.__modoVideo || "kenburns";
  return `
    <div class="bloque">
      <h2>5 · Video final</h2>
      <label>Modo de generación</label>
      <div id="modos-video" style="margin-bottom:10px">
        ${MODOS_VIDEO.map((m) => `
          <label class="modo-opcion ${m.disabled ? "off" : ""}">
            <input type="radio" name="modo-video" value="${m.id}"
              ${m.id === modoSel ? "checked" : ""} ${m.disabled ? "disabled" : ""}>
            <span><b>${esc(m.nombre)}</b><br><span class="meta">${esc(m.desc)}</span></span>
          </label>`).join("")}
      </div>
      <div class="acciones" style="margin-bottom:12px">
        <button id="gen-video" ${ocupado ? "disabled" : ""}>
          ${p.video_disponible ? "↻ Rehacer video" : "🎬 Generar video"}
        </button>
      </div>
      ${enVideo ? `<p class="spinner">${esc(enVideo)}</p>` : ""}
      ${p.video_disponible ? `
        <video controls src="/api/proyectos/${p.id}/video?v=${Date.now()}"
               style="width:280px;max-width:100%;border-radius:12px"></video>` : ""}
    </div>`;
}

// ---------- vista: detalle de proyecto ----------
async function renderProyecto(id) {
  const p = await api(`/proyectos/${id}`);
  const ocupado = p.jobs_activos > 0;
  panel.innerHTML = `
    <div class="bloque">
      <span class="estado-chip">${esc(p.estado)}</span>
      <h2 style="margin-top:8px">${esc(p.idea?.titulo ?? p.slug)}</h2>
      ${ocupado ? `<p class="spinner">Trabajando… (un job en curso)</p>` : ""}
    </div>
    ${bloqueGuion(p, ocupado)}
    ${bloqueVoz(p, ocupado)}
    ${bloqueMetadatos(p, ocupado)}
    ${bloqueEscenas(p, ocupado)}
    ${bloqueVideo(p, ocupado)}`;
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

const pid = () => vista.id;

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
    } else if (b.id === "regenerar-guion") {
      await api(`/proyectos/${pid()}/guion/regenerar`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "preview-voz") {
      $("#audio-preview-voz")?.play();
    } else if (b.id === "crear-voz") {
      const nombre = $("#voz-nombre").value.trim();
      const instruct = $("#voz-instruct").value.trim();
      if (!nombre || !instruct) return;
      await api("/voces", { method: "POST", body: { nombre, instruct } });
      b.textContent = "Creando voz…"; b.disabled = true;
      refrescarJobs();
    } else if (b.id === "gen-voz") {
      await api(`/proyectos/${pid()}/voz`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-meta") {
      await api(`/proyectos/${pid()}/metadatos`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-escenas") {
      await api(`/proyectos/${pid()}/escenas`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-imagenes") {
      await guardarPrompts();
      await api(`/proyectos/${pid()}/imagenes`, { method: "POST" });
      refrescarJobs(); renderVista();
    } else if (b.id === "gen-video") {
      const modo = document.querySelector('input[name="modo-video"]:checked')?.value || "kenburns";
      await api(`/proyectos/${pid()}/video`, { method: "POST", body: { modo } });
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

document.addEventListener("change", async (ev) => {
  if (ev.target.id === "sel-voz" && vista?.tipo === "proyecto") {
    const voz = ev.target.value;
    if (voz) await api(`/proyectos/${pid()}/voz`, { method: "PUT", body: { voz } });
    renderVista();
  } else if (ev.target.name === "modo-video") {
    window.__modoVideo = ev.target.value; // recordar el modo elegido
  }
});

async function guardarPrompts() {
  const escenas = [...document.querySelectorAll(".escena-prompt")].map((t) => ({
    orden: +t.dataset.orden, prompt: t.value.trim(),
  }));
  await api(`/proyectos/${pid()}/escenas`, { method: "PUT", body: { escenas } });
}

document.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    if (ev.target.id === "form-guion") {
      const frases = [...document.querySelectorAll("#g-frases input")]
        .map((i) => i.value.trim()).filter(Boolean);
      await api(`/proyectos/${pid()}/guion`, {
        method: "PUT",
        body: { gancho: $("#g-gancho").value.trim(), frases, cta: $("#g-cta").value.trim() },
      });
      renderVista();
    } else if (ev.target.id === "form-escenas") {
      await guardarPrompts();
      renderVista();
    }
  } catch (e) {
    panel.insertAdjacentHTML("afterbegin", `<div class="error-box">${esc(e.message)}</div>`);
  }
});

// ---------- arranque ----------
(async function init() {
  const [plantillas, bancoVoces] = await Promise.all([api("/plantillas"), api("/voces")]);
  voces = bancoVoces;
  $("#tema-plantilla").innerHTML =
    plantillas.map((p) => `<option>${esc(p)}</option>`).join("");
  cargarListas();
  refrescarSalud();
  refrescarJobs();
  setInterval(refrescarSalud, 15000);
  setInterval(refrescarJobs, 2500);
})();
