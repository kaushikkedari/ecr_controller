import subprocess
import boto3
import base64
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration: adjust as needed
AWS_REGION       = 'us-east-2'
ECR_ACCOUNT_ID   = '231733667519'

# Project-specific configurations
PROJECT_CONFIGS = {
    "invoice-ai-agent": {
        "ECR_REPO_NAME": 'invoice-ai-agent',
        "IMAGE_TAG": 'latest',
        "CONTAINER_NAME": 'invoice-agent',
        "STARTUP_COMMAND": '-d -p 8501:8501 --env-file .env',
        "is_ECR": True
    },
    
    "open-webui": {
        "ECR_REPO_NAME": 'open-webui',
        "IMAGE_TAG": 'main',
        "CONTAINER_NAME": 'ghcr.io/open-webui/open-webui:main',
        "STARTUP_COMMAND": '-d -p 8502:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --restart always',
        "is_ECR": False
    },

    "langflow": {
        "ECR_REPO_NAME": 'langflow',
        "IMAGE_TAG": 'latest',
        "CONTAINER_NAME": 'langflowai/langflow:latest',
        "STARTUP_COMMAND": '-d -p 8503:7860',
        "is_ECR": False
    }
    
}

ecr = boto3.client('ecr', region_name=AWS_REGION)

def ecr_login():
    """Authenticate Docker to ECR."""
    token_resp = ecr.get_authorization_token(registryIds=[ECR_ACCOUNT_ID])
    token = token_resp['authorizationData'][0]['authorizationToken']
    endpoint = token_resp['authorizationData'][0]['proxyEndpoint']
    user_pass = base64.b64decode(token).decode('utf-8')  # "AWS:xxxx"
    username, password = user_pass.split(':', 1)
    
    login_cmd = [
        'docker', 'login',
        '--username', username,
        '--password', password,
        endpoint
    ]
    subprocess.check_call(login_cmd)
    return endpoint

def pull_image(project_name: str):
    """Pull the latest image from ECR or public registry based on project configuration."""
    if project_name not in PROJECT_CONFIGS:
        raise ValueError(f"Project {project_name} not configured.")
    
    config = PROJECT_CONFIGS[project_name]
    is_ecr = config.get('is_ECR', True)  # Default to True for backward compatibility
    
    if is_ecr:
        # ECR workflow - authenticate and pull from ECR
        endpoint = ecr_login()
        image_uri = f"{endpoint.replace('https://','')}/{config['ECR_REPO_NAME']}:{config['IMAGE_TAG']}"
    else:
        # Public registry workflow - use CONTAINER_NAME as the full image URI
        image_uri = config['CONTAINER_NAME']
    
    subprocess.check_call(['docker', 'pull', image_uri])
    return image_uri

def run_container(project_name: str, image_uri: str):
    """Run the container for the specified project."""
    if project_name not in PROJECT_CONFIGS:
        raise ValueError(f"Project {project_name} not configured.")
    
    config = PROJECT_CONFIGS[project_name]
    is_ecr = config.get('is_ECR', True)  # Default to True for backward compatibility
    
    if is_ecr:
        # For ECR projects, use CONTAINER_NAME as the runtime container name
        container_name = config['CONTAINER_NAME']
    else:
        # For non-ECR projects, use ECR_REPO_NAME as the runtime container name
        container_name = config['ECR_REPO_NAME']
    
    startup_command = config['STARTUP_COMMAND']

    # Stop existing container if running
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])
    
    # Start new container
    cmd = f"docker run --name {container_name} {startup_command} {image_uri}"
    cmd_parts = cmd.split()

    print(f'--- Attempting to run for project: {project_name} ---')
    print(f'Full command string: {cmd}')
    print(f'Command parts for subprocess: {cmd_parts}')
    
    try:
        # Using subprocess.run to capture output
        process = subprocess.run(
            cmd_parts, 
            capture_output=True, 
            text=True, # Decodes stdout/stderr as text
            check=False # We will check the returncode manually
        )
        
        print(f'Docker command stdout for {project_name}:')
        print(process.stdout if process.stdout else "<No stdout>")
        
        if process.returncode != 0:
            print(f'!!! Docker command stderr for {project_name} (Return Code: {process.returncode}):')
            print(process.stderr if process.stderr else "<No stderr>")
            raise subprocess.CalledProcessError(process.returncode, cmd_parts, output=process.stdout, stderr=process.stderr)
        else:
            print(f'Docker command stderr for {project_name} (Return Code: 0 - Success):') # Still print stderr for warnings
            print(process.stderr if process.stderr else "<No stderr>")

        print(f'--- Successfully started container for {project_name} ---')
        return True
    except FileNotFoundError:
        print(f"!!! Error: Docker command not found. Is Docker installed and in PATH?")
        raise
    except subprocess.CalledProcessError as e:
        print(f"!!! Docker command failed for {project_name} with return code {e.returncode}")
        # The CalledProcessError already contains stdout and stderr, so no need to print them again here if they were already printed.
        raise

def stop_container(project_name: str):
    """Stop and remove the container for the specified project."""
    if project_name not in PROJECT_CONFIGS:
        raise ValueError(f"Project {project_name} not configured.")

    config = PROJECT_CONFIGS[project_name]
    is_ecr = config.get('is_ECR', True)  # Default to True for backward compatibility
    
    if is_ecr:
        # For ECR projects, use CONTAINER_NAME as the runtime container name
        container_name = config['CONTAINER_NAME']
    else:
        # For non-ECR projects, use ECR_REPO_NAME as the runtime container name
        container_name = config['ECR_REPO_NAME']
    
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])
    return True

@app.route('/start/<project_name>', methods=['POST'])
def start(project_name: str):
    """Endpoint to pull & start the container for a specific project via URL parameter."""
    print(f"--- Received POST request for /start/{project_name} ---")
    if project_name not in PROJECT_CONFIGS:
        print(f"--- Project {project_name} not found in PROJECT_CONFIGS ---")
        return jsonify({"status": "error", "message": f"Project {project_name} not configured."}), 404
    
    print(f"--- Configuration found for project: {project_name} ---")
    try:
        print(f"--- Attempting to pull image for {project_name} ---")
        image_uri = pull_image(project_name)
        print(f'image_uri for {project_name} --> ', image_uri)
        print(f"--- Attempting to run container for {project_name} ---")
        run_container(project_name, image_uri)
        return jsonify({"status": "started", "project": project_name, "image": image_uri})
    except subprocess.CalledProcessError as e:
        print(f"--- subprocess.CalledProcessError in /start/{project_name}: {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 500
    except ValueError as e: # Catches project not configured in pull_image/run_container if missed above
        print(f"--- ValueError in /start/{project_name}: {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 400
    except Exception as e: # Catch any other unexpected errors
        print(f"--- Unexpected Exception in /start/{project_name}: {type(e).__name__} - {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/stop/<project_name>', methods=['POST'])
def stop(project_name: str):
    """Endpoint to stop & remove the container for a specific project via URL parameter."""
    print(f"--- Received POST request for /stop/{project_name} ---")
    if project_name not in PROJECT_CONFIGS:
        print(f"--- Project {project_name} not found in PROJECT_CONFIGS (stop endpoint) ---")
        return jsonify({"status": "error", "message": f"Project {project_name} not configured."}), 404

    try:
        stop_container(project_name)
        return jsonify({"status": "stopped", "project": project_name})
    except subprocess.CalledProcessError as e:
        print(f"--- subprocess.CalledProcessError in /stop/{project_name}: {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 500
    except ValueError as e: # Catches project not configured in stop_container if missed above
        print(f"--- ValueError in /stop/{project_name}: {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": str(e)}), 400
    except Exception as e: # Catch any other unexpected errors
        print(f"--- Unexpected Exception in /stop/{project_name}: {type(e).__name__} - {str(e)} ---")
        return jsonify({"status": "error", "project": project_name, "message": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    # Listen on all interfaces on port 5000
    app.run(host='0.0.0.0', port=5000)

# List which service is running on which port
# docker ps
# docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}"
# docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}" --no-trunc
# docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}" --no-trunc --format "{{.ID}}\t{{.Names}}\t{{.Ports}}"

# docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}" --no-trunc --format "{{.ID}}\t{{.Names}}\t{{.Ports}}"
# Add openwebUi and langflow with postgres 