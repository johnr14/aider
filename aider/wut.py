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
