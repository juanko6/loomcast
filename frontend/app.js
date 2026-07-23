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

// Tope del fragmento a clonar (debe coincidir con MAX_REF_S del backend): un
// clip corto clona igual de bien y pesa menos en cada narración.
const MAX_CLIP_S = 15;

function actualizarClipInfo() {
  const s = window.__clipSel, info = $("#clip-info");
  if (!s || !info) return;
  info.textContent =
    `Fragmento a clonar: ${s.inicio.toFixed(1)}s → ${s.fin.toFixed(1)}s ` +
    `(${(s.fin - s.inicio).toFixed(1)}s).`;
}

// Prepara el reproductor del clip subido y la selección [inicio, fin] por defecto.
function seleccionarClip(file) {
  const recorte = $("#voz-recorte"), audio = $("#clip-preview");
  if (!recorte || !audio) return;
  if (!file) { recorte.style.display = "none"; window.__clipSel = null; return; }
  audio.src = URL.createObjectURL(file);
  recorte.style.display = "";
  audio.onloadedmetadata = () => {
    const dur = audio.duration || 0;
    window.__clipSel = { inicio: 0, fin: Math.min(dur, MAX_CLIP_S), dur };
    actualizarClipInfo();
  };
  // Al oír la selección, para al llegar al fin marcado.
  audio.ontimeupdate = () => {
    const s = window.__clipSel;
    if (s && !audio.paused && audio.currentTime >= s.fin) audio.pause();
  };
}

// ---------- estado global ----------
let vista = null; // {tipo: "tema"|"proyecto", id}
let jobsPrevios = 0;
let voces = []; // banco de voces cacheado

// ---------- salud y jobs ----------
// Un modelo gestionado pasa la mayor parte del tiempo descargado (ámbar): no
// es un fallo, se carga solo cuando llega una etapa de texto.
const ESTADO_LLM = {
  activo: ["on", "levantado por ti, fuera de Loomcast"],
  cargado: ["on", "cargado en memoria"],
  en_espera: ["espera", "descargado; se carga solo al generar texto"],
  caido: ["off", "no responde en su url"],
};

async function refrescarSalud() {
  try {
    const s = await api("/salud");
    const [clase, detalle] = ESTADO_LLM[s.llm_estado.estado] ?? ["off", ""];
    const dot = $("#dot-llm");
    dot.className = `dot ${clase}`;
    dot.title = `${s.llm_estado.nombre} — ${detalle}`;
    $("#dot-comfy").className = `dot ${s.comfy ? "on" : "off"}`;
  } catch { /* servidor caído; los dots quedan como estén */ }
}

async function cargarModelosLLM() {
  const { activo, modelos } = await api("/llm/modelos");
  const sel = $("#llm-modelo");
  sel.innerHTML = modelos.map((m) => `
    <option value="${esc(m.id)}" ${m.id === activo ? "selected" : ""}>${esc(m.nombre)}</option>
  `).join("");
  // Con un solo modelo declarado el desplegable no aporta nada.
  sel.classList.toggle("oculto", modelos.length < 2);
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
      <button class="borrar-tema" data-borrar-tema="${t.id}"
              data-texto="${esc(t.texto.slice(0, 40))}" title="Borrar tema">🗑</button>
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
          ${g.narracion ? `
            <label>Gancho</label>
            <input id="g-gancho" value="${esc(g.gancho)}">
            <label>Narración</label>
            <textarea id="g-narracion" rows="10">${esc(g.narracion)}</textarea>
            <label>CTA (cierre)</label>
            <input id="g-cta" value="${esc(g.cta)}">
          ` : `
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
          `}
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
      <select id="sel-voz" style="margin:0 0 8px;width:100%">
        <option value="">— sin elegir —</option>
        ${opciones}
      </select>
      ${vozSel ? `
        <audio controls src="/api/voces/${vozSel.slug}/audio"
               style="width:100%;margin-bottom:8px"></audio>
        <p class="resumen" style="margin-bottom:8px">${esc(vozSel.instruct)}</p>` : ""}
      <details style="margin-bottom:12px">
        <summary style="cursor:pointer;color:var(--dim)">＋ Crear una voz nueva</summary>
        <div style="margin-top:8px">
          <input id="voz-nombre" placeholder="Nombre (ej: Narrador Épico)">
          <div class="voz-modo" style="display:flex;gap:14px;margin:6px 0;font-size:.9em">
            <label><input type="radio" name="voz-modo" value="design" checked> Describir</label>
            <label><input type="radio" name="voz-modo" value="clon"> Clonar de un audio</label>
          </div>
          <div id="voz-campos-design">
            <textarea id="voz-instruct" rows="2"
              placeholder="Describe cómo suena: voz masculina grave, tono misterioso, ritmo pausado…"></textarea>
            <button type="button" class="sec" id="crear-voz">Crear voz (VoiceDesign)</button>
          </div>
          <div id="voz-campos-clon" style="display:none">
            <input id="voz-audio" type="file" accept="audio/*">
            <div id="voz-recorte" style="display:none;margin:6px 0">
              <audio id="clip-preview" controls style="width:100%"></audio>
              <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px">
                <button type="button" class="sec" id="marcar-inicio">⇤ Inicio aquí</button>
                <button type="button" class="sec" id="marcar-fin">Fin aquí ⇥</button>
                <button type="button" class="sec" id="oir-seleccion">▶ Oír selección</button>
              </div>
              <p class="meta" id="clip-info" style="margin:4px 0 0"></p>
            </div>
            <textarea id="voz-descripcion" rows="1"
              placeholder="Nota interna opcional (no afecta al clon)"></textarea>
            <button type="button" class="sec" id="clonar-voz">Clonar voz del fragmento</button>
          </div>
        </div>
      </details>
      <details style="margin-bottom:12px">
        <summary style="cursor:pointer;color:var(--dim)">Gestionar voces (${voces.length})</summary>
        <div style="margin-top:8px">
          ${voces.length ? voces.map((v) => `
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 0">
              <span>${esc(v.nombre)}${v.estado === "lista" ? "" : ` <span class="meta">(${esc(v.estado)})</span>`}</span>
              <button type="button" class="sec borrar-voz" data-slug="${esc(v.slug)}"
                      data-nombre="${esc(v.nombre)}" title="Borrar voz">🗑</button>
            </div>`).join("") : `<p class="meta">El banco está vacío</p>`}
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

const NOMBRE_MODO = { estatico: "Estático", kenburns: "Ken Burns", i2v: "i2v" };

// ---------- visor de imagen / clip ----------
function abrirVisor(html, pie) {
  $("#visor-contenido").innerHTML = html;
  $("#visor-pie").textContent = pie || "";
  $("#visor").classList.remove("oculto");
}

function cerrarVisor() {
  $("#visor").classList.add("oculto");
  $("#visor-contenido").innerHTML = ""; // corta la reproducción del clip
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") cerrarVisor();
});

// Controles por escena: regenerar su imagen o su clip sin tocar las demás.
function escenaAcciones(e) {
  // Estos botones NO se bloquean cuando hay trabajo en curso: la cola procesa
  // de uno en uno igualmente, así que se pueden dejar varias escenas pedidas y
  // seguir usando la app. Solo se bloquea la escena que ya está en la cola,
  // para no encolarla dos veces.
  const dis = e.en_cola ? "disabled" : "";
  const estado = [];
  if (e.imagen_s) estado.push(`img ${e.imagen_s}s`);
  if (e.clip) {
    // Los clips hechos antes de que se registrara el modo no tienen forma de
    // saberlo: se dice explícitamente en vez de mostrar un signo suelto.
    estado.push(e.clip_modo
      ? `clip ${NOMBRE_MODO[e.clip_modo]}${e.clip_s ? ` · ${e.clip_s}s` : ""}`
      : `clip (modo sin registrar)`);
  }
  return `
    <div class="escena-acciones">
      <button type="button" class="mini" data-regen-img="${e.orden}" ${dis}
              title="Genera otra imagen distinta (seed nuevo)">↻ Otra imagen</button>
      <button type="button" class="mini sec" data-regen-img-seed="${e.orden}" ${dis}
              title="Rehace la imagen con el mismo seed: solo cambia si editaste el prompt">↻ Mismo seed</button>
      <select class="escena-modo mini" data-orden="${e.orden}" style="width:auto;margin:0">
        ${["estatico", "kenburns", "i2v"].map((m) =>
          `<option value="${m}" ${(e.modo || "kenburns") === m ? "selected" : ""}>${NOMBRE_MODO[m]}</option>`
        ).join("")}
      </select>
      <button type="button" class="mini" data-regen-clip="${e.orden}" ${dis}
              ${!e.imagen ? "disabled title='Genera antes la imagen'" : ""}>↻ Clip</button>
      ${e.clip ? `<button type="button" class="mini sec" data-ver-clip="${e.orden}"
                          title="Reproducir el clip de esta escena">▶ Ver clip</button>` : ""}
      ${e.en_cola
        ? `<span class="estado-chip en-cola">⏳ ${e.en_cola === "imagen" ? "imagen" : "clip"} en cola</span>`
        : ""}
      ${estado.length ? `<span class="meta">${estado.join(" · ")}</span>` : ""}
      ${e.clip_viejo ? `<span class="estado-chip aviso">clip desactualizado</span>` : ""}
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
          <p class="resumen">Revisa y edita cada escena: arriba el prompt visual (imagen), abajo el de movimiento (solo lo usa el modo i2v). Cuando estés conforme, genera las imágenes.</p>
          ${p.escenas.map((e) => `
            <div class="escena-row">
              <div class="escena-cab">
                <span class="estado-chip">#${e.orden + 1} · ${e.t_inicio.toFixed(1)}–${e.t_fin.toFixed(1)}s</span>
                <span class="meta">${esc(e.texto)}</span>
              </div>
              <div style="display:flex;gap:8px;align-items:flex-start">
                ${e.imagen
                  ? `<img class="escena-miniatura" data-ver-img="${e.orden}"
                         title="Ver la imagen en grande"
                         src="/api/proyectos/${p.id}/imagenes/${e.orden}?v=${Date.now()}"
                         style="width:54px;border-radius:6px;aspect-ratio:9/16;object-fit:cover;flex-shrink:0">`
                  : `<div style="width:54px;aspect-ratio:9/16;border-radius:6px;flex-shrink:0;
                         background:var(--panel2);display:flex;align-items:center;justify-content:center;
                         color:var(--dim);font-size:11px">${e.orden + 1}</div>`}
                <div style="flex:1;display:flex;flex-direction:column;gap:6px">
                  <textarea class="escena-prompt" data-orden="${e.orden}" rows="3"
                            placeholder="Prompt visual (imagen)">${esc(e.prompt)}</textarea>
                  <textarea class="escena-movimiento" data-orden="${e.orden}" rows="2"
                            placeholder="Prompt de movimiento (solo modo i2v)">${esc(e.prompt_movimiento || "")}</textarea>
                  ${escenaAcciones(e)}
                </div>
              </div>
            </div>`).join("")}
          <div class="acciones" style="margin-top:10px;align-items:center">
            <label class="meta" style="display:flex;gap:6px;align-items:center;margin:0">
              Modo de todas:
              <select id="modo-todas" style="width:auto;margin:0">
                <option value="">— elegir —</option>
                <option value="estatico">Estático</option>
                <option value="kenburns">Ken Burns</option>
                <option value="i2v">i2v</option>
              </select>
            </label>
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
  generar_clips_mixto: "Generando clips (modo por escena)…",
  regenerar_imagen: "Regenerando una imagen…",
  regenerar_clip: "Regenerando un clip…",
  armar_video: "Armando video final (subtítulos + voz)…",
};

const MODOS_VIDEO = [
  { id: "estatico", nombre: "Estático (rápido)",
    desc: "Imágenes fijas + subtítulos + voz. ~30s. Ideal para iterar guion/voz/prompts." },
  { id: "kenburns", nombre: "Ken Burns (con movimiento)",
    desc: "ESRGAN + zoom/paneo a 60fps. Más nítido y vistoso. ~2-3 min." },
  { id: "i2v", nombre: "Image-to-video (movimiento IA)",
    desc: "Anima cada escena con tu workflow i2v de ComfyUI + RIFE a 60fps. Lo más vistoso, lo más lento." },
  { id: "mixto", nombre: "Mixto (modo por escena)",
    desc: "Usa el modo elegido en cada escena arriba. Salta las que ya tengan su clip hecho con ese modo." },
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
               style="width:280px;max-width:100%;border-radius:12px"></video>
        <div class="acciones" style="margin-top:8px">
          <button type="button" class="mini sec" id="ver-final">⤢ Ver en grande</button>
          <a class="boton mini sec" href="/api/proyectos/${p.id}/video"
             download="${esc(p.slug)}.mp4">⬇ Descargar</a>
          <button type="button" class="mini peligro" id="borrar-video">🗑 Borrar video</button>
        </div>` : ""}
      ${bloqueVersiones(p)}
      <div class="acciones" style="margin-top:16px;border-top:1px solid var(--borde);padding-top:12px">
        <button type="button" class="mini peligro" id="borrar-proyecto" ${ocupado ? "disabled" : ""}>
          🗑 Borrar proyecto entero
        </button>
        <span class="meta">Borra el guion, la voz, las imágenes, los clips y los videos.</span>
      </div>
    </div>`;
}

// Montajes anteriores: al rehacer el video, el que había se guarda en vez de
// perderse.
function bloqueVersiones(p) {
  if (!p.versiones?.length) return "";
  const total = p.versiones.reduce((a, v) => a + v.mb, 0).toFixed(0);
  return `
    <details style="margin-top:12px">
      <summary style="cursor:pointer;color:var(--dim)">
        Versiones anteriores (${p.versiones.length} · ${total} MB)
      </summary>
      <div style="margin-top:8px">
        ${p.versiones.map((v) => `
          <div class="version-row">
            <span class="meta">${esc(v.fecha)} · ${v.mb} MB</span>
            <button type="button" class="mini sec" data-ver-version="${esc(v.nombre)}">▶ Ver</button>
            <a class="boton mini sec" href="/api/proyectos/${p.id}/versiones/${esc(v.nombre)}"
               download="${esc(v.nombre)}">⬇</a>
            <button type="button" class="mini peligro" data-borrar-version="${esc(v.nombre)}">🗑</button>
          </div>`).join("")}
      </div>
    </details>`;
}

// ---------- vista: detalle de proyecto ----------
async function renderProyecto(id) {
  const p = await api(`/proyectos/${id}`);
  const ocupado = p.jobs_activos > 0;
  window.__escenas = p.escenas; // lo consulta el visor para etiquetar el clip
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

  // Visor: se atiende antes que nada porque vive fuera del panel
  if (b.id === "visor" || b.id === "visor-cerrar") return cerrarVisor();
  if (b.dataset?.verImg !== undefined && b.dataset.verImg !== "") {
    const o = +b.dataset.verImg;
    return abrirVisor(
      `<img src="/api/proyectos/${pid()}/imagenes/${o}?v=${Date.now()}">`,
      `Escena ${o + 1} · imagen`);
  }
  if (b.dataset?.verClip) {
    const o = +b.dataset.verClip;
    const e = (window.__escenas || []).find((x) => x.orden === o) || {};
    return abrirVisor(
      // muted: los clips no llevan audio (se generan con -an) y sin ello el
      // navegador bloquea el autoplay.
      `<video src="/api/proyectos/${pid()}/clips/${o}?v=${Date.now()}"
              controls autoplay loop muted playsinline></video>`,
      `Escena ${o + 1} · clip ${NOMBRE_MODO[e.clip_modo] || ""}`.trim());
  }

  // Borrados: van antes de la navegación porque el botón vive dentro del <li>
  if (b.dataset?.borrarTema) {
    if (!confirm(`¿Borrar el tema «${b.dataset.texto}» y todas sus ideas?\n\n` +
                 `Esto no se puede deshacer.`)) return;
    try {
      const r = await api(`/temas/${b.dataset.borrarTema}`, { method: "DELETE" });
      if (vista?.tipo === "tema" && vista.id === +b.dataset.borrarTema) {
        vista = null;
        panel.innerHTML = `<p class="vacio">Tema borrado (${r.ideas} ideas).</p>`;
      }
      cargarListas();
    } catch (e) {
      alert(String(e.message || e));
    }
    return;
  }

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
    } else if (b.id === "crear-voz") {
      const nombre = $("#voz-nombre").value.trim();
      const instruct = $("#voz-instruct").value.trim();
      if (!nombre || !instruct) return;
      await api("/voces", { method: "POST", body: { nombre, instruct } });
      b.textContent = "Creando voz…"; b.disabled = true;
      refrescarJobs();
    } else if (b.id === "clonar-voz") {
      const nombre = $("#voz-nombre").value.trim();
      const archivo = $("#voz-audio").files[0];
      if (!nombre || !archivo) return;
      const fd = new FormData();
      fd.append("nombre", nombre);
      fd.append("audio", archivo);
      fd.append("descripcion", $("#voz-descripcion").value.trim());
      const sel = window.__clipSel;
      if (sel) { fd.append("inicio", sel.inicio); fd.append("fin", sel.fin); }
      b.textContent = "Subiendo…"; b.disabled = true;
      const r = await fetch("/api/voces/clonar", { method: "POST", body: fd });
      if (!r.ok) {
        alert((await r.text()).slice(0, 300));
        b.textContent = "Clonar voz del audio"; b.disabled = false;
        return;
      }
      b.textContent = "Clonando voz…";
      refrescarJobs();
    } else if (b.classList?.contains("borrar-voz")) {
      if (!confirm(`¿Borrar la voz «${b.dataset.nombre}»?\n\n` +
                   `Los proyectos que la usaban quedarán sin voz seleccionada.`)) return;
      await api(`/voces/${b.dataset.slug}`, { method: "DELETE" });
      voces = await api("/voces");
      cargarListas();
      renderVista();
    } else if (b.id === "marcar-inicio") {
      const a = $("#clip-preview"), s = window.__clipSel; if (!s) return;
      s.inicio = Math.max(0, a.currentTime);
      if (s.fin <= s.inicio) s.fin = Math.min(s.dur, s.inicio + MAX_CLIP_S);
      if (s.fin - s.inicio > MAX_CLIP_S) s.fin = s.inicio + MAX_CLIP_S;
      actualizarClipInfo();
    } else if (b.id === "marcar-fin") {
      const a = $("#clip-preview"), s = window.__clipSel; if (!s) return;
      s.fin = Math.min(Math.max(a.currentTime, s.inicio + 0.5), s.inicio + MAX_CLIP_S);
      actualizarClipInfo();
    } else if (b.id === "oir-seleccion") {
      const a = $("#clip-preview"), s = window.__clipSel; if (!s) return;
      a.currentTime = s.inicio; a.play();
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
    } else if (b.dataset?.regenImg || b.dataset?.regenImgSeed) {
      // Regenerar la imagen de una escena: con seed nuevo (otra distinta) o
      // con el mismo (solo cambia si se editó el prompt).
      const nuevoSeed = !!b.dataset.regenImg;
      const orden = +(b.dataset.regenImg ?? b.dataset.regenImgSeed);
      await guardarPrompts();
      await api(`/proyectos/${pid()}/escenas/${orden}/imagen`, {
        method: "POST", body: { nuevo_seed: nuevoSeed },
      });
      refrescarJobs(); renderVista();
    } else if (b.dataset?.regenClip) {
      const orden = +b.dataset.regenClip;
      const sel = document.querySelector(`.escena-modo[data-orden="${orden}"]`);
      await guardarPrompts();
      await guardarModos();
      await api(`/proyectos/${pid()}/escenas/${orden}/clip`, {
        method: "POST", body: { modo: sel ? sel.value : "" },
      });
      refrescarJobs(); renderVista();
    } else if (b.id === "ver-final") {
      abrirVisor(
        `<video src="/api/proyectos/${pid()}/video?v=${Date.now()}"
                controls autoplay playsinline></video>`, "Video final");
    } else if (b.dataset?.verVersion) {
      const n = b.dataset.verVersion;
      abrirVisor(
        `<video src="/api/proyectos/${pid()}/versiones/${n}" controls autoplay
                playsinline></video>`, n);
    } else if (b.dataset?.borrarVersion) {
      const n = b.dataset.borrarVersion;
      if (!confirm(`¿Borrar la versión ${n}?\n\nEsto no se puede deshacer.`)) return;
      await api(`/proyectos/${pid()}/versiones/${n}`, { method: "DELETE" });
      renderVista();
    } else if (b.id === "borrar-video") {
      const conVers = confirm(
        "¿Borrar el video final?\n\n" +
        "Aceptar: borra también las versiones anteriores.\n" +
        "Cancelar: te pregunto solo por el video final.");
      if (!conVers && !confirm("¿Borrar solo el video final?")) return;
      const r = await api(`/proyectos/${pid()}/video?con_versiones=${conVers}`,
                          { method: "DELETE" });
      alert(`Borrado: ${r.final} video final, ${r.versiones} versiones.`);
      renderVista();
    } else if (b.id === "borrar-proyecto") {
      const t = document.querySelector("#panel h2")?.textContent?.trim() || "";
      if (!confirm(`¿Borrar el proyecto «${t}» POR COMPLETO?\n\n` +
                   `Se pierden guion, voz, subtítulos, imágenes, clips y videos.\n` +
                   `Esto no se puede deshacer.`)) return;
      if (!confirm("Confirma otra vez: se borra la carpeta entera del proyecto.")) return;
      try {
        const r = await api(`/proyectos/${pid()}`, { method: "DELETE" });
        vista = null;
        panel.innerHTML = `<p class="vacio">Proyecto «${esc(r.slug)}» borrado
                           (${r.archivos} archivos).</p>`;
        cargarListas();
      } catch (e) {
        alert(String(e.message || e));
      }
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
  } else if (ev.target.name === "voz-modo") {
    const clon = ev.target.value === "clon";
    $("#voz-campos-design").style.display = clon ? "none" : "";
    $("#voz-campos-clon").style.display = clon ? "" : "none";
  } else if (ev.target.id === "voz-audio") {
    seleccionarClip(ev.target.files[0]);
  } else if (ev.target.id === "modo-todas") {
    // Atajo: poner el mismo modo en todas las escenas, sin perder el control
    // fino de cada una (que sigue editable después).
    const modo = ev.target.value;
    if (!modo) return;
    document.querySelectorAll(".escena-modo").forEach((s) => { s.value = modo; });
    ev.target.value = "";
    await guardarModos();
  } else if (ev.target.classList?.contains("escena-modo")) {
    await guardarModos();
  }
});

async function guardarModos() {
  const escenas = [...document.querySelectorAll(".escena-modo")].map((s) => ({
    orden: +s.dataset.orden, modo: s.value,
  }));
  if (escenas.length) {
    await api(`/proyectos/${pid()}/escenas/modos`, { method: "PUT", body: { escenas } });
  }
}

async function guardarPrompts() {
  const escenas = [...document.querySelectorAll(".escena-prompt")].map((t) => {
    const orden = +t.dataset.orden;
    const mov = document.querySelector(`.escena-movimiento[data-orden="${orden}"]`);
    return { orden, prompt: t.value.trim(), prompt_movimiento: mov ? mov.value.trim() : null };
  });
  await api(`/proyectos/${pid()}/escenas`, { method: "PUT", body: { escenas } });
}

document.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    if (ev.target.id === "form-guion") {
      const narracionEl = $("#g-narracion");
      let body;
      if (narracionEl) {
        body = {
          gancho: $("#g-gancho").value.trim(),
          narracion: narracionEl.value.trim(),
          cta: $("#g-cta").value.trim(),
        };
      } else {
        const frases = [...document.querySelectorAll("#g-frases input")]
          .map((i) => i.value.trim()).filter(Boolean);
        body = { gancho: $("#g-gancho").value.trim(), frases, cta: $("#g-cta").value.trim() };
      }
      await api(`/proyectos/${pid()}/guion`, { method: "PUT", body });
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
  await cargarModelosLLM();
  $("#llm-modelo").addEventListener("change", async (ev) => {
    await api("/llm/modelo", { method: "POST", body: { id: ev.target.value } });
    refrescarSalud();
  });
  refrescarSalud();
  refrescarJobs();
  setInterval(refrescarSalud, 15000);
  setInterval(refrescarJobs, 2500);
})();
