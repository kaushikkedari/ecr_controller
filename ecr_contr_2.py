import subprocess
import boto3
import base64
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import shlex
import os
# ==============================================================================
# 1. INITIAL SETUP & CONFIGURATION
# ==============================================================================
app = Flask(__name__)
CORS(app, origins=["http://localhost:3000","http://livelabs.nitor.in", "https://livelabs.nitor.in"])

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:mypassword@livelabs.nitor.in:5432/poc_showcase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- AWS Configuration ---
AWS_REGION       = 'us-east-2'
ECR_ACCOUNT_ID   = '231733667519'
ecr = boto3.client('ecr', region_name=AWS_REGION)

# ==============================================================================
# 2. DATABASE MODEL DEFINITION
# ==============================================================================
# This class defines the structure of your 'projects' table in the database.

class Project(db.Model):
    __tablename__ = 'poc_projects'

    id = db.Column(db.Integer, primary_key=True)
    # 'name' is the unique identifier for your project, e.g., "invoice-ai-agent"
    name = db.Column(db.String(100), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description= db.Column(db.Text, nullable=True)
    tag = db.Column(db.String(100), nullable=True)
    market_trend = db.Column(db.Text, nullable=True)
    videourl = db.Column(db.String(255), nullable=True)
    # Docker-specific fields
    ecr_repo_name = db.Column(db.String(200), nullable=False)
    image_tag = db.Column(db.String(100), nullable=False, default='latest')
    # 'container_name' is the name passed to `docker run --name`
    container_name = db.Column(db.String(200), nullable=False)
    startup_command = db.Column(db.Text, nullable=False)
    is_ecr = db.Column(db.Boolean, default=True, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    dns_url = db.Column(db.String(255), nullable=True)
    public_url = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    # Column to store the binary data of the thumbnail image
    thumb_image = db.Column(db.LargeBinary, nullable=True)
    documentation_text = db.Column(db.Text, nullable=True)
    documentation_link = db.Column(db.String(255), nullable=True)
    is_featured=db.Column(db.Boolean, default=True, nullable=False)
# Helper function to convert the database object to a dictionary
    def to_dict(self):
        # Base64 encode the image if it exists to make it JSON-safe
        thumb_image = None
        if self.thumb_image:
            thumb_image = base64.b64encode(self.thumb_image).decode('utf-8')

        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "tag": self.tag,
            "market_trend": self.market_trend,
            "videourl": self.videourl,
            "ecr_repo_name": self.ecr_repo_name,
            "image_tag": self.image_tag,
            "container_name": self.container_name,
            "startup_command": self.startup_command,
            "is_ecr": self.is_ecr,
            "category": self.category,
            "dns_url": self.dns_url,
            "public_url": self.public_url,
            "port": self.port,
            # Add the encoded image to the dictionary response
            "thumb_image": thumb_image,
            "documentation_text": self.documentation_text,
            "documentation_link": self.documentation_link,
            "is_featured":self.is_featured

        }
# ==============================================================================
# 3. API ENDPOINTS (Your Request)
# ==============================================================================


@app.route('/projects', methods=['POST'])
def add_project():
    """
    API Endpoint 1: Adds a new project configuration to the database.
    Receives multipart/form-data: text fields from the UI form and an optional image.
    """
    # When using multipart/form-data, text fields are in `request.form`
    data = request.form
    if not data or not data.get('name') or not data.get('container_name'):
        return jsonify({"status": "error", "message": "Missing required fields: name, container_name"}), 400

    # Check if a project with this name already exists
    if Project.query.filter_by(name=data['name']).first():
        return jsonify({"status": "error", "message": f"Project with name '{data['name']}' already exists."}), 409

    # Handle the optional image file upload from `request.files`
    thumb_image_data = None
    if 'thumb_image' in request.files:
        image_file = request.files['thumb_image']
        # Ensure the file is a valid image upload
        if image_file and image_file.filename != '':
            thumb_image_data = image_file.read()

    # Safely convert 'port' from string to integer
    port_val = None
    if data.get('port') and data.get('port').isdigit():
        port_val = int(data.get('port'))
        
    # Safely convert 'is_ecr' from string to boolean
    is_ecr_val = data.get('is_ecr', 'true').lower() in ['true', '1', 't', 'yes']
    is_featured_val=data.get('is_featured','true').lower() in ['true','1','t','yes']

    new_project = Project(
        name=data.get('name'),
        title=data.get('title'),
        description=data.get('description'),
        tag=data.get('tag'),
        market_trend=data.get('market_trend'),
        videourl=data.get('videourl'),
        ecr_repo_name=data.get('ecr_repo_name'),
        image_tag=data.get('image_tag', 'latest'),
        container_name=data.get('container_name'),
        startup_command=data.get('startup_command'),
        is_ecr=is_ecr_val,
        category=data.get('category'),
        dns_url=data.get('dns_url'),
        public_url=data.get('public_url'),
        port=port_val,
        # Add the binary image data to the model
        thumb_image=thumb_image_data,
        documentation_text=data.get('documentation_text'),
        documentation_link=data.get('documentation_link'),
        is_featured=is_featured_val
    )

    try:
        db.session.add(new_project)
        db.session.commit()
        return jsonify({"status": "success", "message": "Project added successfully.", "project": new_project.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500
    


@app.route('/projects/<string:project_name>', methods=['GET'])
def get_project(project_name):
    """
    API Endpoint 2: Gets the configuration for a specific project from the database.
    """
    project_name = project_name.strip()
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        return jsonify({"status": "error", "message": f"Project '{project_name}' not found."}), 404

    return jsonify(project.to_dict())


def get_project_config_from_db(project_name: str) -> dict:
    """
    NEW HELPER: Fetches project configuration from the database.
    This replaces the old static PROJECT_CONFIGS dictionary lookup.
    """
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        raise ValueError(f"Project {project_name} not found in the database.")
    return {k.upper(): v for k, v in project.to_dict().items()}

def ecr_login():
    """Authenticate Docker to ECR. (No changes needed)"""
    token_resp = ecr.get_authorization_token(registryIds=[ECR_ACCOUNT_ID])
    token = token_resp['authorizationData'][0]['authorizationToken']
    endpoint = token_resp['authorizationData'][0]['proxyEndpoint']
    user_pass = base64.b64decode(token).decode('utf-8')
    username, password = user_pass.split(':', 1)
    login_cmd = ['docker', 'login', '--username', username, '--password', password, endpoint]
    subprocess.check_call(login_cmd)
    return endpoint
def pull_image(config: dict):
    """
    Pull image based on project config dictionary.
    This version correctly handles both ECR and public images.
    """
    is_ecr = config.get('IS_ECR', True)
    
    if is_ecr:
        # ECR Logic: Build the URI from the endpoint and repo name
        endpoint = ecr_login()
        image_uri = f"{endpoint.replace('https://','')}/{config['ECR_REPO_NAME']}:{config['IMAGE_TAG']}"
    else:
        # Public Image Logic: Build the URI directly from repo name and tag
        image_uri = f"{config['ECR_REPO_NAME']}:{config['IMAGE_TAG']}"

    print(f"--- Attempting to pull image: {image_uri} ---")
    subprocess.check_call(['docker', 'pull', image_uri])
    return image_uri


def run_container(config: dict, image_uri: str):
    """Run the container using the project config dictionary."""
    container_name = config['CONTAINER_NAME']
    startup_command = config['STARTUP_COMMAND']

    # Stop and remove any existing container with the same name
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])

    # --- NEW: Make env-file path absolute ---
    # This ensures that relative paths in startup commands work correctly
    command_parts = shlex.split(startup_command)
    try:
        env_file_index = command_parts.index('--env-file')
        if env_file_index + 1 < len(command_parts):
            env_file_path = command_parts[env_file_index + 1]
            if not os.path.isabs(env_file_path):
                # Assumes script is two levels deep from project root (e.g., /app/ecr_controller/ecr_contr_2.py)
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                abs_env_file_path = os.path.join(project_root, env_file_path)
                command_parts[env_file_index + 1] = abs_env_file_path
                print(f"--- Resolved relative --env-file path to: {abs_env_file_path} ---")
    except ValueError:
        # --env-file not in command, do nothing
        pass


    # Build the command safely
    cmd_parts = ['docker', 'run', '--name', container_name] + command_parts + [image_uri]

    print(f"--- Attempting to run container: {container_name} ---")
    print(f"--- Full command parts: {cmd_parts} ---")

    process = subprocess.run(cmd_parts, capture_output=True, text=True, check=False)

    if process.returncode != 0:
        print(f"!!! Docker command failed for {container_name}. Stderr: {process.stderr}")
        raise subprocess.CalledProcessError(process.returncode, cmd_parts, output=process.stdout, stderr=process.stderr)
    
    print(f"--- Successfully started container {container_name} ---")
    print(f"--- Stdout: {process.stdout}")
    if process.stderr:
        print(f"--- Stderr (warnings): {process.stderr}")
    return True

def stop_container(config: dict):
    """Stop and remove the container using the project config dictionary."""
    container_name = config['CONTAINER_NAME']
    print(f"--- Stopping and removing container: {container_name} ---")
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])
    return True

def get_running_containers():
    """Get a list of running docker containers with their details. (No changes needed)"""
    cmd = ['docker', 'ps', '--format', '{{json .}}']
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = process.stdout.strip()
        return [json.loads(line) for line in output.splitlines()] if output else []
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error getting running containers: {e}")
        return None
    
@app.route('/start/<project_name>', methods=['POST'])
def start(project_name: str):
    """Endpoint to pull & start a container by fetching its config from the DB."""
    project_name = project_name.strip()
    try:
        config = get_project_config_from_db(project_name)
        image_uri = pull_image(config)
        run_container(config, image_uri)
        return jsonify({"status": "started", "project": project_name, "image": image_uri})
    except ValueError as e:
        # Specifically catch the "not found" error and return a 404
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 404
    except subprocess.CalledProcessError as e:
        # Other errors during execution are 500
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 500
    except Exception as e:
        return jsonify({"status": "error", "project": project_name, "message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/stop/<project_name>', methods=['POST'])
def stop(project_name: str):
    """Endpoint to stop & remove a container by fetching its config from the DB."""
    project_name = project_name.strip()
    try:
        config = get_project_config_from_db(project_name)
        stop_container(config)
        return jsonify({"status": "stopped", "project": project_name})
    except ValueError as e:
        # Specifically catch the "not found" error and return a 404
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 404
    except subprocess.CalledProcessError as e:
        # Other errors during execution are 500
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 500
    except Exception as e:
        return jsonify({"status": "error", "project": project_name, "message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/status', methods=['GET'])
def status():
    """Endpoint to get the status of all projects defined in the database."""
    running_containers = get_running_containers()
    if running_containers is None:
        return jsonify({"status": "error", "message": "Failed to retrieve container status from Docker."}), 500

    running_container_map = {c.get('Names'): c for c in running_containers}
    
    all_projects = Project.query.all()
    project_statuses = {}
    for project in all_projects:
        # The name given to `docker run --name` is in the 'container_name' field
        container_name = project.container_name
        if container_name in running_container_map:
            project_statuses[project.name] = {
                "status": "running",
                "details": running_container_map[container_name]
            }
        else:
            project_statuses[project.name] = {"status": "stopped"}

    return jsonify(project_statuses)

@app.route('/projects/<string:project_name>', methods=['PUT'])
def update_project(project_name):
    """
    API Endpoint 4: Updates an existing project's configuration.
    Receives multipart/form-data for updates.
    """
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        return jsonify({"status": "error", "message": f"Project '{project_name}' not found."}), 404

    data = request.form

    # Update fields only if they are provided in the incoming form data
    if 'name' in data and data['name'] != project.name:
        # Check if the new name is already taken by another project
        if Project.query.filter_by(name=data['name']).first():
            return jsonify({"status": "error", "message": f"Project name '{data['name']}' is already in use."}), 409
        project.name = data['name']
    
    # Update all other text-based fields
    for key, value in data.items():
        if hasattr(project, key) and key != 'name':
            # Special handling for boolean and integer fields
            if key == 'is_ecr':
                setattr(project, key, value.lower() in ['true', '1', 't', 'yes'])
            elif key == 'is_featured':
                setattr(project, key, value.lower() in ['true','1','t','yes'])
            elif key == 'port' and value.isdigit():
                setattr(project, key, int(value))
            else:
                setattr(project, key, value)

    # Handle optional image file update
    if 'thumb_image' in request.files:
        image_file = request.files['thumb_image']
        if image_file and image_file.filename != '':
            project.thumb_image = image_file.read()

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Project updated successfully.", "project": project.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500
# ==============================================================================
# 6. DATABASE INITIALIZATION & APP START
# ==============================================================================
if __name__ == '__main__':
    # This block creates the 'project' table if it doesn't exist.
    # It's safe to run every time.
    with app.app_context():
        db.create_all()
    
    app.run(host='0.0.0.0', port=5000, debug=True)


