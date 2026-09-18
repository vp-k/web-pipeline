"""Lifetime containment for checks (not an adversarial execution sandbox).

On Windows the trusted helper waits for input until assigned to a kill-on-close
Job Object, so the command cannot spawn descendants before containment exists.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


class WindowsJob:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w

        class Limits(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64),
                        ('flags', w.DWORD), ('min_ws', c.c_size_t), ('max_ws', c.c_size_t),
                        ('active_limit', w.DWORD), ('affinity', c.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Extended(c.Structure):
            _fields_ = [('basic', Limits), ('io', c.c_uint64 * 6),
                        ('memory', c.c_size_t * 4)]

        class Accounting(c.Structure):
            _fields_ = [('times', c.c_int64 * 4), ('faults', w.DWORD),
                        ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]

        self.c, self.Accounting = c, Accounting
        self.api = c.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            ('QueryInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
            ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
            ('TerminateJobObject', [w.HANDLE, w.UINT], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway
        try:
            self._check(self.api.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def _check(self, result):
        if not result:
            raise self.c.WinError(self.c.get_last_error())

    def assign(self, process):
        self._check(self.api.AssignProcessToJobObject(self.handle, int(process._handle)))

    def active(self):
        value = self.Accounting()
        self._check(self.api.QueryInformationJobObject(
            self.handle, 1, self.c.byref(value), self.c.sizeof(value), None))
        return value.active

    def terminate(self):
        self._check(self.api.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + 10
        while self.active():
            if time.monotonic() >= deadline:
                raise RuntimeError('Process job did not terminate within cleanup deadline')
            time.sleep(.01)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            self._check(self.api.CloseHandle(handle))


def group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def wait_log_release(path, timeout=10):
    """Drain Windows handle teardown before evidence is consumed or removed."""
    if os.name != 'nt':
        return
    import ctypes as c
    from ctypes import wintypes as w
    api = c.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                               w.DWORD, w.DWORD, w.HANDLE]
    api.CreateFileW.restype = w.HANDLE
    api.CloseHandle.argtypes = [w.HANDLE]
    api.CloseHandle.restype = w.BOOL
    deadline = time.monotonic() + timeout
    while True:
        # OPEN_EXISTING, GENERIC_READ, no sharing. Windows rejects this while
        # an inherited writer still owns the log, even after job active == 0.
        # https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilew
        handle = api.CreateFileW(str(Path(path).resolve()), 0x80000000, 0, None, 3, 0, None)
        if handle != c.c_void_p(-1).value:
            if not api.CloseHandle(handle):
                raise c.WinError(c.get_last_error())
            return
        error = c.get_last_error()
        if error != 32:  # ERROR_SHARING_VIOLATION; other errors are not retried.
            raise c.WinError(error)
        if time.monotonic() >= deadline:
            raise RuntimeError('Process log handles did not close within cleanup deadline')
        time.sleep(.01)


def resolve(argv, env=None):
    """Resolve a bare command through PATH/PATHEXT so shims such as npm.cmd launch without a shell."""
    found = shutil.which(argv[0], path=(env or os.environ).get('PATH'))
    return [found, *argv[1:]] if found else list(argv)


def execute(argv, cwd, env, log, timeout, status_path):
    """Return (exit code, failure reason); reap/kill descendants before returning."""
    process, job = None, None
    deadline = time.monotonic() + timeout
    try:
        if os.name == 'nt':
            job = WindowsJob()
            process = subprocess.Popen(
                [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()), str(status_path)],
                cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            job.assign(process)
            process.stdin.write((json.dumps(argv) + '\n').encode('utf-8'))
            process.stdin.close()
        else:
            process = subprocess.Popen(resolve(argv, env), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return None, 'timeout'
        if job:
            # The helper waits for the actual command; all other live members
            # are abandoned descendants, even when its parent returned zero.
            if job.active():
                return None, 'command left running descendant processes'
            outcome = json.loads(Path(status_path).read_text(encoding='utf-8-sig'))
            if outcome.get('error'):
                raise OSError(outcome['error'])
            code = outcome['exit_code']
        elif group_alive(process.pid):
            return None, 'command left running descendant processes'
        return code, None if code == 0 else f'exit code {code}'
    finally:
        try:
            if job:
                try:
                    job.terminate()
                finally:
                    job.close()
            elif process:
                # The leader may already have exited. Its group still belongs
                # to this command and must be killed on success and timeout.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if process:
                if process.poll() is None:
                    process.kill()  # also covers a helper whose job assignment failed
                process.wait(timeout=10)
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()


def _helper():
    argv = json.loads(sys.stdin.buffer.readline().decode('utf-8'))
    try:
        child = subprocess.Popen(resolve(argv), stdin=subprocess.DEVNULL)
        outcome = {'exit_code': child.wait()}
    except Exception as exc:
        outcome = {'error': f'{type(exc).__name__}: {exc}'}
    Path(sys.argv[1]).write_text(json.dumps(outcome), encoding='utf-8')


if __name__ == '__main__':
    _helper()
