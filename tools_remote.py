# =============================================================================
# tools_remote.py — Herramientas de ejecución remota (SSH) y Wake-on-LAN
# Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
from pathlib import Path
from typing import Optional

import config as cfg
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

_MAX_SSH_OUTPUT = cfg.MAX_OUTPUT_CHARS


def ejecutar_ssh(
    host: str,
    user: str,
    comando: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: Optional[int] = None,
    require_confirmation: Optional[bool] = None,
) -> str:
    """
    Ejecuta un comando en un host remoto via SSH usando paramiko.

    Parámetros
    ----------
    host                 : IP o hostname del host remoto.
    user                 : Usuario SSH.
    comando              : Comando a ejecutar.
    key_path             : Ruta a clave privada SSH (usa ~/.ssh/id_rsa si es None).
    password             : Contraseña SSH (alternativa a key_path).
    port                 : Puerto SSH (default: 22).
    timeout              : Timeout en segundos.
    require_confirmation : Si True, pide confirmación antes de ejecutar.

    Retorna
    -------
    String con stdout + stderr del comando remoto.
    """
    if require_confirmation is None:
        require_confirmation = cfg.REQUIRE_CONFIRMATION
    if timeout is None:
        timeout = cfg.SSH_DEFAULT_TIMEOUT

    # Mostrar qué se va a hacer
    console.print(Panel(
        f"[bold]Host:[/]    {user}@{host}:{port}\n"
        f"[bold]Comando:[/] {comando}",
        title="[bold cyan]🔒 Comando SSH remoto[/]",
        border_style="cyan",
    ))

    # Confirmación en modo seguro
    if require_confirmation:
        try:
            ok = Confirm.ask(
                "[bold yellow]  ¿Ejecutar este comando remoto?[/]",
                default=True,
                console=console,
            )
        except (KeyboardInterrupt, EOFError):
            ok = False
        if not ok:
            console.print("  [dim]↩ Comando SSH cancelado.[/dim]")
            return "Comando SSH cancelado por el usuario."

    try:
        import paramiko
    except ImportError:
        return "Error: librería 'paramiko' no instalada. Ejecutá: pip install paramiko"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        connect_kwargs: dict = {
            "hostname": host,
            "username": user,
            "port": port,
            "timeout": timeout,
        }

        if password:
            connect_kwargs["password"] = password
        else:
            # Intentar con clave privada
            key_file = Path(key_path or "~/.ssh/id_rsa").expanduser()
            if key_file.exists():
                connect_kwargs["key_filename"] = str(key_file)
                connect_kwargs["look_for_keys"] = False
            else:
                connect_kwargs["look_for_keys"] = True

        ssh.connect(**connect_kwargs)

        stdin, stdout, stderr = ssh.exec_command(comando, timeout=timeout)
        salida  = stdout.read().decode("utf-8", errors="replace").strip()
        errores = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()

    except paramiko.AuthenticationException:
        return f"Error SSH: Fallo de autenticación en {user}@{host}."
    except paramiko.SSHException as e:
        return f"Error SSH: {e}"
    except Exception as e:
        return f"Error al conectar a {host}: {e}"
    finally:
        try:
            ssh.close()
        except Exception:
            pass

    # Combinar salidas
    partes = []
    if salida:
        partes.append(salida)
    if errores:
        partes.append(f"[STDERR]\n{errores}")

    output = "\n".join(partes) if partes else "(sin salida)"

    # Mostrar en terminal
    color = "green" if exit_code == 0 else "red"
    console.print(Panel(
        output[:2000],
        title=f"[bold {color}]SSH Output [{user}@{host}] [Exit: {exit_code}][/]",
        border_style=color,
    ))

    # Truncar para el LLM
    if len(output) > _MAX_SSH_OUTPUT:
        output = output[:_MAX_SSH_OUTPUT] + f"\n[...truncado a {_MAX_SSH_OUTPUT} chars]"

    return f"SSH {user}@{host} — Exit code: {exit_code}\n{output}"


def wake_on_lan(
    mac_address: str,
    broadcast: Optional[str] = None,
    port: int = 9,
) -> str:
    """
    Envía un magic packet Wake-on-LAN a la MAC especificada.

    Parámetros
    ----------
    mac_address : Dirección MAC del equipo (formato: AA:BB:CC:DD:EE:FF o AA-BB-CC-DD-EE-FF).
    broadcast   : Dirección de broadcast (usa WOL_BROADCAST de config si es None).
    port        : Puerto UDP (default: 9).

    Retorna
    -------
    Mensaje de éxito o error.
    """
    bcast = broadcast or cfg.WOL_BROADCAST

    console.print(
        f"  [dim]🔌 Enviando Wake-on-LAN a [bold]{mac_address}[/bold] "
        f"via broadcast {bcast}...[/dim]"
    )

    try:
        import wakeonlan
    except ImportError:
        return "Error: librería 'wakeonlan' no instalada. Ejecutá: pip install wakeonlan"

    try:
        # Normalizar formato de MAC
        mac_clean = mac_address.replace("-", ":").upper()
        wakeonlan.send_magic_packet(mac_clean, ip_address=bcast, port=port)
        msg = f"Magic packet enviado a {mac_clean} via broadcast {bcast}:{port}."
        console.print(f"  [green]✓ {msg}[/green]")
        return msg
    except Exception as e:
        msg = f"Error al enviar Wake-on-LAN: {e}"
        console.print(f"  [red]✗ {msg}[/red]")
        return msg
