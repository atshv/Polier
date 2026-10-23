"""Files a shell command line would write, as far as a static look can tell.

write_targets() reads a command the way a guard sees it, before it runs: no
variables, no globbing, no knowledge of what a script or program does inside.
It finds redirections (`>`, `>>`, `&>`, `>|`, `<>`), `tee`, `cp`/`mv`/`install`/
`ln` targets, `rm`/`unlink`/`touch`/`truncate`, in-place `sed -i`/`perl -i`,
`dd of=`, and recurses into `bash -c`/`sh -c`/`eval`. `cd` within the line moves
the base folder for later relative paths. Everything else (interpreters,
build tools, git, xargs, find -exec, ...) is invisible here; the stop check
catches those writes after the fact.
"""
from __future__ import annotations

import os
import re
import shlex
from typing import List, NamedTuple, Optional, Tuple

OPS = ("&>>", "<<<", ">>", ">|", "&>", ">&", "<&", "<<", "<>", "&&", "||", "|&", ";;",
       ">", "<", "|", "&", ";", "(", ")")
SEPARATORS = {"&&", "||", "|&", ";;", "|", "&", ";", "(", ")"}
WRITE_REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<>"}
READ_REDIRECTS = {"<", "<<", "<<<"}
WRAPPERS = {"sudo", "env", "nohup", "time", "command", "exec", "nice", "ionice", "stdbuf", "doas"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
UNRESOLVED = re.compile(r"[$`*?\[{]")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
MAX_DEPTH = 4


class Target(NamedTuple):
    path: str     # absolute
    how: str      # write | delete
    command: str  # the program or redirection that writes


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies; their text is data, not commands."""
    out: List[str] = []
    pending: List[Tuple[str, bool]] = []
    for line in command.split("\n"):
        if pending:
            delimiter, tabs = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            continue
        out.append(line)
        pending += [(m.group(3), m.group(1) == "-") for m in HEREDOC.finditer(line) if "<<<" not in m.group(0)]
    return "\n".join(out)


def _lines(command: str) -> List[str]:
    """Split on newlines outside quotes."""
    lines, current, quote, escape = [], [], "", False
    for char in command:
        if escape:
            escape = False
        elif char == "\\" and quote != "'":
            escape = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "\n":
            lines.append("".join(current))
            current = []
            continue
        current.append(char)
    lines.append("".join(current))
    return lines


def _split_ops(token: str) -> List[str]:
    out = []
    while token:
        op = next((o for o in OPS if token.startswith(o)), token[0])
        out.append(op)
        token = token[len(op):]
    return out


def tokens(command: str) -> List[str]:
    """Shell words and operators; a ValueError means the line cannot be read (open quote)."""
    out: List[str] = []
    for line in _lines(_strip_heredocs(command)):
        lexer = shlex.shlex(line, posix=True, punctuation_chars="();<>|&")
        lexer.whitespace_split = True
        for token in lexer:
            if token and all(c in "();<>|&" for c in token):
                out += _split_ops(token)
            else:
                out.append(token)
        out.append(";")
    return out


def _segments(words: List[str]) -> List[List[str]]:
    segments, current = [], []
    for word in words:
        if word in SEPARATORS:
            if current:
                segments.append(current)
            current = []
            if word in "()":
                segments.append([word])
        else:
            current.append(word)
    if current:
        segments.append(current)
    return segments


def _options_and_args(args: List[str], with_value: Tuple[str, ...] = ()) -> Tuple[List[str], List[str]]:
    options, positional, i = [], [], 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional += args[i + 1:]
            break
        if arg.startswith("-") and arg != "-":
            options.append(arg)
            if arg in with_value and i + 1 < len(args):
                options.append(args[i + 1])
                i += 1
        else:
            positional.append(arg)
        i += 1
    return options, positional


def _in_place_files(args: List[str], perl: bool) -> Optional[List[str]]:
    """Files edited by `sed -i` / `perl -i`, or None without -i."""
    in_place, script_given, positional, i = False, False, [], 0
    while i < len(args):
        arg = args[i]
        if arg in ("-e", "--expression", "-f", "--file"):
            script_given = True
            i += 2
            continue
        short = arg.startswith("-") and not arg.startswith("--")
        if arg.startswith("--in-place") or (short and "i" in arg):
            in_place = True
        if perl and short and "e" in arg[1:]:  # perl -pie: the script follows
            script_given = True
            i += 2
            continue
        if not arg.startswith("-") or arg == "-":
            positional.append(arg)
        i += 1
    if not in_place:
        return None
    return positional if script_given else positional[1:]


def _command_targets(args: List[str]) -> List[Tuple[str, str, str, Optional[str]]]:
    """(path, how, command, source) written by one simple command, paths as written.
    `source` is set for a copy or move whose destination may be an existing folder."""
    while args and ASSIGNMENT.match(args[0]):
        args = args[1:]
    while args and os.path.basename(args[0]) in WRAPPERS:
        args = args[1:]
        while args and (args[0].startswith("-") or ASSIGNMENT.match(args[0])):
            args = args[1:]
    if not args:
        return []
    name, rest = os.path.basename(args[0]), args[1:]
    found: List[Tuple[str, str, str, Optional[str]]] = []
    if name == "tee":
        found += [(p, "write", name, None) for p in _options_and_args(rest)[1]]
    elif name in ("touch", "truncate"):
        found += [(p, "write", name, None) for p in _options_and_args(rest, ("-s", "--size", "-r", "--reference", "-d", "-t"))[1]]
    elif name in ("rm", "unlink"):
        found += [(p, "delete", name, None) for p in _options_and_args(rest)[1]]
    elif name in ("cp", "mv", "install", "ln"):
        options, positional = _options_and_args(rest, ("-t", "--target-directory", "-m", "--mode", "-o", "-g", "-S", "--suffix"))
        folder = None
        for i, opt in enumerate(options):
            if opt in ("-t", "--target-directory") and i + 1 < len(options):
                folder = options[i + 1]
            elif opt.startswith("--target-directory="):
                folder = opt.split("=", 1)[1]
        if folder is None and len(positional) > 2:
            folder = positional[-1]
        if folder is not None:
            sources = positional if folder not in positional[-1:] else positional[:-1]
            found += [(os.path.join(folder, os.path.basename(s.rstrip("/"))), "write", name, None) for s in sources]
        elif len(positional) == 2:
            sources = positional[:1]
            found.append((positional[1], "write", name, positional[0]))  # into it, if it is a folder
        else:
            sources = []
        if name == "mv":
            found += [(s, "delete", name, None) for s in sources]
    elif name in ("sed", "gsed", "perl"):
        files = _in_place_files(rest, perl=name == "perl")
        found += [(p, "write", f"{name} -i", None) for p in files or []]
    elif name == "dd":
        found += [(a[3:], "write", name, None) for a in rest if a.startswith("of=")]
    return found


def write_targets(command: str, cwd: Optional[str], _depth: int = 0) -> Tuple[List[Target], List[str]]:
    """Files `command` would write, resolved against `cwd`, and the targets it could not resolve.

    Unresolved are paths with variables, globs or command substitution, and relative
    paths after a `cd` that cannot be followed. A line that cannot be tokenized
    (open quote) gives ([], [command]).
    """
    try:
        words = tokens(command)
    except ValueError:
        return [], [command]
    targets: List[Target] = []
    unresolved: List[str] = []
    stack: List[Optional[str]] = []
    base = cwd

    def add(path: str, how: str, name: str, source: Optional[str] = None) -> None:
        if UNRESOLVED.search(path):
            unresolved.append(path)
            return
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            if base is None:
                unresolved.append(path)
                return
            path = os.path.join(base, path)
        path = os.path.abspath(path)
        if source and os.path.isdir(path):
            path = os.path.join(path, os.path.basename(source.rstrip("/")))
        targets.append(Target(path, how, name))

    for segment in _segments(words):
        if segment == ["("]:
            stack.append(base)
            continue
        if segment == [")"]:
            base = stack.pop() if stack else base
            continue
        args: List[str] = []
        i = 0
        while i < len(segment):
            word = segment[i]
            nxt = segment[i + 1] if i + 1 < len(segment) else None
            if word in WRITE_REDIRECTS or word in READ_REDIRECTS or word in (">&", "<&"):
                if args and args[-1].isdigit():
                    args.pop()  # file descriptor of `2>`
                if nxt is not None:
                    if word in WRITE_REDIRECTS or (word == ">&" and not (nxt.isdigit() or nxt == "-")):
                        add(nxt, "write", word)
                    i += 2
                    continue
            else:
                args.append(word)
            i += 1
        if not args:
            continue
        name = os.path.basename(args[0])
        if name in ("cd", "pushd"):
            dest = next((a for a in args[1:] if not a.startswith("-")), "~")
            if UNRESOLVED.search(dest):
                base = None
            else:
                dest = os.path.expanduser(dest)
                base = os.path.abspath(os.path.join(base, dest)) if base is not None or os.path.isabs(dest) else None
            continue
        if _depth < MAX_DEPTH and name in SHELLS and "-c" in args[1:]:
            index = args.index("-c")
            if index + 1 < len(args):
                inner, missed = write_targets(args[index + 1], base, _depth + 1)
                targets += inner
                unresolved += missed
            continue
        if _depth < MAX_DEPTH and name == "eval":
            inner, missed = write_targets(" ".join(args[1:]), base, _depth + 1)
            targets += inner
            unresolved += missed
            continue
        for path, how, prog, source in _command_targets(args):
            add(path, how, prog, source)
    return targets, unresolved
