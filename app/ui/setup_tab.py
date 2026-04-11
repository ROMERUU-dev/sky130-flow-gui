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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.command_runner import CommandRunner, CommandSpec
from app.core.env_validator import EnvValidator
from app.core.i18n import pick
from app.core.settings_manager import AppSettings
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
        self.detected_label = QLabel()
        self.detected_label.setWordWrap(True)
        self.log = QTextEdit()
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
        self._runner_action = ""

        self.validate_btn = QPushButton(pick(self.lang, "Validar entorno", "Validate environment"))
        self.apply_defaults_btn = QPushButton(pick(self.lang, "Aplicar rutas detectadas", "Apply detected paths"))
        self.install_btn = QPushButton(pick(self.lang, "Instalar entorno VLSI en Ubuntu", "Install Ubuntu VLSI environment"))
        self.refresh_detect_btn = QPushButton(pick(self.lang, "Refrescar detección", "Refresh detection"))
        self.detect_pdk_btn = QPushButton(pick(self.lang, "Buscar PDK reutilizable", "Find reusable PDK"))
        self.use_pdk_btn = QPushButton(pick(self.lang, "Usar PDK seleccionado", "Use selected PDK"))
        self.install_managed_pdk_btn = QPushButton(pick(self.lang, "Instalar PDK gestionado", "Install managed PDK"))
        self.install_bundle_pdk_btn = QPushButton(pick(self.lang, "Descargar bundle PDK", "Download PDK bundle"))
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
        self.pdk_source_preflight_summary = QLabel()
        self.pdk_source_preflight_summary.setWordWrap(True)
        self.prev_btn = QPushButton(pick(self.lang, "Atrás", "Back"))
        self.next_btn = QPushButton(pick(self.lang, "Siguiente", "Next"))

        self._build_ui()
        self._wire()
        self._sync_step_ui()
        self._set_activity_idle()
        self._sync_action_gates()
        self.refresh_validation()
        self.refresh_detection()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel(pick(self.lang, "Asistente de entorno", "Setup Assistant"))
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #2563eb;")
        subtitle = QLabel(
            pick(
                self.lang,
                "Sigue estos pasos para dejar lista la máquina antes de correr extracción, simulación o LVS.",
                "Follow these steps to prepare the machine before running extraction, simulation, or LVS.",
            )
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #667085;")
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

        content_row = QHBoxLayout()
        content_row.setSpacing(18)

        step_card = QFrame()
        step_card.setObjectName("setupSidebar")
        step_card_layout = QVBoxLayout(step_card)
        step_card_layout.setContentsMargins(12, 12, 12, 12)
        step_card_layout.setSpacing(10)
        step_heading = QLabel(pick(self.lang, "Pasos", "Steps"))
        step_heading.setStyleSheet("font-weight: 800; color: #2563eb;")
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

        self.setStyleSheet(
            """
            QFrame#setupSidebar, QFrame#setupPageCard {
                background: #ffffff;
                border: 1px solid #e8eef7;
                border-radius: 18px;
            }
            QListWidget#setupSteps {
                background: transparent;
                border: 0;
                outline: 0;
            }
            QListWidget#setupSteps::item {
                min-height: 38px;
                padding: 10px 12px;
                margin: 0 0 6px 0;
                border: 1px solid transparent;
                border-radius: 12px;
                font-weight: 700;
                color: #475569;
            }
            QListWidget#setupSteps::item:selected {
                background: #f5f9ff;
                border: 1px solid #d8e5ff;
                color: #2563eb;
            }
            QProgressBar {
                background: #eef4fb;
                border: 0;
                border-radius: 7px;
                min-height: 10px;
                max-height: 10px;
            }
            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 7px;
            }
            QFrame#statusCard {
                background: #fbfdff;
                border: 1px solid #e1ebf8;
                border-radius: 14px;
            }
            QLabel#statusCardTitle {
                color: #667085;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#statusCardValue {
                color: #0f172a;
                font-size: 15px;
                font-weight: 800;
            }
            QLabel#readyBadge {
                color: #0f9d8a;
                background: #ecfdf3;
                border: 1px solid #b7ebcf;
                border-radius: 11px;
                padding: 5px 10px;
                font-weight: 800;
            }
            QLabel#activityBadge {
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                border-radius: 14px;
                font-weight: 900;
                font-size: 15px;
                padding: 0;
            }
            QLabel#activityText {
                color: #475467;
                font-weight: 700;
            }
            QLabel {
                color: #344054;
            }
            """
        )

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
                    "Este paso instala paquetes del sistema para Ubuntu y compila Magic 8.3.634 desde la fuente oficial para SKY130. No crea `.venv` ni toca el entorno Python del usuario.",
                    "This step installs Ubuntu system packages and builds Magic 8.3.634 from the official source release for SKY130. It does not create `.venv` or touch the user-owned Python environment.",
                )
            )
        )
        actions = QHBoxLayout()
        actions.addWidget(self.install_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
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
        actions.addWidget(self.install_bundle_pdk_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel(pick(self.lang, "Preflight de instalación gestionada", "Managed install preflight")))
        layout.addWidget(self.pdk_preflight_summary)
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
        self.ready_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #2563eb;")
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
        final_hint.setStyleSheet("color: #475467; font-weight: 600;")
        layout.addWidget(final_hint)
        return page

    def _page_heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 18px; font-weight: 800; color: #2563eb;")
        return label

    def _page_hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #667085;")
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
        self.validate_btn.clicked.connect(self.refresh_validation)
        self.apply_defaults_btn.clicked.connect(self.apply_detected_defaults)
        self.install_btn.clicked.connect(self.install_environment)
        self.refresh_detect_btn.clicked.connect(self.refresh_detection)
        self.detect_pdk_btn.clicked.connect(self.refresh_pdk_candidates)
        self.use_pdk_btn.clicked.connect(self.apply_selected_pdk_candidate)
        self.install_managed_pdk_btn.clicked.connect(self.install_managed_pdk)
        self.install_bundle_pdk_btn.clicked.connect(self.install_bundle_pdk)
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
                f"Checks correctos: {ok_count}/{total}. Herramientas, PDK y `.venv` se validan por separado.",
                f"Passing checks: {ok_count}/{total}. Tools, PDK, and `.venv` are validated independently.",
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
        self.refresh_detection()
        self.refresh_validation()
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
            self._set_step(self.STEP_APPLY)
            self._finish_activity(True, pick(self.lang, "PDK listo para usar", "PDK ready to use"))
            return
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
            self.refresh_detection()
            self.refresh_validation()
            self._set_step(self.STEP_APPLY)
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
                f"Listo para instalar: {'sí' if summary.ready else 'no'}",
                f"Bundle: {summary.bundle_name}\n"
                f"Version: {summary.bundle_version or 'not published'}\n"
                f"Canonical install: {summary.target_sky130a}\n"
                f"Cache: {summary.cache_root}\n"
                f"Free space: {summary.free_bytes / (1024 ** 3):.1f} GB\n"
                f"Asset configured: {'yes' if bool(summary.asset_url and summary.asset_filename) else 'no'}\n"
                f"Published by the app: {'yes' if summary.enabled else 'no'}\n"
                f"Ready to install: {'yes' if summary.ready else 'no'}",
            )
        )
        self._sync_action_gates()

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
                "Lanzando bootstrap de Ubuntu con privilegios. Este paso instala paquetes del sistema y Magic 8.3.634; `.venv` debe prepararse después como usuario normal.\n",
                "Launching Ubuntu bootstrap with privileges. This step installs system packages and Magic 8.3.634; `.venv` must be prepared afterwards as the normal user.\n",
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
            self.refresh_detection()
            self.refresh_validation()
            self._apply_detected_defaults(automatic=True)
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
            self.refresh_detection()
            self.refresh_validation()
            self._set_step(self.STEP_APPLY)
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
            self.refresh_detection()
            self.refresh_validation()
            self._apply_detected_defaults(automatic=True)
            self._set_step(self.STEP_APPLY)
            self._finish_activity(True, pick(self.lang, "Bundle PDK listo", "PDK bundle ready"))
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

        if action == "install_tools":
            self.log.append(
                pick(
                    self.lang,
                    f"\nEl proceso terminó con error (exit={code}, status={status}). Revisa el log; si falló `pkexec` o `apt`, el `.venv` no fue tocado.\n",
                    f"\nThe process ended with an error (exit={code}, status={status}). Review the log; if `pkexec` or `apt` failed, `.venv` was not modified.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Setup falló", "Setup failed"))
            self._finish_activity(False, pick(self.lang, "Instalación falló", "Installation failed"))
            return

        self._finish_activity(code == 0, pick(self.lang, "Acción completada", "Action finished"))

    def _apply_detected_defaults(self, automatic: bool) -> None:
        self._begin_activity(
            pick(self.lang, "Aplicando rutas detectadas...", "Applying detected paths...")
            if not automatic
            else pick(self.lang, "Guardando rutas detectadas...", "Saving detected paths...")
        )
        changed = self.setup_mgr.apply_detected_defaults(self.settings)
        self.refresh_detection()
        self.refresh_validation()
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

    def _update_ready_state(self, diagnosis) -> None:
        tools_ready = all(tool.status in {"ok", "alias"} for tool in diagnosis.tools.values())
        pdk_ready = diagnosis.pdk.status == "present"
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
                else "La app no marcará el entorno como listo mientras falte el PDK, exista un `.venv` roto o falten permisos de escritura.",
                "You can go back to Simulation, Extraction, or LVS with confidence."
                if overall_ready
                else "The app will not report the environment as ready while the PDK is missing, `.venv` is broken, or write permissions are insufficient.",
            )
        )

    def _set_activity_idle(self) -> None:
        self.activity_badge.setObjectName("activityBadge")
        self.activity_badge.setStyleSheet(
            "background: #f2f4f7; color: #667085; border: 1px solid #e4e7ec;"
        )
        self.activity_badge.setText("•")
        self.activity_text.setObjectName("activityText")
        self.activity_text.setText(pick(self.lang, "Esperando acciones del asistente", "Waiting for setup actions"))

    def _begin_activity(self, message: str) -> None:
        self._active_operations += 1
        self._spinner_index = 0
        self.activity_badge.setText(self._spinner_frames[self._spinner_index])
        self.activity_badge.setStyleSheet(
            "background: #eef4ff; color: #2563eb; border: 1px solid #cfe0ff;"
        )
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
        self.activity_badge.setStyleSheet(
            "background: #ecfdf3; color: #0f9d8a; border: 1px solid #b7ebcf;"
            if success
            else "background: #fef3f2; color: #d92d20; border: 1px solid #fecdca;"
        )
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

    def _sync_action_gates(self) -> None:
        if self._active_operations > 0:
            return
        diagnosis = self._last_diagnosis
        tools_ready = bool(diagnosis) and all(tool.status in {"ok", "alias"} for tool in diagnosis.tools.values())

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
