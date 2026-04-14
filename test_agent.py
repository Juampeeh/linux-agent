#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_agent.py - Test integral del Linux Local AI Agent en la VM.
Ejecutar en la VM con: python test_agent.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def ok(msg):   print(f"{GREEN}  [OK] {msg}{RESET}")
def info(msg): print(f"{CYAN}  [..] {msg}{RESET}")
def fail(msg): print(f"{RED}  [FAIL] {msg}{RESET}")
def section(t): print(f"\n{BOLD}=== {t} ==={RESET}")


passed = 0
failed = 0


def test(nombre, fn):
    global passed, failed
    info(nombre)
    try:
        fn()
        ok(nombre)
        passed += 1
    except Exception as e:
        fail(f"{nombre}: {e}")
        failed += 1


# =============================================================================
# Tests
# =============================================================================

section("1. Importación de módulos")


def t_config():
    import config
    assert config.LMSTUDIO_BASE_URL, "LMSTUDIO_BASE_URL vacío"
    assert config.LMSTUDIO_BASE_URL.startswith("http"), (
        f"LMSTUDIO_BASE_URL inválida: {config.LMSTUDIO_BASE_URL}"
    )


def t_tools():
    import tools
    assert callable(tools.ejecutar_bash)


def t_router():
    from llm.router import motores_disponibles, crear_agente
    motores = motores_disponibles()
    assert "local" in motores


def t_history():
    from llm.history import HistorialCanonico
    h = HistorialCanonico("system prompt")
    h.agregar_usuario("hola")
    msgs = h.to_openai()
    assert any(m["role"] == "user" for m in msgs)


def t_tool_registry():
    from llm.tool_registry import HERRAMIENTAS, to_openai_format
    assert len(HERRAMIENTAS) > 0
    fmt = to_openai_format(HERRAMIENTAS)
    assert fmt[0]["type"] == "function"


test("Importar config", t_config)
test("Importar tools", t_tools)
test("Importar router", t_router)
test("HistorialCanonico", t_history)
test("Tool Registry", t_tool_registry)


section("2. execute_local_bash (sin confirmación)")


def t_bash_echo():
    from tools import ejecutar_bash
    result = ejecutar_bash("echo 'TEST_OK'", require_confirmation=False)
    assert "TEST_OK" in result, f"Output inesperado: {result}"


def t_bash_uname():
    from tools import ejecutar_bash
    result = ejecutar_bash("uname -a", require_confirmation=False)
    assert "Linux" in result


def t_bash_ls():
    from tools import ejecutar_bash
    result = ejecutar_bash("ls -la /home", require_confirmation=False)
    assert "Exit code: 0" in result


def t_bash_timeout():
    from tools import ejecutar_bash
    import config
    old_timeout = config.COMMAND_TIMEOUT
    config.COMMAND_TIMEOUT = 2
    result = ejecutar_bash("sleep 10", require_confirmation=False)
    config.COMMAND_TIMEOUT = old_timeout
    assert "timeout" in result.lower() or "Timeout" in result


test("echo TEST_OK", t_bash_echo)
test("uname -a", t_bash_uname)
test("ls -la /home", t_bash_ls)
test("Timeout de comando", t_bash_timeout)


section("3. Conexión a LM Studio")


def t_lmstudio_connect():
    import openai
    import config
    client = openai.OpenAI(base_url=config.LMSTUDIO_BASE_URL, api_key="lm-studio")
    models = client.models.list()
    ids = [m.id for m in models.data]
    assert len(ids) > 0, "No hay modelos cargados en LM Studio"
    print(f"\n    Modelos disponibles: {ids}")


def t_lmstudio_agent_init():
    from llm.router import crear_agente
    agente = crear_agente("local")
    agente.inicializar()
    print(f"\n    Motor: {agente.nombre_motor}")
    assert agente.nombre_motor


test("Conectar a LM Studio", t_lmstudio_connect)
test("Inicializar LM Studio Agent", t_lmstudio_agent_init)


section("4. Tool Call real con LLM")


def t_tool_call_completo():
    """Test de extremo a extremo: LLM decide usar execute_local_bash."""
    import json
    from llm.router import crear_agente
    from llm.history import HistorialCanonico
    from llm.tool_registry import HERRAMIENTAS, SYSTEM_PROMPT
    from tools import ejecutar_bash

    agente = crear_agente("local")
    agente.inicializar()

    historial = HistorialCanonico(system_prompt=SYSTEM_PROMPT)
    historial.agregar_usuario(
        "Ejecutá el comando 'uname -a' para mostrarme información del sistema operativo."
    )

    print("\n    Enviando turno al LLM...")
    respuesta = agente.enviar_turno(historial, HERRAMIENTAS)

    print(f"    Respuesta del LLM: texto='{respuesta.texto[:80]}' | tool_calls={len(respuesta.tool_calls)}")

    # El LLM debería hacer un tool call
    assert respuesta.tiene_tool_calls, (
        "El LLM no generó tool calls. "
        f"Respuesta: '{respuesta.texto}'"
    )

    tc = respuesta.tool_calls[0]
    assert tc.nombre == "execute_local_bash", f"Tool name inesperado: {tc.nombre}"
    assert "comando" in tc.argumentos, f"Falta 'comando' en args: {tc.argumentos}"

    cmd = tc.argumentos["comando"]
    print(f"    LLM propuso ejecutar: {cmd}")

    # Ejecutar el comando
    resultado = ejecutar_bash(cmd, require_confirmation=False)
    assert "Linux" in resultado or "Exit code" in resultado, f"Output inesperado: {resultado}"
    print(f"    Resultado del comando OK: {resultado[:100]}")


test("Tool Call E2E (uname -a)", t_tool_call_completo)


section("5. Memoria semántica (llm/memory.py)")


def t_memory_import():
    """Verifica que el módulo se importa correctamente."""
    from llm.memory import MemoriaSemantica, crear_memoria, formatear_contexto_memoria
    assert MemoriaSemantica is not None
    assert callable(crear_memoria)
    assert callable(formatear_contexto_memoria)


def t_memory_coseno():
    """Verifica el cálculo de similitud coseno."""
    from llm.memory import MemoriaSemantica
    # Vectores idénticos → similitud = 1.0
    v = [1.0, 0.0, 0.0]
    sim = MemoriaSemantica._coseno(v, v)
    assert abs(sim - 1.0) < 1e-5, f"Similitud esperada 1.0, obtenida {sim}"
    # Vectores ortogonales → similitud = 0.0
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    sim2 = MemoriaSemantica._coseno(a, b)
    assert abs(sim2 - 0.0) < 1e-5, f"Similitud esperada 0.0, obtenida {sim2}"


def t_memory_db_init():
    """Verifica que se puede crear la DB SQLite y la tabla de memorias."""
    import tempfile, os
    from llm.memory import MemoriaSemantica
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        # Creamos instancia con motor "claude" (sin embeddings) para probar
        # solo la lógica de la DB sin llamadas HTTP
        mem = MemoriaSemantica(motor_key="local", db_path=db_path)
        # Si no hay conexión a LM Studio, activa puede ser False — no es error
        # Lo que nos interesa es que no lance excepciones al construir
        if mem._conn:
            mem.cerrar()
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass


def t_memory_guardar_buscar_mock():
    """
    Guarda un recuerdo con embedding sintético y lo recupera con búsqueda coseno.
    No requiere conexión a LM Studio — inyecta el embedding directamente en la DB.
    """
    import tempfile, os, json, time, sqlite3
    from llm.memory import MemoriaSemantica

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        # Crear instancia con motor "local" y la DB temporal
        mem = MemoriaSemantica(motor_key="local", db_path=db_path)
        # Activar forzosamente aunque no haya embeddings disponibles
        if not mem._conn:
            mem._init_db()

        # Insertar un recuerdo con embedding sintético directamente en la DB
        embedding_sintetico = [1.0, 0.0, 0.0] + [0.0] * 253  # 256 dims
        conn = mem._conn
        conn.execute(
            """INSERT INTO memorias
               (contenido, embedding, tipo, embedding_provider, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "Comando bash exitoso: `df -h`\nOutput:\nFilesystem Size Used",
                json.dumps(embedding_sintetico),
                "comando_exitoso",
                "local",  # provider
                time.time(),
                "{}",
            ),
        )
        conn.commit()

        # Simular búsqueda con vector muy similar (cos=1.0 con el sintético)
        # Parchamos get_embedding para devolver el mismo vector
        mem.get_embedding = lambda texto: embedding_sintetico

        resultados = mem.buscar("cuánto espacio libre hay", threshold=0.5)
        assert len(resultados) == 1, f"Se esperaba 1 resultado, obtenidos: {len(resultados)}"
        assert "df -h" in resultados[0]["contenido"]
        assert resultados[0]["similitud"] >= 0.99
        mem.cerrar()
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass


def t_memory_degradacion_claude():
    """Verifica que la memoria se desactiva silenciosamente para motores sin embeddings."""
    import tempfile, os
    from llm.memory import MemoriaSemantica
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mem = MemoriaSemantica(motor_key="claude", db_path=db_path)
        assert not mem.activa, "La memoria debería estar desactivada para Claude"
        # Operaciones sobre memoria desactivada no deben lanzar excepciones
        resultados = mem.buscar("hola mundo")
        assert resultados == []
        guardado = mem.guardar("test", "preferencia")
        assert not guardado
        stats = mem.stats()
        assert not stats["activa"]
        mem.cerrar()
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass


def t_memory_guardar_si_exitoso():
    """Verifica la heurística de extracción de aprendizajes."""
    import tempfile, os, json, time
    from llm.memory import MemoriaSemantica

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mem = MemoriaSemantica(motor_key="local", db_path=db_path)
        if not mem._conn:
            mem._init_db()
        mem.activa = True  # Forzar activo

        # Tracking manual: cuántas filas hay antes
        count_antes = mem._conn.execute(
            "SELECT COUNT(*) FROM memorias"
        ).fetchone()[0]

        # Parchamos get_embedding para no necesitar red
        mem.get_embedding = lambda texto: [0.5] * 64

        # Caso exitoso (exit_code: 0 en resultado)
        mem.guardar_si_exitoso(
            "execute_local_bash",
            {"comando": "apt list --installed"},
            "Listing...\nexit_code: 0\napt/focal,now 2.0.6",
        )
        count_exitoso = mem._conn.execute(
            "SELECT COUNT(*) FROM memorias"
        ).fetchone()[0]
        assert count_exitoso == count_antes + 1, "Debería haber guardado 1 recuerdo"

        # Caso fallido (no debe guardar)
        mem.guardar_si_exitoso(
            "execute_local_bash",
            {"comando": "rm /etc/passwd"},
            "rm: cannot remove '/etc/passwd': Permission denied",
        )
        count_fallido = mem._conn.execute(
            "SELECT COUNT(*) FROM memorias"
        ).fetchone()[0]
        assert count_fallido == count_exitoso, "No debería guardar comandos con error"

        mem.cerrar()
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass


def t_memory_lmstudio_embedding():
    """
    Verifica que LM Studio responde a /v1/embeddings.
    Requiere conexión a LM Studio — se marca como advertencia si no está disponible.
    """
    import config
    from llm.memory import MemoriaSemantica
    mem = MemoriaSemantica(
        motor_key="local",
        base_url=config.LMSTUDIO_BASE_URL,
        model_id=config.LMSTUDIO_EMBED_MODEL or None,
    )
    if not mem.activa:
        print(f"\n    [SKIP] Memoria no activa (numpy o config). Verificá MEMORY_ENABLED.")
        return
    emb = mem.get_embedding("texto de prueba para embeddings")
    if emb is None:
        print(f"\n    [WARN] LM Studio no respondió /v1/embeddings con el modelo actual.")
        print(f"    Esto es normal si el modelo no soporta embeddings. La memoria se desactivará.")
        return
    assert isinstance(emb, list), f"Embedding debe ser una lista, obtenido: {type(emb)}"
    assert len(emb) > 0, "El embedding está vacío"
    print(f"\n    Embedding OK: {len(emb)} dimensiones")
    mem.cerrar()


test("Importar memory.py", t_memory_import)
test("Similitud coseno", t_memory_coseno)
test("Inicialización DB SQLite", t_memory_db_init)
test("Guardar y buscar (mock embedding)", t_memory_guardar_buscar_mock)
test("Degradación silenciosa (Claude/Grok)", t_memory_degradacion_claude)
test("Extracción de aprendizajes", t_memory_guardar_si_exitoso)
test("Embeddings reales vía LM Studio", t_memory_lmstudio_embedding)


# =============================================================================
# Resumen
# =============================================================================

total = passed + failed
print(f"""
{BOLD}=== RESUMEN ==={RESET}
  Pasados : {GREEN}{passed}/{total}{RESET}
  Fallados: {RED}{failed}/{total}{RESET}
""")

if failed > 0:
    sys.exit(1)
