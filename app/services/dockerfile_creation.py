import pandas as pd
import os
import json
from typing import Dict, List, Optional


class CopyInstruction:
    def __init__(self, src: str, dest: str, from_stage: Optional[str] = None):
        self.src = src
        self.dest = dest
        self.from_stage = from_stage

    def to_docker(self) -> str:
        if self.from_stage:
            return f"COPY --from={self.from_stage} {self.src} {self.dest}"
        return f"COPY {self.src} {self.dest}"


class AddInstruction:
    def __init__(self, src: str, dest: str, chown: Optional[str] = None):
        self.src = src
        self.dest = dest
        self.chown = chown

    def to_docker(self) -> str:
        if self.chown:
            return f"ADD --chown={self.chown} {self.src} {self.dest}"
        return f"ADD {self.src} {self.dest}"


class DockerfileStage:
    def __init__(
        self,
        name: Optional[str],
        base_image: str,
        workdir: Optional[str] = None,
        add: Optional[List[AddInstruction]] = None,
        copy: Optional[List[CopyInstruction]] = None,
        run_commands: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        args: Optional[Dict[str, str]] = None,
        expose_ports: Optional[List[int]] = None,
        entrypoint: Optional[List[str]] = None,
        cmd: Optional[List[str]] = None,
        label_pairs: Optional[Dict[str, str]] = None,
        maintainer: Optional[str] = None,
        onbuild_cmd: Optional[str] = None,
        shell: Optional[List[str]] = None,
        stopsignal: Optional[str] = None,
        user: Optional[str] = None,
        volume_dirs: Optional[List[str]] = None,
        healthcheck: Optional[str] = None,
    ):
        self.name = name
        self.base_image = base_image
        self.workdir = workdir
        self.add = add or []
        self.copy = copy or []
        self.run_commands = run_commands or []
        self.env_vars = env_vars or {}
        self.args = args or {}
        self.expose_ports = expose_ports or []
        self.entrypoint = entrypoint
        self.cmd = cmd
        self.label_pairs = label_pairs or {}
        self.maintainer = maintainer
        self.onbuild_cmd = onbuild_cmd
        self.shell = shell
        self.stopsignal = stopsignal
        self.user = user
        self.volume_dirs = volume_dirs or []
        self.healthcheck = healthcheck


# def validate_and_fix_stage_config(stage: DockerfileStage) -> DockerfileStage:
#     """
#     Validate and fix common configuration issues in Dockerfile stages
#     """
#     base_image = stage.base_image.lower()
    
#     # Check for nginx + Python conflicts
#     if 'nginx' in base_image:
#         # If using nginx but trying to run Python, suggest fixes
#         has_python_commands = False
#         python_indicators = ['pip install', 'python', 'pip3', 'requirements.txt']
        
#         # Check RUN commands
#         for cmd in stage.run_commands:
#             if any(indicator in cmd.lower() for indicator in python_indicators):
#                 has_python_commands = True
#                 break
        
#         # Check ENTRYPOINT/CMD for Python
#         if stage.entrypoint and any('python' in str(ep).lower() for ep in stage.entrypoint):
#             has_python_commands = True
#         if stage.cmd and any('python' in str(c).lower() for c in stage.cmd):
#             has_python_commands = True
            
#         if has_python_commands:
#             print(f"⚠️  WARNING: Detected nginx base image with Python commands for {stage.name or 'stage'}")
#             print("   Automatically fixing: switching to python:3.9-slim base image")
#             stage.base_image = "python:3.9-slim"
            
#     # Check for Python base images that don't have requirements.txt handling
#     elif 'python' in base_image:
#         # Ensure we have proper Python setup if requirements.txt is mentioned
#         has_requirements = any('requirements.txt' in cmd for cmd in stage.run_commands)
#         if has_requirements:
#             # Make sure we copy requirements.txt first
#             requirements_copied = any('requirements.txt' in copy.src for copy in stage.copy)
#             if not requirements_copied:
#                 print(f"⚠️  Adding COPY requirements.txt for {stage.name or 'stage'}")
#                 stage.copy.insert(0, CopyInstruction("requirements.txt", "requirements.txt"))
    
#     # Check for common port exposure issues
#     if stage.expose_ports:
#         # If running a Python web app, make sure it's configured properly
#         if 'python' in base_image.lower() and stage.cmd:
#             # Add WORKDIR if not specified for Python apps
#             if not stage.workdir:
#                 stage.workdir = "/app"
#                 print(f"⚠️  Adding WORKDIR /app for Python application")
    
#     return stage


def generate_dockerfile(stages: List[DockerfileStage]) -> str:
    lines = []

    for stage in stages:
        # Validate and fix configuration issues
        # stage = validate_and_fix_stage_config(stage)
        
        # FROM
        if stage.name:
            lines.append(f"FROM {stage.base_image} AS {stage.name}")
        else:
            lines.append(f"FROM {stage.base_image}")

        # MAINTAINER
        if stage.maintainer:
            lines.append(f"MAINTAINER {stage.maintainer}")

        # LABEL
        for k, v in stage.label_pairs.items():
            lines.append(f'LABEL {k}="{v}"')

        # ARG
        for k, v in stage.args.items():
            lines.append(f"ARG {k}={v}")

        # ENV
        for k, v in stage.env_vars.items():
            lines.append(f"ENV {k}={v}")

        # WORKDIR
        if stage.workdir:
            lines.append(f"WORKDIR {stage.workdir}")

        # ADD
        for add_inst in stage.add:
            lines.append(add_inst.to_docker())

        # COPY
        for copy_inst in stage.copy:
            lines.append(copy_inst.to_docker())

        # RUN
        for cmd in stage.run_commands:
            lines.append(f"RUN {cmd}")

        # ONBUILD
        if stage.onbuild_cmd:
            lines.append(f"ONBUILD {stage.onbuild_cmd}")

        # SHELL
        if stage.shell:
            shell_str = ",".join(f'"{s}"' for s in stage.shell)
            lines.append(f"SHELL [{shell_str}]")

        # STOPSIGNAL
        if stage.stopsignal:
            lines.append(f"STOPSIGNAL {stage.stopsignal}")

        # USER
        if stage.user:
            lines.append(f"USER {stage.user}")

        # VOLUME
        for v in stage.volume_dirs:
            lines.append(f'VOLUME ["{v}"]')

        # EXPOSE
        for port in stage.expose_ports:
            lines.append(f"EXPOSE {port}")

        # HEALTHCHECK
        if stage.healthcheck:
            lines.append(f"HEALTHCHECK {stage.healthcheck}")

        # ENTRYPOINT
        if stage.entrypoint:
            entry_str = ",".join(f'"{e}"' for e in stage.entrypoint)
            lines.append(f"ENTRYPOINT [{entry_str}]")

        # CMD
        if stage.cmd:
            cmd_str = ",".join(f'"{c}"' for c in stage.cmd)
            lines.append(f"CMD [{cmd_str}]")

        lines.append("")  # spacing between stages

    return "\n".join(lines).strip()


def parse_key_value_pairs(cell: Optional[str], sep=";") -> Dict[str, str]:
    if not cell or str(cell).strip() == "":
        return {}
    result = {}
    for kv in str(cell).split(sep):
        if "=" in kv:
            k, v = kv.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def load_configs_from_excel(file_path: str) -> Dict[str, List[DockerfileStage]]:
    df = pd.read_excel(file_path)
    # Replace NaN values with empty strings
    df = df.fillna('')
    app_configs: Dict[str, List[DockerfileStage]] = {}

    for _, row in df.iterrows():
        app_name = str(row["app_name"])
        stage_name = row.get("stage_name", None)

        # ADD (JSON list)
        add_instructions = []
        if str(row.get("add_files", "")).strip() != "":
            try:
                add_list = json.loads(str(row["add_files"]))
                for a in add_list:
                    add_instructions.append(
                        AddInstruction(
                            src=a["src"],
                            dest=a["dest"],
                            chown=a.get("chown"),
                        )
                    )
            except Exception:
                pass

        # COPY (JSON list)
        copy_instructions = []
        if str(row.get("copy_pairs", "")).strip() != "":
            try:
                copy_list = json.loads(str(row["copy_pairs"]))
                for c in copy_list:
                    copy_instructions.append(
                        CopyInstruction(
                            src=c["src"],
                            dest=c["dest"],
                            from_stage=c.get("from"),
                        )
                    )
            except Exception:
                pass

        # RUN
        run_cmds = []
        if str(row.get("run_commands", "")).strip() != "":
            run_cmds = [cmd.strip() for cmd in str(row["run_commands"]).split(";") if cmd.strip()]

        # ENV
        env_vars = parse_key_value_pairs(row.get("env_vars", ""), sep=";")

        # ARG
        args = parse_key_value_pairs(row.get("args", ""), sep=";")

        # LABEL
        label_pairs = parse_key_value_pairs(row.get("label_pairs", ""), sep=";")

        # Ports
        expose_ports = []
        if str(row.get("expose_ports", "")).strip() != "":
            expose_ports = [int(float(p.strip())) for p in str(row["expose_ports"]).replace(",", ";").split(";") if p.strip()]

        # Entrypoint & CMD
        entrypoint = str(row["entrypoint"]).split() if str(row.get("entrypoint", "")).strip() != "" else None
        cmd = str(row["cmd"]).split() if str(row.get("cmd", "")).strip() != "" else None

        # Shell
        shell = None
        if str(row.get("shell", "")).strip() != "":
            try:
                shell = json.loads(str(row["shell"]))
            except Exception:
                shell = str(row["shell"]).split()

        # Volumes
        volume_dirs = []
        if str(row.get("volume_dirs", "")).strip() != "":
            volume_dirs = [v.strip() for v in str(row["volume_dirs"]).replace(",", ";").split(";") if v.strip()]

        stage = DockerfileStage(
            name=stage_name,
            base_image=str(row["base_image"]),
            workdir=row.get("workdir"),
            add=add_instructions,
            copy=copy_instructions,
            run_commands=run_cmds,
            env_vars=env_vars,
            args=args,
            expose_ports=expose_ports,
            entrypoint=entrypoint,
            cmd=cmd,
            label_pairs=label_pairs,
            maintainer=row.get("maintainer"),
            onbuild_cmd=row.get("onbuild_cmd"),
            shell=shell,
            stopsignal=row.get("stopsignal"),
            user=row.get("user"),
            volume_dirs=volume_dirs,
            healthcheck=row.get("healthcheck"),
        )

        if app_name not in app_configs:
            app_configs[app_name] = []
        app_configs[app_name].append(stage)

    return app_configs


def create_dockerfiles_for_all_apps(excel_path: str, output_dir: str) -> None:
    app_configs = load_configs_from_excel(excel_path)
    for app_name, stages in app_configs.items():
        dockerfile_content = generate_dockerfile(stages)
        folder = os.path.join(output_dir, app_name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "Dockerfile"), "w") as f:
            f.write(dockerfile_content)
        print(f"✅ Dockerfile generated for {app_name} at {folder}/Dockerfile")
