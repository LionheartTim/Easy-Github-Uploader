# Easy-Github-Uploader v1.0.1

A simple Qt6 Linux desktop application with just four steps:

1. **Sign in** — use your existing GitHub account, including accounts signed in through Google.
2. **Read repository** — paste the GitHub repository URL; the app checks write access and identifies the default branch.
3. **Select folder** — drag and drop your project folder or browse for it.
4. **Upload** — review the changes, confirm, and upload.

## New in v1.0.1 — EGU application icon

The chosen EGU blue GitHub upload icon is included in multiple PNG resolutions under `assets/icons/hicolor/`. The Qt6 app now shows the image as its window/taskbar icon. `install-launcher.sh` installs the PNGs to your user's XDG icon theme and updates the existing KDE application-menu shortcut, with no root privileges required. The AppStream metadata includes the matching stock icon name. **No changes were made to the upload workflow.**

**Important:** Extract the entire new ZIP (including `assets/`) to a separate folder; don't copy only `app.py`. Run `./install-launcher.sh` again from v1.0.1 to update the menu shortcut and icon.

## Version 1.0.0

The application now displays an always-visible footer across all four steps: **v1.0.0** at the bottom left and **Made by [LionheartTim](https://github.com/LionheartTim)** at the bottom right. Clicking the author name opens the GitHub profile in your default browser. No changes were made to the upload workflow.

## Added in v0.1.2

- **`LICENSE`** — complete GNU General Public License version 3 text. The project is offered under **GPL-3.0-only**.
- **`io.github.LionheartTim.EasyGithubUploader.metainfo.xml`** — AppStream metadata describing the app, including its ID, license, GitHub links, features, and release details. The `launchable` entry matches the KDE shortcut created by `install-launcher.sh` (`easy-github-uploader.desktop`).

**No changes to the tested upload workflow:** the four-step English interface and the empty-repository fix from v0.1.1 are retained. Uploading this new folder to the existing GitHub repository should preview the added license and XML metadata and replace the old version. Merely adding AppStream XML to a GitHub repository does not publish the app to Flathub; distribution packaging can be added later.

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
2. Open a terminal in the extracted `Easy-Github-Uploader-v1.0.1` directory.
3. Run:

```bash
./start.sh
```

The launcher creates an isolated Python virtual environment and installs PySide6 on the first run only. `requirements.txt` pins the supported dependency.

To add a KDE application-menu shortcut, run:

```bash
./install-launcher.sh
```

**If you use the application-menu shortcut, run `./install-launcher.sh` from the new v1.0.1 folder to point it at this version.** Otherwise the shortcut may still open the previous version.

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

The user confirmed the complete v1.0.0 workflow and clickable author footer on Bazzite. Version 1.0.1 changes only icon/launcher/metadata integration; the graphical icon appearance and the updated launcher still need Bazzite testing.

## Technical overview

Python, PySide6 (Qt6), Git, and GitHub CLI; no embedded OAuth webview and no forced push. This app does not create GitHub repositories — it *can* create the first commit in an already created empty repository.

## License

Copyright (C) 2026 LionheartTim. This project is licensed under **GNU GPL version 3 only** (`GPL-3.0-only`). See [`LICENSE`](LICENSE). The AppStream XML metadata is licensed under `CC0-1.0`, as declared in its `metadata_license` element.
