"""Subprocess executor for mrbench.

Handles running external CLI commands with proper timeout handling,
streaming support, and metric collection.
"""

from __future__ import annotations

import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO


@dataclass
class ExecutorResult:
    """Result from executing a subprocess."""

    stdout: str
    stderr: str
    exit_code: int
    wall_time_ms: float
    timed_out: bool = False
    ttft_ms: float | None = None  # Time to first token (for streaming)
    chunks: list[str] = field(default_factory=list)


class SubprocessExecutor:
    """Execute subprocesses with timeout and streaming support."""

    def __init__(
        self,
        timeout: float = 300.0,
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            timeout: Maximum execution time in seconds.
            env: Optional environment variables to add/override.
        """
        self.timeout = timeout
        self.env = env

    def run(
        self,
        args: list[str],
        stdin: str | None = None,
        cwd: str | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ExecutorResult:
        """Run a subprocess and capture output.

        Args:
            args: Command and arguments as list.
            stdin: Optional input to send to stdin.
            cwd: Optional working directory.
            stream_callback: Optional callback for each line of output (for streaming).

        Returns:
            ExecutorResult with stdout, stderr, timing, etc.
        """
        start_time = time.perf_counter()
        stdout_data: list[str] = []
        stderr_data: list[str] = []
        chunks: list[str] = []
        ttft_ms: float | None = None
        timed_out = False
        exit_code = -1

        try:
            # Build environment
            import os

            env = os.environ.copy()
            if self.env:
                env.update(self.env)

            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                text=True,
                # Use process group for proper timeout killing
                start_new_session=True,
            )

            if stream_callback:
                # Streaming mode: read line by line
                ttft_ms, timed_out = self._stream_output(
                    process,
                    stdin,
                    stdout_data,
                    stderr_data,
                    chunks,
                    stream_callback,
                    start_time,
                )
            else:
                # Non-streaming mode: use communicate with timeout
                try:
                    stdout, stderr = process.communicate(
                        input=stdin,
                        timeout=self.timeout,
                    )
                    stdout_data.append(stdout)
                    stderr_data.append(stderr)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    # Kill the process group
                    try:
                        import os

                        os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        process.kill()
                    process.wait()

            exit_code = process.returncode

        except FileNotFoundError:
            stderr_data.append(f"Command not found: {args[0]}")
            exit_code = 127
        except Exception as e:
            stderr_data.append(f"Execution error: {e}")
            exit_code = 1

        wall_time_ms = (time.perf_counter() - start_time) * 1000

        return ExecutorResult(
            stdout="".join(stdout_data),
            stderr="".join(stderr_data),
            exit_code=exit_code,
            wall_time_ms=wall_time_ms,
            timed_out=timed_out,
            ttft_ms=ttft_ms,
            chunks=chunks,
        )

    def _stream_output(
        self,
        process: subprocess.Popen[str],
        stdin: str | None,
        stdout_data: list[str],
        stderr_data: list[str],
        chunks: list[str],
        callback: Callable[[str], None],
        start_time: float,
    ) -> tuple[float | None, bool]:
        """Stream output from process, collecting chunks and timing.

        Returns:
            Tuple of (time to first token in ms, timed_out flag).
        """
        import os
        import selectors

        ttft_ms: float | None = None
        timed_out = False

        # Send stdin if provided
        if stdin and process.stdin:
            process.stdin.write(stdin)
            process.stdin.close()

        # Set up selector for non-blocking reads
        sel = selectors.DefaultSelector()
        if process.stdout:
            sel.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            sel.register(process.stderr, selectors.EVENT_READ)

        deadline = start_time + self.timeout

        try:
            while sel.get_map():
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    # Timeout
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        process.kill()
                    break

                events = sel.select(timeout=min(remaining, 0.1))

                for key, _ in events:
                    fileobj: IO[str] = key.fileobj  # type: ignore
                    line = fileobj.readline()

                    if not line:
                        sel.unregister(fileobj)
                        continue

                    if fileobj is process.stdout:
                        stdout_data.append(line)
                        chunks.append(line)
                        callback(line)

                        # Record TTFT on first non-empty output
                        if ttft_ms is None and line.strip():
                            ttft_ms = (time.perf_counter() - start_time) * 1000
                    else:
                        stderr_data.append(line)

                # Check if process has exited
                if process.poll() is not None:
                    # Drain remaining output
                    for key in list(sel.get_map().values()):
                        fileobj = key.fileobj  # type: ignore
                        remaining_output = fileobj.read()
                        if remaining_output:
                            if fileobj is process.stdout:
                                stdout_data.append(remaining_output)
                            else:
                                stderr_data.append(remaining_output)
                    break

        finally:
            sel.close()

        process.wait()
        return ttft_ms, timed_out

    def run_with_stdin_prompt(
        self,
        args: list[str],
        prompt: str,
        cwd: str | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ExecutorResult:
        """Run command with prompt sent via stdin.

        This is the preferred method for sending prompts to avoid
        exposing sensitive content in command line arguments.

        Args:
            args: Command and arguments.
            prompt: Prompt to send via stdin.
            cwd: Optional working directory.
            stream_callback: Optional streaming callback.

        Returns:
            ExecutorResult.
        """
        return self.run(args, stdin=prompt, cwd=cwd, stream_callback=stream_callback)
