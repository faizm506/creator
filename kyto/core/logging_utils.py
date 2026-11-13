import contextvars
import logging

request_id_var = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Puts the current request's reference on every log line, so one problem can be followed from page to log."""

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True
