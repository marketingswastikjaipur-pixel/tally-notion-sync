import sys
import os
import json

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app
from flask import jsonify, request

@app.before_request
def check_debug():
    if request.path == '/debug' or request.path.endswith('/debug'):
        env_dict = {k: str(v) for k, v in request.environ.items() if not k.startswith('wsgi.')}
        return jsonify(env_dict)

class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # Let's inspect what Vercel passes
        path = environ.get('PATH_INFO', '')
        # Don't overwrite PATH_INFO if it already has the path!
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
