"""Four-step Qt6 interface: sign in, read repository, choose folder, upload."""
# Copyright (C) 2026 LionheartTim
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from backend import (
    PreparedUpload, UploadError, check_login, commit_and_push,
    parse_github_url, prepare_upload, read_repository,
)


APP_VERSION = '1.0.0'
AUTHOR_GITHUB_URL = 'https://github.com/LionheartTim'


STYLE = """
QWidget { background: #111827; color: #e5edf8; font-size: 13px; }
QLabel { background: transparent; }
QMainWindow { background: #111827; }
QLabel#title { font-size: 26px; font-weight: 750; color: #f8fafc; }
QLabel#subtitle { color: #9caac0; font-size: 13px; }
QLabel#step { color: #7caefa; font-weight: 600; font-size: 12px; }
QLabel#headline { color: #f8fafc; font-size: 20px; font-weight: 700; }
QLabel#muted { color: #a9b7c9; }
QLabel#footer { color: #94a3b8; font-size: 12px; }
QFrame#panel, QFrame#drop { background: #1c293b; border: 1px solid #34455e; border-radius: 13px; }
QFrame#drop[hovered="true"] { border: 2px dashed #5da6ff; background: #263f5c; }
QLineEdit { background: #101b2a; border: 1px solid #455c79; border-radius: 8px; padding: 12px; color: white; selection-background-color: #3c81ce; }
QLineEdit:focus { border-color: #65a9fa; }
QPushButton { border-radius: 8px; padding: 10px 15px; background: #344963; border: 1px solid #4a6383; font-weight: 600; color: #f3f7ff; }
QPushButton:hover { background: #405b7b; }
QPushButton:disabled { color: #8291a5; background: #253449; border-color: #324256; }
QPushButton#primary { background: #347de0; border-color: #347de0; color: white; }
QPushButton#primary:hover { background: #4693f5; }
QPushButton#danger { background: #b84949; border-color: #b84949; color: white; }
QPlainTextEdit { background: #0c1624; border: 1px solid #374a63; border-radius: 9px; padding: 10px; color: #c7d7e7; font-family: monospace; }
QProgressBar { border: 1px solid #3d536e; border-radius: 6px; background: #263448; height: 12px; text-align: center; }
QProgressBar::chunk { background: #4a9af4; border-radius: 5px; }
"""


class Job(QThread):
    success = Signal(object)
    failure = Signal(str)
    progress = Signal(str)

    def __init__(self, action: Callable, *args):
        super().__init__()
        self.action = action
        self.args = args

    def run(self):
        try:
            if self.action in (prepare_upload, commit_and_push):
                result = self.action(*self.args, progress=self.progress.emit)
            else:
                result = self.action(*self.args)
            self.success.emit(result)
        except Exception as exc:
            self.failure.emit(str(exc))


class DropArea(QFrame):
    folder_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName('drop')
        self.setProperty('hovered', False)
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 20, 24, 20)
        box.setSpacing(7)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main = QLabel('Drop your project folder here')
        main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.setStyleSheet('font-size: 16px; font-weight: 600; background: transparent;')
        hint = QLabel('or choose a folder using the button below')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName('muted')
        hint.setStyleSheet('color: #a9b7c9; background: transparent;')
        box.addWidget(main)
        box.addWidget(hint)

    def _valid_folder(self, event) -> str | None:
        mime = event.mimeData()
        if not mime.hasUrls() or len(mime.urls()) != 1:
            return None
        u = mime.urls()[0]
        if not u.isLocalFile():
            return None
        path = Path(u.toLocalFile())
        return str(path) if path.is_dir() else None

    def _hover(self, active: bool):
        self.setProperty('hovered', active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if self._valid_folder(event):
            event.acceptProposedAction()
            self._hover(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._hover(False)
        event.accept()

    def dropEvent(self, event):
        self._hover(False)
        folder = self._valid_folder(event)
        if folder:
            self.folder_selected.emit(folder)
            event.acceptProposedAction()
        else:
            event.ignore()


class ConfirmDialog(QDialog):
    def __init__(self, prepared: PreparedUpload, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Review upload')
        self.resize(680, 515)
        box = QVBoxLayout(self)
        box.setSpacing(12)
        heading = QLabel('This upload will replace the current GitHub files' if not prepared.first_upload
                         else 'This will create the first commit on GitHub')
        heading.setStyleSheet('font-size: 17px; font-weight: 700;')
        box.addWidget(heading)
        box.addWidget(QLabel(
            f'Repository: {prepared.repository["name"]}  •  branch: {prepared.repository["branch"]}'
        ))
        totals = QLabel(
            f'Added: {prepared.additions}     Modified: {prepared.modifications}     '
            f'Deleted: {prepared.deletions}'
        )
        totals.setStyleSheet('font-size: 15px; font-weight: 700; color: #85beff;')
        box.addWidget(totals)
        note = QLabel('Deleted files will disappear from the latest version; previous commits remain in history.'
                      if not prepared.first_upload
                      else 'This repository is empty. The selected files will create its initial main branch.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        box.addWidget(note)
        info = QPlainTextEdit()
        info.setReadOnly(True)
        lines = ['CHANGES PREVIEW', *prepared.paths_preview]
        if prepared.changed_total > len(prepared.paths_preview):
            lines.append(f'… and {prepared.changed_total - len(prepared.paths_preview)} more changes')
        lines.extend(['', f'SKIPPED: {prepared.skipped_total} items', *prepared.skipped])
        if prepared.skipped_total > len(prepared.skipped):
            lines.append(f'… and {prepared.skipped_total - len(prepared.skipped)} more skipped items')
        info.setPlainText('\n'.join(lines))
        box.addWidget(info, 1)
        caution = QLabel('Check that the source folder contains no secrets or private data. Files in public repositories are visible to everyone.')
        caution.setWordWrap(True)
        caution.setStyleSheet('color: #f6c887;')
        box.addWidget(caution)
        actions = QHBoxLayout()
        actions.addStretch()
        abort = QPushButton('Cancel')
        abort.clicked.connect(self.reject)
        upload = QPushButton('Confirm and upload')
        upload.setObjectName('danger')
        upload.clicked.connect(self.accept)
        actions.addWidget(abort)
        actions.addWidget(upload)
        box.addLayout(actions)


class UploaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Easy-Github-Uploader')
        self.resize(840, 660)
        self.setMinimumSize(680, 580)
        self.username: str | None = None
        self.repository: dict | None = None
        self.source_folder: str | None = None
        self.prepared: PreparedUpload | None = None
        self.worker: Job | None = None
        self._auth_output_buffer = ''
        self.auth_process: QProcess | None = None
        self.current_index = 0
        self.busy = False
        self._browser_opened = False

        base = QWidget()
        self.setCentralWidget(base)
        main = QVBoxLayout(base)
        main.setContentsMargins(34, 28, 34, 28)
        main.setSpacing(17)
        heading = QLabel('Easy-Github-Uploader')
        heading.setObjectName('title')
        main.addWidget(heading)
        sub = QLabel('Upload your project folder to GitHub — no terminal commands needed.')
        sub.setObjectName('subtitle')
        main.addWidget(sub)
        self.steps_label = QLabel()
        self.steps_label.setObjectName('step')
        main.addWidget(self.steps_label)
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)
        self._build_login()
        self._build_repository()
        self._build_folder()
        self._build_upload()
        nav = QHBoxLayout()
        nav.addStretch()
        self.back_button = QPushButton('Back')
        self.back_button.clicked.connect(self.go_back)
        self.next_button = QPushButton('Next')
        self.next_button.setObjectName('primary')
        self.next_button.clicked.connect(self.go_next)
        nav.addWidget(self.back_button)
        nav.addWidget(self.next_button)
        main.addLayout(nav)

        # Always-visible version and author credits, on every step.
        footer_rule = QFrame()
        footer_rule.setFrameShape(QFrame.Shape.HLine)
        footer_rule.setStyleSheet('color: #34455e; background: #34455e; max-height: 1px;')
        main.addWidget(footer_rule)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        version_label = QLabel(f'v{APP_VERSION}')
        version_label.setObjectName('footer')
        footer.addWidget(version_label)
        footer.addStretch()
        author_label = QLabel(
            f'Made by <a href="{AUTHOR_GITHUB_URL}" '
            'style="color: #88bdff; text-decoration: underline;">LionheartTim</a>'
        )
        author_label.setObjectName('footer')
        author_label.setOpenExternalLinks(True)
        author_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        author_label.setToolTip(AUTHOR_GITHUB_URL)
        footer.addWidget(author_label)
        main.addLayout(footer)

        self._set_page(0)
        self._job(check_login, self._login_checked)

    def _panel(self):
        panel = QFrame()
        panel.setObjectName('panel')
        box = QVBoxLayout(panel)
        box.setContentsMargins(26, 26, 26, 26)
        box.setSpacing(17)
        return panel, box

    def _build_login(self):
        page, box = self._panel()
        box.addWidget(self._headline('1. Sign in to GitHub'))
        hint = QLabel('Sign in securely using your browser. Your existing Google-based GitHub login works too.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        box.addWidget(hint)
        self.login_status = QLabel('Checking sign-in…')
        self.login_status.setWordWrap(True)
        box.addWidget(self.login_status)
        self.signin_button = QPushButton('Sign in with GitHub in browser')
        self.signin_button.setObjectName('primary')
        self.signin_button.clicked.connect(self.start_browser_login)
        box.addWidget(self.signin_button)
        self.device_code = QLabel('')
        self.device_code.setStyleSheet('font-size: 21px; font-weight: 750; color: #8dc3ff;')
        box.addWidget(self.device_code)
        self.copy_code = QPushButton('Copy verification code')
        self.copy_code.clicked.connect(lambda: QApplication.clipboard().setText(self.device_code.text()))
        self.copy_code.setVisible(False)
        box.addWidget(self.copy_code)
        self.open_device_page = QPushButton('Open GitHub verification page')
        self.open_device_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/login/device')))
        self.open_device_page.setVisible(False)
        box.addWidget(self.open_device_page)
        box.addStretch()
        self.pages.addWidget(page)

    def _build_repository(self):
        page, box = self._panel()
        box.addWidget(self._headline('2. Read your GitHub repository'))
        box.addWidget(self._muted('Paste the link to your GitHub repository. The app reads the repository details for you.'))
        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText('https://github.com/username/repository')
        self.repo_edit.returnPressed.connect(self.load_repository)
        self.repo_edit.textChanged.connect(self._repo_changed)
        box.addWidget(self.repo_edit)
        self.read_button = QPushButton('Read repository')
        self.read_button.setObjectName('primary')
        self.read_button.clicked.connect(self.load_repository)
        box.addWidget(self.read_button)
        self.repo_status = QLabel('No repository loaded yet.')
        self.repo_status.setWordWrap(True)
        box.addWidget(self.repo_status)
        box.addStretch()
        self.pages.addWidget(page)

    def _build_folder(self):
        page, box = self._panel()
        box.addWidget(self._headline('3. Choose your project folder'))
        box.addWidget(self._muted('Drag and drop the complete folder, or browse for it on your computer.'))
        self.drop = DropArea()
        self.drop.folder_selected.connect(self.select_folder)
        box.addWidget(self.drop)
        browse = QPushButton('Choose folder…')
        browse.clicked.connect(self.browse_folder)
        box.addWidget(browse)
        self.folder_status = QLabel('No folder selected yet.')
        self.folder_status.setWordWrap(True)
        box.addWidget(self.folder_status)
        box.addStretch()
        self.pages.addWidget(page)

    def _build_upload(self):
        page, box = self._panel()
        box.addWidget(self._headline('4. Upload to GitHub'))
        box.addWidget(self._muted('Existing files on the current branch will be replaced with those in your selected folder.'))
        self.review_repo = QLabel('')
        self.review_repo.setWordWrap(True)
        box.addWidget(self.review_repo)
        self.review_folder = QLabel('')
        self.review_folder.setWordWrap(True)
        box.addWidget(self.review_folder)
        self.upload_button = QPushButton('Upload to GitHub')
        self.upload_button.setObjectName('primary')
        self.upload_button.clicked.connect(self.prepare_for_upload)
        box.addWidget(self.upload_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        box.addWidget(self.progress_bar)
        self.upload_status = QLabel('Check the details and click Upload.')
        self.upload_status.setWordWrap(True)
        box.addWidget(self.upload_status)
        self.open_repo_button = QPushButton('Open repository on GitHub')
        self.open_repo_button.clicked.connect(self.open_repository)
        self.open_repo_button.hide()
        box.addWidget(self.open_repo_button)
        box.addStretch()
        self.pages.addWidget(page)

    @staticmethod
    def _headline(text):
        label = QLabel(text)
        label.setObjectName('headline')
        return label

    @staticmethod
    def _muted(text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName('muted')
        return label

    def _set_page(self, index: int):
        self.current_index = index
        self.pages.setCurrentIndex(index)
        self.steps_label.setText(['STEP 1 OF 4   •   SIGN IN',
                                  'STEP 2 OF 4   •   REPOSITORY',
                                  'STEP 3 OF 4   •   CHOOSE FOLDER',
                                  'STEP 4 OF 4   •   UPLOAD'][index])
        self.back_button.setVisible(index > 0)
        self.next_button.setVisible(index != 3)
        self.next_button.setEnabled(not self.busy and self._can_advance())
        self.back_button.setEnabled(not self.busy)
        if index == 3:
            self.review_repo.setText(f'GitHub:  {self.repository["name"]} ({self.repository["branch"]})')
            self.review_folder.setText(f'Project folder:  {self.source_folder}')

    def _can_advance(self):
        if self.current_index == 0:
            return self.username is not None
        if self.current_index == 1:
            return self.repository is not None
        if self.current_index == 2:
            return self.source_folder is not None
        return False

    def go_next(self):
        if not self.busy and self._can_advance() and self.current_index < 3:
            self._set_page(self.current_index + 1)

    def go_back(self):
        if not self.busy and self.current_index > 0:
            self._set_page(self.current_index - 1)

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.back_button.setEnabled(not busy)
        self.next_button.setEnabled(not busy and self._can_advance())
        self.read_button.setEnabled(not busy)
        self.repo_edit.setEnabled(not busy)
        self.drop.setEnabled(not busy)
        self.signin_button.setEnabled(not busy)
        self.upload_button.setEnabled(not busy)
        self.progress_bar.setVisible(busy and self.current_index == 3)

    def _job(self, action, success, *args):
        if self.busy:
            return
        self._set_busy(True)
        worker = Job(action, *args)
        self.worker = worker
        outcome = {'value': None, 'error': None, 'received': False}

        def got_success(value):
            outcome['value'] = value
            outcome['received'] = True

        def got_error(message):
            outcome['error'] = message
            outcome['received'] = True

        def done():
            if self.worker is worker:
                self.worker = None
            self._set_busy(False)
            if outcome['error'] is not None:
                self._show_error(outcome['error'])
            elif outcome['received']:
                success(outcome['value'])
            worker.deleteLater()

        worker.success.connect(got_success)
        worker.failure.connect(got_error)
        worker.progress.connect(self._show_progress)
        worker.finished.connect(done)
        worker.start()

    def _show_error(self, message):
        if self.current_index == 0:
            self.login_status.setText(message)
        elif self.current_index == 1:
            self.repo_status.setText(message)
        elif self.current_index == 3:
            self.upload_status.setText(message)
        QMessageBox.warning(self, 'Operation failed', message)

    def _show_progress(self, message):
        self.upload_status.setText(message)

    def _login_checked(self, username):
        self.username = username
        if username:
            self.login_status.setText(f'✓ Signed in as {username}')
            self.signin_button.setText('Sign in again')
        else:
            self.login_status.setText('Not signed in yet. Use the button above to sign in through GitHub.')
        self._set_page(self.current_index)

    def start_browser_login(self):
        if self.busy:
            return
        if not shutil.which('gh'):
            QMessageBox.information(self, 'GitHub CLI required',
                                    'Install GitHub CLI on Bazzite first:\n\nbrew install gh\n\nThen restart the app.')
            return
        self.username = None
        self._set_page(0)
        self._set_busy(True)
        self._browser_opened = False
        self._auth_output_buffer = ''
        self.device_code.setText('')
        self.copy_code.hide()
        self.open_device_page.hide()
        self.login_status.setText('Starting GitHub sign-in…')
        self.auth_process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('GH_NO_UPDATE_NOTIFIER', '1')
        env.insert('NO_COLOR', '1')
        self.auth_process.setProcessEnvironment(env)
        self.auth_process.setProgram('gh')
        self.auth_process.setArguments(['auth', 'login', '--hostname', 'github.com',
                                        '--git-protocol', 'https', '--web', '--skip-ssh-key'])
        self.auth_process.readyReadStandardError.connect(self._read_auth_output)
        self.auth_process.readyReadStandardOutput.connect(self._read_auth_output)
        self.auth_process.finished.connect(self._auth_finished)
        self.auth_process.errorOccurred.connect(self._auth_error)
        self.auth_process.start()

    def _auth_error(self, error):
        self.login_status.setText(f'Could not start sign-in: {error}')
        self._set_busy(False)

    def _read_auth_output(self):
        if not self.auth_process:
            return
        raw = bytes(self.auth_process.readAllStandardOutput()) + bytes(self.auth_process.readAllStandardError())
        text = raw.decode('utf-8', errors='replace')
        self._auth_output_buffer = (self._auth_output_buffer + text)[-1200:]
        self.login_status.setText('Complete sign-in in your browser. Keep this window open.')
        match = re.search(r'\b[A-Z0-9]{4}-[A-Z0-9]{4}\b', self._auth_output_buffer)
        if match:
            self.device_code.setText(match.group(0))
            self.copy_code.show()
            self.open_device_page.show()
            if not self._browser_opened:
                self._browser_opened = True
                QDesktopServices.openUrl(QUrl('https://github.com/login/device'))
        if 'press enter' in text.lower():
            self.auth_process.write(b'\n')

    def _auth_finished(self, exit_code, exit_status):
        self._set_busy(False)
        if exit_code == 0:
            self.login_status.setText('Sign-in completed. Checking your account…')
            self._job(check_login, self._login_checked)
        else:
            self.login_status.setText('Sign-in cancelled or failed. Please retry.')

    def _repo_changed(self):
        self.repository = None
        self.repo_status.setText('Click Read repository to check this link.')
        self._set_page(self.current_index)

    def load_repository(self):
        try:
            parse_github_url(self.repo_edit.text())
        except UploadError as exc:
            self.repo_status.setText(str(exc))
            return
        self.repo_status.setText('Reading repository…')
        self._job(read_repository, self._repository_loaded, self.repo_edit.text().strip())

    def _repository_loaded(self, repository):
        self.repository = repository
        visibility = 'Private' if repository['private'] else 'Public'
        self.repo_status.setText(
            f'✓ {repository["name"]}\n'
            f'Branch: {repository["branch"]}  •  {visibility}  •  Write access confirmed'
        )
        self._set_page(self.current_index)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose project folder', str(Path.home() / 'Desktop'))
        if folder:
            self.select_folder(folder)

    def select_folder(self, folder):
        path = Path(folder).expanduser().resolve()
        if not path.is_dir() or path in (Path.home(), Path('/')):
            QMessageBox.warning(self, 'Invalid folder', 'Choose an existing, specific project folder.')
            return
        self.source_folder = str(path)
        self.folder_status.setText(f'✓ Selected: {path}')
        self._set_page(self.current_index)

    def prepare_for_upload(self):
        if not self.repository or not self.source_folder or not self.username:
            return
        self._cleanup_prepared()
        self.open_repo_button.hide()
        self.upload_status.setText('Preparing upload…')
        self._job(prepare_upload, self._upload_prepared, self.source_folder, self.repository)

    def _upload_prepared(self, prepared):
        self.prepared = prepared
        if prepared.copied_total == 0:
            self.upload_status.setText('No eligible source files found. Upload cancelled.')
            self._cleanup_prepared()
            return
        if prepared.changed_total == 0:
            self.upload_status.setText('✓ GitHub already contains the same project files. No upload needed.')
            self._cleanup_prepared()
            return
        dialog = ConfirmDialog(prepared, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.upload_status.setText('Starting upload…')
            self._job(commit_and_push, self._upload_finished, prepared, self.username)
        else:
            self.upload_status.setText('Upload cancelled. Nothing changed on GitHub.')
            self._cleanup_prepared()

    def _upload_finished(self, url):
        self.upload_status.setText('✓ Success! Your project files are now on GitHub.')
        self.open_repo_button.show()
        self._cleanup_prepared()

    def open_repository(self):
        if self.repository:
            QDesktopServices.openUrl(QUrl(self.repository['url']))

    def _cleanup_prepared(self):
        if self.prepared:
            self.prepared.cleanup()
            self.prepared = None

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, 'Operation in progress',
                                    'An operation is still running. Close the app after it finishes.')
            event.ignore()
            return
        self._cleanup_prepared()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setFont(QFont('Noto Sans', 10))
    window = UploaderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
