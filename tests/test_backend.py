import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from backend import (
    UploadError, parse_github_url, prepare_upload, commit_and_push,
)


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


class TestBackend(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(parse_github_url('https://github.com/LionheartTim/deepcool-qt6'), ('LionheartTim', 'deepcool-qt6'))
        self.assertEqual(parse_github_url('https://github.com/LionheartTim/Universal-Linux-Terminal.git/'), ('LionheartTim', 'Universal-Linux-Terminal'))
        for url in ('https://github.com/owner/repo/issues/1', 'https://evil.example/a/b',
                    'https://github.com/owner', 'https://a@github.com/owner/repo'):
            with self.subTest(url=url), self.assertRaises(UploadError):
                parse_github_url(url)

    def test_prepare_replace_and_push_with_local_remote(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            remote = root / 'remote.git'
            git('init', '--bare', '--initial-branch=main', str(remote))
            seed = root / 'seed'
            git('clone', str(remote), str(seed))
            git('config', 'user.name', 'tester', cwd=seed)
            git('config', 'user.email', 'tester@example.com', cwd=seed)
            (seed / 'old.txt').write_text('old')
            (seed / 'keep.txt').write_text('old version')
            git('add', '-A', cwd=seed)
            git('commit', '-m', 'Existing history', cwd=seed)
            git('push', 'origin', 'main', cwd=seed)
            source = root / 'project'
            source.mkdir()
            (source / 'keep.txt').write_text('new version')
            (source / 'new.py').write_text('print("Hi")')
            (source / '.env').write_text('SECRET=private')
            (source / 'extra info').mkdir()
            (source / 'extra info' / 'capture.pcap').write_bytes(b'capture')
            (source / 'build_dir').mkdir()
            (source / 'build_dir' / 'CMakeCache.txt').write_text('junk')
            with (source / 'huge.bin').open('wb') as stream:
                stream.truncate(50 * 1024 * 1024)
            (source / '.git').mkdir()
            (source / '.git' / 'fake').write_text('no')
            repo = {'name': 'test/repo', 'url': 'https://github.com/test/repo',
                    'branch': 'main', 'clone_url': str(remote)}
            prepared = prepare_upload(str(source), repo)
            self.assertEqual(prepared.additions, 2)  # new.py + .gitignore
            self.assertEqual(prepared.modifications, 1)
            self.assertEqual(prepared.deletions, 1)
            self.assertGreaterEqual(prepared.skipped_total, 4)
            self.assertFalse((prepared.worktree / 'huge.bin').exists())
            self.assertFalse((prepared.worktree / '.env').exists())
            self.assertFalse((prepared.worktree / 'extra info').exists())
            self.assertEqual(prepared.changed_total, 4)
            url = commit_and_push(prepared, 'tester')
            self.assertEqual(url, 'https://github.com/test/repo')
            new_clone = root / 'verify'
            git('clone', str(remote), str(new_clone))
            self.assertEqual((new_clone / 'keep.txt').read_text(), 'new version')
            self.assertTrue((new_clone / 'new.py').exists())
            self.assertFalse((new_clone / 'old.txt').exists())
            self.assertFalse((new_clone / '.env').exists())
            self.assertFalse((new_clone / 'huge.bin').exists())
            self.assertEqual(len(git('rev-list', 'main', cwd=new_clone).splitlines()), 2)
            # The selected source is completely unchanged.
            self.assertEqual((source / '.env').read_text(), 'SECRET=private')
            prepared.cleanup()
            self.assertFalse(prepared.temp_root.exists())

    def test_first_upload_to_empty_repository(self):
        """The GitHub Quick setup page corresponds to no refs/heads/main."""
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            remote = root / 'empty.git'
            git('init', '--bare', '--initial-branch=main', str(remote))
            source = root / 'new-project'
            source.mkdir()
            (source / 'app.py').write_text('print("Hello GitHub")')
            (source / 'README.md').write_text('# Easy-Github-Uploader')
            repo = {'name': 'tester/repo', 'url': 'https://github.com/tester/repo',
                    'branch': 'main', 'clone_url': str(remote)}
            prepared = prepare_upload(str(source), repo)
            try:
                self.assertTrue(prepared.first_upload)
                self.assertEqual(prepared.additions, 3)  # 2 files + .gitignore
                self.assertEqual(prepared.modifications, 0)
                self.assertEqual(prepared.deletions, 0)
                self.assertEqual(commit_and_push(prepared, 'tester'), repo['url'])
                verify = root / 'verify'
                git('clone', str(remote), str(verify))
                self.assertEqual((verify / 'app.py').read_text(), 'print("Hello GitHub")')
                self.assertEqual(git('rev-list', '--count', 'HEAD', cwd=verify), '1')
                self.assertTrue((source / 'README.md').exists())
            finally:
                prepared.cleanup()

    def test_first_upload_race_is_rejected(self):
        """A second user creating main while we preview must not be overwritten."""
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            remote = root / 'empty.git'
            git('init', '--bare', '--initial-branch=main', str(remote))
            source = root / 'project'
            source.mkdir()
            (source / 'app.py').write_text('ours')
            repo = {'name': 'tester/repo', 'url': 'https://github.com/tester/repo',
                    'branch': 'main', 'clone_url': str(remote)}
            prepared = prepare_upload(str(source), repo)
            try:
                seed = root / 'other'
                git('clone', str(remote), str(seed))
                git('config', 'user.name', 'other', cwd=seed)
                git('config', 'user.email', 'other@example.com', cwd=seed)
                (seed / 'someone-else.txt').write_text('existing')
                git('add', '-A', cwd=seed)
                git('commit', '-m', 'Other first commit', cwd=seed)
                git('push', 'origin', 'main', cwd=seed)
                with self.assertRaises(UploadError):
                    commit_and_push(prepared, 'tester')
                self.assertEqual(git('rev-list', '--count', 'main', cwd=seed), '1')
            finally:
                prepared.cleanup()

    def test_missing_target_branch_is_not_considered_empty(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            remote = root / 'remote.git'
            git('init', '--bare', '--initial-branch=master', str(remote))
            seed = root / 'seed'
            git('clone', str(remote), str(seed))
            git('config', 'user.name', 'other', cwd=seed)
            git('config', 'user.email', 'other@example.com', cwd=seed)
            (seed / 'file').write_text('original')
            git('add', '-A', cwd=seed)
            git('commit', '-m', 'First commit', cwd=seed)
            git('push', 'origin', 'master', cwd=seed)
            source = root / 'project'
            source.mkdir()
            (source / 'app.py').write_text('our file')
            with self.assertRaisesRegex(UploadError, 'has branches'):
                prepare_upload(str(source), {
                    'name': 'tester/repo', 'url': 'https://github.com/tester/repo',
                    'branch': 'main', 'clone_url': str(remote)
                })

    def test_outdated_push_is_rejected_not_forced(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            remote = root / 'remote.git'
            git('init', '--bare', '--initial-branch=main', str(remote))
            seed = root / 'seed'
            git('clone', str(remote), str(seed))
            git('config', 'user.name', 'tester', cwd=seed)
            git('config', 'user.email', 'tester@example.com', cwd=seed)
            (seed / 'README.md').write_text('Original')
            git('add', '-A', cwd=seed)
            git('commit', '-m', 'Start', cwd=seed)
            git('push', 'origin', 'main', cwd=seed)
            source = root / 'project'
            source.mkdir()
            (source / 'README.md').write_text('Our local project')
            repo = {'name': 'test/repo', 'url': 'https://github.com/test/repo',
                    'branch': 'main', 'clone_url': str(remote)}
            prepared = prepare_upload(str(source), repo)
            (seed / 'other.txt').write_text('A remote update')
            git('add', '-A', cwd=seed)
            git('commit', '-m', 'Someone else pushed', cwd=seed)
            git('push', 'origin', 'main', cwd=seed)
            with self.assertRaises(UploadError):
                commit_and_push(prepared, 'tester')
            verify = root / 'verify'
            git('clone', str(remote), str(verify))
            self.assertEqual((verify / 'README.md').read_text(), 'Original')
            self.assertTrue((verify / 'other.txt').exists())
            prepared.cleanup()

    def test_invalid_source_rejected(self):
        with self.assertRaises(UploadError):
            prepare_upload('/', {'clone_url': 'not-used', 'branch': 'main'})


if __name__ == '__main__':
    unittest.main()
