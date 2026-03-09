#!/usr/bin/env python3
#
# Description: Unified API + Admin panel for JupyterHub standalone application
#

from flask import Flask, make_response, request, render_template, redirect, url_for, flash, jsonify, session
from functools import wraps
import os
import json
import logging
import time
from datetime import datetime
from hashlib import sha256
import jupyterhub_api as hub_api

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('JUPYTERHUB_API_TOKEN', 'secret_key_for_flask')

# Dictionary to track user sessions
dict_user_session = dict()

# Environment variable names
DEFAULT_TIMEOUT = 'JUPYTERHUB_TIMEOUT'
DEFAULT_MAX_USER = 'JUPYTERHUB_USER'
DEFAULT_CPU_PERCENTAGE = 'JUPYTERHUB_PERCENTAGE_CPU'
DEFAULT_MEMORY_LIMIT = 'JUPYTERHUB_MEMORY_LIMIT'
API_URL = os.getenv('API_JUPYTERHUB')


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def require_token(f):
    """Decorator that enforces Bearer token authentication using JUPYTERHUB_API_TOKEN."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.getenv('JUPYTERHUB_API_TOKEN', '')
        if not auth_header.startswith('Bearer ') or auth_header[len('Bearer '):] != expected_token:
            return jsonify({'error': 'Unauthorized', 'message': 'Valid Bearer token required'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_session_id():
    """Generate a unique session ID based on IP and user agent"""
    ip_address = request.environ.get('REMOTE_ADDR')
    user_agent = request.environ.get('HTTP_USER_AGENT')
    unique_string = f"{ip_address}-{user_agent}"
    return sha256(unique_string.encode()).hexdigest()


def get_user_id(session_id):
    """Get user ID from session ID"""
    session_to_user = {v: k for k, v in dict_user_session.items()}
    return session_to_user.get(session_id)


def remove_session_to_user(user):
    """Remove a user session"""
    if user in dict_user_session:
        dict_user_session.pop(user)


def validate_inputs(timeout, max_user, cpu, memory):
    """Validate all input values with specific ranges and requirements"""
    try:
        timeout = int(timeout)
        if timeout < 5:
            raise ValueError("Timeout must be at least 5 seconds")

        max_user = int(max_user)
        if max_user <= 0:
            raise ValueError("Maximum users must be greater than 0")

        cpu = int(cpu)
        if cpu < 1 or cpu > 100:
            raise ValueError("CPU percentage must be between 1 and 100")

        if not memory.endswith(('M', 'G')):
            raise ValueError("Memory must end with M or G")

        memory_value = int(memory[:-1])
        if memory_value <= 0:
            raise ValueError("Memory value must be greater than 0")

        return timeout, max_user, cpu, memory

    except ValueError as e:
        raise ValueError(str(e))


def update_env_variable(key, value):
    """Update environment variable"""
    try:
        os.environ[key] = str(value)
        return True
    except Exception as e:
        log.error(f"Error updating environment variable {key}: {str(e)}")
        return False


# ---------------------------------------------------------------------------
# Core API routes (originally api.py, port 6000)
# ---------------------------------------------------------------------------

@app.route('/get_user', methods=['GET'])
def get_user():
    usr = hub_api.get_free_user()
    if usr is None:
        html_content = render_template('jupyterhub_no_users.html')
        response = make_response(html_content, 503)
        response.mimetype = "text/html"
        log.info("No free users available - returning HTML template")
        return response

    response = {'user': usr}
    log.info(f"get_user-get_free_user {response}")
    r = json.dumps(response, indent=4)
    response = make_response(r, 200)
    response.mimetype = "application/json"
    return response


@app.route('/running_user', methods=['GET'])
@require_token
def running_user():
    return hub_api.get_running_users()


@app.route('/copy_notebook', methods=['GET'])
@require_token
def copy_notebook():
    username = request.args.get('username')
    notebook_name = request.args.get('notebook_name')
    result = hub_api.copy_notebook_to_container(username, notebook_name)
    return str(result)


@app.route('/cleanup_volumes', methods=['GET'])
@require_token
def cleanup_volumes():
    result = hub_api.cleanup_unused_volumes()
    return str(result)


# ---------------------------------------------------------------------------
# Admin / demo routes (originally admin_app.py, port 7000)
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Main dashboard page"""
    extra_vars = {
        'max_users': os.environ.get('JUPYTERHUB_USER', '3'),
        'base_url': os.environ.get('JUPYTERNOTEBOOK_URL', 'http://localhost:8000/ldmjupyter/')
    }
    return render_template('dashboard.html', **extra_vars)


@app.route('/list_notebooks')
@require_token
def list_notebooks():
    """List all available notebooks in the notebooks folder"""
    try:
        notebooks_path = os.getenv('STORAGE_PATH', '/note')
        notebooks = []
        log.info(f"notebooks_path {notebooks_path}")
        if os.path.exists(notebooks_path) and os.path.isdir(notebooks_path):
            log.info(f"notebooks_path OK {notebooks_path}")
            for filename in os.listdir(notebooks_path):
                log.info(f"notebook filename {filename}")
                if filename.endswith('.ipynb'):
                    file_path = os.path.join(notebooks_path, filename)
                    try:
                        stat = os.stat(file_path)
                        modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                    except:
                        modified = 'Unknown'

                    notebooks.append({
                        'name': filename,
                        'modified': modified
                    })

        notebooks.sort(key=lambda x: x['name'])
        return jsonify({'notebooks': notebooks})
    except Exception as e:
        log.error(f"Error listing notebooks: {str(e)}")
        return jsonify({'notebooks': [], 'error': str(e)}), 500


@app.route('/open_notebook/<notebook_name>')
def open_notebook(notebook_name):
    """Open a notebook — handles session management"""
    try:
        session_id = generate_session_id()
        log.info(f"Session ID: {session_id}")

        current_session = False

        if session_id in dict_user_session.values():
            user = get_user_id(session_id)
            current_session = True
            log.info(f"Existing session found for user: {user}")
        else:
            user = hub_api.get_free_user()
            if user is None:
                log.error("No free users available")
                return jsonify({
                    'error': 'no_users',
                    'message': 'No free JupyterHub users available. Please wait a few minutes and try again.'
                }), 503

            dict_user_session[user] = session_id
            log.info(f"New session created for user: {user}")

        log.info(f"Current session dictionary: {dict_user_session}")

        result = hub_api.copy_notebook_to_container(user, notebook_name)

        if not result:
            log.error(f"Failed to copy notebook {notebook_name} for user {user}")
            return jsonify({
                'error': 'copy_failed',
                'message': 'Failed to copy notebook to user container'
            }), 500

        base_url = os.getenv('JUPYTERNOTEBOOK_URL', 'http://localhost:8000/ldmjupyter/')
        notebook_url = f"{base_url}user/{user}/notebooks/{notebook_name}"
        log.info(f"Notebook URL: {notebook_url}")

        return jsonify({
            'success': True,
            'url': notebook_url,
            'user': user,
            'existing_session': current_session
        })

    except Exception as e:
        log.error(f"Error opening notebook: {str(e)}")
        return jsonify({'error': 'server_error', 'message': str(e)}), 500


@app.route('/admin', methods=['GET', 'POST'])
@require_token
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'default_setup':
            timeout = request.form.get(DEFAULT_TIMEOUT, '')
            max_user = request.form.get(DEFAULT_MAX_USER, '')
            cpu = request.form.get(DEFAULT_CPU_PERCENTAGE, '')
            memory = request.form.get(DEFAULT_MEMORY_LIMIT, '').strip()
            need_restart = False

            try:
                timeout, max_user, cpu, memory = validate_inputs(timeout, max_user, cpu, memory)

                old_max_user = os.environ.get('JUPYTERHUB_USER')
                old_timeout = os.environ.get('JUPYTERHUB_TIMEOUT')

                if old_max_user != str(max_user) or old_timeout != str(timeout):
                    need_restart = True

                updates = {
                    'JUPYTERHUB_TIMEOUT': str(timeout),
                    'JUPYTERHUB_USER': str(max_user),
                    'JUPYTERHUB_PERCENTAGE_CPU': str(cpu),
                    'JUPYTERHUB_MEMORY_LIMIT': memory
                }

                success = all(update_env_variable(k, v) for k, v in updates.items())

                if success:
                    if need_restart:
                        env_file = '/srv/jupyterhub/custom_env.json'
                        try:
                            custom_env = {}
                            if os.path.exists(env_file):
                                with open(env_file, 'r') as f:
                                    custom_env = json.load(f)
                            custom_env.update(updates)
                            with open(env_file, 'w') as f:
                                json.dump(custom_env, f, indent=2)
                            log.info(f"Saved environment updates to {env_file}")
                        except Exception as e:
                            log.error(f"Error saving environment file: {str(e)}")

                        restart_file = '/srv/jupyterhub/restart_requested'
                        try:
                            with open(restart_file, 'w') as f:
                                f.write('restart requested at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
                            log.info("Restart flag created")
                        except Exception as e:
                            log.error(f"Error creating restart flag: {str(e)}")

                        flash('JupyterHub settings updated successfully. Services are restarting...', 'success')
                    else:
                        flash('JupyterHub settings updated successfully.', 'success')
                else:
                    flash('Error updating JupyterHub settings.', 'error')

            except ValueError as e:
                flash(f"Invalid input: {str(e)}", 'error')

    extra_vars = {
        'timeout': os.environ.get('JUPYTERHUB_TIMEOUT'),
        'max_user': os.environ.get('JUPYTERHUB_USER'),
        'cpu': os.environ.get('JUPYTERHUB_PERCENTAGE_CPU'),
        'memory': os.environ.get('JUPYTERHUB_MEMORY_LIMIT')
    }
    log.info(f"Response: {extra_vars}")
    return render_template('admin_jupyter.html', **extra_vars)


@app.route('/running_users')
@require_token
def running_users():
    try:
        running_list = hub_api.get_running_users()
        log.info(f"Running users: {running_list}")
        return render_template('running_users.html', users=running_list)
    except Exception as e:
        log.error(f"Error getting running users: {str(e)}")
        return render_template('running_users.html', users=[])


@app.route('/session_info')
@require_token
def session_info():
    """Debug endpoint to see current session information"""
    session_id = generate_session_id()
    user = get_user_id(session_id) if session_id in dict_user_session.values() else None
    return jsonify({
        'session_id': session_id,
        'user': user,
        'all_sessions': dict_user_session
    })


@app.route('/status')
def status():
    """Health-check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': time.time()})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # port = int(os.environ.get('JUPYTERHUB_API_PORT', 6000))
    # app.run(host='0.0.0.0', port=port)
    app.run(host='0.0.0.0', port=6000)
