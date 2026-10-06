"""Ekbasis as a shell guard (a prototype in 0.1.2; how it was measured: results/client_0.1.2 once it is).

What a command line will do to the files of a folder, before it runs: does any file's content get lost for good, does
each command fail. The state is a listing of the paths the commands could touch and the folders above them (names, types,
sizes, ages, symbolic links and where they point, hidden names) and NEVER a file's content: a file appears only with a
short fingerprint of its content, keyed anew for each check, so the model can tell equal contents apart without any
secret being copied into the prompt. What the shell decides before a command runs is written out as facts (how unquoted
patterns expand here, how unquoted spaces split names, which other files hold the same content), and a few plain-text
shell rules are added only for the command forms that need them (shell_notes), the way the git guard adds its notes.

Nothing is executed. The guard reads the folder (names, sizes, and file contents only to compute the fingerprints) and,
on Linux, `ls --version` and `bash --version` once, to name the versions. Lines with variables, command substitution,
subshells, here-documents or brace expansion are not evaluated: the state says so, and the listing may miss what those
parts touch.
"""
from __future__ import annotations

import glob as _glob
import hashlib
import hmac
import os
import platform
import re
import secrets
import stat
import subprocess
import tarfile
import time
import zipfile
from dataclasses import dataclass, field
from types import SimpleNamespace

from . import prompts as P
from .client import CannotJudge, Ekbasis

# ---------------------------------------------------------------- the prompt's fixed parts

SHELL_LOST = P.yes_no("Do these commands permanently lose any file content: content that was in some file before (a file "
                      "inside an archive counts) and afterwards is in no file at all?")


def shell_fails(k: int) -> dict:
    """Does command line k (1-based) fail?"""
    return P.yes_no(f"Does command {k} fail (end with a non-zero exit status)?")


NOTES_LABEL = "Shell rules for these commands"
LISTING_HEAD = ("Folder listing (paths relative to the folder the session starts in; only what the commands could touch "
                "and the folders above it, hidden names included):")

# ---------------------------------------------------------------- notes: one shell rule each, added only when needed

NOTE_SEQUENCE = ("In one line, `;` and new lines run the next command even if the previous one failed, `&&` runs it only "
                 "if the previous one succeeded and `||` only if it failed; so when `cd DIR` fails, `cd DIR; rm -rf *` "
                 "deletes in the folder the session started in. A line's exit status is that of the last command that ran.")
NOTE_SPLIT = ("The shell splits unquoted words at spaces before the command runs: `rm old notes.txt` passes two names, "
              "`old` and `notes.txt`; only quotes (`rm \"old notes.txt\"`) pass one.")
NOTE_GLOB_FIND = ("The shell expands an unquoted pattern before the command runs, in the folder the command runs in: in "
                  "`find . -name *.tmp`, if *.tmp matches files there, find receives their names instead of the pattern "
                  "(with two or more it fails with an error); only a pattern that matches nothing, or a quoted one, "
                  "reaches find as typed.")
NOTE_ZSH_NOMATCH = "In zsh, an unquoted pattern that matches nothing is an error: the command does not run and fails."
NOTE_TRUNCATE = ("`>` empties its target file before the command starts, so a command that reads a file and writes it "
                 "back with `>` in the same line (`sort f > f`, `cat f > f`, `sed ... f > f`, `grep -v x f > f`) reads an "
                 "empty file and leaves it empty; `>>` appends instead (but `cat f >> f` is refused, input file is output "
                 "file, and fails), and `sort -o f f` or `sed -i` edit the file safely.")
NOTE_NOCLOBBER = ("After `set -o noclobber` (or `set -C`), `>` refuses to overwrite an existing file and the command fails; "
                  "`>|` and `>>` still write.")
NOTE_REFUSE = ("These refuse, fail and change nothing there: rm without -r (or -d) on a folder, rmdir on a folder that is "
               "not empty, cp without -r on a folder (it skips it), mv or cp of a folder onto an existing file, mv or cp "
               "with several sources when the last name is not an existing folder, and ln without -f onto a name that "
               "exists.")
NOTE_RM_F = "rm -f ignores names that do not exist and exits with status 0 even when it removes nothing."
NOTE_CP_U = ("cp -u (--update) copies a file only when the destination is missing or older than the source; otherwise it "
             "leaves the destination as it is.")
NOTE_LINK_SLASH = ("A trailing slash makes a symbolic link to a folder mean the folder itself: `rm -r link/` deletes "
                   "everything inside the folder it points to and then fails on the link, which stays; `rm link` and "
                   "`rm -r link` remove only the link.")
NOTE_CP_MERGE = ("`cp -r SRC/. DEST` and `cp -r SRC/* DEST` copy SRC's contents into DEST, replacing files with the same "
                 "names there; `cp -r SRC DEST` copies the folder SRC into DEST when DEST exists (DEST/SRC), and makes DEST "
                 "a copy of SRC when it does not.")
NOTE_NO_CLOBBER_FLAG = "mv -n and cp -n (--no-clobber) never replace an existing file."
NOTE_NO_CLOBBER_94 = ("mv -n and cp -n (--no-clobber) never replace an existing file; with GNU coreutils 9.4, mv -n then exits "
                      "with status 1 and cp -n with status 0.")
NOTE_RSYNC = ("rsync copies the contents of a source written with a trailing slash (`rsync -a src/ dst/` puts src's files "
              "directly in dst) and the folder itself when written without one (`rsync -a src dst/` writes dst/src); "
              "files with the same names at that place are replaced, and --delete deletes, at that place only, the files "
              "the source does not have; -n or --dry-run changes nothing.")
NOTE_XARGS = ("xargs splits its input at spaces and new lines, so a name with a space reaches the command as two names "
              "(`-print0 | xargs -0` keeps names whole); xargs exits with status 123 when the command fails, and with no "
              "input at all GNU xargs still runs the command once, with no arguments.")
NOTE_TAR = ("tar -x replaces existing files with the archive's versions; with -k (--keep-old-files) it keeps the existing "
            "files, skips those members and exits with status 2; --skip-old-files skips them without an error.")

NOTES = [("cd_seq", NOTE_SEQUENCE), ("split", NOTE_SPLIT), ("glob_find", NOTE_GLOB_FIND), ("nomatch", NOTE_ZSH_NOMATCH),
         ("truncate", NOTE_TRUNCATE), ("noclobber", NOTE_NOCLOBBER), ("refuse", NOTE_REFUSE), ("rm_f", NOTE_RM_F),
         ("link_slash", NOTE_LINK_SLASH), ("cp_merge", NOTE_CP_MERGE), ("cp_u", NOTE_CP_U),
         ("no_clobber_flag", NOTE_NO_CLOBBER_FLAG), ("rsync", NOTE_RSYNC), ("xargs", NOTE_XARGS), ("tar_x", NOTE_TAR)]

# ---------------------------------------------------------------- reading a command line (no expansion, no execution)

CONTROL = ("&&", "||", ";;", "|&", ";", "|", "&", "\n")
REDIRECT = ("&>>", "&>", ">>", ">|", ">&", "<<<", "<<", "<>", "<&", ">", "<")
OPERATORS = sorted(CONTROL + REDIRECT, key=len, reverse=True)
TRUNCATING = {">", ">|", "&>"}
NOT_FILES = {"/dev/null", "/dev/stdout", "/dev/stderr", "-"}
BRACE_EXPANSION = re.compile(r"\{[^{}\s]*(,|\.\.)[^{}\s]*\}")

P_SUBST = "variables or command substitution ($, `)"
P_SUBSHELL = "subshells or grouping ( )"
P_GROUP = "grouping { }"
P_BRACE = "brace expansion {a,b}"
P_NESTED = "a nested shell or script string (bash -c, sh -c, eval, source)"
P_HEREDOC_OPEN = "a here-document without its closing line"
P_DYNAMIC_PATH = "a path that comes from a variable or command substitution ($, `)"
P_DYNAMIC_NAME = "a command name that comes from a variable or command substitution"
P_PROCSUB = "process substitution <( ) >( )"
P_QUOTE = "an unclosed quote"
P_SUDO = "sudo (the command runs as another user)"


@dataclass
class Word:
    text: str                 # after quote removal; no expansion
    raw: str                  # as typed
    glob: bool = False        # an unquoted *, ? or [
    quoted: bool = False      # some part was quoted or escaped
    dynamic: bool = False     # a $ or ` the shell would expand (the guard does not)
    start: int = -1           # where it is in the line (0.1.3; -1 for a here-document delimiter)
    end: int = -1


@dataclass
class Redirect:
    op: str                   # >, >>, >|, <, &>, &>>, <>, >&, <&, <<, <<<
    fd: str                   # the descriptor written before it ("" if none)
    target: Word | None


@dataclass
class Simple:
    words: list               # Words: the command and its arguments
    redirects: list           # Redirect
    joined_by: str            # the operator before it: "" (the first), ";", "\n", "&&", "||", "|", "|&", "&"


@dataclass
class Parsed:
    commands: list            # Simple, in order
    problems: list            # shell features the guard does not evaluate


def _heredoc_delim(line: str, i: int):
    """The delimiter after `<<` or `<<-` at i: (delimiter, strip tabs, quoted, raw, index after it) or None."""
    strip = line.startswith("-", i)
    j = i + 1 if strip else i
    m = re.match(r"[ \t]*(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|<>()]+))", line[j:])
    if not m:
        return None
    delim = m.group(1) if m.group(1) is not None else (m.group(2) if m.group(2) is not None else m.group(3).replace("\\", ""))
    quoted = m.group(3) is None or "\\" in m.group(3)
    return delim, strip, quoted, m.group(0).strip(), j + m.end()


def _skip_bodies(line: str, i: int, pending: list) -> tuple[int, bool]:
    """From i (the start of the line after a here-document's command line), skip each pending body up to its
    delimiter line; returns (where the next command starts, every body was closed)."""
    closed = True
    for delim, strip in pending:
        while True:
            if i >= len(line):
                closed = False
                break
            e = line.find("\n", i)
            cur = line[i:e if e >= 0 else len(line)]
            i = e + 1 if e >= 0 else len(line)
            if (cur.lstrip("\t") if strip else cur) == delim:
                break
    return i, closed


def lex(line: str, parens: bool = False):
    """The words and operators of a command line, quotes removed: (tokens, problems). A token is a Word or a tuple
    ("op", operator, fd). Here-document bodies are the command's input, not commands: they are skipped.
    parens=True (0.1.3) also gives each ( and ) as an ("op", "(" or ")", "") token, so a caller can follow subshells;
    the problem is recorded either way."""
    toks, problems, pending = [], [], []
    cur = {"text": [], "raw": [], "glob": False, "quoted": False, "dynamic": False, "in": False, "start": -1}

    def flush():
        if cur["in"]:
            toks.append(Word("".join(cur["text"]), "".join(cur["raw"]), cur["glob"], cur["quoted"], cur["dynamic"],
                             cur["start"], i))
        cur.update(text=[], raw=[], glob=False, quoted=False, dynamic=False, start=-1)
        cur["in"] = False

    def problem(p):
        if p not in problems:
            problems.append(p)

    def put(t, r):
        if not cur["in"]:
            cur["start"] = i
        cur["text"].append(t)
        cur["raw"].append(r)
        cur["in"] = True

    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t":
            flush()
            i += 1
            continue
        if ch == "#" and not cur["in"]:
            j = line.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "\\":
            if line.startswith("\\\n", i):
                i += 2
                continue
            if i + 1 < n:
                put(line[i + 1], line[i:i + 2])
                cur["quoted"] = True
            i += 2
            continue
        if ch == "'":
            j = line.find("'", i + 1)
            if j < 0:
                problem(P_QUOTE)
                j = n
            put(line[i + 1:j], line[i:j + 1])
            cur["quoted"] = True
            i = j + 1
            continue
        if ch == '"':
            j, buf = i + 1, []
            while j < n and line[j] != '"':
                c = line[j]
                if c == "\\" and j + 1 < n and line[j + 1] in '$`"\\\n':
                    if line[j + 1] != "\n":
                        buf.append(line[j + 1])
                    j += 2
                    continue
                if c in "$`":
                    cur["dynamic"] = True
                buf.append(c)
                j += 1
            if j >= n:
                problem(P_QUOTE)
            put("".join(buf), line[i:j + 1])
            cur["quoted"] = True
            i = j + 1
            continue
        if ch in "$`":
            cur["dynamic"] = True
            put(ch, ch)
            i += 1
            continue
        if ch in "()":
            problem(P_SUBSHELL)
            flush()
            if parens:
                toks.append(("op", ch, ""))
            i += 1
            continue
        if ch == "{":
            if BRACE_EXPANSION.match(line, i):
                problem(P_BRACE)
                cur["dynamic"] = True
            elif not cur["in"] and (i + 1 >= n or line[i + 1] in " \t\n"):
                problem(P_GROUP)
        op = next((o for o in OPERATORS if line.startswith(o, i)), None)
        if op:
            if op in ("<", ">") and line.startswith("(", i + 1):
                problem(P_PROCSUB)
            fd = ""
            if op in REDIRECT and cur["in"] and not cur["quoted"] and "".join(cur["raw"]).isdigit():
                fd = "".join(cur["text"])
                cur.update(text=[], raw=[], glob=False, quoted=False, dynamic=False, start=-1)
                cur["in"] = False
            else:
                flush()
            toks.append(("op", op, fd))
            i += len(op)
            if op == "<<":
                d = _heredoc_delim(line, i)
                if d is None:
                    problem(P_QUOTE)
                    continue
                delim, strip, quoted, raw, i = d
                toks.append(Word(delim, raw, quoted=quoted))
                pending.append((delim, strip))
            elif op == "\n" and pending:
                i, closed = _skip_bodies(line, i, pending)
                pending = []
                if not closed:
                    problem(P_HEREDOC_OPEN)
            continue
        if ch in "*?[":
            cur["glob"] = True
        put(ch, ch)
        i += 1
    flush()
    if pending:
        problem(P_HEREDOC_OPEN)
    return toks, problems


def parse(line: str) -> Parsed:
    """The simple commands of a command line, with their redirections and the operators that join them."""
    toks, problems = lex(line)
    cmds, words, redirs, joined = [], [], [], ""
    i = 0
    while i < len(toks):
        t = toks[i]
        if isinstance(t, tuple):
            _, op, fd = t
            if op in CONTROL:
                if words or redirs:
                    cmds.append(Simple(words, redirs, joined))
                    words, redirs = [], []
                joined = op
            else:
                target = toks[i + 1] if i + 1 < len(toks) and isinstance(toks[i + 1], Word) else None
                redirs.append(Redirect(op, fd, target))
                if target is not None:
                    i += 1
        else:
            words.append(t)
        i += 1
    if words or redirs:
        cmds.append(Simple(words, redirs, joined))
    return Parsed(cmds, problems)


# ---------------------------------------------------------------- what a command could touch

PREFIXES = {"nohup", "nice", "time", "command", "builtin", "exec", "env"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
READS = {"cat", "head", "tail", "sort", "uniq", "wc", "tr", "cut", "paste", "nl", "tac", "rev", "grep", "egrep", "fgrep",
         "awk", "sed", "perl", "less", "more", "diff", "cmp", "md5sum", "sha1sum", "sha256sum", "file", "stat", "ls", "du",
         "readlink", "realpath", "jq", "xxd", "od", "strings", "column"}
FILE_CMDS = {"rm", "rmdir", "unlink", "mv", "cp", "ln", "touch", "mkdir", "tee", "truncate", "shred", "rsync", "tar",
             "unzip", "zip", "gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "chmod", "chown", "chgrp", "install",
             "split", "dd", "find", "cd"} | READS
FIRST_NOT_PATH = {"sed", "grep", "egrep", "fgrep", "awk", "chmod", "chown", "chgrp", "perl", "tr", "jq"}
RECURSIVE = {"rm": "rR", "cp": "rRa", "chmod": "R", "chown": "R", "chgrp": "R", "zip": "r", "grep": "rR"}
ALWAYS_TREE = {"rsync", "find", "mv", "tar", "du", "unzip"}
COPY_LIKE = {"cp", "mv", "rsync", "install", "ln", "tar", "unzip"}
SHORT_VALUE = {"tar": "fCbHKLNTVgX", "sort": "otkSTy", "sed": "efl", "grep": "efmABCD", "egrep": "efmABCD",
               "fgrep": "efmABCD", "cp": "tS", "mv": "tS", "ln": "tS", "install": "mogtS", "truncate": "sr", "mkdir": "m",
               "touch": "drt", "head": "nc", "tail": "ncs", "split": "lbnaC", "perl": "eEIlM", "awk": "Fvf", "unzip": "dxP",
               "gzip": "S", "gunzip": "S", "shred": "ns", "rsync": "efTB", "xargs": "aEeIiLlnPsd", "du": "dBt",
               "cut": "bcdf", "zip": "bnt"}
SHORT_PATH = {"tar": "fC", "sort": "oT", "sed": "f", "grep": "f", "egrep": "f", "fgrep": "f", "cp": "t", "mv": "t",
              "ln": "t", "install": "t", "truncate": "r", "touch": "r", "awk": "f", "unzip": "d", "rsync": "T"}
LONG_PATH = {"--target-directory", "--output", "--file", "--directory", "--reference", "--files-from", "--backup-dir",
             "--temp-dir", "--log-file", "--exclude-from", "--include-from"}
LONG_VALUE = LONG_PATH | {"--suffix", "--exclude", "--include", "--mode", "--owner", "--group", "--size", "--lines",
                          "--bytes", "--format", "--chmod", "--rsh", "--key", "--field-separator", "--max-count",
                          "--regexp", "--expression"}
FIND_PATH_ARGS = {"-newer", "-anewer", "-cnewer", "-samefile", "-fprint", "-fprint0", "-fprintf", "-fls"}
NO_FILE_ARGS = {"echo", "printf", "true", "false", ":", "test", "[", "sleep", "date", "export", "local", "declare",
                "read", "unset", "shift", "return", "exit", "wait", "kill", "type", "which", "hash", "alias"}
NESTED = {"bash", "sh", "zsh", "dash", "ksh", "eval", "source", "."}
MESSAGE_OPTS = {"-m", "--message", "-F", "--file"}
FIND_PATTERN_ARGS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex", "-lname",
                     "-ilname"}


def command_name(words: list) -> tuple[str, int, list]:
    """(name, index of the command word, problems): leading assignments and prefixes (sudo, env, nohup...) skipped."""
    problems, i = [], 0
    while i < len(words):
        w = words[i].text
        if ASSIGN.match(w):
            i += 1
        elif w == "sudo":
            problems.append(P_SUDO)
            i += 1
            while i < len(words) and words[i].text.startswith("-"):
                i += 1
        elif w in PREFIXES:
            i += 1
            while i < len(words) and (words[i].text.startswith("-") or ASSIGN.match(words[i].text)):
                i += 1
        else:
            return os.path.basename(w), i, problems
    return "", len(words), problems


def split_args(name: str, args: list) -> tuple[list, set, list]:
    """(positional arguments, option names and letters, [(option, value, is a path)]). `--` ends the options."""
    pos, opts, vals = [], set(), []
    short_v, short_p = SHORT_VALUE.get(name, ""), SHORT_PATH.get(name, "")
    if name == "tar" and args and not args[0].startswith("-") and re.fullmatch(r"[A-Za-z]+", args[0]):
        args = ["-" + args[0]] + list(args[1:])  # old-style tar: `tar xzf a.tgz`
    i, in_opts = 0, True
    while i < len(args):
        a = args[i]
        if in_opts and a == "--":
            in_opts = False
        elif in_opts and a.startswith("--") and len(a) > 2:
            key = a.split("=", 1)[0]
            opts.add(key)
            if "=" in a:
                vals.append((key, a.split("=", 1)[1], key in LONG_PATH))
            elif key in LONG_VALUE and i + 1 < len(args):
                vals.append((key, args[i + 1], key in LONG_PATH))
                i += 1
        elif in_opts and a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:]):
                opts.add(ch)
                if ch in short_v:
                    rest = a[k + 2:]
                    if rest:
                        vals.append((ch, rest, ch in short_p))
                    elif i + 1 < len(args):
                        vals.append((ch, args[i + 1], ch in short_p))
                        i += 1
                    break
        else:
            pos.append(a)
        i += 1
    return pos, opts, vals


def find_parts(args: list) -> tuple[list, list]:
    """find's starting points (default .) and the paths its expression names."""
    starts, paths, i = [], [], 0
    while i < len(args) and args[i] in ("-H", "-L", "-P"):
        i += 1
    while i < len(args) and not (args[i].startswith("-") or args[i] in ("(", "!", ")")):
        starts.append(args[i])
        i += 1
    while i < len(args):
        if args[i] in FIND_PATH_ARGS and i + 1 < len(args):
            paths.append(args[i + 1])
            i += 1
        i += 1
    return starts or ["."], paths


# ---------------------------------------------------------------- reading patterns and find expressions (no execution)

POSIX_CLASS = {"alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z",
               "space": " \\t\\n\\r\\f\\v", "blank": " \\t", "xdigit": "0-9A-Fa-f"}


def _scan_delim(s: str, i: int, d: str):
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == d:
            return i
        i += 1
    return None


def sed_patterns(script: str) -> list:
    """The regular expressions of a sed script's `s` commands and `/re/` addresses."""
    out, i, n = [], 0, len(script)
    while i < n:
        c = script[i]
        if c == "/":
            j = _scan_delim(script, i + 1, "/")
            if j is None:
                break
            out.append(script[i + 1:j])
            i = j + 1
        elif c == "s" and i + 1 < n and not script[i + 1].isalnum() and not script[i + 1].isspace():
            d = script[i + 1]
            j = _scan_delim(script, i + 2, d)
            if j is None:
                break
            out.append(script[i + 2:j].replace("\\" + d, d) if d != "/" else script[i + 2:j])
            k2 = _scan_delim(script, j + 1, d)
            if k2 is None:
                break
            i = k2 + 1
            while i < n and script[i] not in ";\n":
                i += 1
        else:
            i += 1
    return out


def to_python_regex(p: str, extended: bool = False) -> str | None:
    """A POSIX basic (or extended) regular expression as a Python one, for the common cases; None otherwise."""
    out, i, n = [], 0, len(p)
    while i < n:
        c = p[i]
        if c == "\\":
            if i + 1 >= n:
                return None
            d = p[i + 1]
            if d.isdigit():
                return None
            if not extended and d in "(){}|+?":
                out.append(d)
            elif d in "<>":
                out.append(r"\b")
            elif d in "nt":
                out.append("\\" + d)
            elif d in "wWsSb":
                out.append("\\" + d)
            else:
                out.append(re.escape(d))
            i += 2
            continue
        if c == "[":
            j, body = i + 1, "["
            if j < n and p[j] == "^":
                body, j = body + "^", j + 1
            if j < n and p[j] == "]":
                body, j = body + "\\]", j + 1
            while j < n and p[j] != "]":
                if p.startswith("[:", j):
                    e = p.find(":]", j)
                    cls = POSIX_CLASS.get(p[j + 2:e]) if e > 0 else None
                    if cls is None:
                        return None
                    body, j = body + cls, e + 2
                    continue
                body += "\\\\" if p[j] == "\\" else ("\\[" if p[j] == "[" else p[j])
                j += 1
            if j >= n:
                return None
            out.append(body + "]")
            i = j + 1
            continue
        out.append(c if extended or c not in "(){}|+?" else re.escape(c))
        i += 1
    return "".join(out)


def iter_files(path: str, recursive: bool, cap: int):
    """The regular files a command reads at path (a file, or with recursion every file under a folder)."""
    if os.path.isfile(path):
        yield path
        return
    if recursive and os.path.isdir(path):
        n = 0
        for dp, dns, fns in os.walk(path):
            dns.sort()
            if ".git" in dns:
                dns.remove(".git")
            for fn in sorted(fns):
                f = os.path.join(dp, fn)
                if os.path.isfile(f) and not os.path.islink(f):
                    yield f
                    n += 1
                    if n >= cap:
                        return


FIND_OK = {"-name", "-iname", "-type", "-maxdepth", "-mindepth", "-print", "-print0"}


def find_names(argv: list, base: str, cap: int = 5000) -> list | None:
    """The paths `find` prints here for the expressions the guard can follow; None for any other expression."""
    starts, i = [], 0
    while i < len(argv) and argv[i] in ("-H", "-P"):
        i += 1
    while i < len(argv) and not (argv[i].startswith("-") or argv[i] in ("(", "!", ")")):
        starts.append(argv[i])
        i += 1
    name = iname = typ = None
    mind, maxd = 0, None
    while i < len(argv):
        a = argv[i]
        if a not in FIND_OK:
            return None
        if a in ("-print", "-print0"):
            i += 1
            continue
        if i + 1 >= len(argv):
            return None
        v = argv[i + 1]
        try:
            if a == "-name":
                name = v
            elif a == "-iname":
                iname = v
            elif a == "-type":
                if v not in ("f", "d", "l"):
                    return None
                typ = v
            elif a == "-maxdepth":
                maxd = int(v)
            else:
                mind = int(v)
        except ValueError:
            return None
        i += 2
    import fnmatch
    out = []
    for st in starts or ["."]:
        root = os.path.join(base, st)
        if not os.path.lexists(root):
            continue
        cands = [(root, 0)]
        if os.path.isdir(root) and not os.path.islink(root):
            for dp, dns, fns in os.walk(root):
                dns.sort()
                d0 = 0 if dp == root else os.path.relpath(dp, root).count(os.sep) + 1
                cands += [(os.path.join(dp, x), d0 + 1) for x in sorted(dns + fns)]
                if maxd is not None and d0 + 1 >= maxd:
                    dns[:] = []
                if len(cands) > cap:
                    return None
        for path, depth in cands:
            if depth < mind or (maxd is not None and depth > maxd):
                continue
            bn = os.path.basename(path.rstrip("/")) if path != root else (os.path.basename(st.rstrip("/")) or st)
            if name is not None and not fnmatch.fnmatchcase(bn, name):
                continue
            if iname is not None and not fnmatch.fnmatchcase(bn.lower(), iname.lower()):
                continue
            if typ == "f" and not (os.path.isfile(path) and not os.path.islink(path)):
                continue
            if typ == "d" and not (os.path.isdir(path) and not os.path.islink(path)):
                continue
            if typ == "l" and not os.path.islink(path):
                continue
            out.append(st if path == root else os.path.join(st, os.path.relpath(path, root)))
    return out


# ---------------------------------------------------------------- the folder, without contents

def _key(salt) -> bytes:
    if salt is None:
        return secrets.token_bytes(16)
    return salt if isinstance(salt, bytes) else str(salt).encode()


def _fp(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()[:8]


def _read(path: str, cap: int) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read(cap)
    except OSError:
        return None


ARCHIVE = re.compile(r"\.(tar|tgz|tar\.gz|tar\.bz2|tbz2|tar\.xz|txz|zip)$", re.I)


def archive_members(path: str, key: bytes, max_members: int = 200, cap: int = 16 << 20) -> list | None:
    """[(member name, fingerprint)] of a tar or zip file's regular files ("" for empty ones); None if unreadable."""
    out = []
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                for info in z.infolist()[:max_members]:
                    if not info.is_dir():
                        with z.open(info) as f:
                            data = f.read(cap)
                        out.append((info.filename, _fp(key, data) if data else ""))
        else:
            with tarfile.open(path, "r:*") as t:
                for m in t.getmembers()[:max_members]:
                    if m.isfile():
                        f = t.extractfile(m)
                        data = f.read(cap) if f else b""
                        out.append((m.name, _fp(key, data) if data else ""))
    except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError, RuntimeError, ValueError):
        return None
    return out


@dataclass
class Folder:
    """A bounded scan of the starting folder: each file's fingerprint and each archive's members, for the 'same content
    elsewhere' facts and the count of what is not listed. Contents are read only to compute fingerprints."""
    root: str
    key: bytes
    fps: dict = field(default_factory=dict)        # relative path -> fingerprint ("" for an empty file)
    members: dict = field(default_factory=dict)    # relative path of an archive -> [(member, fingerprint)]
    complete: bool = True

    @classmethod
    def scan(cls, root: str, key: bytes, max_files: int = 5000, max_bytes: int = 256 << 20, file_cap: int = 16 << 20):
        f, used, nfiles = cls(root, key), 0, 0
        for dp, dns, fns in os.walk(root):
            dns.sort()
            if ".git" in dns:
                dns.remove(".git")
            for fn in sorted(fns):
                full = os.path.join(dp, fn)
                try:
                    st = os.lstat(full)
                except OSError:
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
                nfiles += 1
                if nfiles > max_files or used + min(st.st_size, file_cap) > max_bytes:
                    f.complete = False
                    return f
                data = _read(full, file_cap) if st.st_size else b""
                if data is None:
                    continue
                used += len(data)
                rel = os.path.relpath(full, root)
                f.fps[rel] = _fp(key, data) if data else ""
                if ARCHIVE.search(fn) and st.st_size <= 50 << 20:
                    m = archive_members(full, key)
                    if m:
                        f.members[rel] = m
        return f


def _age(mtime: float) -> str:
    days = int((time.time() - mtime) // 86400)
    return "today" if days < 1 else ("1 day ago" if days == 1 else f"{days} days ago")


def _q(p: str) -> str:
    return f'"{p}"' if " " in p else p


# ---------------------------------------------------------------- the machine

_VERSIONS: dict = {}


def _version(cmd: list, pattern: str, fmt: str) -> str | None:
    """A tool's version, formatted with fmt. The cache keeps each command's raw output (0.1.3): 0.1.2 cached the
    formatted text by command line only, so the first format read won ("9.4" where the rules say "GNU coreutils 9.4")."""
    k = " ".join(cmd)
    if k not in _VERSIONS:
        try:
            _VERSIONS[k] = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            _VERSIONS[k] = None
    out = _VERSIONS[k]
    m = re.search(pattern, out) if out else None
    return fmt.format(m.group(1)) if m else None


def platform_text(shell: str) -> str:
    """The machine and its tools, as the rules name them (versions read once, on Linux)."""
    if platform.system() == "Linux":
        core = _version(["ls", "--version"], r"coreutils\)?\s*([\d.]+)", "GNU coreutils {}") or "GNU coreutils"
        sh = _version([shell, "--version"], r"version\s+(\d+\.\d+)", shell + " {}") or shell
        return f"a Linux machine ({sh} with default options, {core}, findutils, sed, tar, rsync)"
    if platform.system() == "Darwin":
        return f"a macOS machine ({shell} with default options; the BSD versions of cp, mv, rm, find and sed)"
    return f"a {platform.system() or 'Unix'} machine ({shell} with default options)"


def default_shell() -> str:
    s = os.path.basename(os.environ.get("SHELL", ""))
    return s if s in ("bash", "zsh") else "bash"


def shell_rules(shell: str, where: str | None = None) -> str:
    return (f"You are looking at a folder on {where or platform_text(shell)}. The commands below are run in order in one "
            f"{shell} session that starts in this folder; each command runs even if an earlier one failed, nothing asks "
            "for confirmation, and you own every file. The listing shows the files and folders the commands could touch "
            "and the folders above them, hidden ones included; a file's content is shown only as a fingerprint, and equal "
            "fingerprints mean equal content.")


# ---------------------------------------------------------------- the state

@dataclass
class ShellView:
    rules: str
    state: str
    commands: list
    parsed: list                                 # Parsed, one per command line
    info: dict = field(default_factory=dict)     # what shell_notes needs
    unread: list = field(default_factory=list)   # what the guard could not evaluate
    touched: dict = field(default_factory=dict)  # path -> "self" | "tree" (relative to the folder, or absolute)


class _Reader:
    """Walks the command lines once: expansions, the paths each command could touch, the notes' triggers."""

    def __init__(self, root: str, shell: str, key: bytes, max_members: int):
        self.root, self.shell, self.key, self.max_members = root, shell, key, max_members
        self.touched, self.facts, self.unread = {}, [], []
        self.info = {k: False for k, _ in NOTES}
        self.star_source = False
        self.applied = []  # facts about how a command's arguments apply here (rsync targets, pattern counts, find | xargs)

    def rel(self, p: str, base: str) -> str:
        full = os.path.normpath(os.path.join(base, os.path.expanduser(p)))
        r = os.path.relpath(full, self.root)
        return full if r == ".." or r.startswith(".." + os.sep) else r

    def full(self, r: str) -> str:
        return r if os.path.isabs(r) else os.path.normpath(os.path.join(self.root, r))

    def touch(self, r: str, how: str = "self"):
        if self.touched.get(r) != "tree":
            self.touched[r] = how

    def expand(self, k: int, words: list, base: str) -> list:
        """The arguments after the shell's expansions the guard can do (unquoted patterns, ~); facts recorded."""
        argv = []
        for w in words:
            if w.dynamic:
                argv.append(None)  # a part the guard does not evaluate: not a path it can name
            elif w.glob and not w.quoted:
                pat = os.path.expanduser(w.text)
                hits = sorted(_glob.glob(pat if os.path.isabs(pat) else os.path.join(base, pat)))
                hits = hits if os.path.isabs(pat) else [os.path.relpath(h, base) for h in hits]
                self.facts.append(f"in command {k}, {w.text} " + (f"expands to {' '.join(_q(h) for h in hits)}" if hits else
                                                                  "matches nothing here and stays as typed"))
                if not hits and self.shell == "zsh":
                    self.info["nomatch"] = True
                argv += hits or [w.text]
            else:
                argv.append(os.path.expanduser(w.text) if w.raw.startswith("~") else w.text)
        return argv

    def split_names(self, k: int, words: list, base: str):
        """Unquoted words that, joined with spaces, name a path that exists here."""
        plain = [w for w in words if not (w.quoted or w.glob or w.dynamic or w.text.startswith("-"))]
        for a in range(len(plain)):
            for b in range(a + 2, min(len(plain), a + 4) + 1):
                joined = " ".join(w.text for w in plain[a:b])
                if os.path.lexists(os.path.join(base, joined)):
                    self.info["split"] = True
                    self.facts.append(f"in command {k}, the unquoted words {joined} are passed as {b - a} separate names "
                                      f"({', '.join(w.text for w in plain[a:b])}), and \"{joined}\" exists here")
                    self.touch(self.rel(joined, base))

    def read_line(self, k: int, parsed: Parsed):
        for p in parsed.problems:
            self.unread.append(f"command {k}: {p}")
        base, cmds = self.root, parsed.commands
        pipe_inputs, pipe_outputs, pipe_appends, prev = set(), set(), set(), None
        for j, s in enumerate(cmds):
            if s.joined_by not in ("|", "|&"):
                pipe_inputs, pipe_outputs, pipe_appends, prev = set(), set(), set(), None
            name, at, probs = command_name(list(s.words))
            for p in probs:
                self.unread.append(f"command {k}: {p}")
            args_w = s.words[at + 1:]
            self.dynamic_parts(k, name, s, at, args_w)
            if name == "find":
                for i, w in enumerate(args_w[:-1]):
                    if w.text in FIND_PATTERN_ARGS and args_w[i + 1].glob and not args_w[i + 1].quoted:
                        self.info["glob_find"] = True
            argv = self.expand(k, args_w, base)
            self.split_names(k, args_w, base)
            known = [a for a in argv if a is not None]
            nxt = cmds[j + 1] if j + 1 < len(cmds) else None
            if name == "cd" and nxt is not None and nxt.joined_by in (";", "\n"):
                self.info["cd_seq"] = True
            if s.joined_by == "||":
                self.info["cd_seq"] = True
            if name == "set" and ("noclobber" in known or "-C" in known):
                self.info["noclobber"] = True
            self.star_source = any(w.glob and not w.quoted and re.search(r"/\.?\*$", w.text) for w in args_w)
            inputs = self.read_command(name, known, base, k)
            pipe_inputs |= inputs
            if name == "xargs" and prev is not None and prev[0] == "find":
                self.find_into_xargs(k, prev[1], prev[2], known)
            prev = (name, known, base)
            for rd in s.redirects:
                if rd.target is None or rd.target.dynamic or rd.op in ("<<", "<<<", ">&", "<&") or rd.target.text in NOT_FILES:
                    continue
                r = self.rel(rd.target.text, base)
                self.touch(r)
                if rd.op == "<":
                    pipe_inputs.add(r)
                elif rd.op in TRUNCATING:
                    pipe_outputs.add(r)
                elif rd.op in (">>", "&>>"):
                    pipe_appends.add(r)
            if pipe_inputs & (pipe_outputs | pipe_appends):
                self.info["truncate"] = True
            if name == "cd":
                pos = split_args("cd", known)[0]
                target = pos[0] if pos else os.path.expanduser("~")
                tfull = os.path.normpath(os.path.join(base, os.path.expanduser(target)))
                if os.path.isdir(tfull):
                    base = tfull

    def dynamic_parts(self, k: int, name: str, s: Simple, at: int, args_w: list):
        """Parts of one simple command the guard cannot evaluate: a command name or a path from a variable or a
        substitution, a nested shell or script string. Values of a commit message (-m) and arguments of commands that
        never take files (echo, printf, ...) do not count."""
        if at < len(s.words) and s.words[at].dynamic:
            self.unread.append(f"command {k}: {P_DYNAMIC_NAME}")
        if name in NESTED and (name in ("eval", "source", ".") or any(w.text == "-c" for w in args_w)):
            self.unread.append(f"command {k}: {P_NESTED}")
        if name == "xargs" and any(w.text in NESTED for w in args_w):
            self.unread.append(f"command {k}: {P_NESTED}")
        if name not in NO_FILE_ARGS:
            for i, w in enumerate(args_w):
                if w.dynamic and not (i > 0 and args_w[i - 1].text in MESSAGE_OPTS):
                    self.unread.append(f"command {k}: {P_DYNAMIC_PATH}")
                    break
        if any(rd.target is not None and rd.target.dynamic and rd.op != "<<" for rd in s.redirects):
            self.unread.append(f"command {k}: {P_DYNAMIC_PATH}")

    def find_into_xargs(self, k: int, find_argv: list, base: str, xargs_argv: list):
        """What `find ... | xargs ...` passes here, for find expressions the guard can follow (-name, -iname, -type,
        -maxdepth, -mindepth, -print, -print0): names split at spaces, or no name at all."""
        names = find_names(find_argv, base)
        if names is None:
            return
        xpos, xopts, _ = split_args("xargs", xargs_argv)
        whole = bool(xopts & {"0", "--null", "d", "--delimiter", "I", "i", "--replace"})
        empty_ok = bool(xopts & {"r", "--no-run-if-empty"})
        shown = ", ".join(_q(n) for n in names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
        if not names:
            self.applied.append(f"in command {k}, find lists no name here" + ("" if empty_ok else
                                ", so xargs runs the command once with no arguments"))
        elif any(c.isspace() for n in names for c in n) and not whole:
            parts = [x for n in names[:2] for x in n.split()]
            self.applied.append(f"in command {k}, find lists {len(names)} name{'s' if len(names) > 1 else ''} here ({shown}); "
                                f"xargs passes them split at spaces ({', '.join(parts)})")
        else:
            self.applied.append(f"in command {k}, find lists {len(names)} name{'s' if len(names) > 1 else ''} here ({shown})")

    def patterns(self, k: int, name: str, pos: list, opts: set, vals: list, base: str):
        """How many lines a sed or grep pattern from the command matches in the files it names (counts only, never
        the lines)."""
        if name == "sed":
            explicit = [v for o, v, _ in vals if o in ("e", "--expression")]
            if any(o in ("f", "--file") for o, _, _ in vals):
                return
            files = pos if explicit else pos[1:]
            extended = bool(opts & {"E", "r", "--regexp-extended"})
            pats = [(p, to_python_regex(p, extended)) for sc in (explicit or pos[:1]) for p in sed_patterns(sc)][:3]
            label, flags, invert, recursive = "sed's pattern", 0, False, False
        else:
            explicit = [v for o, v, _ in vals if o in ("e", "--regexp")]
            if any(o in ("f", "--file") for o, _, _ in vals):
                return
            files = pos if explicit else pos[1:]
            recursive = bool(opts & {"r", "R", "--recursive", "--dereference-recursive"})
            if not files and recursive:
                files = ["."]
            fixed = name == "fgrep" or bool(opts & {"F", "--fixed-strings"})
            extended = name == "egrep" or bool(opts & {"E", "P", "--extended-regexp", "--perl-regexp"})
            pats = []
            for raw in (explicit or pos[:1])[:3]:
                py = re.escape(raw) if fixed else to_python_regex(raw, extended)
                if py is not None and opts & {"w", "--word-regexp"}:
                    py = rf"(?<!\w)(?:{py})(?!\w)"
                if py is not None and opts & {"x", "--line-regexp"}:
                    py = rf"^(?:{py})$"
                pats.append((raw, py))
            label = "grep's pattern"
            flags = re.I if opts & {"i", "y", "--ignore-case"} else 0
            invert = bool(opts & {"v", "--invert-match"})
        for raw, py in pats:
            if py is None:
                continue
            try:
                cre = re.compile(py, flags)
            except re.error:
                continue
            counts = []
            for f in files[:4]:
                for path in iter_files(os.path.join(base, os.path.expanduser(f)), recursive, 2000):
                    data = _read(path, 16 << 20)
                    if data is None:
                        continue
                    lines = data.decode(errors="replace").splitlines()
                    counts.append((os.path.relpath(path, base), sum(1 for l in lines if bool(cre.search(l)) != invert)))
            if not counts:
                continue
            what = "selects" if invert else "matches"
            if len(counts) == 1:
                p, n = counts[0]
                self.applied.append(f"in command {k}, {label} \"{raw}\" {what} "
                                    + (f"{n} line{'s' if n != 1 else ''} of {_q(p)}" if n else f"no line of {_q(p)}"))
            else:
                hit = [(p, n) for p, n in counts if n]
                total = sum(n for _, n in hit)
                self.applied.append(f"in command {k}, {label} \"{raw}\" {what} "
                                    + (f"{total} line{'s' if total != 1 else ''} in {len(hit)} of the {len(counts)} files"
                                       if hit else f"no line in the {len(counts)} files"))

    def rsync_targets(self, k: int, pos: list, opts: set, base: str):
        if len(pos) < 2:
            return
        dest, dry = pos[-1], bool(opts & {"n", "--dry-run"})
        delete = any(o.startswith("--delete") for o in opts)
        for src in pos[:-1]:
            full = os.path.join(base, src)
            if not os.path.isdir(full):
                continue
            slash = src.endswith("/")
            where = dest.rstrip("/") or dest
            if not slash:
                where = os.path.join(where, os.path.basename(src.rstrip("/")))
            what = f"the contents of {_q(src)}" if slash else f"the folder {_q(src.rstrip('/'))} itself"
            fact = f"in command {k}, rsync copies {what} into {_q(where + '/')}, replacing same-named files there"
            if delete:
                fact += f"; --delete deletes the files in {_q(where + '/')} that {_q(src.rstrip('/'))} does not have"
            if dry:
                fact += "; it is a dry run (-n), so nothing changes"
            self.applied.append(fact)

    def read_command(self, name: str, argv: list, base: str, k: int = 0) -> set:
        """Touch what one simple command names; returns the files it reads (for the truncation note)."""
        if name == "xargs":
            self.info["xargs"] = True
            pos = split_args("xargs", argv)[0]
            if pos:
                inner = os.path.basename(pos[0])
                return self.read_command(inner, pos[1:], base, k)
            return set()
        pos, opts, vals = split_args(name, argv)
        tree = name in ALWAYS_TREE or any(ch in opts for ch in RECURSIVE.get(name, "")) or \
            bool(opts & {"--recursive", "--archive"})
        paths, reads = [], set()
        if name == "find":
            starts, fpaths = find_parts(argv)
            paths = starts + fpaths
        elif name in FILE_CMDS:
            explicit = any(v[0] in ("e", "f", "--expression", "--file", "--regexp") for v in vals)
            paths = pos[1:] if name in FIRST_NOT_PATH and not explicit else list(pos)
            if name in ("chmod", "chown", "chgrp") and "--reference" in opts:
                paths = list(pos)
            if name == "dd":
                paths = [a.split("=", 1)[1] for a in argv if a.startswith(("if=", "of="))]
            paths += [v for _, v, is_path in vals if is_path]
            if name in READS:
                reads = {self.rel(p, base) for p in paths}
        else:
            paths = [a for a in pos if os.path.lexists(os.path.join(base, os.path.expanduser(a)))]
        if name == "rsync":
            self.info["rsync"] = True
            self.rsync_targets(k, pos, opts, base)
        if name in ("sed", "grep", "egrep", "fgrep"):
            self.patterns(k, name, pos, opts, vals, base)
        exists = lambda p: os.path.lexists(os.path.join(base, os.path.expanduser(p)))  # noqa: E731
        is_dir = lambda p: os.path.isdir(os.path.join(base, os.path.expanduser(p)))  # noqa: E731
        if name == "rm" and opts & {"f", "--force"} and any(not exists(p) for p in pos):
            self.info["rm_f"] = True
        if name == "cp" and opts & {"u", "--update"}:
            self.info["cp_u"] = True
        has_t = any(o in ("t", "--target-directory") for o, _, _ in vals) or bool(opts & {"T", "--no-target-directory"})
        if name in ("mv", "cp") and len(pos) >= 2 and not has_t:
            srcs, dest = pos[:-1], pos[-1]
            if len(srcs) >= 2 and not is_dir(dest):
                self.info["refuse"] = True
            if exists(dest) and not is_dir(dest) and any(is_dir(x) and not os.path.islink(os.path.join(base, x)) for x in srcs):
                self.info["refuse"] = True
        if name == "ln" and not opts & {"f", "--force"} and not has_t and pos:
            link = pos[-1] if len(pos) >= 2 else os.path.basename(pos[0].rstrip("/"))
            if exists(link):
                self.info["refuse"] = True
        if name in ("mv", "cp") and ("n" in opts or "--no-clobber" in opts):
            self.info["no_clobber_flag"] = True
        extract = name == "tar" and bool(opts & {"x", "--extract", "--get"})
        if extract:
            self.info["tar_x"] = True
            arch = next((v for o, v, _ in vals if o in ("f", "--file")), None)
            dest = next((v for o, v, _ in vals if o in ("C", "--directory")), ".")
            if arch:
                for m, _ in (archive_members(self.full(self.rel(arch, base)), self.key) or [])[:self.max_members]:
                    self.touch(self.rel(os.path.join(dest, m), base))
        sources = pos[:-1] if name in ("cp", "mv", "rsync", "install", "ln") and len(pos) > 1 else pos
        for p in paths:
            r = self.rel(p, base)
            fp = self.full(r)
            is_dir = os.path.isdir(fp) and not os.path.islink(fp)
            self.touch(r, "tree" if is_dir and (tree or name in COPY_LIKE) else "self")
            if os.path.islink(fp) and os.path.isdir(fp) and p.endswith("/"):
                tgt = os.path.realpath(fp)
                rt = os.path.relpath(tgt, self.root)
                self.touch(tgt if rt.startswith("..") else rt, "tree" if tree else "self")
                if name == "rm":
                    self.info["link_slash"] = True
            if is_dir and name in ("rm", "unlink") and not tree and "d" not in opts:
                self.info["refuse"] = True
            if is_dir and name == "rmdir":
                try:
                    if os.listdir(fp):
                        self.info["refuse"] = True
                except OSError:
                    pass
            if is_dir and name == "cp" and not tree and p in sources:
                self.info["refuse"] = True
        if name == "cp" and tree and (self.star_source or any(p.endswith(("/.", "/")) for p in sources)):
            self.info["cp_merge"] = True
        return reads


def inspect(commands, cwd: str = ".", shell: str | None = None, salt=None, where: str | None = None,
            max_entries: int = 60, max_children: int = 25, max_depth: int = 4, coreutils: str | None = None) -> ShellView:
    """The state the guard sends: a listing of what the commands could touch, the facts the shell decides before they
    run, and what could not be evaluated. salt: the fingerprint key (bytes or text; a fresh random one by default)."""
    shell = shell or default_shell()
    root = os.path.realpath(cwd)  # real paths on both sides, so links resolve inside the folder (macOS: /var -> /private/var)
    key = _key(salt)
    folder = Folder.scan(root, key)
    commands = [c.strip() for c in commands]
    parsed = [parse(c) for c in commands]
    rd = _Reader(root, shell, key, max_entries)
    for k, ps in enumerate(parsed, 1):
        rd.read_line(k, ps)
    rd.info["shell"] = shell
    rd.info["coreutils"] = coreutils if coreutils is not None else (
        _version(["ls", "--version"], r"coreutils\)?\s*([\d.]+)", "{}") if platform.system() == "Linux" else None)

    # what to list: every touched path first, then the contents of trees while there is room, then the parents
    shown: dict = {}
    for r in sorted(rd.touched):
        if len(shown) < max_entries:
            shown[r] = True
    frontier = [(r, max_depth) for r in sorted(rd.touched) if rd.touched[r] == "tree"]
    while frontier and len(shown) < max_entries:
        nxt = []
        for r, depth in frontier:
            fp = rd.full(r)
            if depth <= 0 or not os.path.isdir(fp) or os.path.islink(fp):
                continue
            try:
                kids = sorted(x for x in os.listdir(fp) if x != ".git")
            except OSError:
                continue
            for c in kids[:max_children]:
                cr = c if r == "." else (os.path.join(r, c) if not os.path.isabs(r) else os.path.join(r, c))
                if cr not in shown and len(shown) < max_entries:
                    shown[cr] = True
                    nxt.append((cr, depth - 1))
        frontier = nxt
    for r in list(shown):
        if os.path.isabs(r) or r == ".":
            continue
        parts = r.split(os.sep)
        for i in range(1, len(parts)):
            shown.setdefault(os.sep.join(parts[:i]), True)

    lines = [_entry(r, rd.full(r), folder, shown, key) for r in sorted(shown, key=lambda p: (os.path.isabs(p), p.split(os.sep)))]
    state = [LISTING_HEAD] + (lines or ["(none of the paths the commands name exists here)"])
    other = [p for p in folder.fps if p not in shown]
    if other:
        nf = len({os.path.dirname(p) for p in other if os.path.dirname(p)})
        state.append(f"Not listed: {len(other)} other file{'s' if len(other) != 1 else ''}"
                     + (f" in {nf} folder{'s' if nf != 1 else ''} and the starting folder" if nf else " in the starting folder")
                     + ("" if folder.complete else ", and more that the guard did not scan") + ".")
    same = _same_content(folder, shown)
    if same:
        state.append("Same content elsewhere (not listed above): " + "; ".join(same) + ".")
    facts = list(dict.fromkeys(rd.facts))
    if facts:
        state.append("What the shell does before running them: " + "; ".join(facts) + ".")
    applied = list(dict.fromkeys(rd.applied))
    if applied:
        state.append("How the commands' arguments apply here: " + "; ".join(applied) + ".")
    unread = list(dict.fromkeys(rd.unread))
    if unread:
        state.append("Not evaluated by the guard: " + "; ".join(unread) + ". What those parts touch may be missing from "
                     "the listing.")
    return ShellView(shell_rules(shell, where), "\n".join(state), commands, parsed, dict(rd.info), unread, dict(rd.touched))


def _entry(r: str, fp: str, folder: Folder, shown: dict, key: bytes) -> str:
    depth = 0 if os.path.isabs(r) or r == "." else r.count(os.sep)
    ind = "  " * depth
    name = os.path.basename(r.rstrip(os.sep)) or r
    hidden = "hidden " if name.startswith(".") and name not in (".", "..") else ""
    outside = " (outside the starting folder)" if os.path.isabs(r) else ""
    label = "the starting folder itself (.)" if r == "." else _q(r)
    try:
        st = os.lstat(fp)
    except OSError:
        return f"{ind}- {label}: does not exist{outside}"
    if stat.S_ISLNK(st.st_mode):
        try:
            tgt = os.readlink(fp)
        except OSError:
            tgt = "?"
        kind = "a folder" if os.path.isdir(fp) else ("a file" if os.path.exists(fp) else "nothing (broken)")
        return f"{ind}- {label}: {hidden}symbolic link to {tgt} (points to {kind}){outside}"
    if stat.S_ISDIR(st.st_mode):
        try:
            kids = os.listdir(fp)
        except OSError:
            kids = []
        n = len(kids)
        inside = {c for c in kids if (c if r == "." else os.path.join(r, c)) in shown}
        more = f", {n - len(inside)} of them not listed" if inside and len(inside) < n else ""
        what = "empty" if n == 0 else f"{n} entr{'y' if n == 1 else 'ies'}{more}"
        if r == ".":
            return f"- {label}: folder, {what}"
        return f"{ind}- {_q(r + '/')}: {hidden}folder, {what}{outside}"
    if stat.S_ISREG(st.st_mode):
        f = folder.fps.get(r)
        if f is None:
            data = _read(fp, 16 << 20)
            f = (_fp(key, data) if data else "") if data is not None else None
        content = "empty" if st.st_size == 0 else (f"fingerprint {f}" if f else "content not read")
        ro = "" if os.access(fp, os.W_OK) else ", read-only"
        kind = "archive" if ARCHIVE.search(r) else "file"
        s = f"{ind}- {label}: {hidden}{kind}, {st.st_size} bytes, modified {_age(st.st_mtime)}, {content}{ro}{outside}"
        if kind == "archive":
            members = folder.members[r] if r in folder.members else archive_members(fp, key)
            if members:
                held = ", ".join(f"{_q(m)} ({'fingerprint ' + x if x else 'empty'})" for m, x in members[:12])
                s += (f"; holds {len(members)} file{'s' if len(members) != 1 else ''}: {held}"
                      + (" and more" if len(members) > 12 else ""))
        return s
    return f"{ind}- {label}: {hidden}special file (not a regular file){outside}"


def _same_content(folder: Folder, shown: dict, cap: int = 12) -> list:
    """Files and archive members not listed whose content equals that of a listed file or a listed archive's member."""
    listed = {}
    for r in shown:
        if folder.fps.get(r):
            listed.setdefault(folder.fps[r], r)
        for m, x in folder.members.get(r, []):
            if x:
                listed.setdefault(x, f"{m} in {r}")
    out = []
    for p, x in sorted(folder.fps.items()):
        if x and p not in shown and x in listed:
            out.append(f"{_q(p)} (same content as {_q(listed[x])})")
    for a, ms in sorted(folder.members.items()):
        if a in shown:
            continue
        for m, x in ms:
            if x and x in listed:
                out.append(f"{_q(a)} holds {_q(m)} (same content as {_q(listed[x])})")
    return out[:cap] + ([f"and {len(out) - cap} more"] if len(out) > cap else [])


def shell_notes(view: ShellView) -> list:
    """The shell rules the commands need, in a fixed order, each once (the -n note names the exit statuses only for the
    coreutils version they were measured on)."""
    out = []
    for key, note in NOTES:
        if view.info.get(key):
            out.append(NOTE_NO_CLOBBER_94 if key == "no_clobber_flag" and view.info.get("coreutils") == "9.4" else note)
    return out


def shell_prompt(view: ShellView, notes: bool = True) -> str:
    """The exact text the model reads (world layout; notes after the command list)."""
    return P.world_state(view.rules, view.state, view.commands, notes=shell_notes(view) if notes else None,
                         notes_label=NOTES_LABEL)


@dataclass
class ShellVerdict:
    commands: list
    p_lost: float                       # probability that some file content is lost for good
    p_fail: list                        # per command line: probability that it fails
    risky: bool = False                 # lost_risky or cannot_judge: what a caller should act on
    lost_risky: bool = False            # p_lost >= the threshold
    cannot_judge: bool = False          # some parts could not be evaluated (unread) and the check fails closed
    reasons: list = field(default_factory=list)
    unread: list = field(default_factory=list)  # parts of the lines the guard did not evaluate
    notes: list = field(default_factory=list)   # the shell rules that were added
    state: str = ""                     # the exact text the model read

    @property
    def judged(self) -> bool:
        return not self.unread

    def summary(self) -> str:
        status = "RISKY" if self.lost_risky else ("CANNOT JUDGE" if self.cannot_judge else "ok")
        out = [f"Ekbasis: {status}  (lose file content: {100 * self.p_lost:.0f}%)"]
        for c, p in zip(self.commands, self.p_fail):
            out.append(f"  {100 * p:3.0f}% fails  {c}")
        out += [f"  - {r}" for r in self.reasons]
        if self.unread:
            out.append("  ! not evaluated: " + "; ".join(self.unread))
        return "\n".join(out)


def check(commands, cwd: str = ".", client: Ekbasis | None = None, lost_threshold: float = 0.2,
          fail_threshold: float = 0.5, notes: bool = True, shell: str | None = None, salt=None,
          where: str | None = None, fail_closed: bool = True, skip=None) -> ShellVerdict:
    """What these shell command lines will do to the files of `cwd`, before they run: content lost for good, failures.
    Each element of `commands` is one line as you would type it (it may join commands with ;, &&, || or |); a single
    string is one line. notes=False leaves the shell rules out (to measure them). shell: "bash" or "zsh" (default: from
    $SHELL). salt: the fingerprint key (fresh and random by default). where: the machine and its tools as the rules
    should name them (default: read from this machine).

    Fails closed: a folder that cannot be read, or a server that cannot be reached or does not answer in time, raises
    CannotJudge; a line with parts the guard cannot evaluate (unread) gives a risky verdict with cannot_judge=True.
    fail_closed=False reports those parts without making the verdict risky (server errors still raise).
    skip (0.1.3): a function of the parsed lines (an object with .parsed and .info["shell"], as a ShellView has),
    called before the folder scan; when it returns a reason, the model is not asked and the verdict is not risky (the
    hook passes recover.touched_recoverable: everything the lines could change is in git or rebuildable)."""
    commands = [c.strip() for c in ([commands] if isinstance(commands, str) else list(commands))]
    if not commands or any(not c for c in commands):
        raise ValueError("empty command: pass each command line as one non-empty string")
    if not os.path.isdir(cwd):
        raise CannotJudge(f"cannot read the folder {cwd!r}: it does not exist or is not a folder")
    if not os.access(cwd, os.R_OK | os.X_OK):
        raise CannotJudge(f"cannot read the folder {cwd!r}: permission denied")
    client = client or Ekbasis()
    if skip is not None:  # before the folder scan: the skip needs only the parsed lines
        why_skip = skip(SimpleNamespace(parsed=[parse(c) for c in commands], info={"shell": shell or default_shell()}))
        if why_skip:
            return ShellVerdict(commands=commands, p_lost=0.0, p_fail=[0.0] * len(commands), reasons=[why_skip])
    view = inspect(commands, cwd, shell=shell, salt=salt, where=where)
    prompt = shell_prompt(view, notes=notes)
    qs = {"lost": SHELL_LOST}
    qs.update({f"fails_{k}": shell_fails(k) for k in range(1, len(commands) + 1)})
    ans = client.ask(prompt, qs)
    v = ShellVerdict(commands=commands, p_lost=ans["lost"].p_yes,
                     p_fail=[ans[f"fails_{k}"].p_yes for k in range(1, len(commands) + 1)], unread=view.unread,
                     notes=shell_notes(view) if notes else [], state=prompt)
    if v.p_lost >= lost_threshold:
        v.lost_risky = True
        v.reasons.append(f"may permanently lose file content ({100 * v.p_lost:.0f}%)")
    if v.unread and fail_closed:
        v.cannot_judge = True
        v.reasons.append("cannot judge every part of the line (" + "; ".join(v.unread) + "): treat it as risky")
    v.risky = v.lost_risky or v.cannot_judge
    v.reasons += [f"command {k} likely fails: {c}" for k, (c, p) in enumerate(zip(commands, v.p_fail), 1)
                  if p >= fail_threshold]
    return v
