"""Setup assistant tab for environment bootstrap and validation."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner, CommandSpec
from app.core.container_tools import detect_runtime, image_present
from app.core.env_probe import EnvProbe
from app.core.env_validator import EnvValidator
from app.core.i18n import pick
from app.ui.widgets import configure_table, MAX_LOG_BLOCKS
from app.core.settings_manager import AppSettings
from app.ui.theme import badge_style, heading_style, hint_style, resolve
from app.core.setup_manager import SetupManager


class SetupTab(QWidget):
    """Guide users through validating and bootstrapping the local environment."""

    settings_updated = Signal(object)
    send_status = Signal(str)

    STEP_REVIEW = 0
    STEP_PDK = 1
    STEP_TOOLS = 2
    STEP_APPLY = 3
    STEP_VALIDATE = 4

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self._theme = resolve(settings.theme)
        self.validator = EnvValidator()
        self.setup_mgr = SetupManager()
        self.runner = CommandRunner()
        self._wizard_steps = [
            pick(self.lang, "1. Revisar sistema", "1. Review system"),
            pick(self.lang, "2. Preparar PDK", "2. Prepare PDK"),
            pick(self.lang, "3. Instalar tools", "3. Install tools"),
            pick(self.lang, "4. Aplicar rutas", "4. Apply paths"),
            pick(self.lang, "5. Validar", "5. Validate"),
        ]
        self._current_step = 0

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.progress_label = QLabel()
        self.progress_bar = QProgressBar()
        self.step_list = QListWidget()
        self.step_list.setObjectName("setupSteps")
        self.step_list.setSpacing(6)
        self.step_stack = QStackedWidget()
        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(
            [
                pick(self.lang, "Elemento", "Item"),
                pick(self.lang, "Estado", "Status"),
                pick(self.lang, "Detalle", "Detail"),
            ]
        )
        configure_table(self.status_table, stretch_column=2, visible_rows=8)
        self.detected_label = QLabel()
        self.detected_label.setWordWrap(True)
        self.log = QTextEdit()
        self.log.document().setMaximumBlockCount(MAX_LOG_BLOCKS)
        self.log.setReadOnly(True)
        self.ready_badge = QLabel()
        self.ready_title = QLabel()
        self.ready_text = QLabel()
        self.ready_text.setWordWrap(True)
        self.activity_badge = QLabel()
        self.activity_text = QLabel()
        self.card_tools_value = QLabel("—")
        self.card_pdk_value = QLabel("—")
        self.card_python_value = QLabel("—")
        self.card_overall_value = QLabel("—")
        self._spinner_frames = ("◜", "◠", "◝", "◞", "◡", "◟")
        self._spinner_index = 0
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(120)
        self._activity_timer.timeout.connect(self._advance_spinner)
        self._active_operations = 0
        self._verification_completed = False
        self._last_diagnosis = None
        self._detected_defaults_available = False
        self._pdk_candidates_available = False
        self._pdk_preflight = None
        self._pdk_source_preflight = None
        self._pdk_bundle_preflight = None
        self._container_runtime = None
        self._digital_flow_ready = False
        self._runner_action = ""

        self.validate_btn = QPushButton(pick(self.lang, "Validar entorno", "Validate environment"))
        self.apply_defaults_btn = QPushButton(pick(self.lang, "Aplicar rutas detectadas", "Apply detected paths"))
        self.install_btn = QPushButton(pick(self.lang, "Instalar entorno VLSI en Ubuntu", "Install Ubuntu VLSI environment"))
        self.refresh_detect_btn = QPushButton(pick(self.lang, "Refrescar detección", "Refresh detection"))
        self.detect_pdk_btn = QPushButton(pick(self.lang, "Buscar PDK reutilizable", "Find reusable PDK"))
        self.use_pdk_btn = QPushButton(pick(self.lang, "Usar PDK seleccionado", "Use selected PDK"))
        self.install_managed_pdk_btn = QPushButton(pick(self.lang, "Instalar PDK gestionado", "Install managed PDK"))
        self.install_bundle_pdk_btn = QPushButton(pick(self.lang, "Descargar bundle PDK", "Download PDK bundle"))
        self.install_docker_btn = QPushButton(
            pick(self.lang, "Instalar Docker", "Install Docker"))
        self.pull_digital_flow_btn = QPushButton(
            pick(self.lang, "Descargar flujo digital (OpenLane + OpenROAD)",
                 "Download digital flow (OpenLane + OpenROAD)"))
        self.digital_flow_summary = QLabel()
        self.digital_flow_summary.setWordWrap(True)

        self.install_prebuilt_pdk_btn = QPushButton(
            pick(self.lang, "Instalar PDK oficial  ·  recomendado", "Install official PDK  ·  recommended")
        )
        self.install_prebuilt_pdk_btn.setObjectName("primaryAction")
        self.install_prebuilt_pdk_btn.setToolTip(
            pick(self.lang,
                 "Descarga el sky130A precompilado oficial. No necesita sudo.",
                 "Downloads the official prebuilt sky130A. No sudo required.")
        )
        self.check_source_build_btn = QPushButton(pick(self.lang, "Precheck build desde fuentes", "Source-build precheck"))
        self.build_from_sources_btn = QPushButton(pick(self.lang, "Build PDK desde fuentes", "Build PDK from sources"))
        self.pdk_candidate_combo = QComboBox()
        self.pdk_candidate_combo.setPlaceholderText(pick(self.lang, "Sin candidatos detectados", "No detected candidates"))
        self.pdk_candidate_summary = QLabel()
        self.pdk_candidate_summary.setWordWrap(True)
        self.pdk_preflight_summary = QLabel()
        self.pdk_preflight_summary.setWordWrap(True)
        self.pdk_bundle_summary = QLabel()
        self.pdk_bundle_summary.setWordWrap(True)
        self.pdk_prebuilt_summary = QLabel()
        self.pdk_prebuilt_summary.setWordWrap(True)
        self.pdk_source_preflight_summary = QLabel()
        self.pdk_source_preflight_summary.setWordWrap(True)
        self.prev_btn = QPushButton(pick(self.lang, "Atrás", "Back"))
        self.next_btn = QPushButton(pick(self.lang, "Siguiente", "Next"))

        self._build_ui()
        self._wire()
        self._sync_step_ui()
        self._set_activity_idle()
        self._sync_action_gates()
        self._probe = EnvProbe(self)
        self._probe.finished.connect(self._on_probe_finished)
        self._probe.failed.connect(self._on_probe_failed)
        self._show_probe_placeholder()
        self._probe.start(self.settings, self.lang)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll)

        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        title = QLabel(pick(self.lang, "Asistente de entorno", "Setup Assistant"))
        title.setStyleSheet(heading_style(self._theme, 22))
        subtitle = QLabel(
            pick(
                self.lang,
                "Sigue estos pasos para dejar lista la máquina antes de correr extracción, simulación o LVS.",
                "Follow these steps to prepare the machine before running extraction, simulation, or LVS.",
            )
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(hint_style(self._theme))
        layout.addWidget(title)
        layout.addWidget(subtitle)
        activity_row = QHBoxLayout()
        self.activity_badge.setMinimumWidth(32)
        self.activity_badge.setAlignment(Qt.AlignmentFlag.AlignCenter) if False else None
        self.activity_text.setWordWrap(True)
        activity_row.addWidget(self.activity_badge, 0)
        activity_row.addWidget(self.activity_text, 1)
        activity_row.addStretch(1)
        layout.addLayout(activity_row)
        self.progress_bar.setRange(0, len(self._wizard_steps) - 1)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.summary_label)

        for step in self._wizard_steps:
            self.step_list.addItem(QListWidgetItem(step))

        # Five short steps in a scrollable box showed two and a half of them.
        self.step_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.step_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_row = QVBoxLayout()
        content_row.setSpacing(18)

        step_card = QFrame()
        step_card.setObjectName("setupSidebar")
        step_card_layout = QVBoxLayout(step_card)
        step_card_layout.setContentsMargins(12, 12, 12, 12)
        step_card_layout.setSpacing(10)
        step_heading = QLabel(pick(self.lang, "Pasos", "Steps"))
        step_heading.setStyleSheet(f"font-weight: 800; color: {self._theme.accent};")
        step_card_layout.addWidget(step_heading)
        step_card_layout.addWidget(self.step_list)
        content_row.addWidget(step_card, 0)

        page_card = QFrame()
        page_card.setObjectName("setupPageCard")
        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(18, 18, 18, 18)
        page_layout.setSpacing(14)
        page_layout.addWidget(self.step_stack, 1)
        content_row.addWidget(page_card, 1)

        layout.addLayout(content_row, 1)

        nav = QHBoxLayout()
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        layout.addLayout(nav)

        self.step_stack.addWidget(self._build_review_page())
        self.step_stack.addWidget(self._build_pdk_page())
        self.step_stack.addWidget(self._build_install_page())
        self.step_stack.addWidget(self._build_apply_page())
        self.step_stack.addWidget(self._build_validate_page())

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(self._page_heading(pick(self.lang, "Revisa el sistema actual", "Review the current system")))
        layout.addWidget(
            self._page_hint(
                pick(
                    self.lang,
                    "Primero valida qué herramientas y rutas ya existen en esta computadora.",
                    "First validate which tools and paths already exist on this computer.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.validate_btn)
        actions.addWidget(self.refresh_detect_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel(pick(self.lang, "Estado del entorno", "Environment status")))
        layout.addWidget(self.status_table, 1)
        return page

    def _build_install_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(self._page_heading(pick(self.lang, "Instala el toolchain base", "Install the base toolchain")))
        layout.addWidget(
            self._page_hint(
                pick(
                    self.lang,
                    "Este paso instala paquetes del sistema para Ubuntu y compila Magic desde la fuente oficial para SKY130. No toca el entorno Python del usuario.",
                    "This step installs Ubuntu system packages and builds Magic from the official source release for SKY130. It does not touch the user Python environment.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.install_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(self._page_heading(
            pick(self.lang, "Flujo digital (opcional)", "Digital flow (optional)"), size=16))
        layout.addWidget(self._page_hint(
            pick(
                self.lang,
                "OpenLane y OpenROAD corren dentro de un contenedor, así que no se instalan "
                "paquetes extra en tu sistema. Sólo hace falta si vas a hacer flujo digital.",
                "OpenLane and OpenROAD run inside a container, so no extra packages land on "
                "your system. You only need this for the digital flow.",
            )
        ))
        layout.addWidget(self.digital_flow_summary)
        digital_actions = QHBoxLayout()
        digital_actions.addWidget(self.install_docker_btn)
        digital_actions.addWidget(self.pull_digital_flow_btn)
        digital_actions.addStretch(1)
        layout.addLayout(digital_actions)

        layout.addWidget(QLabel(pick(self.lang, "Log del asistente", "Assistant log")))
        layout.addWidget(self.log, 1)
        return page

    def _build_apply_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(self._page_heading(pick(self.lang, "Aplica rutas detectadas", "Apply detected paths")))
        layout.addWidget(
            self._page_hint(
                pick(
                    self.lang,
                    "Después de instalar o si ya tienes entorno, aplica automáticamente rutas comunes para tools y SKY130A.",
                    "After installation or if the environment already exists, automatically apply common tool and SKY130A paths.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.apply_defaults_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel(pick(self.lang, "Detección automática", "Automatic detection")))
        layout.addWidget(self.detected_label, 1)
        return page

    def _build_pdk_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(self._page_heading(pick(self.lang, "Prepara un PDK reutilizable", "Prepare a reusable PDK")))
        layout.addWidget(
            self._page_hint(
                pick(
                    self.lang,
                    "Antes de compilar nada, detecta si ya existe un `sky130A` utilizable en staging, volare, ciel u otras rutas comunes.",
                    "Before compiling anything, detect whether a usable `sky130A` already exists in staging, volare, ciel, or other common roots.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.detect_pdk_btn)
        actions.addWidget(self.use_pdk_btn)
        actions.addWidget(self.install_managed_pdk_btn)
        actions.addWidget(self.install_prebuilt_pdk_btn)
        actions.addWidget(self.install_bundle_pdk_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel(pick(self.lang, "Preflight de instalación gestionada", "Managed install preflight")))
        layout.addWidget(self.pdk_preflight_summary)
        layout.addWidget(QLabel(pick(self.lang, "PDK oficial precompilado", "Official prebuilt PDK")))
        layout.addWidget(self.pdk_prebuilt_summary)
        layout.addWidget(QLabel(pick(self.lang, "Bundle PDK", "PDK bundle")))
        layout.addWidget(self.pdk_bundle_summary)
        source_actions = QHBoxLayout()
        source_actions.addWidget(self.check_source_build_btn)
        source_actions.addWidget(self.build_from_sources_btn)
        source_actions.addStretch(1)
        layout.addLayout(source_actions)
        layout.addWidget(QLabel(pick(self.lang, "Prechecks de build desde fuentes", "Source-build prechecks")))
        layout.addWidget(self.pdk_source_preflight_summary)
        layout.addWidget(QLabel(pick(self.lang, "Candidato activo", "Active candidate")))
        layout.addWidget(self.pdk_candidate_combo)
        layout.addWidget(self.pdk_candidate_summary, 1)
        return page

    def _build_validate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(self._page_heading(pick(self.lang, "Valida antes de usar el flujo", "Validate before using the flow")))
        layout.addWidget(
            self._page_hint(
                pick(
                    self.lang,
                    "Haz una validación final. Si algo sigue faltando, vuelve al paso correspondiente o afina las rutas en Preferences.",
                    "Run a final validation. If something is still missing, go back to the corresponding step or fine-tune the paths in Preferences.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.validate_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        cards.addWidget(self._build_status_card(pick(self.lang, "Tools", "Tools"), self.card_tools_value), 0, 0)
        cards.addWidget(self._build_status_card("PDK", self.card_pdk_value), 0, 1)
        cards.addWidget(self._build_status_card("Python", self.card_python_value), 1, 0)
        cards.addWidget(self._build_status_card(pick(self.lang, "General", "Overall"), self.card_overall_value), 1, 1)
        layout.addLayout(cards)
        self.ready_badge.setObjectName("readyBadge")
        self.ready_title.setStyleSheet(heading_style(self._theme, 20))
        ready_row = QHBoxLayout()
        ready_row.addWidget(self.ready_badge)
        ready_row.addStretch(1)
        layout.addLayout(ready_row)
        layout.addWidget(self.ready_title)
        layout.addWidget(self.ready_text)
        final_hint = QLabel(
            pick(
                self.lang,
                "Sugerencia: cuando todo esté en OK, la app ya queda lista para extracción, simulación y LVS.",
                "Tip: when everything is OK, the app is ready for extraction, simulation, and LVS.",
            )
        )
        final_hint.setWordWrap(True)
        final_hint.setStyleSheet(f"color: {self._theme.text_subtle}; font-weight: 600;")
        layout.addWidget(final_hint)
        return page

    def _page_heading(self, text: str, size: int = 18) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(heading_style(self._theme, size))
        return label

    def _page_hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(hint_style(self._theme))
        return label

    def _build_status_card(self, title: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("statusCardTitle")
        value_label.setObjectName("statusCardValue")
        layout.addWidget(heading)
        layout.addWidget(value_label)
        return card

    def _wire(self) -> None:
        self.validate_btn.clicked.connect(self.rescan_environment)
        self.apply_defaults_btn.clicked.connect(self.apply_detected_defaults)
        self.install_btn.clicked.connect(self.install_environment)
        self.refresh_detect_btn.clicked.connect(self.rescan_environment)
        self.detect_pdk_btn.clicked.connect(self.refresh_pdk_candidates)
        self.use_pdk_btn.clicked.connect(self.apply_selected_pdk_candidate)
        self.install_managed_pdk_btn.clicked.connect(self.install_managed_pdk)
        self.install_bundle_pdk_btn.clicked.connect(self.install_bundle_pdk)
        self.install_prebuilt_pdk_btn.clicked.connect(self.install_prebuilt_pdk)
        self.install_docker_btn.clicked.connect(self.install_docker)
        self.pull_digital_flow_btn.clicked.connect(self.pull_digital_flow)
        self.check_source_build_btn.clicked.connect(self.refresh_pdk_source_preflight)
        self.build_from_sources_btn.clicked.connect(self.build_pdk_from_sources)
        self.pdk_candidate_combo.currentIndexChanged.connect(self._update_pdk_candidate_summary)
        self.prev_btn.clicked.connect(self._go_prev)
        self.next_btn.clicked.connect(self._go_next)
        self.step_list.currentRowChanged.connect(self._set_step)
        self.runner.started.connect(lambda cmd: self.log.append(f"$ {cmd}"))
        self.runner.line_output.connect(lambda text: self.log.insertPlainText(text))
        self.runner.finished.connect(self._on_finished)

    def _go_prev(self) -> None:
        self._set_step(max(0, self._current_step - 1))

    def _go_next(self) -> None:
        self._set_step(min(len(self._wizard_steps) - 1, self._current_step + 1))

    def _set_step(self, index: int) -> None:
        if index < 0 or index >= len(self._wizard_steps):
            return
        if not self._verification_completed and index > 0:
            return
        self._current_step = index
        self.step_stack.setCurrentIndex(index)
        if self.step_list.currentRow() != index:
            self.step_list.setCurrentRow(index)
        self._sync_step_ui()

    def _sync_step_ui(self) -> None:
        self.prev_btn.setEnabled(self._current_step > 0)
        can_move_forward = self._current_step < len(self._wizard_steps) - 1 and (
            self._verification_completed or self._current_step > 0
        )
        self.next_btn.setEnabled(can_move_forward)
        self.progress_bar.setValue(self._current_step)
        self.progress_label.setText(
            pick(
                self.lang,
                f"Paso {self._current_step + 1} de {len(self._wizard_steps)}",
                f"Step {self._current_step + 1} of {len(self._wizard_steps)}",
            )
        )
        if self.step_list.currentRow() != self._current_step:
            self.step_list.setCurrentRow(self._current_step)
        for index in range(self.step_list.count()):
            item = self.step_list.item(index)
            flags = item.flags()
            if index == 0 or self._verification_completed:
                item.setFlags(flags | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            else:
                item.setFlags(flags & ~Qt.ItemIsEnabled)

    def refresh_validation(self) -> None:
        self._begin_activity(pick(self.lang, "Validando entorno...", "Validating environment..."))
        diagnosis = self.validator.diagnose(self.settings, lang=self.lang)
        self._last_diagnosis = diagnosis
        self._verification_completed = True
        rows = self.validator.validation_rows(diagnosis, lang=self.lang)
        ok_count = sum(1 for row in rows if row.ok)
        total = len(rows)
        self.summary_label.setText(
            pick(
                self.lang,
                f"Checks correctos: {ok_count}/{total}. Herramientas, PDK y entorno Python XDG se validan por separado.",
                f"Passing checks: {ok_count}/{total}. Tools, PDK, and the XDG Python environment are validated independently.",
            )
        )
        self._update_ready_state(diagnosis)
        self.status_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.status_table.setItem(i, 0, QTableWidgetItem(row.item))
            self.status_table.setItem(i, 1, QTableWidgetItem(row.status))
            self.status_table.setItem(i, 2, QTableWidgetItem(row.detail))
        self.status_table.resizeColumnsToContents()
        self._sync_action_gates()
        self._finish_activity(True, pick(self.lang, "Validación lista", "Validation ready"))

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Size the step list to its contents.

        Row heights come from the window stylesheet, which is applied after
        this widget is constructed, so the measurement has to wait until the
        page is actually shown.
        """
        super().showEvent(event)
        self._fit_step_list()

    def _fit_step_list(self) -> None:
        count = self.step_list.count()
        if not count:
            return
        spacing = self.step_list.spacing()
        total = sum(self.step_list.sizeHintForRow(row) for row in range(count))
        height = total + 2 * spacing * count + 2 * self.step_list.frameWidth()
        if height != self.step_list.height():
            self.step_list.setFixedHeight(height)

    def rescan_environment(self) -> None:
        """Re-probe the machine after something changed, without blocking the UI."""
        EnvValidator.invalidate_cache()
        if not self._probe.start(self.settings, self.lang, refresh=True):
            return
        self._show_probe_placeholder()

    def _show_probe_placeholder(self) -> None:
        """Tell the user a scan is running instead of showing a frozen window."""
        scanning = pick(self.lang, "Analizando el sistema...", "Scanning the system...")
        self.summary_label.setText(scanning)
        for card in (self.card_tools_value, self.card_pdk_value, self.card_python_value, self.card_overall_value):
            card.setText("...")

    def _on_probe_finished(self, _diagnosis: object) -> None:
        """Populate the page from the warm cache the worker thread just filled."""
        self.refresh_detection()
        self.refresh_validation()

    def _on_probe_failed(self, message: str) -> None:
        self.summary_label.setText(
            pick(self.lang, f"No se pudo analizar el entorno: {message}",
                 f"The environment could not be scanned: {message}")
        )

    def refresh_detection(self) -> None:
        self._begin_activity(pick(self.lang, "Refrescando detección...", "Refreshing detection..."))
        lines = self.setup_mgr.summarize_detection(self.settings)
        diagnosis = self.validator.diagnose(self.settings, lang=self.lang)
        self._last_diagnosis = diagnosis
        self._verification_completed = True
        self._detected_defaults_available = bool(self.setup_mgr.detect_tool_defaults() or self.setup_mgr.detect_pdk_defaults())
        translated: list[str] = []
        for line in lines:
            if line == "Detected tools:":
                translated.append(pick(self.lang, "Herramientas detectadas:", "Detected tools:"))
            elif line == "Detected PDK paths:":
                translated.append(pick(self.lang, "Rutas PDK detectadas:", "Detected PDK paths:"))
            elif line == "Detected Python environment:":
                translated.append(pick(self.lang, "Entorno Python detectado:", "Detected Python environment:"))
            elif line == "No common Ubuntu VLSI installation was detected automatically.":
                translated.append(
                    pick(
                        self.lang,
                        "No se detectó automáticamente una instalación VLSI común de Ubuntu.",
                        "No common Ubuntu VLSI installation was detected automatically.",
                    )
                )
            else:
                translated.append(line)
        if diagnosis.recommendations:
            translated.append("")
            translated.append(pick(self.lang, "Recomendaciones:", "Recommendations:"))
            translated.extend(f"- {item}" for item in diagnosis.recommendations)
        self.detected_label.setText("\n".join(translated))
        self.refresh_pdk_candidates()
        self._sync_action_gates()
        self._finish_activity(True, pick(self.lang, "Detección actualizada", "Detection updated"))

    def refresh_pdk_candidates(self) -> None:
        self._begin_activity(pick(self.lang, "Buscando PDK reutilizable...", "Searching reusable PDK..."))
        current_path = self.pdk_candidate_combo.currentData()
        candidates = self.setup_mgr.detect_reusable_pdk_candidates()
        self.pdk_candidate_combo.blockSignals(True)
        self.pdk_candidate_combo.clear()
        for candidate in candidates:
            self.pdk_candidate_combo.addItem(
                f"{candidate.status.upper()} | {candidate.sky130a_path}",
                candidate.sky130a_path,
            )
        self.pdk_candidate_combo.blockSignals(False)
        self._pdk_candidates_available = bool(candidates)
        if current_path:
            index = self.pdk_candidate_combo.findData(current_path)
            if index >= 0:
                self.pdk_candidate_combo.setCurrentIndex(index)
        if self.pdk_candidate_combo.count() and self.pdk_candidate_combo.currentIndex() < 0:
            self.pdk_candidate_combo.setCurrentIndex(0)
        self._refresh_pdk_preflight()
        self.refresh_pdk_bundle_preflight()
        self.refresh_pdk_prebuilt_summary()
        self.refresh_digital_flow_summary()
        self.refresh_pdk_source_preflight()
        self._update_pdk_candidate_summary()
        self._sync_action_gates()
        self._finish_activity(True, pick(self.lang, "Búsqueda de PDK lista", "PDK search ready"))

    def apply_selected_pdk_candidate(self) -> None:
        sky130a_path = str(self.pdk_candidate_combo.currentData() or "").strip()
        if not sky130a_path:
            self.pdk_candidate_summary.setText(
                pick(self.lang, "No hay un PDK seleccionado todavía.", "No PDK candidate is selected yet.")
            )
            return
        self._begin_activity(pick(self.lang, "Adoptando PDK detectado...", "Adopting detected PDK..."))
        changed = self.setup_mgr.apply_pdk_candidate(self.settings, sky130a_path)
        self.rescan_environment()
        if changed:
            self.settings_updated.emit(self.settings)
            self.send_status.emit(pick(self.lang, "PDK detectado aplicado", "Detected PDK applied"))
            self.log.append(
                pick(
                    self.lang,
                    f"Se adoptó el PDK detectado en {sky130a_path}.\n",
                    f"The detected PDK at {sky130a_path} was adopted.\n",
                )
            )
            self._route_after_pdk_ready()
            self._finish_activity(True, pick(self.lang, "PDK listo para usar", "PDK ready to use"))
            return
        self._route_after_pdk_ready()
        self._finish_activity(True, pick(self.lang, "El PDK ya estaba aplicado", "The PDK was already applied"))

    def install_managed_pdk(self) -> None:
        self._begin_activity(pick(self.lang, "Instalando PDK gestionado...", "Installing managed PDK..."))
        result = self.setup_mgr.install_managed_pdk(self.settings)
        if result.ok:
            if result.changed:
                self.settings_updated.emit(self.settings)
            self.log.append(
                pick(
                    self.lang,
                    f"{result.message}\n",
                    f"{result.message}\n",
                )
            )
            self.send_status.emit(pick(self.lang, "PDK gestionado listo", "Managed PDK ready"))
            self.rescan_environment()
            self._route_after_pdk_ready()
            self._finish_activity(True, pick(self.lang, "PDK gestionado instalado", "Managed PDK installed"))
            return
        self.log.append(pick(self.lang, f"{result.message}\n", f"{result.message}\n"))
        self.send_status.emit(pick(self.lang, "Instalación de PDK pendiente", "PDK installation pending"))
        self._refresh_pdk_preflight()
        self._finish_activity(False, pick(self.lang, "No se pudo instalar el PDK", "Failed to install PDK"))

    def refresh_pdk_source_preflight(self) -> None:
        self._pdk_source_preflight = self.setup_mgr.pdk_source_build_preflight(self.settings)
        summary = self._pdk_source_preflight
        missing = ", ".join(summary.missing_commands) if summary.missing_commands else pick(self.lang, "ninguno", "none")
        self.pdk_source_preflight_summary.setText(
            pick(
                self.lang,
                f"Build root: {summary.build_root}\n"
                f"Destino: {summary.target_sky130a}\n"
                f"Espacio libre: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Fuente pinneada: {'sí' if summary.has_pinned_source else 'no'}\n"
                f"Comandos faltantes: {missing}\n"
                f"Candidato reutilizable detectado: {'sí' if summary.reusable_candidate_available else 'no'}\n"
                f"Listo para build: {'sí' if summary.ready else 'no'}",
                f"Build root: {summary.build_root}\n"
                f"Target: {summary.target_sky130a}\n"
                f"Free space: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Pinned source: {'yes' if summary.has_pinned_source else 'no'}\n"
                f"Missing commands: {missing}\n"
                f"Reusable candidate detected: {'yes' if summary.reusable_candidate_available else 'no'}\n"
                f"Ready to build: {'yes' if summary.ready else 'no'}",
            )
        )
        self._sync_action_gates()

    def refresh_pdk_bundle_preflight(self) -> None:
        self._pdk_bundle_preflight = self.setup_mgr.pdk_bundle_preflight(self.settings)
        summary = self._pdk_bundle_preflight
        disabled_reason = "" if summary.enabled else self.setup_mgr.manifest.channel().pdk_bundle_disabled_reason
        self.pdk_bundle_summary.setText(
            pick(
                self.lang,
                f"Bundle: {summary.bundle_name}\n"
                f"Versión: {summary.bundle_version or 'no publicado'}\n"
                f"Instalación canónica: {summary.target_sky130a}\n"
                f"Cache: {summary.cache_root}\n"
                f"Espacio libre: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Asset configurado: {'sí' if bool(summary.asset_url and summary.asset_filename) else 'no'}\n"
                f"Publicado por la app: {'sí' if summary.enabled else 'no'}\n"
                f"Listo para instalar: {'sí' if summary.ready else 'no'}"
                + (f"\nMotivo: {disabled_reason}" if disabled_reason else ""),
                f"Bundle: {summary.bundle_name}\n"
                f"Version: {summary.bundle_version or 'not published'}\n"
                f"Canonical install: {summary.target_sky130a}\n"
                f"Cache: {summary.cache_root}\n"
                f"Free space: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Asset configured: {'yes' if bool(summary.asset_url and summary.asset_filename) else 'no'}\n"
                f"Published by the app: {'yes' if summary.enabled else 'no'}\n"
                f"Ready to install: {'yes' if summary.ready else 'no'}"
                + (f"\nReason: {disabled_reason}" if disabled_reason else ""),
            )
        )
        self._sync_action_gates()

    def refresh_pdk_prebuilt_summary(self) -> None:
        """Describe the upstream prebuilt PDK route pinned by the manifest."""
        policy = self.setup_mgr.manifest.channel()
        if not policy.pdk_prebuilt_enabled:
            self.pdk_prebuilt_summary.setText(
                pick(self.lang, "Ruta no disponible en este canal.", "Route unavailable in this channel.")
            )
            return
        version = policy.pdk_prebuilt_version
        short = version[:12] if version else pick(self.lang, "sin fijar", "unpinned")
        self.pdk_prebuilt_summary.setText(
            pick(
                self.lang,
                f"Proveedor: {policy.pdk_prebuilt_provider} (builds oficiales upstream)\n"
                f"Familia: {policy.pdk_prebuilt_family}\n"
                f"Build fijado: {short}\n"
                f"PDK_ROOT: {policy.pdk_prebuilt_root}\n"
                f"Releases: {policy.pdk_prebuilt_releases_url}\n"
                "Se instala como usuario normal, sin sudo.",
                f"Provider: {policy.pdk_prebuilt_provider} (official upstream builds)\n"
                f"Family: {policy.pdk_prebuilt_family}\n"
                f"Pinned build: {short}\n"
                f"PDK_ROOT: {policy.pdk_prebuilt_root}\n"
                f"Releases: {policy.pdk_prebuilt_releases_url}\n"
                "Installs as the normal user, without sudo.",
            )
        )

    def refresh_digital_flow_summary(self) -> None:
        """Describe the container runtime and whether the image is present."""
        policy = self.setup_mgr.manifest.channel()
        if not policy.digital_flow_enabled:
            self.digital_flow_summary.setText(
                pick(self.lang, "Flujo digital deshabilitado en este canal.",
                     "Digital flow disabled in this channel.")
            )
            self._digital_flow_ready = False
            return

        runtime = detect_runtime()
        self._container_runtime = runtime
        has_image = image_present(policy.digital_flow_image, runtime) if runtime.ready else False
        self._digital_flow_ready = has_image

        tools = ", ".join(policy.digital_flow_includes)
        lines = [
            pick(self.lang, f"Imagen: {policy.digital_flow_image}", f"Image: {policy.digital_flow_image}"),
            pick(self.lang, f"Incluye: {tools}", f"Includes: {tools}"),
            pick(self.lang, f"Descarga: ~{policy.digital_flow_download_gb} GB",
                 f"Download: ~{policy.digital_flow_download_gb} GB"),
            pick(self.lang, f"Runtime: {runtime.message}", f"Runtime: {runtime.message}"),
            pick(
                self.lang,
                f"Imagen descargada: {'sí' if has_image else 'no'}",
                f"Image downloaded: {'yes' if has_image else 'no'}",
            ),
        ]
        self.digital_flow_summary.setText("\n".join(lines))

    def install_docker(self) -> None:
        """Install the container runtime. This is a privileged system change."""
        script = self.setup_mgr.docker_install_script()
        if not script.is_file():
            self.log.append(pick(self.lang, f"Script no encontrado: {script}\n",
                                 f"Script not found: {script}\n"))
            return
        self._begin_activity(pick(self.lang, "Instalando Docker...", "Installing Docker..."))
        self.log.append(
            pick(
                self.lang,
                "Instalando docker.io desde los repositorios de Ubuntu y agregando tu usuario "
                "al grupo `docker`. Al terminar tendrás que cerrar sesión para que aplique.\n",
                "Installing docker.io from the Ubuntu repositories and adding your user to the "
                "`docker` group. You will need to log out before it takes effect.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Instalando Docker", "Installing Docker"))
        self._runner_action = "install_docker"
        self.runner.run(CommandSpec(command=self.setup_mgr.docker_install_command()))

    def pull_digital_flow(self) -> None:
        """Download the LibreLane image, which carries OpenLane and OpenROAD."""
        runtime = getattr(self, "_container_runtime", None) or detect_runtime()
        if not runtime.ready:
            self.log.append(f"\n{runtime.message}\n")
            if runtime.needs_relogin:
                self.log.append(
                    pick(self.lang,
                         "Cierra sesión y vuelve a entrar; el grupo `docker` ya está concedido.\n",
                         "Log out and back in; the `docker` group is already granted.\n")
                )
            return
        script = self.setup_mgr.digital_flow_image_script()
        if not script.is_file():
            self.log.append(pick(self.lang, f"Script no encontrado: {script}\n",
                                 f"Script not found: {script}\n"))
            return
        self._begin_activity(pick(self.lang, "Descargando flujo digital...", "Downloading digital flow..."))
        self.log.append(
            pick(self.lang,
                 "Descargando la imagen de LibreLane (~1.6 GB). Puede tardar varios minutos.\n",
                 "Downloading the LibreLane image (~1.6 GB). This can take several minutes.\n")
        )
        self.send_status.emit(pick(self.lang, "Descargando flujo digital", "Downloading digital flow"))
        self._runner_action = "pull_digital_flow"
        self.runner.run(CommandSpec(command=self.setup_mgr.digital_flow_image_command()))

    def install_prebuilt_pdk(self) -> None:
        """Install sky130A from the upstream prebuilt releases."""
        script_path = self.setup_mgr.pdk_prebuilt_install_script()
        if not script_path.is_file():
            self.log.append(
                pick(
                    self.lang,
                    f"Script del PDK oficial no encontrado: {script_path}\n",
                    f"Official PDK script was not found: {script_path}\n",
                )
            )
            return
        self._begin_activity(pick(self.lang, "Instalando PDK oficial...", "Installing official PDK..."))
        self.log.append(
            pick(
                self.lang,
                "Descargando el sky130A precompilado desde los releases upstream. Puede tardar varios minutos.\n",
                "Downloading the prebuilt sky130A from the upstream releases. This can take several minutes.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Instalando PDK oficial", "Installing official PDK"))
        self._runner_action = "install_pdk_prebuilt"
        self.runner.run(CommandSpec(command=self.setup_mgr.pdk_prebuilt_install_command()))

    def install_bundle_pdk(self) -> None:
        self.refresh_pdk_bundle_preflight()
        summary = self._pdk_bundle_preflight
        if summary is None or not summary.ready:
            self.log.append(
                pick(
                    self.lang,
                    "El bundle PDK todavía no está listo para descargarse e instalarse. Revisa el panel del bundle.\n",
                    "The PDK bundle is not ready to download and install yet. Review the bundle panel.\n",
                )
            )
            return
        script_path = self.setup_mgr.pdk_bundle_install_script()
        if not script_path.exists():
            self.log.append(
                pick(
                    self.lang,
                    f"Script del bundle no encontrado: {script_path}\n",
                    f"Bundle script not found: {script_path}\n",
                )
            )
            return
        self._begin_activity(pick(self.lang, "Descargando bundle PDK...", "Downloading PDK bundle..."))
        self.log.append(
            pick(
                self.lang,
                "Descargando e instalando el bundle PDK en la ruta canónica del usuario. Esto puede tardar bastante.\n",
                "Downloading and installing the PDK bundle into the user's canonical path. This can take a while.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Instalando bundle PDK", "Installing PDK bundle"))
        self._runner_action = "install_pdk_bundle"
        self.runner.run(CommandSpec(command=self.setup_mgr.pdk_bundle_install_command()))

    def build_pdk_from_sources(self) -> None:
        self.refresh_pdk_source_preflight()
        summary = self._pdk_source_preflight
        if summary is None or not summary.ready:
            self.log.append(
                pick(
                    self.lang,
                    "El build desde fuentes sigue bloqueado. Revisa el panel de prechecks.\n",
                    "Source build is still blocked. Review the precheck panel.\n",
                )
            )
            return
        script_path = self.setup_mgr.pdk_source_build_script()
        if not script_path.exists():
            self.log.append(
                pick(
                    self.lang,
                    f"Script de build no encontrado: {script_path}\n",
                    f"Build script not found: {script_path}\n",
                )
            )
            return
        self._begin_activity(pick(self.lang, "Compilando PDK desde fuentes...", "Building PDK from sources..."))
        self.log.append(
            pick(
                self.lang,
                "Lanzando build gestionado del PDK desde fuentes pinneadas. Este proceso puede tardar bastante.\n",
                "Launching managed PDK build from pinned sources. This process can take a while.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Build de PDK en progreso", "PDK build in progress"))
        self._runner_action = "build_pdk_sources"
        self.runner.run(CommandSpec(command=self.setup_mgr.pdk_source_build_command()))

    def apply_detected_defaults(self) -> None:
        self._apply_detected_defaults(automatic=False)

    def install_environment(self) -> None:
        script_path = self.setup_mgr.installer_script()
        if not script_path.exists():
            self.log.append(
                pick(
                    self.lang,
                    f"Script de instalación no encontrado: {script_path}\n",
                    f"Installer script not found: {script_path}\n",
                )
            )
            return
        self._begin_activity(pick(self.lang, "Instalando toolchain...", "Installing toolchain..."))
        self.log.append(
            pick(
                self.lang,
                "Lanzando bootstrap de Ubuntu con privilegios. Este paso instala paquetes del sistema y Magic 8.3.634; el entorno Python XDG se prepara después como usuario normal.\n",
                "Launching Ubuntu bootstrap with privileges. This step installs system packages and Magic 8.3.634; the XDG Python environment is prepared afterwards as the normal user.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Instalación en progreso", "Installation in progress"))
        self._set_step(self.STEP_TOOLS)
        self._runner_action = "install_tools"
        self.runner.run(CommandSpec(command=self.setup_mgr.installer_command()))

    def _on_finished(self, code: int, status: str) -> None:
        action = self._runner_action
        self._runner_action = ""

        if code == 0 and action == "install_tools":
            self.log.append(
                pick(
                    self.lang,
                    "\nInstalación o validación completada. Aplicando rutas detectadas automáticamente y refrescando el diagnóstico.\n",
                    "\nInstallation or validation completed. Applying detected paths automatically and refreshing diagnostics.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Setup listo", "Setup ready"))
            self.rescan_environment()
            self._apply_detected_defaults(automatic=True)
            self._route_after_tools_ready()
            self._finish_activity(True, pick(self.lang, "Instalación lista", "Installation ready"))
            return

        if code == 0 and action == "build_pdk_sources":
            self.log.append(
                pick(
                    self.lang,
                    "\nBuild del PDK completado. Refrescando detección y validación.\n",
                    "\nPDK build completed. Refreshing detection and validation.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Build de PDK listo", "PDK build ready"))
            self.rescan_environment()
            self._route_after_pdk_ready()
            self._finish_activity(True, pick(self.lang, "Build de PDK listo", "PDK build ready"))
            return

        if code == 0 and action == "install_pdk_bundle":
            self.log.append(
                pick(
                    self.lang,
                    "\nBundle PDK instalado. Refrescando detección y validación.\n",
                    "\nPDK bundle installed. Refreshing detection and validation.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Bundle PDK listo", "PDK bundle ready"))
            self.rescan_environment()
            self._apply_detected_defaults(automatic=True)
            self._route_after_pdk_ready()
            self._finish_activity(True, pick(self.lang, "Bundle PDK listo", "PDK bundle ready"))
            return

        if code == 0 and action == "install_pdk_prebuilt":
            self.log.append(
                pick(
                    self.lang,
                    "\nPDK oficial instalado. Refrescando detección y validación.\n",
                    "\nOfficial PDK installed. Refreshing detection and validation.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "PDK oficial listo", "Official PDK ready"))
            self.rescan_environment()
            self._apply_detected_defaults(automatic=True)
            self._route_after_pdk_ready()
            self._finish_activity(True, pick(self.lang, "PDK oficial listo", "Official PDK ready"))
            return

        if action == "build_pdk_sources":
            self.log.append(
                pick(
                    self.lang,
                    f"\nEl build del PDK falló (exit={code}, status={status}). Revisa el log y corrige el precheck bloqueante.\n",
                    f"\nThe PDK build failed (exit={code}, status={status}). Review the log and fix the blocking precheck.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Build de PDK falló", "PDK build failed"))
            self.refresh_pdk_source_preflight()
            self._finish_activity(False, pick(self.lang, "Build de PDK falló", "PDK build failed"))
            return

        if action == "install_pdk_bundle":
            self.log.append(
                pick(
                    self.lang,
                    f"\nLa instalación del bundle PDK falló (exit={code}, status={status}). Revisa el log y la configuración del asset.\n",
                    f"\nPDK bundle installation failed (exit={code}, status={status}). Review the log and the asset configuration.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Bundle PDK falló", "PDK bundle failed"))
            self.refresh_pdk_bundle_preflight()
            self._finish_activity(False, pick(self.lang, "Bundle PDK falló", "PDK bundle failed"))
            return

        if action == "install_pdk_prebuilt":
            self.log.append(
                pick(
                    self.lang,
                    f"\nLa instalación del PDK oficial falló (exit={code}, status={status}). "
                    "Revisa el log; suele faltar `pip` de usuario o `~/.local/bin` en el PATH.\n",
                    f"\nOfficial PDK installation failed (exit={code}, status={status}). "
                    "Check the log; a missing user `pip` or `~/.local/bin` on PATH is the usual cause.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "PDK oficial falló", "Official PDK failed"))
            self._finish_activity(False, pick(self.lang, "PDK oficial falló", "Official PDK failed"))
            return

        if action == "install_docker":
            if code == 0:
                self.log.append(
                    pick(
                        self.lang,
                        "\nDocker instalado. Cierra sesión y vuelve a entrar para que el grupo "
                        "`docker` aplique, y luego descarga el flujo digital.\n",
                        "\nDocker installed. Log out and back in so the `docker` group applies, "
                        "then download the digital flow.\n",
                    )
                )
                self.send_status.emit(pick(self.lang, "Docker instalado", "Docker installed"))
            else:
                self.log.append(
                    pick(self.lang,
                         f"\nLa instalación de Docker falló (exit={code}, status={status}).\n",
                         f"\nDocker installation failed (exit={code}, status={status}).\n")
                )
                self.send_status.emit(pick(self.lang, "Docker falló", "Docker failed"))
            self.refresh_digital_flow_summary()
            self._finish_activity(code == 0, pick(self.lang, "Docker", "Docker"))
            return

        if action == "pull_digital_flow":
            if code == 0:
                self.log.append(
                    pick(self.lang,
                         "\nFlujo digital listo. La imagen trae OpenROAD, Yosys, Magic, KLayout y netgen.\n",
                         "\nDigital flow ready. The image carries OpenROAD, Yosys, Magic, KLayout and netgen.\n")
                )
                self.send_status.emit(pick(self.lang, "Flujo digital listo", "Digital flow ready"))
            else:
                self.log.append(
                    pick(self.lang,
                         f"\nLa descarga del flujo digital falló (exit={code}, status={status}).\n",
                         f"\nDigital flow download failed (exit={code}, status={status}).\n")
                )
                self.send_status.emit(pick(self.lang, "Flujo digital falló", "Digital flow failed"))
            self.refresh_digital_flow_summary()
            self._finish_activity(code == 0, pick(self.lang, "Flujo digital", "Digital flow"))
            return

        if action == "install_tools":
            self._handle_install_tools_failure(code, status)
            return

        self._finish_activity(code == 0, pick(self.lang, "Acción completada", "Action finished"))

    def _handle_install_tools_failure(self, code: int, status: str) -> None:
        self.log.append(
            pick(
                self.lang,
                f"\nEl instalador terminó con advertencia/error (exit={code}, status={status}). Revalidando lo que quedó instalado.\n",
                f"\nThe installer ended with a warning/error (exit={code}, status={status}). Revalidating what is installed now.\n",
            )
        )
        self.rescan_environment()
        self._apply_detected_defaults(automatic=True)
        diagnosis = self._last_diagnosis
        if diagnosis is not None and self._tools_ready(diagnosis):
            self.log.append(
                pick(
                    self.lang,
                    "Las tools base ya se detectan correctamente; se conserva el log porque el proceso reportó error al salir.\n",
                    "The base tools are now detected correctly; the log is kept because the process reported an error on exit.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Tools detectadas", "Tools detected"))
            self._route_after_tools_ready()
            self._finish_activity(True, pick(self.lang, "Tools detectadas", "Tools detected"))
            return

        self.log.append(
            pick(
                self.lang,
                "Siguen faltando tools después de revalidar. Revisa el log del instalador para ver el paquete o comando bloqueante.\n",
                "Tools are still missing after revalidation. Review the installer log for the blocking package or command.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Setup falló", "Setup failed"))
        self._set_step(self.STEP_TOOLS)
        self._finish_activity(False, pick(self.lang, "Instalación falló", "Installation failed"))

    def _apply_detected_defaults(self, automatic: bool) -> None:
        self._begin_activity(
            pick(self.lang, "Aplicando rutas detectadas...", "Applying detected paths...")
            if not automatic
            else pick(self.lang, "Guardando rutas detectadas...", "Saving detected paths...")
        )
        changed = self.setup_mgr.apply_detected_defaults(self.settings)
        self.rescan_environment()
        if changed:
            self.settings_updated.emit(self.settings)
            if automatic:
                self.log.append(
                    pick(
                        self.lang,
                        "Se guardaron rutas detectadas automáticamente para tools y PDK.\n",
                        "Detected tool and PDK paths were saved automatically.\n",
                    )
                )
            else:
                self.log.append(
                    pick(
                        self.lang,
                        "Se aplicaron rutas detectadas automáticamente. Revisa Preferences si quieres afinarlas.\n",
                        "Automatically detected paths were applied. Review Preferences if you want to fine-tune them.\n",
                    )
                )
            self.send_status.emit(pick(self.lang, "Rutas detectadas aplicadas", "Detected paths applied"))
            self._set_step(self.STEP_VALIDATE)
            self._finish_activity(True, pick(self.lang, "Rutas aplicadas", "Paths applied"))
            return

        if automatic:
            self.log.append(
                pick(
                    self.lang,
                    "No se encontraron rutas nuevas para autoconfigurar; puedes revisarlas manualmente en Preferences.\n",
                    "No new paths were found to auto-configure; you can review them manually in Preferences.\n",
                )
            )
        else:
            self.log.append(
                pick(
                    self.lang,
                    "No hubo cambios: ya existían rutas válidas o no se detectó una instalación compatible.\n",
                    "No changes were applied: valid paths already existed or no compatible installation was detected.\n",
                )
            )
        self._finish_activity(True, pick(self.lang, "Sin cambios pendientes", "No pending changes"))

    @staticmethod
    def _tools_ready(diagnosis) -> bool:
        return all(tool.status in {"ok", "alias"} for tool in diagnosis.tools.values())

    @staticmethod
    def _pdk_ready(diagnosis) -> bool:
        return diagnosis.pdk.status == "present"

    def _route_after_pdk_ready(self) -> None:
        diagnosis = self._last_diagnosis
        if diagnosis is not None and not self._tools_ready(diagnosis):
            self.log.append(
                pick(
                    self.lang,
                    "PDK listo. Aún faltan tools base, continúa con el paso de instalación de tools.\n",
                    "PDK is ready. Base tools are still missing, continue with the tools installation step.\n",
                )
            )
            self._set_step(self.STEP_TOOLS)
            return
        self._set_step(self.STEP_APPLY)

    def _route_after_tools_ready(self) -> None:
        diagnosis = self._last_diagnosis
        if diagnosis is not None and self._pdk_ready(diagnosis):
            self._set_step(self.STEP_APPLY)
            return
        self._set_step(self.STEP_PDK)

    def _update_ready_state(self, diagnosis) -> None:
        tools_ready = self._tools_ready(diagnosis)
        pdk_ready = self._pdk_ready(diagnosis)
        python_ready = not diagnosis.python_env.problems and diagnosis.python_env.requirements_ok

        def summary(ready: bool, partial: bool = False) -> str:
            if ready:
                return pick(self.lang, "Listo", "Ready")
            if partial:
                return pick(self.lang, "Parcial", "Partial")
            return pick(self.lang, "Pendiente", "Pending")

        self.card_tools_value.setText(summary(tools_ready, partial=any(tool.status in {"ok", "alias"} for tool in diagnosis.tools.values())))
        self.card_pdk_value.setText(
            pick(self.lang, "Listo", "Ready")
            if pdk_ready
            else pick(self.lang, "Incompleto", "Incomplete")
            if diagnosis.pdk.found
            else pick(self.lang, "Ausente", "Absent")
        )
        self.card_python_value.setText(summary(python_ready, partial=diagnosis.python_env.venv_exists))
        overall_ready = diagnosis.overall_status == "ok"
        self.card_overall_value.setText(
            pick(self.lang, "Listo", "Ready")
            if overall_ready
            else pick(self.lang, "Atención", "Attention")
            if diagnosis.overall_status == "warning"
            else pick(self.lang, "Pendiente", "Pending")
        )
        self.ready_badge.setText(pick(self.lang, "ENVIRONMENT READY", "ENVIRONMENT READY") if overall_ready else pick(self.lang, "SETUP IN PROGRESS", "SETUP IN PROGRESS"))
        self.ready_title.setText(
            pick(self.lang, "Tu entorno está listo", "Your environment is ready")
            if overall_ready
            else pick(self.lang, "Aún faltan algunos pasos críticos", "A few critical steps are still pending")
        )
        self.ready_text.setText(
            pick(
                self.lang,
                "Puedes volver a Simulation, Extraction o LVS con confianza."
                if overall_ready
                else "La app no marcará el entorno como listo mientras falte el PDK, exista un entorno Python roto o falten permisos de escritura.",
                "You can go back to Simulation, Extraction, or LVS with confidence."
                if overall_ready
                else "The app will not report the environment as ready while the PDK is missing, the Python environment is broken, or write permissions are insufficient.",
            )
        )

    def _set_activity_idle(self) -> None:
        self.activity_badge.setObjectName("activityBadge")
        self.activity_badge.setStyleSheet(badge_style(self._theme, "idle"))
        self.activity_badge.setText("•")
        self.activity_text.setObjectName("activityText")
        self.activity_text.setText(pick(self.lang, "Esperando acciones del asistente", "Waiting for setup actions"))

    def _begin_activity(self, message: str) -> None:
        self._active_operations += 1
        self._spinner_index = 0
        self.activity_badge.setText(self._spinner_frames[self._spinner_index])
        self.activity_badge.setStyleSheet(badge_style(self._theme, "busy"))
        self.activity_text.setText(message)
        if not self._activity_timer.isActive():
            self._activity_timer.start()
        self._set_action_buttons_enabled(False)
        QCoreApplication.processEvents()

    def _finish_activity(self, success: bool, message: str) -> None:
        self._active_operations = max(0, self._active_operations - 1)
        if self._active_operations > 0:
            return
        self._activity_timer.stop()
        self.activity_badge.setText("✓" if success else "!")
        self.activity_badge.setStyleSheet(badge_style(self._theme, "ok" if success else "error"))
        self.activity_text.setText(message)
        self._set_action_buttons_enabled(True)
        QTimer.singleShot(1800, self._restore_idle_if_quiet)
        QCoreApplication.processEvents()

    def _restore_idle_if_quiet(self) -> None:
        if self._active_operations == 0:
            self._set_activity_idle()

    def _advance_spinner(self) -> None:
        if self._active_operations <= 0:
            self._activity_timer.stop()
            return
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self.activity_badge.setText(self._spinner_frames[self._spinner_index])

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.validate_btn.setEnabled(False)
            self.apply_defaults_btn.setEnabled(False)
            self.install_btn.setEnabled(False)
            self.refresh_detect_btn.setEnabled(False)
            self.detect_pdk_btn.setEnabled(False)
            self.use_pdk_btn.setEnabled(False)
            self.install_managed_pdk_btn.setEnabled(False)
            self.install_bundle_pdk_btn.setEnabled(False)
            self.check_source_build_btn.setEnabled(False)
            self.build_from_sources_btn.setEnabled(False)
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return
        self._sync_action_gates()

    def _explain_disabled_actions(self) -> None:
        """Say why a greyed-out button is greyed out.

        Three of the six PDK actions are normally disabled on a machine that
        already has a PDK. With no explanation that reads as the assistant
        being broken rather than as nothing needing to be done.
        """
        pending = pick(self.lang, "Primero revisa el sistema.", "Review the system first.")

        def explain(button, reason: str) -> None:
            if button.isEnabled():
                button.setToolTip("")
                return
            button.setToolTip(pending if not self._verification_completed else reason)

        existing = getattr(self._pdk_preflight, "existing_status", "")
        explain(
            self.install_managed_pdk_btn,
            pick(
                self.lang,
                f"Ya hay un PDK en {getattr(self._pdk_preflight, 'target_sky130a', '~/pdk/sky130A')}, "
                "así que no hay nada que instalar aquí."
                if existing == "present"
                else "Selecciona antes un candidato con `Buscar PDK reutilizable`.",
                f"A PDK already exists at {getattr(self._pdk_preflight, 'target_sky130a', '~/pdk/sky130A')}, "
                "so there is nothing to install here."
                if existing == "present"
                else "Pick a candidate first with `Find reusable PDK`.",
            ),
        )
        explain(
            self.install_bundle_pdk_btn,
            pick(
                self.lang,
                "El bundle descargable está deshabilitado desde 0.3.0. "
                "Usa `Instalar PDK oficial (ciel)`.",
                "The downloadable bundle has been disabled since 0.3.0. "
                "Use `Install official PDK (ciel)` instead.",
            ),
        )
        explain(
            self.build_from_sources_btn,
            pick(
                self.lang,
                "Corre antes `Precheck build desde fuentes`; el build necesita "
                "compiladores y ~20 GB libres.",
                "Run `Source-build precheck` first; the build needs compilers "
                "and about 20 GB of free space.",
            ),
        )
        explain(
            self.use_pdk_btn,
            pick(
                self.lang,
                "No hay candidatos todavía. Usa `Buscar PDK reutilizable`.",
                "No candidates yet. Use `Find reusable PDK`.",
            ),
        )
        runtime = getattr(self, "_container_runtime", None)
        explain(
            self.install_docker_btn,
            pick(
                self.lang,
                "Docker ya está instalado y funcionando.",
                "Docker is already installed and working.",
            ),
        )
        explain(
            self.pull_digital_flow_btn,
            pick(
                self.lang,
                "La imagen del flujo digital ya está descargada."
                if getattr(self, "_digital_flow_ready", False)
                else (runtime.message if runtime is not None else "Instala Docker primero."),
                "The digital flow image is already downloaded."
                if getattr(self, "_digital_flow_ready", False)
                else (runtime.message if runtime is not None else "Install Docker first."),
            ),
        )
        explain(
            self.apply_defaults_btn,
            pick(
                self.lang,
                "No se detectaron rutas nuevas que aplicar.",
                "No newly detected paths to apply.",
            ),
        )

    def _sync_action_gates(self) -> None:
        if self._active_operations > 0:
            return
        diagnosis = self._last_diagnosis
        tools_ready = bool(diagnosis) and self._tools_ready(diagnosis)

        self.validate_btn.setEnabled(True)
        self.refresh_detect_btn.setEnabled(True)
        self.install_btn.setEnabled(self._verification_completed and not tools_ready)
        self.apply_defaults_btn.setEnabled(self._verification_completed and self._detected_defaults_available)
        self.detect_pdk_btn.setEnabled(self._verification_completed)
        self.use_pdk_btn.setEnabled(self._verification_completed and self._pdk_candidates_available)
        self.install_managed_pdk_btn.setEnabled(
            self._verification_completed
            and self._pdk_preflight is not None
            and self._pdk_preflight.enough_space
            and self._pdk_preflight.existing_status == "missing"
            and bool(self._pdk_preflight.selected_candidate)
        )
        self.install_bundle_pdk_btn.setEnabled(
            self._verification_completed
            and self._pdk_bundle_preflight is not None
            and self._pdk_bundle_preflight.ready
        )
        self.install_prebuilt_pdk_btn.setEnabled(self._verification_completed)
        runtime = getattr(self, "_container_runtime", None)
        self.install_docker_btn.setEnabled(
            self._verification_completed and (runtime is None or not runtime.ready)
        )
        self.pull_digital_flow_btn.setEnabled(
            self._verification_completed
            and runtime is not None
            and runtime.ready
            and not getattr(self, "_digital_flow_ready", False)
        )
        self.check_source_build_btn.setEnabled(self._verification_completed)
        self.build_from_sources_btn.setEnabled(
            self._verification_completed
            and self._pdk_source_preflight is not None
            and self._pdk_source_preflight.ready
        )
        self.install_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica el sistema." if not self._verification_completed else
                "Las tools base ya están instaladas." if tools_ready else
                "Instala el toolchain base sólo si aún falta.",
                "Verify the system first." if not self._verification_completed else
                "The base tools are already installed." if tools_ready else
                "Install the base toolchain only if it is still missing.",
            )
        )
        self.apply_defaults_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica y detecta rutas." if not self._verification_completed else
                "No hay rutas nuevas detectadas para aplicar." if not self._detected_defaults_available else
                "Aplica sólo las rutas detectadas válidas.",
                "Verify and detect paths first." if not self._verification_completed else
                "There are no new detected paths to apply." if not self._detected_defaults_available else
                "Apply only valid detected paths.",
            )
        )
        self.use_pdk_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica y busca candidatos de PDK." if not self._verification_completed else
                "No hay un PDK reutilizable detectado todavía." if not self._pdk_candidates_available else
                "Adopta el `sky130A` detectado como PDK activo de la app.",
                "Verify first and search for PDK candidates." if not self._verification_completed else
                "No reusable PDK was detected yet." if not self._pdk_candidates_available else
                "Adopt the detected `sky130A` as the app's active PDK.",
            )
        )
        self.install_managed_pdk_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica y busca un PDK reutilizable." if not self._verification_completed else
                "No hay espacio libre o no existe candidato reutilizable." if (
                    self._pdk_preflight is None
                    or not self._pdk_preflight.enough_space
                    or not self._pdk_preflight.selected_candidate
                ) else
                "Instala un PDK gestionado en la ruta canónica configurada.",
                "Verify first and search for a reusable PDK." if not self._verification_completed else
                "There is not enough free space or no reusable candidate exists." if (
                    self._pdk_preflight is None
                    or not self._pdk_preflight.enough_space
                    or not self._pdk_preflight.selected_candidate
                ) else
                "Install a managed PDK in the configured canonical path.",
            )
        )
        self.install_bundle_pdk_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica el sistema y configura un asset del bundle PDK en el manifiesto." if not self._verification_completed else
                "El bundle PDK sigue bloqueado por configuración, espacio o porque ya existe el destino." if (
                    self._pdk_bundle_preflight is None or not self._pdk_bundle_preflight.ready
                ) else
                "Descarga e instala un bundle `sky130A` ya preparado en `~/pdk`.",
                "Verify the system first and configure a PDK bundle asset in the manifest." if not self._verification_completed else
                "The PDK bundle is still blocked by configuration, space, or because the target already exists." if (
                    self._pdk_bundle_preflight is None or not self._pdk_bundle_preflight.ready
                ) else
                "Download and install a prebuilt `sky130A` bundle into `~/pdk`.",
            )
        )
        self.build_from_sources_btn.setToolTip(
            pick(
                self.lang,
                "Primero verifica y ejecuta los prechecks de build." if not self._verification_completed else
                "El build desde fuentes sigue bloqueado por dependencias, pinning, espacio, destino o candidatos reutilizables." if (
                    self._pdk_source_preflight is None or not self._pdk_source_preflight.ready
                ) else
                "La máquina ya cumple las condiciones mínimas para intentar un build desde fuentes.",
                "Verify first and run the source-build prechecks." if not self._verification_completed else
                "Source build is still blocked by dependencies, pinning, space, target state, or reusable candidates." if (
                    self._pdk_source_preflight is None or not self._pdk_source_preflight.ready
                ) else
                "The machine now satisfies the minimum conditions to attempt a source build.",
            )
        )
        self._sync_step_ui()
        self._explain_disabled_actions()

    def _update_pdk_candidate_summary(self) -> None:
        sky130a_path = str(self.pdk_candidate_combo.currentData() or "").strip()
        if not sky130a_path:
            self.pdk_candidate_summary.setText(
                pick(
                    self.lang,
                    "Aún no se detectó un `sky130A` reutilizable. Usa la búsqueda para revisar staging locales, volare, ciel y rutas comunes.",
                    "No reusable `sky130A` has been detected yet. Use the search to inspect local staging, volare, ciel, and common roots.",
                )
            )
            return
        for candidate in self.setup_mgr.detect_reusable_pdk_candidates():
            if candidate.sky130a_path == sky130a_path:
                self.pdk_candidate_summary.setText(
                    pick(
                        self.lang,
                        f"Origen: {candidate.source}\nEstado: {candidate.status}\nRoot: {candidate.root_path}\nDetalle: {candidate.detail}",
                        f"Source: {candidate.source}\nStatus: {candidate.status}\nRoot: {candidate.root_path}\nDetail: {candidate.detail}",
                    )
                )
                return
        self.pdk_candidate_summary.setText(sky130a_path)

    def _refresh_pdk_preflight(self) -> None:
        self._pdk_preflight = self.setup_mgr.pdk_install_preflight(self.settings)
        summary = self._pdk_preflight
        self.pdk_preflight_summary.setText(
            pick(
                self.lang,
                f"Destino: {summary.target_sky130a}\n"
                f"Modo: {summary.install_mode}\n"
                f"Espacio libre: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Estado actual del destino: {summary.existing_status}\n"
                f"Candidato reutilizable: {summary.selected_candidate or 'ninguno'}",
                f"Target: {summary.target_sky130a}\n"
                f"Mode: {summary.install_mode}\n"
                f"Free space: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Current target status: {summary.existing_status}\n"
                f"Reusable candidate: {summary.selected_candidate or 'none'}",
            )
        )
