# This code is imported/inspired by wut (https://github.com/shobrook/wut) 
# from author Jonathan Shobrook
import argparse
import os
import re
import tempfile
from collections import namedtuple
from subprocess import check_output, run, CalledProcessError, DEVNULL
from typing import List, Optional, Tuple, Set

from psutil import Process

def get_wut_context() -> str:
    """Get terminal context for wut functionality"""
    return TerminalContext.get_context()

def process_wut_output(output, io=None):
    """Process wut output for file references and prompt user to select files"""
    file_refs = ErrorParser.parse_error_output(output)
    
    if not file_refs:
        return []
        
    if io:
        from aider.utils import prompt_file_selection
        return prompt_file_selection(list(file_refs), io)
        
    return list(file_refs)
# Constants
MAX_CHARS = 10000
MAX_COMMANDS = 3
SHELLS = ["bash", "fish", "zsh", "csh", "tcsh", "powershell", "pwsh"]

# Data Structures
Shell = namedtuple("Shell", ["path", "name", "prompt"])
Command = namedtuple("Command", ["text", "output"])

class TerminalContext:
    """Handles terminal context extraction and processing"""
    
    @staticmethod
    def get_context() -> str:
        """Get terminal context including commands and output"""
        if not TerminalContext._is_terminal_multiplexer():
            raise ValueError(
                "wut must be run inside a tmux or screen session to access terminal history"
            )
        
        shell = ShellManager.get_shell()
        return TerminalContext._build_terminal_context(shell)

    @staticmethod
    def _is_terminal_multiplexer() -> bool:
        """Check if running in tmux or screen"""
        return bool(os.environ.get("TMUX") or os.environ.get("STY"))

    @staticmethod
    def _build_terminal_context(shell: Shell) -> str:
        """Build terminal context string from shell output"""
        output = TerminalContext._get_pane_output()
        if not output:
            return "<terminal_history>No terminal output found.</terminal_history>"

        if not shell.prompt:
            output = TerminalContext._truncate_pane_output(output)
            return f"<terminal_history>\n{output}\n</terminal_history>"

        commands = TerminalContext._get_commands(output, shell)
        commands = TerminalContext._truncate_commands(commands[:MAX_COMMANDS])
        commands = list(reversed(commands))  # Order: Oldest to newest

        previous_commands = commands[:-1]
        last_command = commands[-1]

        context = "<terminal_history>\n"
        context += "<previous_commands>\n"
        context += "\n".join(
            TerminalContext._command_to_string(c, shell.prompt) 
            for c in previous_commands
        )
        context += "\n</previous_commands>\n"
        context += "\n<last_command>\n"
        context += TerminalContext._command_to_string(last_command, shell.prompt)
        context += "\n</last_command>"
        context += "\n</terminal_history>"

        return context

    @staticmethod
    def _get_pane_output() -> str:
        """Capture terminal pane output"""
        output_file = None
        output = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                output_file = temp_file.name

                if os.getenv("TMUX"):  # tmux session
                    cmd = ["tmux", "capture-pane", "-p", "-S", "-"]
                    with open(output_file, "w") as f:
                        run(cmd, stdout=f, text=True)
                elif os.getenv("STY"):  # screen session
                    cmd = ["screen", "-X", "hardcopy", "-h", output_file]
                    check_output(cmd, text=True)
                else:
                    return ""

                with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                    output = f.read()
        except CalledProcessError:
            pass
        finally:
            if output_file:
                os.remove(output_file)

        return output

    @staticmethod
    def _get_commands(pane_output: str, shell: Shell) -> List[Command]:
        """Extract commands from pane output"""
        commands = []  # Order: newest to oldest
        buffer = []
        
        for line in reversed(pane_output.splitlines()):
            if not line.strip():
                continue

            if shell.prompt.lower() in line.lower():
                command_text = line.split(shell.prompt, 1)[1].strip()
                command = Command(command_text, "\n".join(reversed(buffer)).strip())
                commands.append(command)
                buffer = []
                continue

            buffer.append(line)

        return commands[1:]  # Exclude the wut command itself

    @staticmethod
    def _truncate_commands(commands: List[Command]) -> List[Command]:
        """Truncate commands to fit within MAX_CHARS"""
        num_chars = 0
        truncated_commands = []
        
        for command in commands:
            command_chars = len(command.text)
            if command_chars + num_chars > MAX_CHARS:
                break
            num_chars += command_chars

            output = []
            for line in reversed(command.output.splitlines()):
                line_chars = len(line)
                if line_chars + num_chars > MAX_CHARS:
                    break

                output.append(line)
                num_chars += line_chars

            output = "\n".join(reversed(output))
            truncated_commands.append(Command(command.text, output))

        return truncated_commands

    @staticmethod
    def _truncate_pane_output(output: str) -> str:
        """Truncate pane output to fit within MAX_CHARS"""
        hit_non_empty_line = False
        lines = []  # Order: newest to oldest
        
        for line in reversed(output.splitlines()):
            if line and line.strip():
                hit_non_empty_line = True

            if hit_non_empty_line:
                lines.append(line)

        lines = lines[1:]  # Remove wut command
        output = "\n".join(reversed(lines))
        return output[-MAX_CHARS:].strip()

    @staticmethod
    def _command_to_string(command: Command, shell_prompt: Optional[str] = None) -> str:
        """Format command as string with prompt"""
        shell_prompt = shell_prompt if shell_prompt else "$"
        command_str = f"{shell_prompt} {command.text}"
        if command.output.strip():
            command_str += f"\n{command.output}"
        return command_str


class ShellManager:
    """Handles shell detection and information gathering"""
    
    @staticmethod
    def get_shell() -> Shell:
        """Get shell information"""
        name, path = ShellManager._get_shell_name_and_path()
        prompt = ShellManager._get_shell_prompt(name, path)
        return Shell(path, name, prompt)

    @staticmethod
    def _get_shell_name_and_path() -> Tuple[Optional[str], Optional[str]]:
        """Get shell name and path"""
        path = os.environ.get("SHELL") or os.environ.get("TF_SHELL")
        if shell_name := ShellManager._get_shell_name(path):
            return shell_name, path

        proc = Process(os.getpid())
        while proc is not None and proc.pid > 0:
            try:
                _path = proc.name()
            except TypeError:
                _path = proc.name

            if shell_name := ShellManager._get_shell_name(_path):
                return shell_name, _path

            try:
                proc = proc.parent()
            except TypeError:
                proc = proc.parent

        return None, path

    @staticmethod
    def _get_shell_name(shell_path: Optional[str] = None) -> Optional[str]:
        """Get shell name from path"""
        if not shell_path:
            return None

        if os.path.splitext(shell_path)[-1].lower() in SHELLS:
            return os.path.splitext(shell_path)[-1].lower()

        if os.path.splitext(shell_path)[0].lower() in SHELLS:
            return os.path.splitext(shell_path)[0].lower()

        if shell_path.lower() in SHELLS:
            return shell_path.lower()

        return None

    @staticmethod
    def _get_shell_prompt(shell_name: str, shell_path: str) -> Optional[str]:
        """Get shell prompt string"""
        shell_prompt = None
        try:
            if shell_name == "zsh":
                cmd = [shell_path, "-c", "print -P $PS1"]
                shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
            elif shell_name == "bash":
                cmd = ["echo", '"${PS1@P}"']
                shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
                if shell_prompt.strip() == '"${PS1@P}"':
                    return None
            elif shell_name == "fish":
                cmd = [shell_path, "fish_prompt"]
                shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
            elif shell_name in ["csh", "tcsh"]:
                cmd = [shell_path, "-c", "echo $prompt"]
                shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
            elif shell_name in ["pwsh", "powershell"]:
                cmd = [shell_path, "-c", "Write-Host $prompt"]
                shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
        except Exception:
            shell_prompt = None

        return shell_prompt.strip() if shell_prompt else None


class ErrorParser:
    """Handles parsing of error messages and file references"""
    
    @staticmethod
    def parse_error_output(output: str) -> set:
        """Parse output for file references"""
        file_refs = set()
        patterns = [
            r"File \"([^\"]+)\"",
            r"in ([^\s]+\.py)",
            r"([^\s]+\.\w+):\d+",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output)
            file_refs.update(matches)
            
        return file_refs


# Public API
def get_wut_context() -> str:
    """Get terminal context for wut functionality"""
    return TerminalContext.get_context()

def process_wut_output(output: str) -> set:
    """Process wut output for file references"""
    return ErrorParser.parse_error_output(output)
