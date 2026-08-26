# Centralised programming-language configuration for the coding system.
#
# Single source of truth for the identifiers the API accepts and the
# friendly names shown in the UI. The frontend keeps a mirrored copy
# (frontend/src/languages.js) for display purposes only; the BACKEND is
# authoritative when validating a submission's language.

PROGRAMMING_LANGUAGES = {
    "python": {
        "name": "Python",
        "monaco": "python",
        "extension": ".py",
        # No compile step; interpreted directly from the mounted source file.
        "compile_command": None,
        "run_command": ["python3", "-I", "{source_path}"],
    },
    "javascript": {
        "name": "JavaScript",
        "monaco": "javascript",
        "extension": ".js",
        "compile_command": None,
        # Node runs with no module lookups beyond the sandbox cwd.
        "run_command": ["node", "--no-warnings", "{source_path}"],
    },
    "cpp": {
        "name": "C++",
        "monaco": "cpp",
        "extension": ".cpp",
        "compile_command": [
            "g++", "-O2", "-std=c++17", "-o", "solution", "{source_path}",
        ],
        # Compiled binary is produced into the workspace cwd.
        "run_command": ["./solution"],
    },
    "java": {
        "name": "Java",
        "monaco": "java",
        "extension": ".java",
        # javac requires the file to be named after the public class.
        "filename": "Main.java",
        "compile_command": ["javac", "-nowarn", "{source_path}"],
        "run_command": ["java", "{source_stem}"],
    },
}

# Sandbox resource defaults (overridable via Django settings).
SANDBOX_DEFAULTS = {
    "image": "taskflow-judge:latest",
    "workspace_mount": "/sandbox",
    "memory_mb": 256,
    "cpu_cores": 0.5,
    "pids_limit": 64,
    # Non-root uid/gid inside the container (nobody/nogroup on Debian).
    "container_user": "65534:65534",
    "run_timeout_seconds": 5,
    "compile_timeout_seconds": 20,
}

LANGUAGE_IDENTIFIERS = tuple(PROGRAMMING_LANGUAGES.keys())

DEFAULT_LANGUAGE = "python"


def is_supported_language(identifier):
    """True when `identifier` is a known platform language."""
    return identifier in PROGRAMMING_LANGUAGES


def is_language_allowed_for_problem(problem, identifier):
    """True when the identifier is supported AND configured on the problem."""
    if not is_supported_language(identifier):
        return False
    allowed = problem.allowed_languages or []
    return identifier in allowed


def language_display_name(identifier):
    """Friendly name for a language id; falls back to the raw value."""
    entry = PROGRAMMING_LANGUAGES.get(identifier)
    return entry["name"] if entry else (identifier or "")


def language_choices():
    """Django model choices built from the central registry."""
    return [(identifier, entry["name"]) for identifier, entry in PROGRAMMING_LANGUAGES.items()]


def language_config(identifier):
    """Full execution config for a language, or None when unsupported."""
    return PROGRAMMING_LANGUAGES.get(identifier)


def source_filename(identifier):
    """File the source code is written to inside the sandbox workspace."""
    entry = language_config(identifier) or {}
    # Java must be Main.java for javac; everything else uses solution<ext>.
    return entry.get("filename", f"solution{entry.get('extension', '')}")


def compile_command_for(identifier):
    """Compile argv template (may contain {source_path}), or None."""
    entry = language_config(identifier) or {}
    return entry.get("compile_command")


def run_command_for(identifier):
    """Run argv template; may contain {source_path}/{source_stem}."""
    entry = language_config(identifier) or {}
    return entry.get("run_command")
