FROM jupyterhub/jupyterhub:4.1.6
ARG STORAGE_PATH

RUN pip install --no-cache \
    oauthenticator \
    dockerspawner \
    jupyterhub-nativeauthenticator \
    jupyterhub-idle-culler \
    flask \
    flask-wtf \
    docker

# Copy configuration files
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
COPY jupyterhub_api.py /srv/jupyterhub/jupyterhub_api.py
COPY api.py /srv/jupyterhub/api.py

# Create directory for templates
RUN mkdir -p /srv/jupyterhub/templates

# Copy template files
COPY templates/admin_jupyter.html /srv/jupyterhub/templates/
COPY templates/running_users.html /srv/jupyterhub/templates/
COPY templates/jupyterhub_no_users.html /srv/jupyterhub/templates/
COPY templates/dashboard.html /srv/jupyterhub/templates/

# Create directory for static files (images, css, js)
RUN mkdir -p /srv/jupyterhub/static

# Copy static files
COPY static /srv/jupyterhub/static/

# Copy the startup script into the container
COPY start_api.sh /usr/local/bin/start.sh

# Make the startup script executable
RUN chmod +x /usr/local/bin/start.sh

# Expose the necessary ports (JupyterHub, API, Admin panel)
EXPOSE 8000 6000 7000

# Set the startup script as the entrypoint
ENTRYPOINT ["/usr/local/bin/start.sh"]
