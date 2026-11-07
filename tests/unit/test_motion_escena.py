"""La composición que se dibuja en una escena de motion.

Aquí no se prueba que el dibujo sea bonito —eso se mira— sino las tres cosas
que, si fallan, hacen un vídeo roto sin que nadie se entere hasta verlo: que
las piezas no se pisen, que quepan en el cuadro, y que dos renders del mismo
clip salgan idénticos. Lo último es lo que permite rehacer una escena suelta
sin que cambie el resto del vídeo.
"""
from PIL import Image, ImageDraw

from backend.services.pipeline import _motion_bloques as bloques
from backend.services.pipeline._motion_escena import Escenario, camara
from backend.services.pipeline._motion_lienzo import (ALTO_LIENZO, ANCHO_LIENZO,
                                                      FONDO)


def pieza(pid, tipo="caja", nombre="", ranuras=0, llenas=0, estado="normal"):
    return {"id": pid, "tipo": tipo, "nombre": nombre or pid.upper(),
            "ranuras": ranuras, "llenas": llenas, "estado": estado}


CADENA = {
    "fondo": "negro",
    "piezas": [pieza("cpu", "chip", "Procesador"),
               pieza("l1", "banco", "Caché L1", 4, 2, "veloz"),
               pieza("ram", "banco", "RAM", 8, 8, "lento")],
    "vinculos": [{"de": "cpu", "a": "l1", "coste": "corto"},
                 {"de": "l1", "a": "ram", "coste": "largo"}],
    "animacion": {"tipo": "flujo", "de": "cpu", "a": "l1", "en": ""},
    "foco": "l1",
}


def _pintar(comp, nombre="general", t=1.5, dur=4.0, p=0.5):
    esc = Escenario(comp, dur)
    im = Image.new("RGB", (ANCHO_LIENZO // 2, ALTO_LIENZO // 2), FONDO)
    esc.pintar(ImageDraw.Draw(im), camara(nombre, esc, p), t, 1)
    return im


def _sin_pintar(im, caja) -> bool:
    """Ahí no hay nada dibujado: solo el fondo. No vale `getbbox`, que busca
    píxeles distintos de negro y el fondo de la marca no es negro puro."""
    colores = im.crop(caja).getcolors(maxcolors=4)
    return colores is not None and {c for _, c in colores} == {FONDO}


# --- la colocación ----------------------------------------------------------

def test_lo_que_cuelga_de_algo_va_debajo():
    esc = Escenario(CADENA)
    assert esc.piezas["cpu"]["y"] < esc.piezas["l1"]["y"] < esc.piezas["ram"]["y"]


def test_un_vinculo_largo_abre_mas_hueco_que_uno_corto():
    """El coste no es una etiqueta: es la distancia que se ve en pantalla."""
    esc = Escenario(CADENA)
    cpu, l1, ram = (esc.piezas[i] for i in ("cpu", "l1", "ram"))
    corto = l1["y"] - (cpu["y"] + cpu["h"])
    largo = ram["y"] - (l1["y"] + l1["h"])
    assert largo > corto * 2


def test_lo_que_no_cuelga_de_nada_va_al_lado():
    esc = Escenario({"piezas": [pieza("a"), pieza("b")], "vinculos": [],
                     "animacion": {"tipo": "nada"}, "foco": "a"})
    assert esc.piezas["a"]["y"] == esc.piezas["b"]["y"]
    assert esc.piezas["a"]["x"] != esc.piezas["b"]["x"]


def test_las_piezas_nunca_se_pisan():
    comp = {
        "piezas": [pieza("a", "chip"), pieza("b", "banco", ranuras=6),
                   pieza("c", "disco"), pieza("d", "nodo"), pieza("e")],
        "vinculos": [{"de": "a", "a": "b", "coste": "corto"},
                     {"de": "a", "a": "c", "coste": "corto"},
                     {"de": "b", "a": "d", "coste": "medio"},
                     {"de": "c", "a": "e", "coste": "largo"}],
        "animacion": {"tipo": "nada"}, "foco": "a",
    }
    cajas = [(p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"])
             for p in Escenario(comp).piezas.values()]
    for i, a in enumerate(cajas):
        for b in cajas[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_la_escena_entera_cabe_en_el_cuadro():
    esc = Escenario(CADENA)
    cam = camara("general", esc, 1.0)
    for x, y in ((0, 0), (esc.ancho, esc.alto)):
        px, py = esc.proyectar(cam, x, y)
        assert -1 <= px <= ANCHO_LIENZO + 1
        assert -1 <= py <= ALTO_LIENZO + 1


def test_un_ciclo_de_vinculos_no_cuelga_la_colocacion():
    """Si el modelo conecta A→B y B→A no hay filas que deducir. Sale apretado,
    pero sale: lo que no puede es quedarse dando vueltas."""
    comp = {"piezas": [pieza("a"), pieza("b")],
            "vinculos": [{"de": "a", "a": "b", "coste": "corto"},
                         {"de": "b", "a": "a", "coste": "corto"}],
            "animacion": {"tipo": "nada"}, "foco": "a"}
    assert Escenario(comp).ancho > 0


# --- la cámara y el ancla ---------------------------------------------------

def test_el_foco_cae_en_el_centro_cuando_la_camara_se_acerca():
    esc = Escenario(CADENA)
    cam = camara("cruce", esc, 0.0)
    x, y = esc.proyectar(cam, *esc.centro("l1"))
    assert abs(x - ANCHO_LIENZO / 2) < 2 and abs(y - ALTO_LIENZO / 2) < 2


def test_acercarse_es_acercarse():
    esc = Escenario(CADENA)
    assert camara("entrada", esc, 1.0)["z"] > camara("entrada", esc, 0.0)["z"]
    assert camara("salida", esc, 1.0)["z"] < camara("salida", esc, 0.0)["z"]


def test_el_ancla_de_la_pildora_no_cae_encima_del_nombre():
    esc = Escenario(CADENA)
    assert esc.ancla("l1", borde=True)[0] > esc.ancla("l1")[0]


def test_el_ancla_se_mueve_con_la_camara():
    esc = Escenario(CADENA)
    cam = camara("cruce", esc, 0.0)
    quieta = esc.proyectar(cam, *esc.ancla("l1"))
    movida = esc.proyectar({**cam, "x": cam["x"] + 200}, *esc.ancla("l1"))
    assert movida[0] < quieta[0]


# --- el dibujo --------------------------------------------------------------

def test_el_mismo_cuadro_se_dibuja_igual_dos_veces():
    assert _pintar(CADENA).tobytes() == _pintar(CADENA).tobytes()


def test_lo_que_se_anima_cambia_con_el_tiempo():
    assert _pintar(CADENA, t=0.2).tobytes() != _pintar(CADENA, t=1.9).tobytes()


def test_una_escena_sin_piezas_no_tumba_el_dibujo():
    vacia = {"piezas": [], "vinculos": [], "animacion": {"tipo": "nada"},
             "foco": "", "fondo": "negro"}
    im = _pintar(vacia)
    assert _sin_pintar(im, (0, 0, im.width, im.height))


def test_llenar_va_ocupando_ranuras_durante_la_escena():
    comp = {**CADENA, "animacion": {"tipo": "llenar", "en": "l1", "de": "ram"}}
    esc = Escenario(comp, dur=4.0)
    assert esc._llenas("l1", 0.0) < esc._llenas("l1", 4.0)
    assert esc._llenas("l1", 4.0) == esc.piezas["l1"]["ranuras"]


def test_un_banco_lleno_se_ve_lleno_y_uno_vacio_vacio():
    lleno = Escenario({**CADENA, "piezas": [pieza("x", "banco", ranuras=5,
                                                  estado="lleno")]})
    vacio = Escenario({**CADENA, "piezas": [pieza("x", "banco", ranuras=5,
                                                  llenas=5, estado="vacio")]})
    assert lleno._llenas("x", 0.0) == 5 and vacio._llenas("x", 0.0) == 0


# --- con la anotación encima ------------------------------------------------

def _con_tarjeta(comp, ficha, t=1.2):
    esc = Escenario(comp, 4.0)
    cam = camara(ficha["camara"], esc, 0.5)
    im = Image.new("RGB", (ANCHO_LIENZO, ALTO_LIENZO), FONDO)
    esc.pintar(ImageDraw.Draw(im), cam, t, 1)
    bloques.dibujar(im, {**ficha, "ancla": esc.ancla(esc.foco)}, esc, cam, t, 1)
    return im


def test_el_titular_se_lee_sobre_el_esquema():
    """El plato de detrás del texto no es estética: un titular cruzado por una
    caja de memoria no se lee, y con el esquema debajo pasa siempre."""
    ficha = {"bloque": "TITULAR", "banda": "centro", "camara": "general",
             "texto": "El chip evita la memoria lenta", "apoyo": "",
             "enfasis": ["evita"]}
    im = _con_tarjeta(CADENA, ficha)
    fondo = _pintar(CADENA, "general", t=1.2).resize((ANCHO_LIENZO, ALTO_LIENZO))
    # Donde va el texto, lo que había debajo tiene que haberse apagado.
    franja = (200, 820, 880, 980)
    assert im.crop(franja).tobytes() != fondo.crop(franja).tobytes()


def test_la_tarjeta_no_toca_el_borde_derecho():
    ficha = {"bloque": "TITULAR", "banda": "arriba", "camara": "general",
             "texto": "Una frase larga que podría salirse por la derecha",
             "apoyo": "", "enfasis": []}
    im = _con_tarjeta(CADENA, ficha)
    assert _sin_pintar(im, (im.width - 8, 0, im.width, im.height))


# --- dónde cae cada bloque --------------------------------------------------

class _Fijo:
    """Un mundo en el que el ancla ya está en coordenadas de pantalla."""

    def proyectar(self, cam, x, y, s=1):
        return (x, y)


def _anotar(ficha, ancla):
    im = Image.new("RGB", (ANCHO_LIENZO, ALTO_LIENZO), FONDO)
    bloques.dibujar(im, {**ficha, "ancla": ancla}, _Fijo(),
                    {"z": 1.0, "rot": 0.0, "x": 0, "y": 0}, 2.0, 1)
    return im


def _pintados(im, caja) -> int:
    return sum(n for n, c in im.crop(caja).getcolors(maxcolors=1 << 20)
               if c != FONDO)


def test_la_banda_baja_esta_abajo_y_por_encima_del_titular():
    """`baja` es a donde huyen el círculo y la gráfica cuando lo que señalan
    está arriba, y tiene que acabar antes de donde empieza el titular."""
    alto = 200
    y = bloques._y_banda("baja", alto, 1)
    assert y > ALTO_LIENZO / 2
    assert y + alto <= bloques._y_banda("titular", 2 * 108, 1)


def test_el_titular_vive_abajo_y_no_se_sale_del_cuadro():
    alto = 2 * 108                   # dos líneas
    y = bloques._y_banda("titular", alto, 1)
    assert y > ALTO_LIENZO * 0.7
    assert y + alto <= ALTO_LIENZO


def test_la_etiqueta_del_circulo_huye_de_lo_que_rodea():
    ficha = {"bloque": "CIRCULO", "banda": "centro", "camara": "cruce",
             "texto": "aquí se busca primero", "apoyo": "4 bloques",
             "enfasis": []}
    arriba = (540, 320)
    abajo = (540, 1500)
    medio = ALTO_LIENZO // 2
    # Con el círculo arriba, la etiqueta se va abajo; y al revés.
    im = _anotar(ficha, arriba)
    assert _pintados(im, (0, medio, ANCHO_LIENZO, ALTO_LIENZO)) > \
        _pintados(im, (0, 0, ANCHO_LIENZO, 240))
    im = _anotar(ficha, abajo)
    assert _pintados(im, (0, 0, ANCHO_LIENZO, medio)) > \
        _pintados(im, (0, ALTO_LIENZO - 240, ANCHO_LIENZO, ALTO_LIENZO))


def test_el_plano_general_le_deja_sitio_a_la_tarjeta():
    """Con el rótulo arriba, la primera pieza no puede quedar debajo del texto:
    la cámara encuadra el esquema en lo que queda de pantalla."""
    esc = Escenario(CADENA)
    libre = camara("general", esc, 1.0, "arriba")
    pegado = camara("general", esc, 1.0)
    arriba_libre = esc.proyectar(libre, *esc.centro("cpu"))[1]
    arriba_pegado = esc.proyectar(pegado, *esc.centro("cpu"))[1]
    assert arriba_libre > arriba_pegado + 100
    # Y sin que se salga nada por abajo.
    assert esc.proyectar(libre, 0, esc.alto)[1] <= ALTO_LIENZO + 1


# --- las tres capas de texto ------------------------------------------------

def _capas(ficha, t=1.0):
    im = Image.new("RGB", (ANCHO_LIENZO, ALTO_LIENZO), FONDO)
    bloques.dibujar(im, {"bloque": "NADA", "banda": "centro", "texto": "",
                         "apoyo": "", "enfasis": [], "filas": [], "ancla": None,
                         **ficha}, _Fijo(),
                    {"z": 1.0, "rot": 0.0, "x": 0, "y": 0}, t, 1)
    return im


TITULARES = [{"texto": "nadie lo puede borrar", "enfasis": ["nadie"],
              "t0": 0.0, "t1": 2.0},
             {"texto": "y sigue ahí dentro", "enfasis": ["dentro"],
              "t0": 2.0, "t1": 4.0}]


def test_el_titular_se_releva_con_la_voz():
    """Dos frases, dos titulares: a los tres segundos ya no se lee el primero.
    Era el agujero del formato anterior, una tarjeta quieta nueve segundos."""
    primero = _capas({"titulares": TITULARES}, t=1.6)
    segundo = _capas({"titulares": TITULARES}, t=3.4)
    banda = (0, 1380, ANCHO_LIENZO, ALTO_LIENZO)
    assert _pintados(primero, banda) > 0 and _pintados(segundo, banda) > 0
    assert primero.crop(banda).tobytes() != segundo.crop(banda).tobytes()


def test_antes_del_primer_titular_no_hay_nada_escrito():
    """La escena empieza en el silencio que dejó la anterior: escribir ahí el
    titular lo adelantaría a lo que se está diciendo."""
    im = _capas({"titulares": [{"texto": "tarde", "enfasis": [], "t0": 1.2,
                                "t1": 3.0}]}, t=0.4)
    assert _pintados(im, (0, 1380, ANCHO_LIENZO, ALTO_LIENZO)) == 0


def test_el_titular_no_pisa_ni_la_chapa_ni_la_banda_del_bloque():
    im = _capas({"titulares": TITULARES, "chapa": "el problema"}, t=1.6)
    # La chapa arriba, el titular abajo, y la franja del medio libre para el
    # esquema y su bloque.
    assert _pintados(im, (0, 180, ANCHO_LIENZO, 300)) > 0
    assert _pintados(im, (0, 1440, ANCHO_LIENZO, ALTO_LIENZO)) > 0
    assert _pintados(im, (0, 400, ANCHO_LIENZO, 1200)) == 0


def test_sin_bloque_solo_se_escriben_chapa_y_titular():
    assert _pintados(_capas({"bloque": "NADA", "titulares": TITULARES}),
                     (0, 300, ANCHO_LIENZO, 1380)) == 0


def test_la_lista_dibuja_una_fila_por_cosa():
    una = _capas({"bloque": "LISTA", "filas": [{"texto": "la caché", "chapa": "rápida"},
                                               {"texto": "la RAM", "chapa": "lenta"}]},
                 t=3.0)
    ninguna = _capas({"bloque": "LISTA", "filas": []}, t=3.0)
    assert _pintados(una, (0, 700, ANCHO_LIENZO, 1200)) > 0
    assert _pintados(ninguna, (0, 700, ANCHO_LIENZO, 1200)) == 0


def test_el_ordinal_se_pega_al_margen_y_no_cruza_la_pantalla():
    im = _capas({"bloque": "ORDINAL", "banda": "arriba", "texto": "3"}, t=2.0)
    assert _pintados(im, (0, 300, ANCHO_LIENZO // 2, 800)) > 0
    assert _pintados(im, (ANCHO_LIENZO // 2 + 100, 300, ANCHO_LIENZO, 800)) == 0


# --- las ventanas -----------------------------------------------------------

VENTANA = {"fondo": "negro", "animacion": {"tipo": "teclear", "en": "sh"},
           "foco": "sh",
           "piezas": [{**pieza("sh", "terminal", "claude"),
                       "lineas": ["$ npx skills add obra", "instalado"]}]}


def _tinta(im) -> int:
    """Píxeles de texto. Contar lo que no es el fondo no sirve dentro de una
    ventana: el panel ya lo llena entero y la letra solo lo sustituye."""
    return sum(n for n, c in im.getcolors(maxcolors=1 << 20) if sum(c) > 300)


def test_el_terminal_se_escribe_solo():
    """Ver aparecer el comando es la mitad de lo que se está contando."""
    pronto = _pintar(VENTANA, "cruce", t=0.2, dur=4.0)
    tarde = _pintar(VENTANA, "cruce", t=3.6, dur=4.0)
    assert _tinta(tarde) > _tinta(pronto)


def test_una_ventana_sin_teclear_se_lee_entera_desde_el_primer_cuadro():
    quieta = {**VENTANA, "animacion": {"tipo": "nada"}}
    assert _tinta(_pintar(quieta, "cruce", t=0.1)) == \
        _tinta(_pintar(quieta, "cruce", t=3.9))


def test_dos_renders_de_una_ventana_salen_identicos():
    a = _pintar(VENTANA, "cruce", t=1.7)
    b = _pintar(VENTANA, "cruce", t=1.7)
    assert a.tobytes() == b.tobytes()


def _filas_con_tinta(im, caja) -> list[int]:
    recorte = im.crop(caja)
    ancho = recorte.width
    px = list(recorte.getdata())
    return [y for y in range(recorte.height)
            if any(sum(px[y * ancho + x]) > 300 for x in range(ancho))]


def test_todas_las_palabras_del_titular_comparten_base():
    """Cada palabra se dibujaba restándole **su** desplazamiento, que alinea
    los topes de tinta y no las bases: una palabra sin astas quedaba por
    encima de sus vecinas y la frase se leía rota. Y entraban una a una con su
    propio salto, así que durante la entrada estaban a cuatro alturas."""
    una = [{"texto": "y hay que ir a", "enfasis": ["hay"], "t0": 0.0, "t1": 2.4}]
    banda = (0, 1360, ANCHO_LIENZO, 1760)
    for t in (0.08, 0.14, 0.22, 0.4, 1.2, 2.0):
        filas = _filas_con_tinta(_capas({"titulares": una}, t=t), banda)
        assert filas, t
        # Una sola línea de texto: su tinta no puede ocupar más de lo que mide
        # una línea. Con cada palabra a su altura ocupaba casi el doble.
        assert filas[-1] - filas[0] <= 108, (t, filas[0], filas[-1])


def test_el_titular_de_dos_lineas_queda_centrado_en_las_dos():
    im = _capas({"titulares": [{"texto": "y hay que ir a buscarlo",
                                "enfasis": ["buscarlo"], "t0": 0.0, "t1": 3.0}]}, t=1.2)
    banda = (0, 1360, ANCHO_LIENZO, 1800)
    izq = _pintados(im, (0, 1360, ANCHO_LIENZO // 2, 1800))
    der = _pintados(im, (ANCHO_LIENZO // 2, 1360, ANCHO_LIENZO, 1800))
    assert _filas_con_tinta(im, banda)
    # Centrado de verdad: el hueco entre palabras con el que se dibuja es el
    # mismo con el que se mide, así que las dos mitades pesan casi igual.
    assert abs(izq - der) / max(izq, der) < 0.12
