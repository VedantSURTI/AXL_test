import os
import base64
import subprocess
from typing import Optional, Dict, List, Tuple
import boto3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BuildPushError(Exception):
    pass

def get_aws_session():
    """Create a boto3 session with credentials from environment variables"""
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')  # Optional for temporary credentials
    region = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
    
    if not aws_access_key_id or not aws_secret_access_key:
        raise BuildPushError(
            "AWS credentials not found in environment variables. "
            "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file."
        )
    
    session_kwargs = {
        'aws_access_key_id': aws_access_key_id,
        'aws_secret_access_key': aws_secret_access_key,
        'region_name': region
    }
    
    if aws_session_token:
        session_kwargs['aws_session_token'] = aws_session_token
    
    return boto3.Session(**session_kwargs)

def check_aws_credentials() -> bool:
    """Check if AWS credentials are properly configured"""
    try:
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
        
        print(f"🔍 Checking AWS credentials...")
        print(f"   Access Key ID: {aws_access_key_id[:8]}..." if aws_access_key_id else "   Access Key ID: Not set")
        print(f"   Secret Key: {'*' * 20}..." if aws_secret_access_key else "   Secret Key: Not set")
        print(f"   Region: {region}")
        
        if not aws_access_key_id or not aws_secret_access_key:
            print("❌ AWS credentials not found in environment variables")
            return False
            
        session = get_aws_session()
        sts_client = session.client('sts')
        # Test the credentials
        response = sts_client.get_caller_identity()
        print(f"✅ AWS credentials validated for account: {response.get('Account')}")
        print(f"   User ARN: {response.get('Arn')}")
        return True
    except Exception as e:
        print(f"❌ AWS credentials validation failed: {e}")
        
        # Provide specific guidance based on error type
        error_str = str(e)
        if "InvalidClientTokenId" in error_str:
            print("💡 This error usually means:")
            print("   - The AWS_ACCESS_KEY_ID is incorrect or doesn't exist")
            print("   - The credentials have been deleted from AWS")
            print("   - There are extra spaces or characters in the access key")
        elif "SignatureDoesNotMatch" in error_str:
            print("💡 This error usually means:")
            print("   - The AWS_SECRET_ACCESS_KEY is incorrect")
            print("   - There are extra spaces or characters in the secret key")
        elif "TokenRefreshRequired" in error_str:
            print("💡 This error usually means:")
            print("   - The credentials have expired (if using temporary credentials)")
            print("   - You need to refresh your session token")
        
        return False

def _ensure_ecr_repo(repo_name: str, region: str) -> None:
    """Create ECR repository if it doesn't exist"""
    try:
        session = get_aws_session()
        ecr = session.client("ecr", region_name=region)
        ecr.create_repository(repositoryName=repo_name)
        print(f"✅ Created ECR repo: {repo_name}")
    except Exception as e:
        # Check if it's the "repository already exists" error
        if "RepositoryAlreadyExistsException" in str(e):
            print(f"ℹ️ ECR repo already exists: {repo_name}")
        else:
            raise BuildPushError(f"Failed to ensure ECR repository: {e}")

def _ecr_login(region: str) -> str:
    """
    Log the local docker client into ECR using boto3 auth token.
    Returns the ECR registry endpoint used (e.g. 12345.dkr.ecr.ap-south-1.amazonaws.com)
    """
    try:
        session = get_aws_session()
        ecr = session.client("ecr", region_name=region)
        auth_data = ecr.get_authorization_token()["authorizationData"][0]
        auth_token = auth_data["authorizationToken"]  # base64 of "user:password"
        proxy_endpoint = auth_data["proxyEndpoint"]  # e.g. https://<account>.dkr.ecr.<region>.amazonaws.com

        decoded = base64.b64decode(auth_token).decode()
        if ":" not in decoded:
            raise BuildPushError("Unexpected ECR auth token format")
        username, password = decoded.split(":", 1)

        # docker login requires endpoint without protocol for some clients; use proxy_endpoint as-is
        print(f"🔑 Logging into ECR: {proxy_endpoint}")
        p = subprocess.run(
            ["docker", "login", "--username", username, "--password-stdin", proxy_endpoint],
            input=password.encode(),
            check=False,
            capture_output=True,
        )
        if p.returncode != 0:
            raise BuildPushError(f"docker login failed: {p.stderr.decode().strip()}")
        print("✅ Docker login successful")
        # normalize endpoint to host-only (strip https://)
        return proxy_endpoint.replace("https://", "")
    except Exception as e:
        raise BuildPushError(f"ECR login failed: {e}")



def build_image(
    folder: str,
    repo_name: str,
    aws_account_id: Optional[str] = None,
    region: Optional[str] = None,
    tag: str = "latest",
    dockerfile: str = "Dockerfile",
    build_args: Optional[Dict[str, str]] = None,
    no_cache: bool = False,
    buildx: bool = False,
    platforms: Optional[List[str]] = None,
    fail_on: str = "CRITICAL"
) -> str:
    """
    Build the Dockerfile located in `folder` and tag it for ECR.
    Uses environment variables for AWS configuration if not provided.
    Returns image_uri.
    """
    # Get configuration from environment variables if not provided
    if not aws_account_id:
        aws_account_id = os.getenv('AWS_ACCOUNT_ID')
        if not aws_account_id:
            raise BuildPushError("AWS_ACCOUNT_ID not found in environment variables")
    
    if not region:
        region = os.getenv('ECR_REGION', os.getenv('AWS_DEFAULT_REGION', 'ap-south-1'))
    
    dockerfile_path = os.path.join(folder, dockerfile)
    if not os.path.isfile(dockerfile_path):
        raise BuildPushError(f"Dockerfile not found at {dockerfile_path}")
    
    # Check AWS credentials before proceeding
    if not check_aws_credentials():
        raise BuildPushError("AWS credentials validation failed. Please check your .env file.")
    
    _ensure_ecr_repo(repo_name, region)
    registry = _ecr_login(region)
    image_uri = f"{aws_account_id}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{tag}"

    if buildx:
        if not platforms:
            raise BuildPushError("buildx=True requires 'platforms' to be provided (e.g. ['linux/amd64'])")
        platform_arg = ",".join(platforms)
        cmd = [
            "docker", "buildx", "build",
            "--platform", platform_arg,
            "-t", image_uri,
            "-f", dockerfile_path,
            folder,
        ]
        # add build args
        if build_args:
            for k, v in build_args.items():
                cmd.extend(["--build-arg", f"{k}={v}"])
        if no_cache:
            cmd.insert(2, "--no-cache")
        print("🔨 Running buildx:", " ".join(cmd))
        p = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if p.returncode != 0:
            raise BuildPushError(f"buildx build failed:\n{p.stderr}")
        print("✅ buildx build completed")
    else:
        # Set Docker BuildKit based on environment variable
        docker_buildkit = os.getenv('DOCKER_BUILDKIT', '0')
        env = os.environ.copy()
        env['DOCKER_BUILDKIT'] = docker_buildkit
        
        build_cmd = ["docker", "build"]
        if no_cache:
            build_cmd.append("--no-cache")
        if build_args:
            for k, v in build_args.items():
                build_cmd += ["--build-arg", f"{k}={v}"]
        build_cmd += ["-t", image_uri, "-f", dockerfile_path, folder]
        print("🔨 Running docker build:", " ".join(build_cmd))
        print(f"   DOCKER_BUILDKIT={docker_buildkit}")
        p = subprocess.run(build_cmd, check=False, capture_output=True, text=True, env=env)
        if p.returncode != 0:
            print("❌ Docker build failed!")
            print("STDOUT:", p.stdout)
            print("STDERR:", p.stderr)
            raise BuildPushError(f"docker build failed:\nSTDOUT: {p.stdout}\nSTDERR: {p.stderr}")
        print("✅ docker build completed")

        # Check if Trivy scan should be skipped
        skip_trivy = os.getenv('SKIP_TRIVY_SCAN', 'false').lower() == 'true'
        if skip_trivy:
            print("ℹ️ Skipping Trivy scan (SKIP_TRIVY_SCAN=true)")
        else:
            print("🔎 Scanning image with Trivy...")
            scan_cmd = ["trivy", "image", "--severity", fail_on, "--exit-code", "1", f"{image_uri}"]
            result = subprocess.run(scan_cmd)
            if result.returncode != 0:
                print(f"❌ Vulnerabilities of severity {fail_on} found. Aborting push.")
                raise BuildPushError(f"Vulnerabilities of severity {fail_on} found. Aborting push.")
    
    return image_uri

def push_image(image_uri: str) -> None:
    print(f"🐳 Pushing image: {image_uri}")
    p = subprocess.run(["docker", "push", image_uri], check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise BuildPushError(f"docker push failed:\n{p.stderr}")
    print(f"✅ Image pushed: {image_uri}")
