"""Git-based replacement of a GitHub repository's default-branch working tree.

No repository is changed until commit_and_push is called. All work happens
in a temporary clone, so the selected source folder is never modified.
"""
# Copyright (C) 2026 LionheartTim
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable
from urllib.parse import urlparse

# GitHub's normal Git transport warns above 50 MiB and rejects above 100 MiB.
# Skip files >=50 MiB to keep uploads predictable and free from size warnings.
MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024
MAX_DISPLAYED_SKIPS = 18

EXCLUDED_DIRECTORIES = {
    '.git', '.venv', 'venv', '__pycache__', '.flatpak-builder',
    'build', 'build_dir', 'dist', 'node_modules', 'CMakeFiles', '.pytest_cache',
    '.mypy_cache', '.tox', 'extra info',
}
EXCLUDED_FILES = (
    '*.pyc', '*.gguf', '*.flatpak', '*.pcap', '*.pcapng',
    '*.key', '*.pem', '*.p12', '*.pfx', '*.asar', '*.exe',
    'CMakeCache.txt', 'cmake_install.cmake',
    '.env', '.env.*', 'id_rsa', 'id_ed25519', '*.swp',
    '.DS_Store', 'Thumbs.db',
)
IGNORES_BLOCK = '''\n# Easy-Github-Uploader - local/generated/sensitive files\n.git/\n.venv/\nvenv/\n__pycache__/\n.flatpak-builder/\nbuild/\nbuild_dir/\ndist/\nnode_modules/\n.pytest_cache/\n.mypy_cache/\n.tox/\nlocal-repo*/\nextra info/\n*.pyc\n*.gguf\n*.flatpak\n*.pcap\n*.pcapng\n*.key\n*.pem\n*.p12\n*.pfx\n*.asar\n*.exe\n.env\n.env.*\nid_rsa\nid_ed25519\n*.swp\n.DS_Store\nThumbs.db\n'''

class UploadError(Exception):
    pass


def run_command(args: list[str], *, cwd: str | Path | None = None,
                timeout: int = 180, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GH_NO_UPDATE_NOTIFIER'] = '1'
    env['NO_COLOR'] = '1'
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                timeout=timeout, env=env, errors='replace')
    except FileNotFoundError as exc:
        raise UploadError(f'Program not found: {args[0]}.') from exc
    except subprocess.TimeoutExpired as exc:
        raise UploadError(f'Operation timed out: {args[0]}.') from exc
    if check and result.returncode != 0:
        msg = (result.stderr or result.stdout or 'Unknown error').strip()
        raise UploadError(f'{args[0]} failed:\n{msg[-3500:]}')
    return result


def parse_github_url(value: str) -> tuple[str, str]:
    """Only canonical HTTPS github.com URLs; no arbitrary Git URLs."""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.port:
        raise UploadError('Use a GitHub web link, e.g. https://github.com/owner/repository')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise UploadError('Use the direct GitHub repository link without extra parameters.')
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 2:
        raise UploadError('Enter a repository link, not a link to a file or issue.')
    owner, repo = parts
    if repo.endswith('.git'):
        repo = repo[:-4]
    if not re.fullmatch(r'[A-Za-z0-9-]{1,39}', owner):
        raise UploadError('Invalid GitHub owner name.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', repo):
        raise UploadError('Invalid GitHub repository name.')
    return owner, repo


def check_login() -> str | None:
    if not shutil.which('git'):
        raise UploadError('Git is not installed. Install git first.')
    if not shutil.which('gh'):
        raise UploadError('GitHub CLI (gh) is missing. On Bazzite, install it with: brew install gh')
    status = run_command(['gh', 'auth', 'status', '--hostname', 'github.com'],
                         check=False, timeout=30)
    if status.returncode != 0:
        return None
    # GH user lookup verifies a working, not merely cached, session.
    result = run_command(['gh', 'api', 'user', '--jq', '.login'], timeout=40)
    login = result.stdout.strip()
    if not login:
        raise UploadError('Unable to read the signed-in GitHub account.')
    run_command(['gh', 'auth', 'setup-git', '--hostname', 'github.com'], timeout=30)
    return login


def read_repository(repo_url: str) -> dict:
    owner, repo = parse_github_url(repo_url)
    response = run_command(['gh', 'api', f'repos/{owner}/{repo}'], timeout=45)
    try:
        details = json.loads(response.stdout)
    except json.JSONDecodeError as exc:
        raise UploadError('GitHub returned an invalid repository response.') from exc
    if details.get('archived'):
        raise UploadError('This repository is archived and cannot be updated.')
    if not details.get('permissions', {}).get('push'):
        raise UploadError('Your GitHub account has no write permission for this repository.')
    # An empty repository may have no default branch in the API yet.
    # GitHub's usual initial branch name is main; no existing commits are overwritten.
    default_branch = details.get('default_branch') or 'main'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', default_branch):
        raise UploadError('GitHub returned an invalid default branch name.')
    return {
        'name': details['full_name'],
        'url': details['html_url'],
        'branch': default_branch,
        'private': bool(details.get('private', False)),
        'clone_url': f'https://github.com/{owner}/{repo}.git',
    }


def excluded_dir(name: str) -> bool:
    return (name in EXCLUDED_DIRECTORIES or fnmatch(name, 'local-repo*')
            or fnmatch(name, 'cmake-build-*'))


def excluded_file(name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in EXCLUDED_FILES)


@dataclass
class PreparedUpload:
    temp_root: Path
    worktree: Path
    repository: dict
    first_upload: bool = False
    additions: int = 0
    modifications: int = 0
    deletions: int = 0
    skipped: list[str] = field(default_factory=list)
    skipped_total: int = 0
    copied_total: int = 0
    changed_total: int = 0
    paths_preview: list[str] = field(default_factory=list)

    def cleanup(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)


def _record_skip(prepared: PreparedUpload, path: str, reason: str):
    prepared.skipped_total += 1
    if len(prepared.skipped) < MAX_DISPLAYED_SKIPS:
        prepared.skipped.append(f'{path} — {reason}')


def _copy_source(source: Path, prepared: PreparedUpload,
                 progress: Callable[[str], None]):
    destination = prepared.worktree
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root_path = Path(root)
        relative_dir = root_path.relative_to(source)
        kept_dirs = []
        for name in dirs:
            rel = (relative_dir / name).as_posix()
            if excluded_dir(name):
                _record_skip(prepared, rel + '/', 'generated/excluded folder')
            elif (root_path / name).is_symlink():
                _record_skip(prepared, rel, 'symbolic link')
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        (destination / relative_dir).mkdir(parents=True, exist_ok=True)
        for name in files:
            item = root_path / name
            rel_path = relative_dir / name
            rel = rel_path.as_posix()
            if excluded_file(name):
                _record_skip(prepared, rel, 'excluded file type')
                continue
            if item.is_symlink():
                _record_skip(prepared, rel, 'symbolic link')
                continue
            try:
                size = item.stat().st_size
            except OSError as exc:
                raise UploadError(f'Cannot inspect {rel}: {exc}') from exc
            if size >= MAX_UPLOAD_FILE_BYTES:
                _record_skip(prepared, rel, '50 MiB or larger')
                continue
            target = destination / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, target)
            except OSError as exc:
                raise UploadError(f'Cannot copy {rel}: {exc}') from exc
            prepared.copied_total += 1
            if prepared.copied_total % 150 == 0:
                progress(f'Copied {prepared.copied_total} source files…')


def prepare_upload(source_folder: str, repository: dict,
                   progress: Callable[[str], None] = lambda msg: None) -> PreparedUpload:
    source = Path(source_folder).expanduser().resolve()
    if not source.is_dir():
        raise UploadError('The selected source folder no longer exists.')
    if source == Path.home() or source == Path('/'):
        raise UploadError('Select a specific project folder, not your home or root directory.')
    temp_root = Path(tempfile.mkdtemp(prefix='easy-github-uploader-'))
    prepared = PreparedUpload(temp_root=temp_root, worktree=temp_root / 'repository',
                              repository=repository)
    try:
        progress('Checking the repository on GitHub…')
        # A brand-new GitHub repository has no commits and therefore no remote
        # main branch. Distinguish that from an existing repository whose branch
        # is missing, which must not be silently replaced.
        refs = run_command(['git', 'ls-remote', '--heads', '--',
                            repository['clone_url']], timeout=120)
        heads = {line.split('refs/heads/', 1)[1].strip()
                 for line in refs.stdout.splitlines() if 'refs/heads/' in line}
        branch = repository['branch']
        worktree = prepared.worktree
        if branch in heads:
            progress('Downloading the current GitHub repository…')
            run_command(['git', 'clone', '--quiet', '--depth=1',
                         '--branch', branch, '--', repository['clone_url'],
                         str(worktree)], timeout=300)
            progress('Preparing to replace old GitHub files…')
            # Keep .git/history but replace old tracked files.
            run_command(['git', 'rm', '-r', '-q', '--ignore-unmatch', '--', '.'], cwd=worktree)
            for item in worktree.iterdir():
                if item.name == '.git':
                    continue
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        elif not heads:
            progress('Empty repository found — preparing its first commit…')
            worktree.mkdir(parents=True)
            run_command(['git', 'init', '-q', f'--initial-branch={branch}'], cwd=worktree)
            run_command(['git', 'remote', 'add', 'origin', repository['clone_url']], cwd=worktree)
            prepared.first_upload = True
        else:
            raise UploadError(
                f'GitHub has branches, but not {branch!r}. Refresh the repository and retry.'
            )
        progress('Copying source files and excluding generated files…')
        _copy_source(source, prepared, progress)
        ignore = worktree / '.gitignore'
        current = ignore.read_text(encoding='utf-8', errors='replace') if ignore.exists() else ''
        if '# Easy-Github-Uploader - local/generated/sensitive files' not in current:
            with ignore.open('a', encoding='utf-8') as stream:
                stream.write(IGNORES_BLOCK)
        progress('Comparing the new project with GitHub…')
        run_command(['git', 'add', '-A'], cwd=worktree, timeout=150)
        diff = run_command(['git', '-c', 'core.quotepath=false', 'diff', '--cached',
                            '--name-status', '--no-renames', '-z'], cwd=worktree)
        tokens = diff.stdout.split('\0')
        for index in range(0, len(tokens) - 1, 2):
            status, path = tokens[index], tokens[index + 1]
            if not status or not path:
                continue
            prepared.changed_total += 1
            if status.startswith('A'):
                prepared.additions += 1
            elif status.startswith('D'):
                prepared.deletions += 1
            else:
                prepared.modifications += 1
            if len(prepared.paths_preview) < 25:
                prepared.paths_preview.append(f'{status}  {path}')
        # Files >=50 MiB have already been excluded before staging.
        progress('Preview ready — no changes have been uploaded.')
        return prepared
    except Exception:
        prepared.cleanup()
        raise


def commit_and_push(prepared: PreparedUpload, username: str,
                    progress: Callable[[str], None] = lambda msg: None) -> str:
    if prepared.changed_total == 0:
        raise UploadError('There are no changes to upload.')
    repo = prepared.worktree
    if not repo.is_dir():
        raise UploadError('Temporary upload files are missing. Prepare the upload again.')
    # Use local identity only, never change the user's global Git settings.
    run_command(['git', 'config', '--local', 'user.name', username], cwd=repo)
    run_command(['git', 'config', '--local', 'user.email',
                 f'{username}@users.noreply.github.com'], cwd=repo)
    progress('Creating a commit of the new project…')
    run_command(['git', 'commit', '--quiet', '-m',
                 'Upload project using Easy-Github-Uploader'],
                cwd=repo, timeout=100)
    progress('Uploading the first commit to GitHub…' if prepared.first_upload
             else 'Uploading to GitHub…')
    run_command(['git', 'push', 'origin', f'HEAD:{prepared.repository["branch"]}'],
                cwd=repo, timeout=360)
    progress('Upload complete.')
    return prepared.repository['url']
