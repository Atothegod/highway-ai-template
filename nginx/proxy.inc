    location / {
        # Resolve the service again if Compose replaces the backend container.
        resolver 127.0.0.11 valid=10s;
        set $django_backend backend:8000;
        proxy_pass http://$django_backend;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
