import sys
import os

# Add root folder to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

# WSGI Middleware to fix Vercel path prefixing
class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        
        # Strip /api/index.py or /api/index prefix if added by Vercel rewrites
        if path.startswith('/api/index.py'):
            path = path[len('/api/index.py'):]
        elif path.startswith('/api/index'):
            # Only strip if it's the rewrite target, e.g. /api/index/api/records or /api/index
            sub = path[len('/api/index'):]
            if sub == '' or sub.startswith('/'):
                path = sub

        if not path or path == '':
            path = '/'
            
        environ['PATH_INFO'] = path
        return self.wsgi_app(environ, start_response)

# Wrap Flask with path normalization middleware for Vercel
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
