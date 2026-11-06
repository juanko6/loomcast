#!/usr/bin/env bash
# Levanta Loomcast entero en una sola terminal: ComfyUI + backend, con los logs
# de ambos entremezclados y prefijados. Ctrl+C lo para todo de forma ordenada.
#
# Si el backend muere (el caso real: el OOM del kernel), se relanza solo hasta
# tres veces y ComfyUI se queda en pie, que es lo que cuesta minutos levantar.
#
#   scripts/run-loomcast.sh              ComfyUI + backend; UI en 127.0.0.1:8700
#   scripts/run-loomcast.sh --lan        igual, pero accesible desde la red local
#   scripts/run-loomcast.sh --dev        añade Astro en 4321 con recarga en caliente
#   scripts/run-loomcast.sh --sin-comfy  solo el backend (ComfyUI lo llevas tú aparte)
#
# El frontend no es un proceso: uvicorn sirve el build de web/dist/, así que el
# script lo recompila solo si hay fuentes más nuevas que el build. Con --dev sí
# arranca Astro, y entonces la UI buena es la de 4321.
#
# El llama-server tampoco se arranca aquí: lo gestiona Loomcast según config.toml.

set -euo pipefail
set -m   # cada servicio en su propio grupo de procesos, para pararlo con sus hijos

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

COMFY_DIR="${COMFY_DIR:-$HOME/Documents/ComfyUI}"
PUERTO_BACK=8700
PUERTO_COMFY=8188
PUERTO_WEB=4321
HOST=127.0.0.1
DEV=0
CON_COMFY=1

while [ $# -gt 0 ]; do
  case "$1" in
    --lan)       HOST=0.0.0.0 ;;
    --dev)       DEV=1 ;;
    --sin-comfy) CON_COMFY=0 ;;
    -h|--help|--ayuda)
      # Hasta la última línea de la cabecera: con un rango fijo, tocar el
      # comentario de arriba acaba imprimiendo código.
      sed -n '2,/^$/p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1 (prueba --ayuda)" >&2; exit 2 ;;
  esac
  shift
done

if [ -t 1 ]; then
  ROJO=$'\033[31m'; VERDE=$'\033[32m'; AMAR=$'\033[33m'
  AZUL=$'\033[34m'; MAGENTA=$'\033[35m'; CIAN=$'\033[36m'
  GRIS=$'\033[90m'; NEGRITA=$'\033[1m'; FIN=$'\033[0m'
else
  ROJO=""; VERDE=""; AMAR=""; AZUL=""; MAGENTA=""; CIAN=""; GRIS=""; NEGRITA=""; FIN=""
fi

mkdir -p "$RAIZ/logs"
PIDS=()
NOMBRES=()

escucha() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Lanza un servicio en segundo plano y deja su pid en PID_NUEVO. Su salida va al
# log sin colores y a la pantalla con un prefijo de color, línea a línea
# (awk + fflush: los pipes se bufferizan y si no, los logs llegarían a bloques
# de 4 KB).
#
# Al relanzar el backend el log NO se vacía: la traza de la muerte anterior es
# justo lo que hace falta para entender por qué se reinició.
CONSERVAR_LOG=0
lanzar() {
  local nombre="$1" color="$2"; shift 2
  local log="$RAIZ/logs/$nombre.log"
  [ "$CONSERVAR_LOG" -eq 1 ] || : > "$log"
  { "$@" 2>&1 | tee -a "$log" \
      | awk -v p="${color}[${nombre}]${FIN} " '{ print p $0; fflush() }'; } &
  PID_NUEVO=$!
  echo "${GRIS}→ $nombre arrancando (log: logs/$nombre.log)${FIN}"
}

# Lo mismo, apuntándolo en la lista de servicios vigilados.
arrancar() {
  lanzar "$@"
  PIDS+=("$PID_NUEVO")
  NOMBRES+=("$1")
}

limpiar() {
  trap - EXIT; trap '' INT TERM
  echo; echo "${GRIS}Parando servicios…${FIN}"
  local i pid
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    pid="${PIDS[$i]}"
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  # Margen para el apagado ordenado: el lifespan del backend apaga el
  # llama-server, y matarlo a lo bruto dejaría varios GB de RAM ocupados.
  for _ in $(seq 15); do
    local vivos=0
    for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null && vivos=1; done
    [ "$vivos" -eq 0 ] && break
    sleep 1
  done
  for pid in "${PIDS[@]}"; do kill -KILL "-$pid" 2>/dev/null || true; done
  parar_llm_huerfano
  echo "${GRIS}Listo.${FIN}"
}

# El backend apaga su LLM al cerrarse, pero si no le llega el TERM —o muere
# antes— el LLM se queda: lo arrancó con grupo propio para poder matarle los
# hijos, y ese grupo no cae con nosotros. Queda huérfano (ppid 1) con sus GiB
# dentro, y el Ctrl+C dejaba 22 GiB ocupados sin que nada lo dijera.
#
# Se remata **solo lo que el backend registró** en logs/llm.pid: ahí escribe el
# pgid del servidor que levantó él. Un llama-server o un mlx_lm que hayas
# arrancado tú por tu cuenta no está en ese fichero y no se toca, que para eso
# existen los modelos sin `comando` en config.toml.
parar_llm_huerfano() {
  local pidfile="$RAIZ/logs/llm.pid" pgid
  [ -f "$pidfile" ] || return 0
  pgid="$(sed -n 's/.*"pgid"[[:space:]]*:[[:space:]]*\([0-9]\{1,\}\).*/\1/p' "$pidfile")"
  if [ -n "$pgid" ] && kill -0 "-$pgid" 2>/dev/null; then
    echo "${GRIS}Parando el LLM que levantó el backend (pgid $pgid)…${FIN}"
    kill -TERM "-$pgid" 2>/dev/null || true
    for _ in $(seq 10); do
      kill -0 "-$pgid" 2>/dev/null || break
      sleep 1
    done
    kill -KILL "-$pgid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}
trap 'limpiar; exit 0' INT TERM
trap limpiar EXIT

# El cuarto argumento es opcional: el pid del servicio. Con él, esperar deja de
# esperar en cuanto el proceso muere, en vez de agotar el límite contra algo que
# ya no existe. Importa en el reinicio del backend: un error de import muere al
# instante, y sin esto cada intento se llevaría el minuto entero del límite.
esperar() {
  local nombre="$1" url="$2" limite="$3" pid="${4:-}" i=0
  while [ "$i" -lt "$limite" ]; do
    if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
      echo "${VERDE}✓${FIN} $nombre responde"
      return 0
    fi
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      echo "${ROJO}✗${FIN} $nombre murió al arrancar — revisa sus líneas de arriba"
      return 1
    fi
    sleep 1; i=$((i + 1))
  done
  echo "${AMAR}!${FIN} $nombre no respondió en ${limite}s — revisa sus líneas de arriba"
  return 1
}

# ---------------------------------------------------------------- frontend
if [ "$DEV" -eq 0 ]; then
  if [ ! -f web/dist/index.html ] \
     || [ -n "$(find web/src web/astro.config.mjs web/package.json \
                     -newer web/dist/index.html 2>/dev/null)" ]; then
    echo "${NEGRITA}Compilando el frontend${FIN} ${GRIS}(hay fuentes más nuevas que el build)${FIN}"
    pnpm --dir "$RAIZ/web" build
  else
    echo "${GRIS}Frontend al día, no recompilo.${FIN}"
  fi
fi

# ---------------------------------------------------------------- ComfyUI
# A ComfyUI **no** se le ponen los topes del asignador de MPS que el backend se
# pone a sí mismo (`[voz].mps_tope`), y está medido el 2026-11-05 generando tres
# veces la misma pista de 300 s:
#
#   sin topes        36,1 GiB libres al empezar → 11,9 GiB al swap, pista OK
#   0,90 / 0,75      35,7 GiB libres            →  9,0 GiB al swap, pista OK
#   0,75 / 0,60      38,8 GiB libres            → falla: [VAEDecodeAudio] MPS
#                                                 backend out of memory
#
# O sea: en el backend el pico era el asignador cacheando y el tope lo dejaba
# plano; aquí el pico son activaciones de verdad —`VAEDecodeAudio` necesita unos
# 26 GiB para cinco minutos de audio—, así que el techo no quita el swap, solo
# lo convierte en un fallo. Los 2,9 GiB que ahorra el 0,90 no compran bastante
# para arriesgarse a tumbar un i2v a 768×1376 o un Qwen-Edit con referencias,
# que no están medidos con techo.
#
# Si quieres probarlos, se exportan a mano antes de lanzar:
#   PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.90 scripts/run-loomcast.sh

if [ "$CON_COMFY" -eq 1 ]; then
  if escucha "$PUERTO_COMFY"; then
    echo "${GRIS}ComfyUI ya escucha en $PUERTO_COMFY, lo reutilizo.${FIN}"
    CON_COMFY=0
  elif [ -x "$COMFY_DIR/venv/bin/python" ]; then
    # Su propio intérprete, no comfy-cli: 'comfy launch' usa el python del shell
    # actual y revienta con ModuleNotFoundError (sqlalchemy y compañía viven en
    # el venv de ComfyUI). main.py acepta los flags del Manager por su cuenta.
    arrancar comfy "$MAGENTA" bash -c \
      "cd '$COMFY_DIR/ComfyUI' && exec '$COMFY_DIR/venv/bin/python' main.py \
       --enable-manager --enable-manager-legacy-ui --gpu-only"
  elif command -v comfy >/dev/null 2>&1; then
    # Sin venv a la vista: que lo intente comfy-cli.
    arrancar comfy "$MAGENTA" \
      comfy launch -- --enable-manager --enable-manager-legacy-ui --gpu-only
  else
    echo "${ROJO}No encuentro ComfyUI${FIN} (ni $COMFY_DIR/venv ni 'comfy' en el PATH)." >&2
    exit 1
  fi
  [ "$CON_COMFY" -eq 1 ] && esperar ComfyUI "http://127.0.0.1:$PUERTO_COMFY/system_stats" 180 || true
fi

# ---------------------------------------------------------------- backend
if escucha "$PUERTO_BACK"; then
  echo "${ROJO}El puerto $PUERTO_BACK ya está ocupado.${FIN} ¿Tienes otro Loomcast abierto?" >&2
  exit 1
fi
# En una función porque el vigilante la repite tal cual al relanzarlo.
backend_cmd() {
  lanzar loomcast "$CIAN" \
    env PYTHONUNBUFFERED=1 "$RAIZ/.venv/bin/uvicorn" backend.main:app \
        --host "$HOST" --port "$PUERTO_BACK"
}
backend_cmd
PIDS+=("$PID_NUEVO"); NOMBRES+=("loomcast")
IDX_BACK=$(( ${#PIDS[@]} - 1 ))
esperar Loomcast "http://127.0.0.1:$PUERTO_BACK/api/salud" 60 "$PID_NUEVO" || true

# ---------------------------------------------------------------- astro dev
if [ "$DEV" -eq 1 ]; then
  if [ "$HOST" = "0.0.0.0" ]; then
    arrancar web "$AZUL" pnpm --dir "$RAIZ/web" dev --host 0.0.0.0
  else
    arrancar web "$AZUL" pnpm --dir "$RAIZ/web" dev
  fi
  esperar Astro "http://localhost:$PUERTO_WEB/" 60 || true
fi

# ---------------------------------------------------------------- resumen
PUERTO_UI=$PUERTO_BACK
HOST_UI=127.0.0.1
# Astro escucha en localhost (::1), no en 127.0.0.1: con la IP no responde.
if [ "$DEV" -eq 1 ]; then PUERTO_UI=$PUERTO_WEB; HOST_UI=localhost; fi

echo
echo "${NEGRITA}  Loomcast en marcha${FIN}"
echo "  ${GRIS}·${FIN} UI           http://$HOST_UI:$PUERTO_UI"
if [ "$HOST" = "0.0.0.0" ]; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  [ -n "$IP" ] && echo "  ${GRIS}·${FIN} desde la red http://$IP:$PUERTO_UI  ${AMAR}(sin contraseña: solo en red de confianza)${FIN}"
fi
echo "  ${GRIS}·${FIN} ComfyUI      http://127.0.0.1:$PUERTO_COMFY"
echo "  ${GRIS}·${FIN} logs         $RAIZ/logs/"

# Sin los parches de MPS la música falla en pistas de más de ~33 s y Qwen-Image-Edit
# revienta en cuanto lleva una referencia. Los dos fallos aparecen a mitad de
# generación, no al arrancar, así que mejor avisar aquí.
if [ -f "$RAIZ/logs/comfy.log" ] && ! grep -q "\[loomcast\] Parche" "$RAIZ/logs/comfy.log"; then
  echo "  ${AMAR}!${FIN} no veo el parche MPS en el arranque de ComfyUI:"
  echo "    ${GRIS}./.venv/bin/python scripts/instalar_parches.py${FIN}"
fi
echo
echo "${GRIS}  Ctrl+C para parar todo.${FIN}"
echo

# ---------------------------------------------------------------- vigilancia
# El backend se relanza solo; los demás servicios siguen cerrando todo.
#
# Por qué la diferencia: el backend es lo que muere de verdad. El 2026-10-19 se
# lo llevó el OOM del kernel (`Killed: 9`, sin traza) por lanzar un LLM de
# ~20 GiB mientras ComfyUI retenía los suyos, y cerrarlo todo obligaba a volver
# a levantar ComfyUI y a recargar un modelo de 20 GiB desde disco: minutos por
# una caída que se arregla en segundos. ComfyUI y el llama-server se quedan en
# pie, y el backend vuelve con la cola intacta (`recuperar_pendientes()`
# re-encola lo que quedó a medias).
#
# ComfyUI y Astro mantienen el comportamiento de antes —si uno cae, se cierra
# todo— porque sin ellos no hay nada que relanzar en su sitio: ComfyUI lo
# arranca este script una sola vez y cada intento vuelve a pagar su arranque, y
# un Astro caído solo pasa cuando lo has parado tú.
#
# El llama-server no lo gestiona este script: lo arranca y lo para el backend
# según config.toml. Al volver, `_reclamar_huerfano()` descarga el que dejó la
# ejecución muerta — y eso es lo correcto justo aquí: si el backend murió por
# falta de memoria, esos GB son el problema, no algo que convenga conservar.
MAX_REINICIOS=3
ESPERA_REINICIO_S=5
# Si aguanta esto en pie, el reinicio contó como bueno y la cuenta vuelve a
# cero: una caída cada varias horas no debe agotar los reintentos de la sesión.
ESTABLE_S=300

reinicios=0
arranque_back=$SECONDS

relanzar_backend() {
  local motivo="$1"
  # Avisa en su propio log, al lado de la traza (si la hubo: un SIGKILL del
  # kernel no deja ninguna, y entonces esta línea es todo lo que queda).
  {
    echo
    echo "[lanzador] el backend se reinicia: $motivo"
    echo "[lanzador] reinicio $reinicios de $MAX_REINICIOS; ComfyUI y el LLM siguen en pie"
  } >> "$RAIZ/logs/loomcast.log"
  echo "${ROJO}✗ el backend se ha parado${FIN} ($motivo) — lo relanzo" \
       "${GRIS}(reinicio $reinicios de $MAX_REINICIOS; ComfyUI sigue en pie)${FIN}"
  sleep "$ESPERA_REINICIO_S"
  # El uvicorn muerto puede tardar en soltar el puerto; sin esto el nuevo
  # arrancaría para morir con "address already in use".
  local i=0
  while escucha "$PUERTO_BACK" && [ "$i" -lt 15 ]; do sleep 1; i=$((i + 1)); done
  CONSERVAR_LOG=1; backend_cmd; CONSERVAR_LOG=0
  PIDS[$IDX_BACK]=$PID_NUEVO
  arranque_back=$SECONDS
  esperar Loomcast "http://127.0.0.1:$PUERTO_BACK/api/salud" 60 "$PID_NUEVO" || true
}

while true; do
  for i in "${!PIDS[@]}"; do
    # El `if` y no un `&& continue`: con `set -e`, un `&&` cuyo primer comando
    # falla deja el estado de la lista en no-cero y eso es pisar una mina.
    if kill -0 "${PIDS[$i]}" 2>/dev/null; then
      continue
    fi
    if [ "$i" -ne "$IDX_BACK" ]; then
      echo "${ROJO}✗ ${NOMBRES[$i]} se ha parado${FIN} — cierro el resto."
      exit 1
    fi
    # Llevaba un buen rato en pie: esta caída no es la misma racha.
    if [ $(( SECONDS - arranque_back )) -ge "$ESTABLE_S" ]; then
      reinicios=0
    fi
    if [ "$reinicios" -ge "$MAX_REINICIOS" ]; then
      # El tope es lo que evita el bucle infinito cuando no es una caída sino
      # que no arranca: un error de import muere igual de rápido las tres veces.
      echo "${ROJO}✗ el backend ha muerto $((reinicios + 1)) veces${FIN} — no lo relanzo más."
      echo "  ${GRIS}Mira logs/loomcast.log: si no es una caída sino que no arranca," \
           "el error está en sus últimas líneas.${FIN}"
      exit 1
    fi
    reinicios=$((reinicios + 1))
    relanzar_backend "murió tras $(( SECONDS - arranque_back ))s en pie"
  done
  sleep 2
done
