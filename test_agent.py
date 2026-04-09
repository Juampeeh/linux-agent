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
    assert "192.168.0.142" in config.LMSTUDIO_BASE_URL


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
