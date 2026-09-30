# core/logging.py
"""Attach the current request id to every log record, so one request's lines can be grepped together."""
import contextvars
import logging

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='-')


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True
