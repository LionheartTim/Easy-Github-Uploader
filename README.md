# Easy-Github-Uploader v0.1.1

A simple Qt6 Linux desktop application with just four steps:

1. **Sign in** — use your existing GitHub account, including accounts signed in through Google.
2. **Read repository** — paste the GitHub repository URL; the app checks write access and identifies the default branch.
3. **Select folder** — drag and drop your project folder or browse for it.
4. **Upload** — review the changes, confirm, and upload.

## Fixed in v0.1.1

**First uploads to empty GitHub repositories work.** When GitHub displays the **Quick setup** page, the repository has no commits and the `main` branch does not exist yet. Previously the app tried to clone a nonexistent branch. Now it detects the empty repository and creates the first commit and `main` branch itself, without asking you to create a README or use the terminal.

Existing repositories keep their Git history. The app replaces the files in the **latest** version (rather than force-pushing). The app UI, installer messages, and documentation are in **English**.

## Requirements

- Linux with Python 3 and `python3 -m venv` support
- `git`
- GitHub CLI (`gh`), authenticated to GitHub. On Bazzite, you can usually install it with `brew install gh`.
- Internet access for installing PySide6 on first launch and connecting to GitHub

No GitHub password or token is stored by this application. Authentication uses GitHub CLI in your normal browser.

## Run

1. Extract the ZIP (for example, to your Desktop).
2. Open a terminal in the extracted `Easy-Github-Uploader-v0.1.1` directory.
3. Run:

```bash
./start.sh
```

The launcher creates an isolated Python virtual environment and installs PySide6 on the first run only. `requirements.txt` pins the supported dependency.

To add a KDE application-menu shortcut, run:

```bash
./install-launcher.sh
```

**If you installed the v0.1.0 shortcut, run `./install-launcher.sh` from the new v0.1.1 folder to update the shortcut to the new version.** Otherwise the old shortcut may still open the unfixed app.

## What the uploader does

- Validates a GitHub URL and write access using GitHub CLI.
- Works for both empty repositories and repositories with commits.
- Clones an existing branch to a temporary directory and preserves its history; or initializes a new temporary repository for the first upload.
- Copies selected project files to this temporary working directory. **It never edits your original source folder.**
- Removes old GitHub branch files that do not exist in the selected project, and stages new or changed files.
- Shows a detailed change preview with added, modified, deleted, and excluded file counts.
- Uploads **only after explicit confirmation** using a normal, non-force push. If another push happens meanwhile, Git rejects the outdated push.

### Files excluded by default

The app excludes `.git`, local Python environments and caches, build artifacts, `local-repo*`, `extra info`, environment files, common private-key formats, PCAP captures, `.gguf`, `.flatpak`, `.exe`, `.asar`, symbolic links, and individual files **50 MiB or larger**. The preview shows skipped-file counts. Large files are **not** uploaded using Git LFS.

The app cannot reliably identify every secret or private detail inside source files. Review changes before uploading to a public repository. Earlier commits on GitHub are not erased.

## Local tests

Backend behavior is covered with offline temporary Git repositories (no real GitHub pushes):

```bash
python3 -m unittest discover -s tests -v
```

Tests cover first upload to empty Git repositories, replacement on an existing branch, rejected stale pushes, missing target branches, URL parsing, excluded files, and unchanged source folders.

This release's graphical interface has not yet been verified on your Bazzite installation.

## Technical overview

Python, PySide6 (Qt6), Git, and GitHub CLI; no embedded OAuth webview and no forced push. This app does not create GitHub repositories — it *can* create the first commit in an already created empty repository.
