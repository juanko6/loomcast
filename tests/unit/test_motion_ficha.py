"""La revisión de lo que el LLM escribe para una escena de motion.

Lo que se comprueba aquí no es que el modelo acierte —eso no se puede probar
sin el modelo— sino que lo que no acierta no llegue al vídeo: tarjetas que no
caben, cifras que no están en el guion, bloques repetidos y bandas pisadas.
"""
from backend.schemas import (AnimacionLLM, ComposicionLLM, FichaLLM, FilaLLM,
                              PiezaLLM, PlanoMotionLLM, TitularLLM, VinculoLLM)
from backend.services.pipeline import _motion_ficha as mf


def plano(accion: str, camara: str = "general", chapa: str = "") -> PlanoMotionLLM:
    return PlanoMotionLLM(camara=camara, accion=accion, chapa=chapa)


def tit(texto, *enfasis) -> TitularLLM:
    return TitularLLM(texto=texto, enfasis=list(enfasis))


def ficha(bloque="NADA", banda="centro", texto="", apoyo="", enfasis=(),
          titulares=None, filas=()) -> FichaLLM:
    if titulares is None:
        titulares = [tit("un titular corto", "titular"), tit("y otro distinto", "otro")]
    return FichaLLM(bloque=bloque, banda=banda, texto=texto, apoyo=apoyo,
                    enfasis=list(enfasis), titulares=list(titulares),
                    filas=[FilaLLM(**f) for f in filas])


SEGS = [{"texto": f"el texto narrado de la escena {i}",
         "frases": [{"texto": f"primera frase de la escena {i}", "t0": 0.0, "t1": 2.0},
                    {"texto": f"segunda frase de la escena {i}", "t0": 2.0, "t1": 4.4}]}
        for i in range(6)]


# --- cortar -----------------------------------------------------------------

def test_cortar_suelta_los_enlaces_del_final():
    assert mf.cortar("un fantasma digital en la red", 4) == "un fantasma digital"


def test_cortar_a_cero_palabras_deja_vacio():
    assert mf.cortar("lo que sea", 0) == ""


# --- revisar_planos ---------------------------------------------------------

def test_planos_sacan_el_bloque_de_la_accion():
    revisados, fallos = mf.revisar_planos(
        [plano("CIRCULO: el núcleo del sistema", "entrada")], 1, True)
    assert revisados[0]["bloque"] == "CIRCULO"
    assert revisados[0]["accion"] == "CIRCULO: el núcleo del sistema"
    assert not any(fallos.values())


def test_plano_sin_bloque_reconocible_recibe_uno_y_conserva_la_accion():
    revisados, fallos = mf.revisar_planos([plano("una vista del conjunto")], 1, True)
    assert revisados[0]["bloque"] in mf.ROTACION
    assert fallos["bloque"] == 1
    # Lo que escribió el modelo no se tira: es lo que señala el plano.
    assert "una vista del conjunto" in revisados[0]["accion"]


def test_cifra_sin_numeros_en_el_guion_se_apaga():
    revisados, fallos = mf.revisar_planos([plano("CIFRA: los años que lleva")], 1, False)
    assert revisados[0]["bloque"] == "NADA"
    assert fallos["cifra_sin_numeros"] == 1


def test_la_chapa_del_plano_llega_a_la_ficha():
    """La chapa la decide el storyboard porque es una cuenta del vídeo entero:
    una escena sola no sabe por qué parte va."""
    revisados, _ = mf.revisar_planos(
        [plano("NADA: x", chapa="lo que pasa dentro")], 1, True)
    assert revisados[0]["chapa"] == "lo que pasa dentro"
    revisadas, _ = mf.revisar_fichas([ficha()], revisados, SEGS, "")
    assert revisadas[0]["chapa"] == "lo que pasa dentro"


def test_bloque_repetido_rota_en_vez_de_hacer_pimpon():
    planos = [plano("CIRCULO: uno"), plano("CIRCULO: dos"), plano("CIRCULO: tres")]
    revisados, fallos = mf.revisar_planos(planos, 3, True)
    bloques = [r["bloque"] for r in revisados]
    assert bloques[0] == "CIRCULO"
    assert len(set(bloques)) == 3, bloques
    assert fallos["bloque_repetido"] == 2


def test_nada_puede_repetirse_porque_el_titular_ya_mueve_la_pantalla():
    planos = [plano("NADA: uno"), plano("NADA: dos"), plano("NADA: tres")]
    revisados, fallos = mf.revisar_planos(planos, 3, True)
    assert [r["bloque"] for r in revisados] == ["NADA"] * 3
    assert fallos["bloque_repetido"] == 0


def test_la_grafica_es_una_y_en_el_ultimo_tercio():
    planos = [plano("PILDORA: x") for _ in range(9)]
    revisados, _ = mf.revisar_planos(planos, 9, True)
    bloques = [r["bloque"] for r in revisados]
    assert bloques.count("GRAFICA") <= 1
    if "GRAFICA" in bloques:
        assert bloques.index("GRAFICA") >= 6


def test_camara_invalida_se_sustituye():
    revisados, fallos = mf.revisar_planos([plano("ROTULO: x", "dron")], 1, True)
    assert revisados[0]["camara"] in mf.CAMARAS
    assert fallos["camara"] == 1


def test_lo_que_se_senala_no_se_mira_de_lejos():
    revisados, _ = mf.revisar_planos([plano("CIRCULO: x", "general")], 1, True)
    assert revisados[0]["camara"] != "general"


# --- revisar_fichas ---------------------------------------------------------

def _planos(*bloques, camara="entrada", chapa=""):
    return [{"bloque": b, "camara": camara, "chapa": chapa} for b in bloques]


def test_ficha_que_no_respeta_su_bloque_se_cuenta_y_se_corrige():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="PILDORA", texto="el núcleo")], _planos("CIRCULO"),
        SEGS, "sin números")
    assert revisadas[0]["bloque"] == "CIRCULO"
    assert fallos["no_hizo_caso"] == 1


def test_texto_largo_se_corta_al_tope_del_bloque():
    larga = "una " * 20
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="PILDORA", texto=larga)], _planos("PILDORA"), SEGS, "")
    assert len(revisadas[0]["texto"].split()) <= mf.TOPE["PILDORA"][0]
    assert fallos["largas"] == 1


def test_cifra_que_no_esta_en_el_guion_no_se_publica():
    """Se apaga el bloque entero: el dato lo cuenta la voz, y el titular de esa
    frase ya lo lleva escrito."""
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="CIFRA", texto="9.000", apoyo="MILLONES")],
        _planos("CIFRA"), SEGS, "el guion habla de 12 servidores")
    assert revisadas[0]["bloque"] == "NADA"
    assert revisadas[0]["texto"] == ""
    assert fallos["cifra_inventada"] == 1


def test_cifra_que_si_esta_en_el_guion_se_queda():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="CIFRA", texto="12", apoyo="servidores")],
        _planos("CIFRA"), SEGS, "el guion habla de 12 servidores")
    assert revisadas[0]["bloque"] == "CIFRA"
    assert fallos["cifra_inventada"] == 0


def test_bloque_vacio_se_rellena_con_lo_que_se_narra():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="CIRCULO", texto="   ")], _planos("CIRCULO"), SEGS, "")
    assert revisadas[0]["texto"]
    assert fallos["vacia"] == 1


def test_dos_escenas_seguidas_no_comparten_banda():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="ROTULO", banda="arriba", texto="la caché"),
         ficha(bloque="PILDORA", banda="arriba", texto="la caché")],
        _planos("ROTULO", "PILDORA"), SEGS, "")
    assert revisadas[0]["banda"] != revisadas[1]["banda"]
    assert fallos["banda_repetida"] == 1


def test_una_escena_sin_bloque_no_reserva_banda_para_la_siguiente():
    """`NADA` no dibuja nada encima del esquema, así que no ocupa sitio y la
    escena de después puede usar la banda que le venga bien."""
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="ROTULO", banda="arriba", texto="la caché"),
         ficha(bloque="NADA"),
         ficha(bloque="PILDORA", banda="arriba", texto="la caché")],
        _planos("ROTULO", "NADA", "PILDORA"), SEGS, "")
    assert revisadas[2]["banda"] == "arriba"
    assert fallos["banda_repetida"] == 0


def test_enfasis_que_no_esta_en_el_texto_se_descarta():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="CIRCULO", texto="un error impide su eliminación",
               enfasis=["impide", "jamás"])],
        _planos("CIRCULO"), SEGS, "")
    assert revisadas[0]["enfasis"] == ["impide"]
    assert fallos["enfasis_fuera"] == 1


def test_la_pildora_y_la_cifra_no_llevan_enfasis_porque_ya_son_el_acento():
    revisadas, _ = mf.revisar_fichas(
        [ficha(bloque="PILDORA", texto="código fantasma", enfasis=["código"])],
        _planos("PILDORA"), SEGS, "")
    assert revisadas[0]["enfasis"] == []


def test_la_camara_la_pone_el_plano_y_no_la_ficha():
    revisadas, _ = mf.revisar_fichas(
        [ficha()], _planos("NADA", camara="cruce"), SEGS, "")
    assert revisadas[0]["camara"] == "cruce"


# --- los titulares ----------------------------------------------------------

def test_hay_un_titular_por_frase_y_los_tiempos_son_los_de_la_voz():
    revisadas, fallos = mf.revisar_fichas([ficha()], _planos("NADA"), SEGS, "")
    ts = revisadas[0]["titulares"]
    assert [tt["texto"] for tt in ts] == ["un titular corto", "y otro distinto"]
    assert [(tt["t0"], tt["t1"]) for tt in ts] == [(0.0, 2.0), (2.0, 4.4)]
    assert not fallos["titular_vacio"]


def test_titulares_de_menos_se_rellenan_con_su_propia_frase():
    """Una frase sin titular dejaría la pantalla muda justo mientras se dice."""
    revisadas, fallos = mf.revisar_fichas(
        [ficha(titulares=[tit("solo uno")])], _planos("NADA"), SEGS, "")
    ts = revisadas[0]["titulares"]
    assert len(ts) == 2 and ts[1]["texto"]
    assert ts[1]["t1"] == 4.4
    assert fallos["titular_vacio"] == 1


def test_titulares_de_mas_se_tiran():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(titulares=[tit("uno"), tit("dos"), tit("tres")])],
        _planos("NADA"), SEGS, "")
    assert len(revisadas[0]["titulares"]) == 2
    assert fallos["titulares_de_mas"] == 1


def test_un_titular_largo_se_corta_y_suelta_los_enlaces():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(titulares=[tit("un fantasma digital que nadie puede borrar de la red")])],
        _planos("NADA"), SEGS, "")
    texto = revisadas[0]["titulares"][0]["texto"]
    assert len(texto.split()) <= mf.TOPE_TITULAR
    assert not texto.split()[-1] in mf._ENLACE
    assert fallos["largas"] == 0      # el tope del titular no es el del bloque


def test_el_enfasis_de_un_titular_tiene_que_estar_en_su_texto():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(titulares=[tit("nadie lo puede borrar", "jamás"), tit("y sigue ahí")])],
        _planos("NADA"), SEGS, "")
    assert revisadas[0]["titulares"][0]["enfasis"] == []
    assert fallos["enfasis_fuera"] == 1


# --- lista y ordinal --------------------------------------------------------

def test_una_lista_de_una_sola_fila_no_es_una_lista():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="LISTA", filas=[{"texto": "la primera"}])],
        _planos("LISTA"), SEGS, "")
    assert revisadas[0]["bloque"] == "NADA"
    assert fallos["bloque_sin_datos"] == 1


def test_una_lista_con_filas_las_conserva_con_su_chapa():
    revisadas, _ = mf.revisar_fichas(
        [ficha(bloque="LISTA", filas=[{"texto": "la caché", "chapa": "rápida"},
                                      {"texto": "la RAM", "chapa": "lenta"}])],
        _planos("LISTA"), SEGS, "")
    assert [f["chapa"] for f in revisadas[0]["filas"]] == ["rápida", "lenta"]


def test_un_ordinal_sin_numero_se_apaga():
    revisadas, fallos = mf.revisar_fichas(
        [ficha(bloque="ORDINAL", texto="segundo")], _planos("ORDINAL"), SEGS, "")
    assert revisadas[0]["bloque"] == "NADA"
    assert fallos["bloque_sin_datos"] == 1


def test_un_ordinal_puede_repetirse_porque_es_la_cuenta():
    planos = [plano("ORDINAL: uno"), plano("ORDINAL: dos")]
    revisados, fallos = mf.revisar_planos(planos, 2, True)
    assert [r["bloque"] for r in revisados] == ["ORDINAL", "ORDINAL"]
    assert fallos["bloque_repetido"] == 0


# --- revisar_dibujo ---------------------------------------------------------

def pieza(id, tipo="caja", nombre="X", ranuras=0, llenas=0, estado="normal",
          lineas=()):
    return PiezaLLM(id=id, tipo=tipo, nombre=nombre, ranuras=ranuras,
                    llenas=llenas, estado=estado, lineas=list(lineas))


def comp(piezas=(), vinculos=(), animacion=None, foco="", fondo="negro"):
    return ComposicionLLM(
        bloque="NADA", banda="centro", texto="", apoyo="", enfasis=[],
        fondo=fondo, piezas=list(piezas),
        vinculos=[VinculoLLM(**v) for v in vinculos],
        animacion=AnimacionLLM(**(animacion or {"tipo": "nada"})), foco=foco)


def dibujo(c, continua=False, previa=None):
    return mf.revisar_dibujo(c, {"continua": continua}, previa)


def test_un_tipo_que_no_existe_se_queda_en_caja():
    d, fallos = dibujo(comp([pieza("x", "holograma")]))
    assert d["piezas"][0]["tipo"] == "caja"
    assert fallos["pieza_tipo"] == 1


def test_dos_piezas_con_el_mismo_id_no_se_pisan():
    d, fallos = dibujo(comp([pieza("x"), pieza("x")]))
    assert len({p["id"] for p in d["piezas"]}) == 2
    assert fallos["pieza_sin_id"] == 1


def test_una_pieza_que_se_llama_como_un_bloque_se_tira():
    """La gráfica la dibuja la capa de anotación. Declararla como pieza deja
    una caja vacía al lado del esquema."""
    d, _ = dibujo(comp([pieza("cpu", "chip"), pieza("grafica")]))
    assert [p["id"] for p in d["piezas"]] == ["cpu"]


def test_las_ranuras_solo_cuentan_en_un_banco():
    d, _ = dibujo(comp([pieza("c", "chip", ranuras=5),
                        pieza("b", "banco", ranuras=99, llenas=99)]))
    assert d["piezas"][0]["ranuras"] == 0
    assert d["piezas"][1]["ranuras"] == d["piezas"][1]["llenas"] == 8


def test_un_vinculo_a_una_pieza_que_no_existe_se_tira():
    d, fallos = dibujo(comp([pieza("a")], [{"de": "a", "a": "fantasma"}]))
    assert d["vinculos"] == []
    assert fallos["vinculo_roto"] == 1


def test_un_flujo_entre_piezas_inventadas_usa_el_vinculo_que_hay():
    d, fallos = dibujo(comp(
        [pieza("a"), pieza("b")], [{"de": "a", "a": "b", "coste": "corto"}],
        {"tipo": "flujo", "de": "nada", "a": "ninguna"}))
    assert (d["animacion"]["de"], d["animacion"]["a"]) == ("a", "b")
    assert fallos["animacion"] == 1


def test_buscar_en_algo_que_no_es_una_pila_se_va_a_la_pila():
    d, _ = dibujo(comp([pieza("c", "chip"), pieza("b", "banco", ranuras=4)],
                       animacion={"tipo": "buscar", "en": "c"}))
    assert d["animacion"]["en"] == "b"


def test_buscar_sin_ninguna_pila_se_queda_en_latido():
    d, _ = dibujo(comp([pieza("c", "chip")], animacion={"tipo": "buscar", "en": "c"}))
    assert d["animacion"]["tipo"] == "latido"


def test_comparar_con_un_solo_camino_no_compara_nada():
    d, _ = dibujo(comp([pieza("a"), pieza("b")],
                       [{"de": "a", "a": "b"}], {"tipo": "comparar"}))
    assert d["animacion"]["tipo"] == "flujo"


def test_un_esquema_quieto_se_pone_en_marcha():
    """Ocho segundos de cajas inmóviles son una diapositiva, no un vídeo."""
    d, fallos = dibujo(comp([pieza("a"), pieza("b")], [{"de": "a", "a": "b"}]))
    assert d["animacion"]["tipo"] == "flujo"
    assert fallos["animacion"] == 1


def test_una_escena_sin_piezas_no_anima_nada():
    d, fallos = dibujo(comp(animacion={"tipo": "flujo", "de": "x", "a": "y"}))
    assert d["animacion"]["tipo"] == "nada"
    assert fallos["sin_piezas"] == 1


def test_el_foco_inventado_cae_en_lo_que_se_anima():
    d, fallos = dibujo(comp([pieza("a"), pieza("b")],
                            animacion={"tipo": "latido", "en": "b"}, foco="z"))
    assert d["foco"] == "b"
    assert fallos["foco"] == 1


def test_un_fondo_que_no_existe_es_negro():
    d, fallos = dibujo(comp([pieza("a")], fondo="galaxia"))
    assert d["fondo"] == "negro"
    assert fallos["fondo"] == 1


def test_la_escena_que_continua_hereda_lo_que_habia_en_pantalla():
    previa, _ = dibujo(comp([pieza("cpu", "chip", "Procesador"),
                             pieza("l1", "banco", "Caché", 4, 1)],
                            [{"de": "cpu", "a": "l1", "coste": "corto"}]))
    # La siguiente solo dice lo que cambia: la caché se calienta.
    d, _ = dibujo(comp([pieza("l1", "banco", "Caché", 4, 3, "caliente")]),
                  continua=True, previa=previa)
    assert {p["id"] for p in d["piezas"]} == {"cpu", "l1"}
    l1 = next(p for p in d["piezas"] if p["id"] == "l1")
    assert (l1["estado"], l1["llenas"]) == ("caliente", 3)
    # Y el vínculo de antes sigue ahí sin tener que repetirlo.
    assert d["vinculos"] == [{"de": "cpu", "a": "l1", "coste": "corto"}]


def test_la_escena_que_continua_puede_animar_lo_que_ya_estaba():
    previa, _ = dibujo(comp([pieza("cpu", "chip"), pieza("ram", "banco", ranuras=6)],
                            [{"de": "cpu", "a": "ram", "coste": "largo"}]))
    d, fallos = dibujo(comp(animacion={"tipo": "buscar", "en": "ram"}),
                       continua=True, previa=previa)
    assert d["animacion"] == {"tipo": "buscar", "de": "", "a": "", "en": "ram"}
    assert fallos["animacion"] == 0 and fallos["sin_piezas"] == 0


def test_un_abanico_de_costes_distintos_se_endereza_en_cadena():
    """`cpu→l1 corto`, `cpu→l2 medio`, `cpu→ram largo` dibuja las tres al lado,
    todas a la misma distancia, y ahí se pierde justo lo que explica el vídeo."""
    d, fallos = dibujo(comp(
        [pieza("cpu", "chip"), pieza("l1", "banco", ranuras=4),
         pieza("l2", "banco", ranuras=6), pieza("ram", "banco", ranuras=8)],
        [{"de": "cpu", "a": "ram", "coste": "largo"},
         {"de": "cpu", "a": "l1", "coste": "corto"},
         {"de": "cpu", "a": "l2", "coste": "medio"}]))
    assert {(v["de"], v["a"]) for v in d["vinculos"]} == {
        ("cpu", "l1"), ("l1", "l2"), ("l2", "ram")}
    assert fallos["abanico"] == 1


def test_varias_salidas_al_mismo_coste_son_alternativas_de_verdad():
    d, fallos = dibujo(comp(
        [pieza("a"), pieza("b"), pieza("c"), pieza("d")],
        [{"de": "a", "a": "b", "coste": "corto"},
         {"de": "a", "a": "c", "coste": "corto"},
         {"de": "a", "a": "d", "coste": "corto"}]))
    assert len(d["vinculos"]) == 3
    assert all(v["de"] == "a" for v in d["vinculos"])
    assert fallos["abanico"] == 0


def test_la_animacion_no_se_deja_ids_sueltos_de_otra_cosa():
    """Un `en` que sobró de otra animación acababa en el `foco`, y la cámara
    se iba a enmarcar una pieza que no existe."""
    d, _ = dibujo(comp([pieza("a"), pieza("b")],
                       [{"de": "a", "a": "b"}],
                       {"tipo": "flujo", "de": "a", "a": "b", "en": "grafica"}))
    assert d["animacion"]["en"] == ""
    assert d["foco"] in ("a", "b")


# --- las ventanas -----------------------------------------------------------

def test_una_ventana_sin_lineas_no_es_una_ventana():
    """Un terminal vacío es un rectángulo con tres puntos: no dice nada, y
    encima ocupa media pantalla."""
    d, fallos = dibujo(comp([pieza("sh", "terminal", "claude")]))
    assert d["piezas"][0]["tipo"] == "caja"
    assert fallos["ventana_vacia"] == 1


def test_las_lineas_solo_se_guardan_dentro_de_una_ventana():
    d, _ = dibujo(comp([pieza("c", "caja", lineas=["$ npm i"]),
                        pieza("sh", "terminal", lineas=["$ npm i", "hecho"])]))
    assert d["piezas"][0]["lineas"] == []
    assert d["piezas"][1]["lineas"] == ["$ npm i", "hecho"]


def test_teclear_fuera_de_una_ventana_se_va_a_la_ventana():
    d, fallos = dibujo(comp([pieza("c", "chip"),
                             pieza("sh", "terminal", lineas=["$ npm i"])],
                            animacion={"tipo": "teclear", "en": "c"}))
    assert d["animacion"] == {"tipo": "teclear", "de": "", "a": "", "en": "sh"}
    assert fallos["animacion"] == 1


def test_teclear_sin_ninguna_ventana_se_queda_en_latido():
    d, _ = dibujo(comp([pieza("c", "chip")], animacion={"tipo": "teclear", "en": "c"}))
    assert d["animacion"]["tipo"] == "latido"


def test_una_ventana_quieta_se_pone_a_teclear():
    """Una ventana inmóvil es una captura. Lo que se cuenta es que alguien
    escribe ahí dentro."""
    d, fallos = dibujo(comp([pieza("sh", "terminal", lineas=["$ npm i"])]))
    assert d["animacion"]["tipo"] == "teclear" and d["animacion"]["en"] == "sh"
    assert fallos["animacion"] == 1


def test_al_continuar_una_ventana_cambia_sus_lineas_pero_no_su_nombre():
    """El plano siguiente es el comando siguiente; el título de la ventana es
    su identidad y no se toca."""
    previa, _ = dibujo(comp([pieza("sh", "terminal", "claude", lineas=["$ npm i"])]))
    d, _ = dibujo(comp([pieza("sh", "terminal", "otra cosa", lineas=["$ npm test"])]),
                  continua=True, previa=previa)
    sh = next(p for p in d["piezas"] if p["id"] == "sh")
    assert sh["lineas"] == ["$ npm test"]
    assert sh["nombre"] == "claude"
