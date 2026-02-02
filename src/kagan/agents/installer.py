"""Agent installer functionality.

Provides utilities to check if coding agents (Claude Code, OpenCode) are installed
and install them via their official installation methods.
"""

from __future__ import annotations

import asyncio
import shutil

# Default timeout for installation (2 minutes)
INSTALL_TIMEOUT_SECONDS = 120

# Agent-specific install commands
INSTALL_COMMANDS = {
    "claude": "curl -fsSL https://claude.ai/install.sh | sh",
    "opencode": "npm i -g opencode-ai",
}

# Legacy constant for backward compatibility
INSTALL_COMMAND = INSTALL_COMMANDS["claude"]


class InstallerError(Exception):
    """Raised when installation operations fail."""


def get_install_command(agent: str = "claude") -> str:
    """Return the install command string for display.

    Args:
        agent: The agent to get the install command for.
               Supported values: "claude", "opencode".
               Defaults to "claude".

    Returns:
        The install command for the specified agent.

    Raises:
        ValueError: If an unsupported agent is specified.
    """
    if agent not in INSTALL_COMMANDS:
        raise ValueError(
            f"Unsupported agent: {agent}. Supported agents: {list(INSTALL_COMMANDS.keys())}"
        )
    return INSTALL_COMMANDS[agent]


async def check_claude_code_installed() -> bool:
    """Check if the `claude` command exists in PATH.

    Returns:
        True if claude command is available, False otherwise.
    """
    # Use shutil.which for synchronous check - it's fast enough
    # and doesn't require spawning a subprocess
    return shutil.which("claude") is not None


def check_opencode_installed() -> bool:
    """Check if OpenCode CLI is available in PATH.

    Returns:
        True if opencode command is available, False otherwise.
    """
    return shutil.which("opencode") is not None


async def install_claude_code(
    timeout: float = INSTALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Install Claude Code using the official install script.

    Runs `curl -fsSL https://claude.ai/install.sh | sh` in the user's shell.

    Args:
        timeout: Maximum time in seconds to wait for installation.
                 Defaults to 120 seconds.

    Returns:
        A tuple of (success, message) where:
        - success: True if installation completed successfully
        - message: Descriptive message about the result or error
    """
    try:
        # Use shell=True to properly pipe curl to sh
        # This matches how a user would run the command manually
        proc = await asyncio.create_subprocess_shell(
            INSTALL_COMMANDS["claude"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            # Kill the process if it times out
            proc.kill()
            await proc.wait()
            return False, f"Installation timed out after {timeout} seconds"

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if proc.returncode == 0:
            # Verify installation was successful
            if await check_claude_code_installed():
                return True, "Claude Code installed successfully"
            else:
                # Installation script succeeded but claude not in PATH
                # This might happen if the user needs to restart their shell
                return True, (
                    "Installation script completed. "
                    "You may need to restart your shell or add claude to your PATH."
                )
        else:
            # Collect error information
            error_details = []
            if stderr_str:
                error_details.append(stderr_str)
            if stdout_str:
                error_details.append(stdout_str)

            error_message = (
                "; ".join(error_details)
                if error_details
                else f"Installation failed with exit code {proc.returncode}"
            )
            return False, f"Installation failed: {error_message}"

    except FileNotFoundError:
        return False, "Installation failed: curl command not found. Please install curl."
    except OSError as e:
        return False, f"Installation failed: {e}"


async def install_opencode(
    timeout: float = INSTALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Install OpenCode using npm.

    Runs `npm i -g opencode-ai` to install OpenCode globally.

    Args:
        timeout: Maximum time in seconds to wait for installation.
                 Defaults to 120 seconds.

    Returns:
        A tuple of (success, message) where:
        - success: True if installation completed successfully
        - message: Descriptive message about the result or error
    """
    # Check if npm is available before attempting installation
    if shutil.which("npm") is None:
        return False, (
            "Installation failed: npm is not installed. "
            "Please install Node.js and npm first: https://nodejs.org/"
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            INSTALL_COMMANDS["opencode"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            # Kill the process if it times out
            proc.kill()
            await proc.wait()
            return False, f"Installation timed out after {timeout} seconds"

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if proc.returncode == 0:
            # Verify installation was successful
            if check_opencode_installed():
                return True, "OpenCode installed successfully"
            else:
                # Installation succeeded but opencode not in PATH
                # This might happen if npm global bin is not in PATH
                return True, (
                    "Installation completed. "
                    "You may need to add npm global bin directory to your PATH."
                )
        else:
            # Collect error information
            error_details = []
            if stderr_str:
                error_details.append(stderr_str)
            if stdout_str:
                error_details.append(stdout_str)

            error_message = (
                "; ".join(error_details)
                if error_details
                else f"Installation failed with exit code {proc.returncode}"
            )
            return False, f"Installation failed: {error_message}"

    except FileNotFoundError:
        return False, "Installation failed: npm command not found. Please install Node.js and npm."
    except OSError as e:
        return False, f"Installation failed: {e}"


async def install_agent(
    agent: str,
    timeout: float = INSTALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Install the specified coding agent.

    This is a generic dispatcher that routes to the appropriate
    agent-specific installer.

    Args:
        agent: The agent to install. Supported values: "claude", "opencode".
        timeout: Maximum time in seconds to wait for installation.
                 Defaults to 120 seconds.

    Returns:
        A tuple of (success, message) where:
        - success: True if installation completed successfully
        - message: Descriptive message about the result or error

    Raises:
        ValueError: If an unsupported agent is specified.
    """
    if agent == "claude":
        return await install_claude_code(timeout=timeout)
    elif agent == "opencode":
        return await install_opencode(timeout=timeout)
    else:
        raise ValueError(
            f"Unsupported agent: {agent}. Supported agents: {list(INSTALL_COMMANDS.keys())}"
        )
