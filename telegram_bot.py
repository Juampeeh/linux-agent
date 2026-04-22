# =============================================================================
# telegram_bot.py — Integración Telegram Bidireccional
# Linux Local AI Agent v2.0
#
# Arquitectura:
#   - TelegramBot corre en su propio hilo daemon con asyncio event loop propio.
#   - Mensajes entrantes → input_queue (main.py los lee)
#   - Respuestas del agente → output_queue (TelegramBot los envía)
#   - Alertas directas del centinela → método send_alert() thread-safe
#   - Aprobación en modo seguro → InlineKeyboard + Future para respuesta síncrona
# =============================================================================

from __future__ import annotations
import asyncio
import logging
import queue
import threading
import time
from typing import Callable

import config as cfg

logger = logging.getLogger(__name__)

# Tiempo máximo de espera para aprobación via Telegram (segundos)
_APPROVAL_TIMEOUT = 120


class TelegramMessage:
    """Representa un mensaje recibido de Telegram."""
    def __init__(self, chat_id: int, text: str, message_id: int) -> None:
        self.chat_id    = chat_id
        self.text       = text
        self.message_id = message_id
        self.ts         = time.time()


class ApprovalRequest:
    """Solicitud de aprobación de comando para resolución via Telegram."""
    def __init__(self, comando: str, chat_id: int) -> None:
        self.comando  = comando
        self.chat_id  = chat_id
        self.event    = threading.Event()
        self.approved = False  # Resultado de la aprobación


class TelegramBot:
    """
    Bot de Telegram que corre en un hilo daemon.

    Uso desde main.py:
        bot = TelegramBot()
        bot.start()

        # Enviar mensaje:
        bot.send_message(chat_id, "Hola!")

        # Alerta directa (no requiere chat_id conocido):
        bot.send_alert("⚠ Alerta: disco al 95%")

        # Leer mensajes entrantes:
        msg = bot.get_message(timeout=0.1)  # No bloqueante

        # Pedir aprobación (bloqueante con timeout):
        aprobado = bot.pedir_aprobacion("rm -rf /tmp/test", chat_id=123456)
    """

    def __init__(self) -> None:
        self.enabled     = cfg.TELEGRAM_ENABLED
        self.token       = cfg.TELEGRAM_BOT_TOKEN
        self.allowed_ids = cfg.TELEGRAM_ALLOWED_IDS

        # Colas thread-safe para comunicación con el bucle principal
        self._input_queue: queue.Queue[TelegramMessage]  = queue.Queue()
        self._output_queue: queue.Queue[dict]            = queue.Queue()

        # Solicitudes de aprobación pendientes (callback_data → ApprovalRequest)
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._approvals_lock = threading.Lock()

        # Estado interno
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._registration_mode = False  # Para registrar nuevo chat_id

    def start(self) -> bool:
        """
        Inicia el bot en un hilo daemon.
        Retorna True si se inició correctamente, False si está deshabilitado o falla.
        """
        if not self.enabled:
            logger.info("[Telegram] Deshabilitado (TELEGRAM_ENABLED=False)")
            return False

        if not self.token:
            logger.warning("[Telegram] Sin token configurado (TELEGRAM_BOT_TOKEN vacío)")
            return False

        try:
            import telegram  # noqa: F401
        except ImportError:
            logger.error("[Telegram] python-telegram-bot no instalado. Ejecutá: pip install python-telegram-bot")
            return False

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TelegramBot")
        self._thread.start()

        # Esperar a que el bot se inicialice (máx 10s)
        for _ in range(20):
            if self._started:
                return True
            time.sleep(0.5)

        logger.warning("[Telegram] El bot tardó demasiado en inicializarse.")
        return False

    def _run_loop(self) -> None:
        """Hilo daemon: crea el event loop y corre el bot."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run())
        except Exception as e:
            logger.error(f"[Telegram] Error en el hilo del bot: {e}")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _async_run(self) -> None:
        """Corre el bot de Telegram con polling."""
        from telegram.ext import (
            Application,
            MessageHandler,
            CallbackQueryHandler,
            filters,
        )
        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

        app = (
            Application.builder()
            .token(self.token)
            .build()
        )
        self._app = app

        # Handler de mensajes de texto
        async def handle_message(update: Update, context) -> None:
            if not update.message or not update.effective_chat:
                return

            chat_id = update.effective_chat.id
            text = update.message.text or ""

            # Modo de registro de chat_id
            if not self.allowed_ids or self._registration_mode:
                # Auto-registrar el primer chat_id que escriba
                if chat_id not in self.allowed_ids:
                    self.allowed_ids.append(chat_id)
                    logger.info(f"[Telegram] Chat ID {chat_id} registrado automáticamente.")
                    await update.message.reply_text(
                        f"✅ *Registrado exitosamente*\n"
                        f"Tu chat ID es: `{chat_id}`\n\n"
                        f"Agrega esta línea a tu `.env`:\n"
                        f"`TELEGRAM_ALLOWED_IDS={chat_id}`\n\n"
                        f"Ya podés enviarme comandos 🤖",
                        parse_mode="Markdown",
                    )
                    self._registration_mode = False
                    return

            # Verificar whitelist
            if self.allowed_ids and chat_id not in self.allowed_ids:
                await update.message.reply_text("⛔ No estás autorizado para usar este bot.")
                logger.warning(f"[Telegram] Intento de acceso no autorizado: chat_id={chat_id}")
                return

            # Comandos especiales del bot
            if text.startswith("/start"):
                await update.message.reply_text(
                    "🤖 *AI Sysadmin Autónomo*\n\n"
                    "Estoy conectado y listo.\n"
                    "Podés enviarme cualquier comando o pregunta.\n\n"
                    "Comandos especiales:\n"
                    "• `/status` — Estado del agente\n"
                    "• `/sentinel` — Estado del centinela\n"
                    "• Cualquier texto → enviado al agente",
                    parse_mode="Markdown",
                )
                return

            # Enqueue para que main.py lo procese
            self._input_queue.put(TelegramMessage(
                chat_id=chat_id,
                text=text,
                message_id=update.message.message_id,
            ))
            # Enviar "escribiendo..." para responsividad
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Handler de botones de aprobación
        async def handle_callback(update: Update, context) -> None:
            if not update.callback_query:
                return

            query = update.callback_query
            await query.answer()  # Acusar recibo

            callback_data = query.data or ""
            # Formato: "approve:<key>" o "deny:<key>"
            if ":" not in callback_data:
                return

            action, key = callback_data.split(":", 1)

            with self._approvals_lock:
                req = self._pending_approvals.get(key)

            if req is None:
                await query.edit_message_text("⏱ Esta solicitud ya venció o fue procesada.")
                return

            req.approved = (action == "approve")
            req.event.set()

            emoji = "✅" if req.approved else "❌"
            accion_txt = "aprobado" if req.approved else "denegado"
            await query.edit_message_text(
                f"{emoji} Comando *{accion_txt}* vía Telegram.",
                parse_mode="Markdown",
            )

        app.add_handler(MessageHandler(filters.TEXT, handle_message))
        app.add_handler(CallbackQueryHandler(handle_callback))

        # Inicializar y arrancar polling
        await app.initialize()
        await app.start()

        if not self.allowed_ids:
            self._registration_mode = True
            logger.info(
                "[Telegram] Sin chat_ids configurados. Esperando primer mensaje para registro..."
            )

        logger.info("[Telegram] Bot iniciado con polling.")
        self._started = True

        # Iniciar polling
        await app.updater.start_polling(drop_pending_updates=True)

        # Bucle para enviar mensajes desde la output_queue
        while True:
            try:
                msg_data = self._output_queue.get_nowait()
                chat_id  = msg_data["chat_id"]
                text     = msg_data["text"][:4000]
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    # Reintentar sin markdown si falla el parsing
                    try:
                        await app.bot.send_message(chat_id=chat_id, text=text)
                    except Exception:
                        logger.debug(f"[Telegram] Error enviando a {chat_id}: {e}")
            except queue.Empty:
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"[Telegram] Error en loop de salida: {e}")
                await asyncio.sleep(0.5)

    # ── Métodos públicos (thread-safe) ────────────────────────────────────────

    def send_message(self, chat_id: int, text: str) -> None:
        """Encola un mensaje para enviar a un chat específico."""
        if not self._started:
            return
        self._output_queue.put({"chat_id": chat_id, "text": text})

    def send_alert(self, text: str) -> None:
        """Envía una alerta a todos los chat_ids autorizados."""
        if not self._started:
            return
        for chat_id in self.allowed_ids:
            self.send_message(chat_id, text)

    def get_message(self, timeout: float = 0.0) -> TelegramMessage | None:
        """
        Lee el próximo mensaje entrante de Telegram.
        Retorna None si no hay mensajes (no bloquea si timeout=0).
        """
        try:
            if timeout > 0:
                return self._input_queue.get(timeout=timeout)
            else:
                return self._input_queue.get_nowait()
        except queue.Empty:
            return None

    def pedir_aprobacion(self, comando: str, chat_id: int) -> bool:
        """
        Envía un mensaje con botones inline para aprobar/denegar un comando.
        Bloquea hasta que el usuario responde o vence el timeout.

        Retorna True si fue aprobado, False si fue denegado o timeout.
        """
        if not self._started:
            return False

        import uuid
        key = str(uuid.uuid4())[:8]

        req = ApprovalRequest(comando=comando, chat_id=chat_id)
        with self._approvals_lock:
            self._pending_approvals[key] = req

        # Enviar mensaje con botones via la output_queue
        # (No podemos usar send_message directamente porque necesitamos InlineKeyboard)
        # Usamos un tipo especial de mensaje
        self._output_queue.put({
            "chat_id":      chat_id,
            "text":         (
                f"🔒 *Aprobación requerida*\n\n"
                f"El agente quiere ejecutar:\n"
                f"```\n{comando[:500]}\n```\n\n"
                f"¿Aprobás?"
            ),
            "_approval_key": key,
        })

        # Esperar respuesta con timeout
        aprobado = req.event.wait(timeout=_APPROVAL_TIMEOUT)

        with self._approvals_lock:
            self._pending_approvals.pop(key, None)

        if not aprobado:
            logger.info(f"[Telegram] Aprobación timeout para: {comando[:60]}")

        return req.approved if aprobado else False

    def is_running(self) -> bool:
        """Retorna True si el bot está activo y funcionando."""
        return self._started and (self._thread is not None and self._thread.is_alive())

    def stop(self) -> None:
        """Solicita el stop del bot (async — el hilo terminará pronto)."""
        self._started = False
        if self._loop and self._app:
            asyncio.run_coroutine_threadsafe(
                self._app.stop(),
                self._loop,
            )


# =============================================================================
# Singleton global (instanciado por main.py)
# =============================================================================

_bot_instance: TelegramBot | None = None


def get_bot() -> TelegramBot | None:
    """Retorna la instancia global del bot, o None si no fue iniciado."""
    return _bot_instance


def iniciar_bot() -> TelegramBot:
    """Crea e inicia el bot. Debe llamarse una sola vez desde main.py."""
    global _bot_instance
    _bot_instance = TelegramBot()
    _bot_instance.start()
    return _bot_instance
