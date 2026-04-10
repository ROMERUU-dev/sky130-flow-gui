"""Setup assistant tab for environment bootstrap and validation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.lang = settings.language
        self.validator = EnvValidator()
        self.setup_mgr = SetupManager()
        self.runner = CommandRunner()
        self._wizard_steps = [
            pick(self.lang, "1. Revisar sistema", "1. Review system"),
            pick(self.lang, "2. Instalar tools", "2. Install tools"),
            pick(self.lang, "3. Aplicar rutas", "3. Apply paths"),
            pick(self.lang, "4. Validar", "4. Validate"),
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
        self.card_tools_value = QLabel("—")
        self.card_pdk_value = QLabel("—")
        self.card_python_value = QLabel("—")
        self.card_overall_value = QLabel("—")

        self.validate_btn = QPushButton(pick(self.lang, "Validar entorno", "Validate environment"))
        self.apply_defaults_btn = QPushButton(pick(self.lang, "Aplicar rutas detectadas", "Apply detected paths"))
        self.install_btn = QPushButton(pick(self.lang, "Instalar entorno VLSI en Ubuntu", "Install Ubuntu VLSI environment"))
        self.refresh_detect_btn = QPushButton(pick(self.lang, "Refrescar detección", "Refresh detection"))
        self.prev_btn = QPushButton(pick(self.lang, "Atrás", "Back"))
        self.next_btn = QPushButton(pick(self.lang, "Siguiente", "Next"))

        self._build_ui()
        self._wire()
        self._sync_step_ui()
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
                    "Este paso instala paquetes del sistema para Ubuntu: herramientas EDA base y librerías Qt/X11. No crea `.venv` ni toca el entorno Python del usuario.",
                    "This step installs Ubuntu system packages: base EDA tools and Qt/X11 runtime libraries. It does not create `.venv` or touch the user-owned Python environment.",
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
        self._current_step = index
        self.step_stack.setCurrentIndex(index)
        if self.step_list.currentRow() != index:
            self.step_list.setCurrentRow(index)
        self._sync_step_ui()

    def _sync_step_ui(self) -> None:
        self.prev_btn.setEnabled(self._current_step > 0)
        self.next_btn.setEnabled(self._current_step < len(self._wizard_steps) - 1)
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

    def refresh_validation(self) -> None:
        diagnosis = self.validator.diagnose(self.settings, lang=self.lang)
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

    def refresh_detection(self) -> None:
        lines = self.setup_mgr.summarize_detection(self.settings)
        diagnosis = self.validator.diagnose(self.settings, lang=self.lang)
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
        self.log.append(
            pick(
                self.lang,
                "Lanzando bootstrap de Ubuntu con privilegios. Este paso solo instala paquetes del sistema; `.venv` debe prepararse después como usuario normal.\n",
                "Launching Ubuntu bootstrap with privileges. This step only installs system packages; `.venv` must be prepared afterwards as the normal user.\n",
            )
        )
        self.send_status.emit(pick(self.lang, "Instalación en progreso", "Installation in progress"))
        self._set_step(1)
        self.runner.run(CommandSpec(command=self.setup_mgr.installer_command()))

    def _on_finished(self, code: int, status: str) -> None:
        if code == 0:
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
        else:
            self.log.append(
                pick(
                    self.lang,
                    f"\nEl proceso terminó con error (exit={code}, status={status}). Revisa el log; si falló `pkexec` o `apt`, el `.venv` no fue tocado.\n",
                    f"\nThe process ended with an error (exit={code}, status={status}). Review the log; if `pkexec` or `apt` failed, `.venv` was not modified.\n",
                )
            )
            self.send_status.emit(pick(self.lang, "Setup falló", "Setup failed"))

    def _apply_detected_defaults(self, automatic: bool) -> None:
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
            self._set_step(3)
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
