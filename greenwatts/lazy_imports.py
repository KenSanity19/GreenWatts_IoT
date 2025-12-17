"""
Lazy import utilities for heavy modules.
Reduces Django startup time by deferring imports until needed.
"""
import importlib
from functools import lru_cache


class LazyImport:
    """Lazy import wrapper that imports modules only when accessed."""
    
    def __init__(self, module_name, attribute=None):
        self.module_name = module_name
        self.attribute = attribute
        self._module = None
    
    def __getattr__(self, name):
        if self._module is None:
            self._module = importlib.import_module(self.module_name)
        
        if self.attribute:
            return getattr(getattr(self._module, self.attribute), name)
        return getattr(self._module, name)
    
    def __call__(self, *args, **kwargs):
        if self._module is None:
            self._module = importlib.import_module(self.module_name)
        
        if self.attribute:
            return getattr(self._module, self.attribute)(*args, **kwargs)
        return self._module(*args, **kwargs)


# Heavy modules - lazy loaded
json = LazyImport('json')
csv = LazyImport('csv')
calendar = LazyImport('calendar')

# Google API modules - very heavy
gmail_api = LazyImport('utils.gmail_api')
google_credentials = LazyImport('google.oauth2.credentials', 'Credentials')
google_request = LazyImport('google.auth.transport.requests', 'Request')
googleapiclient_build = LazyImport('googleapiclient.discovery', 'build')

# Database query optimizations
@lru_cache(maxsize=32)
def get_db_models():
    """Cached import of Django models to avoid repeated imports."""
    from django.db import models
    return models

@lru_cache(maxsize=16)
def get_db_functions():
    """Cached import of Django database functions."""
    from django.db.models.functions import ExtractYear, ExtractMonth, TruncDate
    return ExtractYear, ExtractMonth, TruncDate

@lru_cache(maxsize=8)
def get_timezone_utils():
    """Cached import of timezone utilities."""
    from django.utils import timezone
    from datetime import datetime, timedelta, date
    return timezone, datetime, timedelta, date