import sys
import os

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Force unbuffered output
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
        print("*** MIDDLEWARE INITIALIZED ***", flush=True)

    def __call__(self, request):
        print(f"*** REQUEST: {request.method} {request.path} ***", flush=True)
        
        response = self.get_response(request)
        
        print(f"*** RESPONSE: {response.status_code} ***", flush=True)
        
        return response