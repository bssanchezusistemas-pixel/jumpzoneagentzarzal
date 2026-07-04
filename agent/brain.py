# agent/brain.py — Cerebro JumpBot con tool calling

import os
import json
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.tools_schema import TOOLS, ejecutar_tool
from agent.brain_fallback import respuesta_sin_ia

load_dotenv()
logger = logging.getLogger("agentkit")

AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").lower()
MAX_TOOL_ROUNDS = 5
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "256"))


def _crear_cliente_y_modelo() -> tuple[AsyncAnthropic, str]:
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if AI_PROVIDER == "openrouter" or (AI_PROVIDER == "auto" and openrouter_key):
        return _cliente_openrouter()
    if AI_PROVIDER == "anthropic":
        return (
            AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                base_url="https://api.anthropic.com",
            ),
            os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        )
    return (
        AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url="https://api.anthropic.com",
        ),
        "claude-sonnet-4-6",
    )


def _cliente_openrouter() -> tuple[AsyncAnthropic, str]:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    return (
        AsyncAnthropic(api_key=api_key, base_url="https://openrouter.ai/api"),
        os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4"),
    )


client, MODEL = _crear_cliente_y_modelo()


def cargar_config_prompts() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def cargar_system_prompt() -> str:
    return cargar_config_prompts().get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    return cargar_config_prompts().get(
        "error_message",
        "Hay un problema técnico. Intenta de nuevo en unos minutos.",
    )


def obtener_mensaje_fallback() -> str:
    return cargar_config_prompts().get(
        "fallback_message",
        "No entendí. ¿Puedes reformularlo?",
    )


async def _llamar_ia(cli: AsyncAnthropic, model: str, system: str, mensajes: list):
    return await cli.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=TOOLS,
        messages=mensajes,
    )


async def _ejecutar_tool_round(response, mensajes: list, telefono: str):
    mensajes.append({"role": "assistant", "content": response.content})
    tool_results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        logger.info(f"Tool: {block.name}({block.input})")
        resultado = await ejecutar_tool(block.name, block.input, telefono)
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(resultado, ensure_ascii=False),
        })
    mensajes.append({"role": "user", "content": tool_results})


async def _loop_ia(cli: AsyncAnthropic, model: str, system: str, mensajes: list, telefono: str) -> str:
    for _ in range(MAX_TOOL_ROUNDS):
        response = await _llamar_ia(cli, model, system, mensajes)
        if response.stop_reason == "tool_use":
            await _ejecutar_tool_round(response, mensajes, telefono)
            continue
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return obtener_mensaje_fallback()
    return obtener_mensaje_fallback()


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = "") -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    # Intents comunes: responde directo sin gastar créditos de IA
    fb = await respuesta_sin_ia(mensaje, telefono)
    if fb and os.getenv("IA_SOLO_SI_FALLA", "1") == "1":
        logger.info("Respuesta por reglas (sin IA)")
        return fb

    system_prompt = cargar_system_prompt()
    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        return await _loop_ia(client, MODEL, system_prompt, mensajes, telefono)
    except Exception as e:
        logger.error(f"Error IA ({MODEL}): {e}")
        fb = await respuesta_sin_ia(mensaje, telefono)
        if fb:
            logger.info("Respuesta fallback sin IA")
            return fb
        return obtener_mensaje_error()
