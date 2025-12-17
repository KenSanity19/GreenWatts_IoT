"""Lazy loading middleware to defer heavy imports until first request."""
import sys
import importlib


class LazyLoadingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._loaded = False
    
    def __call__(self, request):
        if not self._loaded:
            self._load_heavy_modules()
            self._loaded = True
        return self.get_response(request)
    
    def _load_heavy_modules(self):
        modules = [
            'google.oauth2.credentials',
            'google.auth.transport.requests', 
            'googleapiclient.discovery',
            'email.mime.text',
        ]
        for module in modules:
            try:
                if module not in sys.modules:
                    importlib.import_module(module)
            except ImportError:
                pass