"""Turn raw tool output into something a user can act on.

The previous check grepped for the words "error" and "fatal". That missed the
most common failures outright: ngspice writes its diagnostics to the log file
named by `-o`, not to stdout, so a run that died on an unknown subcircuit was
recorded as a success. Each rule here names the cause and what to do about it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

ACTION_CHECK_PDK = "check_pdk"
ACTION_CHECK_PATHS = "check_paths"
ACTION_OPEN_NETLIST = "open_netlist"
ACTION_INSTALL_MAGIC = "install_magic"
ACTION_NONE = ""


@dataclass(frozen=True)
class Advice:
    """One recognised failure, in terms of cause and remedy."""

    rule_id: str
    tool: str
    severity: str
    title: str
    detail: str
    suggestion: str
    action: str = ACTION_NONE
    evidence: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity == SEVERITY_ERROR


@dataclass(frozen=True)
class Rule:
    rule_id: str
    tool: str
    pattern: re.Pattern
    severity: str
    title: str
    detail: str
    suggestion: str
    action: str = ACTION_NONE


def _rule(rule_id, tool, pattern, severity, title, detail, suggestion, action=ACTION_NONE) -> Rule:
    compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    return Rule(rule_id, tool, compiled, severity, title, detail, suggestion, action)


RULES: tuple[Rule, ...] = (
    # ---------------------------------------------------------------- ngspice
    _rule(
        # ngspice prints the whole offending line; the subcircuit is its last token.
        "ngspice.unknown_subckt", "ngspice", r"unknown subckt:[^\n]*?(?P<name>\S+)[ \t]*$", SEVERITY_ERROR,
        "Subcircuito no definido",
        "El netlist instancia un subcircuito que ngspice nunca vio definido.",
        "Suele faltar la librería del PDK. Revisa que el netlist incluya "
        "`.lib $SKY130A/libs.tech/ngspice/sky130.lib.spice tt`, o que el `.subckt` "
        "esté en un archivo incluido.",
        ACTION_CHECK_PDK,
    ),
    _rule(
        "ngspice.missing_include", "ngspice",
        r"(?:could not find include file|can't open (?:file )?|cannot open)\s*(?P<path>\S+)", SEVERITY_ERROR,
        "Archivo incluido no encontrado",
        "Una directiva `.include` o `.lib` apunta a un archivo que no existe.",
        "Verifica la ruta. Si es del PDK, confirma `SKY130A` en Preferencias; "
        "las rutas relativas se resuelven desde el directorio de la corrida.",
        ACTION_CHECK_PATHS,
    ),
    _rule(
        "ngspice.model_missing", "ngspice",
        r"(?:unknown model|could not find model|no such model|model\s+\S+\s+not found)", SEVERITY_ERROR,
        "Modelo de dispositivo no encontrado",
        "Un dispositivo referencia un `.model` que no está cargado.",
        "Para dispositivos SKY130 hace falta la librería del PDK con su esquina "
        "(`tt`, `ss`, `ff`). Revisa que la línea `.lib` incluya la esquina.",
        ACTION_CHECK_PDK,
    ),
    _rule(
        "ngspice.singular_matrix", "ngspice", r"singular matrix", SEVERITY_ERROR,
        "Matriz singular",
        "El solver no pudo resolver el circuito: casi siempre hay un nodo sin "
        "camino de DC a tierra, o una fuente de voltaje en lazo.",
        "Revisa que cada nodo tenga referencia a `0`. Una resistencia muy grande "
        "(por ejemplo 1G) a tierra en nodos flotantes suele destrabarlo.",
        ACTION_OPEN_NETLIST,
    ),
    _rule(
        "ngspice.no_convergence", "ngspice",
        r"(?:doAnalyses: TRAN;iteration limit reached|no convergence|failed to converge)", SEVERITY_ERROR,
        "El análisis no convergió",
        "El paso de tiempo o el punto de operación no encontró solución estable.",
        "Prueba con `.options reltol=1e-3 abstol=1e-10`, un paso máximo menor en "
        "`.tran`, o añade condiciones iniciales con `.ic`.",
        ACTION_OPEN_NETLIST,
    ),
    _rule(
        "ngspice.simulation_interrupted", "ngspice", r"simulation interrupted due to error", SEVERITY_ERROR,
        "Simulación interrumpida",
        "ngspice abortó antes de terminar el análisis.",
        "La causa concreta está en las líneas anteriores del log de la herramienta.",
    ),
    _rule(
        "ngspice.too_few_parameters", "ngspice", r"too few parameters", SEVERITY_ERROR,
        "Instancia con parámetros incompletos",
        "Una línea de dispositivo no trae todos los nodos o parámetros que su tipo requiere.",
        "Compara la instancia con la definición del `.subckt` o del modelo: el orden "
        "y la cantidad de nodos deben coincidir.",
        ACTION_OPEN_NETLIST,
    ),
    _rule(
        "ngspice.no_such_vector", "ngspice", r"no such vector", SEVERITY_WARNING,
        "Señal solicitada inexistente",
        "Un `.save`, `.plot` o `.print` pide una señal que el análisis no produjo.",
        "Revisa el nombre del nodo. Dentro de un subcircuito se escriben como "
        "`v(x1.nodo)`.",
    ),
    # ------------------------------------------------------------------ magic
    _rule(
        "magic.tech_version", "magic", r"(?:tech file.*version|version.*mismatch).*", SEVERITY_ERROR,
        "Techfile incompatible con esta versión de Magic",
        "El techfile de sky130A exige una revisión de Magic más nueva que la instalada.",
        "Instala una versión actual con `scripts/install_magic_ubuntu.sh`; la de "
        "los repositorios de Ubuntu (8.3.105) es demasiado vieja.",
        ACTION_INSTALL_MAGIC,
    ),
    _rule(
        "magic.no_techfile", "magic", r"(?:couldn't read|cannot open).*\.tech", SEVERITY_ERROR,
        "Techfile no encontrado",
        "Magic no pudo leer el techfile del PDK.",
        "Confirma la ruta del `magicrc` en Preferencias y que `SKY130A` apunte a un PDK completo.",
        ACTION_CHECK_PDK,
    ),
    # ----------------------------------------------------------------- netgen
    _rule(
        "netgen.mismatch", "netgen", r"netlists do not match", SEVERITY_ERROR,
        "LVS no coincide",
        "La extracción del layout y el esquemático describen circuitos distintos.",
        "Revisa el reporte por dispositivos o nodos sobrantes. Las causas típicas son "
        "puertos con nombre distinto o dispositivos en paralelo sin agrupar.",
    ),
    _rule(
        "netgen.no_devices", "netgen", r"contains no devices", SEVERITY_ERROR,
        "Uno de los netlists está vacío",
        "Netgen leyó un netlist sin dispositivos, así que la comparación no significa nada.",
        "Comprueba que la extracción produjo algo y que la celda top es la correcta.",
        ACTION_CHECK_PATHS,
    ),
    # ---------------------------------------------------------- flujo digital
    _rule(
        # Yosys quotes escaped identifiers as `\name', so the backslash and the
        # surrounding quotes have to be stripped off the captured name.
        "yosys.no_such_module", "yosys",
        r"(?:ERROR:\s*)?module\s+[`'\"]?\\?(?P<name>[\w.$]+)['\"]?\s+not found", SEVERITY_ERROR,
        "Módulo Verilog no encontrado",
        "La síntesis referencia un módulo que no está entre los archivos leídos.",
        "Agrega el archivo que lo define a las fuentes del diseño, o revisa el nombre del módulo top.",
    ),
    _rule(
        "yosys.syntax", "yosys", r"ERROR:\s*(?:syntax error|Parser error)", SEVERITY_ERROR,
        "Error de sintaxis en el Verilog",
        "Yosys no pudo interpretar una de las fuentes.",
        "El mensaje trae archivo y línea. Ojo con construcciones SystemVerilog que "
        "el lector por defecto no acepta.",
    ),
    _rule(
        "openroad.error", "openroad", r"^\s*\[ERROR\s+(?P<code>[A-Z]{3}-\d+)\]\s*(?P<body>.*)$", SEVERITY_ERROR,
        "OpenROAD reportó un error",
        "Una etapa del flujo digital falló.",
        "El código entre corchetes identifica la etapa; búscalo en la documentación de OpenROAD.",
    ),
    _rule(
        "librelane.step_failed", "librelane", r"step\s+'?(?P<step>[\w.\- ]+)'?\s+failed", SEVERITY_ERROR,
        "Un paso del flujo falló",
        "LibreLane detuvo el flujo en un paso concreto.",
        "Revisa el log de ese paso dentro del directorio de la corrida.",
    ),
    # ---------------------------------------------------------------- general
    _rule(
        "general.permission_denied", "", r"permission denied", SEVERITY_ERROR,
        "Permiso denegado",
        "La herramienta no pudo leer o escribir una ruta.",
        "Revisa el dueño del directorio de salida. Nada de este flujo debería "
        "necesitar `sudo`.",
        ACTION_CHECK_PATHS,
    ),
    _rule(
        "general.no_space", "", r"no space left on device", SEVERITY_ERROR,
        "Disco lleno",
        "No queda espacio donde se escriben los resultados.",
        "Libera espacio o cambia el directorio de salida del proyecto.",
    ),
    _rule(
        "general.segfault", "", r"segmentation fault", SEVERITY_ERROR,
        "La herramienta se cayó",
        "El proceso terminó con una violación de segmento.",
        "Suele indicar una versión incompatible con el PDK, o una entrada corrupta.",
    ),
)


def analyze(text: str, tool: str = "", limit: int = 6) -> list[Advice]:
    """Return recognised problems, most severe first, without duplicates."""
    if not text:
        return []
    found: list[Advice] = []
    seen: set[str] = set()
    for rule in RULES:
        if tool and rule.tool and rule.tool != tool:
            continue
        match = rule.pattern.search(text)
        if not match or rule.rule_id in seen:
            continue
        seen.add(rule.rule_id)
        detail = rule.detail
        name = match.groupdict().get("name") or match.groupdict().get("path")
        if name:
            detail = f"{detail} ({name.strip().rstrip(':')})"
        found.append(
            Advice(
                rule_id=rule.rule_id, tool=rule.tool, severity=rule.severity,
                title=rule.title, detail=detail, suggestion=rule.suggestion,
                action=rule.action, evidence=match.group(0).strip()[:200],
            )
        )
    found.sort(key=lambda advice: 0 if advice.blocking else 1)
    return found[:limit]


def has_blocking_errors(advices: list[Advice]) -> bool:
    """True when something went wrong regardless of the process exit code."""
    return any(advice.blocking for advice in advices)


def format_advice(advices: list[Advice]) -> str:
    """Render advice as a short block for a log view."""
    if not advices:
        return ""
    lines = []
    for advice in advices:
        marker = "✖" if advice.blocking else "▲"
        lines.append(f"{marker} {advice.title}")
        lines.append(f"   {advice.detail}")
        lines.append(f"   → {advice.suggestion}")
        if advice.evidence:
            lines.append(f"   ({advice.evidence})")
        lines.append("")
    return "\n".join(lines)
