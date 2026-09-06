import sys
import os

# Add root folder to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

# WSGI Middleware to reliably resolve the actual requested URL path on Vercel
class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Check for real requested URI from Vercel headers
        actual_path = (
            environ.get('RAW_URI') or 
            environ.get('REQUEST_URI') or 
            environ.get('HTTP_X_MATCHED_PATH') or 
            environ.get('PATH_INFO') or 
            '/'
        )

        # Strip query parameters if present
        path = actual_path.split('?')[0]

        # Strip internal function prefix if prepended
        if path.startswith('/api/index.py'):
            path = path[len('/api/index.py'):]
        elif path.startswith('/api/index') and (len(path) == 10 or path[10] == '/'):
            path = path[len('/api/index'):]

        if not path or path == '':
            path = '/'

        environ['PATH_INFO'] = path
        return self.wsgi_app(environ, start_response)

# Apply middleware
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
