"""Tests for odm_map.progress.hook_writer.HookWriter"""

import io
import logging


from odm_map.progress.hook_writer import HookWriter, DEFAULT_ENCODING


class TestHookWriterInit:
    def test_init_with_plain_stream(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        assert writer.output_stream is stream
        assert writer.stream is stream

    def test_init_with_stream_handler(self):
        underlying = io.StringIO()
        handler = logging.StreamHandler(underlying)
        writer = HookWriter(handler, None)
        # HookWriter intercepts the handler's stream
        assert handler.stream is writer
        assert writer.output_stream is underlying

    def test_at_new_line_starts_true(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        assert writer.at_new_line is True

    def test_refresh_callback_stored(self):
        stream = io.StringIO()

        def callback():
            pass

        writer = HookWriter(stream, callback)
        assert writer.refresh_callback is callback


class TestHookWriterWrite:
    def test_write_plain_text(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.write("hello")
        assert "hello" in stream.getvalue()

    def test_write_bytes_decoded(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.write(b"bytes_text")
        assert "bytes_text" in stream.getvalue()

    def test_write_bytes_uses_default_encoding(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        msg = "café"
        writer.write(msg.encode(DEFAULT_ENCODING))
        assert msg in stream.getvalue()

    def test_at_new_line_true_after_newline(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.at_new_line = False
        writer.write("text\n")
        assert writer.at_new_line is True

    def test_at_new_line_true_after_carriage_return(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.at_new_line = False
        writer.write("text\r")
        assert writer.at_new_line is True

    def test_at_new_line_false_after_plain_text(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.at_new_line = False
        writer.write("text")
        assert writer.at_new_line is False

    def test_clear_line_escape_inserted_when_at_new_line(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.at_new_line = True
        writer.write("hello")
        output = stream.getvalue()
        # \x1b[2K\r clears the line and returns to start
        assert "\x1b[2K\r" in output

    def test_refresh_callback_called_after_newline(self):
        stream = io.StringIO()
        calls = []
        writer = HookWriter(stream, lambda: calls.append(1))
        writer.write("hello\n")
        assert len(calls) == 1

    def test_refresh_callback_not_called_without_newline(self):
        stream = io.StringIO()
        calls = []
        writer = HookWriter(stream, lambda: calls.append(1))
        writer.write("hello")
        assert len(calls) == 0

    def test_refresh_callback_none_does_not_raise(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.write("hello\n")  # no exception when callback is None


class TestHookWriterRestore:
    def test_restore_stream_handler_reverts_to_original(self):
        underlying = io.StringIO()
        handler = logging.StreamHandler(underlying)
        writer = HookWriter(handler, None)
        assert handler.stream is writer
        writer.restore()
        assert handler.stream is underlying

    def test_restore_plain_stream_does_nothing(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.restore()  # should not raise


class TestHookWriterEncoding:
    def test_encoding_matches_output_stream(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        assert writer.encoding == stream.encoding

    def test_flush_does_not_raise(self):
        stream = io.StringIO()
        writer = HookWriter(stream, None)
        writer.flush()
