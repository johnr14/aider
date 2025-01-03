import os
import re
from wut.wut import main as wut_main
from wut.utils import get_terminal_context, get_shell

def get_wut_context():
    if not (os.environ.get("TMUX") or os.environ.get("STY")):
        raise ValueError(
            "wut must be run inside a tmux or screen session to access terminal history"
        )
    
    shell = get_shell()
    return get_terminal_context(shell)

def process_wut_output(output):
    # Parse output for file references
    file_refs = set()
    # Add regex patterns to detect file references
    patterns = [
        r"File \"([^\"]+)\"",
        r"in ([^\s]+\.py)",
        r"([^\s]+\.\w+):\d+",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, output)
        file_refs.update(matches)
    return file_refs
import os
import re
import tempfile
from collections import namedtuple
from subprocess import check_output, run, CalledProcessError, DEVNULL
from typing import List, Optional, Tuple

from psutil import Process

Shell = namedtuple("Shell", ["path", "name", "prompt"])
Command = namedtuple("Command", ["text", "output"])

def get_shell_name(shell_path: Optional[str] = None) -> Optional[str]:
    SHELLS = ["bash", "fish", "zsh", "csh", "tcsh", "powershell", "pwsh"]
    if not shell_path:
        return None

    if os.path.splitext(shell_path)[-1].lower() in SHELLS:
        return os.path.splitext(shell_path)[-1].lower()

    if os.path.splitext(shell_path)[0].lower() in SHELLS:
        return os.path.splitext(shell_path)[0].lower()

    if shell_path.lower() in SHELLS:
        return shell_path.lower()

    return None

def get_shell_name_and_path() -> Tuple[Optional[str], Optional[str]]:
    path = os.environ.get("SHELL", None) or os.environ.get("TF_SHELL", None)
    if shell_name := get_shell_name(path):
        return shell_name, path

    proc = Process(os.getpid())
    while proc is not None and proc.pid > 0:
        try:
            _path = proc.name()
        except TypeError:
            _path = proc.name

        if shell_name := get_shell_name(_path):
            return shell_name, _path

        try:
            proc = proc.parent()
        except TypeError:
            proc = proc.parent

    return None, path

def get_shell_prompt(shell_name: str, shell_path: str) -> Optional[str]:
    shell_prompt = None
    try:
        if shell_name == "zsh":
            cmd = [
                shell_path,
                "-c",
                "print -P $PS1",
            ]
            shell_prompt = check_output(cmd, text=True, stderr=DEVNULL)
        elif shell_name == "bash":
            cmd = [
                "echo",
                '"${PS1@P}"',
            ]
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
    except:
        shell_prompt = None

    return shell_prompt.strip() if shell_prompt else None

def get_wut_context():
    if not (os.environ.get("TMUX") or os.environ.get("STY")):
        raise ValueError(
            "wut must be run inside a tmux or screen session to access terminal history"
        )
    
    shell = get_shell()
    return get_terminal_context(shell)

def get_shell() -> Shell:
    name, path = get_shell_name_and_path()
    prompt = get_shell_prompt(name, path)
    return Shell(path, name, prompt)

def get_terminal_context(shell: Shell) -> str:
    output = get_pane_output()
    if not output:
        return "<terminal_history>No terminal output found.</terminal_history>"

    if not shell.prompt:
        output = truncate_pane_output(output)
        context = f"<terminal_history>\n{output}\n</terminal_history>"
    else:
        commands = get_commands(output, shell)
        commands = truncate_commands(commands[:3])  # MAX_COMMANDS = 3
        commands = list(reversed(commands))  # Order: Oldest to newest

        previous_commands = commands[:-1]
        last_command = commands[-1]

        context = "<terminal_history>\n"
        context += "<previous_commands>\n"
        context += "\n".join(command_to_string(c, shell.prompt) for c in previous_commands)
        context += "\n</previous_commands>\n"
        context += "\n<last_command>\n"
        context += command_to_string(last_command, shell.prompt)
        context += "\n</last_command>"
        context += "\n</terminal_history>"

    return context

def process_wut_output(output):
    # Parse output for file references
    file_refs = set()
    # Add regex patterns to detect file references
    patterns = [
        r"File \"([^\"]+)\"",
        r"in ([^\s]+\.py)",
        r"([^\s]+\.\w+):\d+",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, output)
        file_refs.update(matches)
    return file_refs

def get_pane_output() -> str:
    output_file = None
    output = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = temp_file.name

            if os.getenv("TMUX"):  # tmux session
                cmd = [
                    "tmux",
                    "capture-pane",
                    "-p",
                    "-S",
                    "-",
                ]
                with open(output_file, "w") as f:
                    run(cmd, stdout=f, text=True)
            elif os.getenv("STY"):  # screen session
                cmd = ["screen", "-X", "hardcopy", "-h", output_file]
                check_output(cmd, text=True)
            else:
                return ""

            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                output = f.read()
    except CalledProcessError as e:
        pass

    if output_file:
        os.remove(output_file)

    return output

def get_commands(pane_output: str, shell: Shell) -> List[Command]:
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

def truncate_commands(commands: List[Command]) -> List[Command]:
    MAX_CHARS = 10000
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
        command = Command(command.text, output)
        truncated_commands.append(command)

    return truncated_commands

def truncate_pane_output(output: str) -> str:
    hit_non_empty_line = False
    lines = []  # Order: newest to oldest
    for line in reversed(output.splitlines()):
        if line and line.strip():
            hit_non_empty_line = True

        if hit_non_empty_line:
            lines.append(line)

    lines = lines[1:]  # Remove wut command
    output = "\n".join(reversed(lines))
    output = output[-10000:]  # MAX_CHARS
    output = output.strip()

    return output

def command_to_string(command: Command, shell_prompt: Optional[str] = None) -> str:
    shell_prompt = shell_prompt if shell_prompt else "$"
    command_str = f"{shell_prompt} {command.text}"
    command_str += f"\n{command.output}" if command.output.strip() else ""
    return command_str
