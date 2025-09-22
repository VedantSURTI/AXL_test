"""
Files router for handling file operations (viewing Dockerfiles, downloading files)
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
import os
import shutil
from typing import Dict, List, Optional
from datetime import datetime, timedelta

router = APIRouter()

OUTPUT_DIR = "output"

@router.get("/dockerfile/{app_name}")
async def get_dockerfile(app_name: str):
    """Get Dockerfile content for a specific app"""
    try:
        dockerfile_path = os.path.join(OUTPUT_DIR, app_name, "Dockerfile")
        
        if not os.path.exists(dockerfile_path):
            raise HTTPException(status_code=404, detail=f"Dockerfile not found for {app_name}")
        
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        
        return PlainTextResponse(content, media_type="text/plain")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading Dockerfile: {str(e)}")

@router.get("/files/{app_name}")
async def list_app_files(app_name: str):
    """List all files in an app's directory"""
    try:
        app_path = os.path.join(OUTPUT_DIR, app_name)
        
        if not os.path.exists(app_path):
            raise HTTPException(status_code=404, detail=f"App directory not found: {app_name}")
        
        files = []
        for item in os.listdir(app_path):
            item_path = os.path.join(app_path, item)
            files.append({
                "name": item,
                "is_directory": os.path.isdir(item_path),
                "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
            })
        
        return {
            "app_name": app_name,
            "files": files,
            "total_files": len(files)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@router.get("/download/{app_name}/{filename}")
async def download_file(app_name: str, filename: str):
    """Download a specific file from an app's directory"""
    try:
        file_path = os.path.join(OUTPUT_DIR, app_name, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        
        return FileResponse(
            file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

@router.delete("/app/{app_name}")
async def delete_app(app_name: str):
    """Delete an app and all its files"""
    try:
        app_path = os.path.join(OUTPUT_DIR, app_name)
        
        if not os.path.exists(app_path):
            raise HTTPException(status_code=404, detail=f"App not found: {app_name}")
        
        import shutil
        shutil.rmtree(app_path)
        
        return {"message": f"App {app_name} deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting app: {str(e)}")

@router.get("/apps")
async def list_all_apps():
    """List all generated apps"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {"apps": [], "total": 0}
        
        apps = []
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                # Get basic info about the app
                dockerfile_path = os.path.join(item_path, "Dockerfile")
                has_dockerfile = os.path.exists(dockerfile_path)
                
                app_info = {
                    "name": item,
                    "has_dockerfile": has_dockerfile,
                    "path": item_path
                }
                
                if has_dockerfile:
                    # Try to get basic info from Dockerfile
                    try:
                        with open(dockerfile_path, 'r') as f:
                            dockerfile_content = f.read()
                            lines = dockerfile_content.split('\n')
                            
                            base_image = None
                            exposed_ports = []
                            
                            for line in lines:
                                line = line.strip()
                                if line.startswith('FROM '):
                                    base_image = line.replace('FROM ', '')
                                elif line.startswith('EXPOSE '):
                                    port = line.replace('EXPOSE ', '')
                                    exposed_ports.append(port)
                            
                            app_info["base_image"] = base_image
                            app_info["exposed_ports"] = exposed_ports
                            
                    except Exception as e:
                        app_info["dockerfile_error"] = str(e)
                
                apps.append(app_info)
        
        return {
            "apps": apps,
            "total": len(apps)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing apps: {str(e)}")

@router.delete("/cleanup")
async def cleanup_all():
    """Delete all generated apps and files"""
    try:
        # Clean output directory
        if os.path.exists(OUTPUT_DIR):
            import shutil
            shutil.rmtree(OUTPUT_DIR)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        return {"message": "All apps and files cleaned up successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")

@router.delete("/cleanup/old")
async def cleanup_old_files(days: int = Query(default=7, description="Delete files older than this many days")):
    """Delete apps and files older than specified days"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {"message": "Output directory doesn't exist", "deleted_apps": []}
        
        cutoff_time = datetime.now() - timedelta(days=days)
        deleted_apps = []
        total_size_freed = 0
        
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                # Check modification time
                mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                if mod_time < cutoff_time:
                    # Calculate size before deletion
                    size = get_directory_size(item_path)
                    total_size_freed += size
                    
                    # Delete the directory
                    shutil.rmtree(item_path)
                    deleted_apps.append({
                        "name": item,
                        "last_modified": mod_time.isoformat(),
                        "size_mb": round(size / (1024 * 1024), 2)
                    })
        
        return {
            "message": f"Cleaned up {len(deleted_apps)} apps older than {days} days",
            "deleted_apps": deleted_apps,
            "total_size_freed_mb": round(total_size_freed / (1024 * 1024), 2)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")

@router.delete("/cleanup/empty")
async def cleanup_empty_directories():
    """Delete empty app directories"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {"message": "Output directory doesn't exist", "deleted_apps": []}
        
        deleted_apps = []
        
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                # Check if directory is empty or contains only hidden files
                contents = [f for f in os.listdir(item_path) if not f.startswith('.')]
                if len(contents) == 0:
                    shutil.rmtree(item_path)
                    deleted_apps.append(item)
        
        return {
            "message": f"Cleaned up {len(deleted_apps)} empty directories",
            "deleted_apps": deleted_apps
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")

@router.delete("/cleanup/invalid")
async def cleanup_invalid_apps():
    """Delete app directories that don't have valid Dockerfiles"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {"message": "Output directory doesn't exist", "deleted_apps": []}
        
        deleted_apps = []
        
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                dockerfile_path = os.path.join(item_path, "Dockerfile")
                
                is_invalid = False
                reason = ""
                
                if not os.path.exists(dockerfile_path):
                    is_invalid = True
                    reason = "No Dockerfile found"
                else:
                    # Check if Dockerfile is valid (has FROM instruction)
                    try:
                        with open(dockerfile_path, 'r') as f:
                            content = f.read().strip()
                            if not content:
                                is_invalid = True
                                reason = "Empty Dockerfile"
                            elif "FROM " not in content.upper():
                                is_invalid = True
                                reason = "No FROM instruction in Dockerfile"
                    except Exception as e:
                        is_invalid = True
                        reason = f"Error reading Dockerfile: {str(e)}"
                
                if is_invalid:
                    shutil.rmtree(item_path)
                    deleted_apps.append({
                        "name": item,
                        "reason": reason
                    })
        
        return {
            "message": f"Cleaned up {len(deleted_apps)} invalid app directories",
            "deleted_apps": deleted_apps
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")

@router.get("/cleanup/preview")
async def preview_cleanup(
    days: Optional[int] = Query(default=None, description="Preview files older than this many days"),
    show_empty: bool = Query(default=False, description="Show empty directories"),
    show_invalid: bool = Query(default=False, description="Show invalid app directories")
):
    """Preview what would be cleaned up without actually deleting"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {"message": "Output directory doesn't exist", "apps": []}
        
        preview_apps = []
        total_size = 0
        
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                app_info = {
                    "name": item,
                    "path": item_path,
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat(),
                    "size_mb": 0,
                    "will_be_deleted": False,
                    "reasons": []
                }
                
                # Calculate size
                size = get_directory_size(item_path)
                app_info["size_mb"] = round(size / (1024 * 1024), 2)
                
                # Check age
                if days is not None:
                    cutoff_time = datetime.now() - timedelta(days=days)
                    mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                    if mod_time < cutoff_time:
                        app_info["will_be_deleted"] = True
                        app_info["reasons"].append(f"Older than {days} days")
                
                # Check if empty
                if show_empty:
                    contents = [f for f in os.listdir(item_path) if not f.startswith('.')]
                    if len(contents) == 0:
                        app_info["will_be_deleted"] = True
                        app_info["reasons"].append("Empty directory")
                
                # Check if invalid
                if show_invalid:
                    dockerfile_path = os.path.join(item_path, "Dockerfile")
                    if not os.path.exists(dockerfile_path):
                        app_info["will_be_deleted"] = True
                        app_info["reasons"].append("No Dockerfile found")
                    else:
                        try:
                            with open(dockerfile_path, 'r') as f:
                                content = f.read().strip()
                                if not content:
                                    app_info["will_be_deleted"] = True
                                    app_info["reasons"].append("Empty Dockerfile")
                                elif "FROM " not in content.upper():
                                    app_info["will_be_deleted"] = True
                                    app_info["reasons"].append("No FROM instruction in Dockerfile")
                        except Exception as e:
                            app_info["will_be_deleted"] = True
                            app_info["reasons"].append(f"Error reading Dockerfile: {str(e)}")
                
                if app_info["will_be_deleted"]:
                    total_size += size
                
                preview_apps.append(app_info)
        
        apps_to_delete = [app for app in preview_apps if app["will_be_deleted"]]
        
        return {
            "preview": True,
            "total_apps": len(preview_apps),
            "apps_to_delete": len(apps_to_delete),
            "total_size_to_free_mb": round(total_size / (1024 * 1024), 2),
            "apps": preview_apps
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during preview: {str(e)}")

def get_directory_size(path: str) -> int:
    """Calculate the total size of a directory in bytes"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
    except Exception:
        pass
    return total_size

@router.get("/storage/summary")
async def get_storage_summary():
    """Get comprehensive storage usage summary"""
    try:
        if not os.path.exists(OUTPUT_DIR):
            return {
                "output_directory_exists": False,
                "total_apps": 0,
                "total_size_mb": 0,
                "apps": []
            }
        
        apps = []
        total_size = 0
        dockerfile_count = 0
        empty_dirs = 0
        invalid_apps = 0
        
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                app_size = get_directory_size(item_path)
                total_size += app_size
                
                dockerfile_path = os.path.join(item_path, "Dockerfile")
                has_dockerfile = os.path.exists(dockerfile_path)
                
                # Check if empty
                contents = [f for f in os.listdir(item_path) if not f.startswith('.')]
                is_empty = len(contents) == 0
                
                # Check if invalid
                is_invalid = False
                if not has_dockerfile:
                    is_invalid = True
                elif has_dockerfile:
                    try:
                        with open(dockerfile_path, 'r') as f:
                            content = f.read().strip()
                            if not content or "FROM " not in content.upper():
                                is_invalid = True
                    except Exception:
                        is_invalid = True
                
                if has_dockerfile and not is_invalid:
                    dockerfile_count += 1
                if is_empty:
                    empty_dirs += 1
                if is_invalid:
                    invalid_apps += 1
                
                apps.append({
                    "name": item,
                    "size_mb": round(app_size / (1024 * 1024), 2),
                    "has_dockerfile": has_dockerfile,
                    "is_empty": is_empty,
                    "is_invalid": is_invalid,
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat(),
                    "file_count": len(contents)
                })
        
        return {
            "output_directory_exists": True,
            "total_apps": len(apps),
            "valid_apps": dockerfile_count,
            "empty_directories": empty_dirs,
            "invalid_apps": invalid_apps,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cleanup_recommendations": {
                "can_cleanup_empty": empty_dirs > 0,
                "can_cleanup_invalid": invalid_apps > 0,
                "total_cleanable_items": empty_dirs + invalid_apps
            },
            "apps": sorted(apps, key=lambda x: x["last_modified"], reverse=True)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting storage summary: {str(e)}")
