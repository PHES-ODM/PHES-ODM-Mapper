from collections.abc import Callable
import logging
import sys

DEFAULT_ENCODING = sys.getdefaultencoding()


class HookWriter(object):
    """
    Intercepts output (eg. to a logging.StreamHandler, sys.stdout, or sys.stderr) and modifies the text
    to ensure that output looks nice while a ProgressCounter is running. The main purpose is to clear
    the output line before writing output, to clear any artifacts left by a tqdm bar.
    """

    def __init__(self, stream, refresh_callback: Callable[[], None]):
        # at_new_line is True whenever we are at the start of a line for this particular HookWriter.
        # If we are at the start of a line then we clear the line and force return to the start
        # before writing text.
        # If we're not at the start we do not clear the line or return to the start before writing text.
        self.at_new_line = True
        self.refresh_callback = refresh_callback
        self.stream = stream
        if isinstance(stream, logging.StreamHandler):
            # For StreamHandlers (ie. a handler for logging), replace the stream with ourself
            # so we can intercept all output to modify it.
            self.output_stream = stream.stream
            try:
                self.stream.setStream(self)
            except Exception:
                # A StreamHandler might not allow setting the stream, for example logging._StderrHandler,
                # which always uses the current sys.stderr
                # logging.error(f"Could not set HookWriter for stream {self.stream}")
                pass
        else:
            # For non-StreamHandlers (eg. stdout and stderr), just save the stream, we will
            # write our modified output to it.
            self.output_stream = stream
        self.flush()

    def restore(self):
        """Restore the original stream so that we no longer intercept output of the stream.

        This will restore streams for a logging.StreamHandler. For others, such as sys.stdout
        and sys.stderr, they should be restored manually by the caller (eg. sys.stdout = original_stdout)
        """
        if isinstance(self.stream, logging.StreamHandler):
            self.stream.setStream(self.output_stream)

    def write(self, msg):
        """Write handler. Called when writing to the original stream that we're intercepting.

        Args:
            msg: The text to write.
        """
        if isinstance(msg, bytes):
            msg = msg.decode(DEFAULT_ENCODING)

        if self.at_new_line:
            # Clear whole line and force return to start of line
            self.output_stream.write("\x1b[2K\r")

        # For this particular Writer, we are at the beginning of a line when at_new_line is True.
        # In the next call to write, we will clear the line when at_new_line is True
        # self.at_new_line = "\n" in msg or "\r" in msg
        self.at_new_line = msg.endswith("\n") or msg.endswith("\r")

        # Any new lines should consist of a clear to end of current line, new line, then clear full line
        msg = msg.replace("\n", "\x1b[K\n\x1b[2K")

        # Output the text
        self.output_stream.write(msg)
        self.flush()

        if self.refresh_callback is not None and self.at_new_line:
            self.refresh_callback()

    def flush(self):
        self.output_stream.flush()

    @property
    def encoding(self):
        return self.output_stream.encoding
