import os
import sys
import platform
import subprocess
from pathlib import Path
import shutil
import json

OS_NAME = platform.system()
IS_WINDOWS = OS_NAME == "Windows"

SERVER_FILES = {
    "app.py": """
        from flask_restful import Resource
        from config import app, db, api
        from models import User

        class Users(Resource):
            def get(self):
                return [u.to_dict() for u in User.query.all()], 200

        api.add_resource(Users, "/users")

        if __name__ == "__main__":
            app.run(port=5555, debug=True)
""",
    "config.py": """
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from flask_migrate import Migrate
        from flask_cors import CORS
        from flask_restful import Api

        app = Flask(__name__)

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.secret_key = "dev-secret-key"

        db = SQLAlchemy(app)
        migrate = Migrate(app, db)
        api = Api(app)

        CORS(app)
""",
    "models.py": """
        from sqlalchemy_serializer import SerializerMixin
        from config import db

        class User(db.Model, SerializerMixin):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String, nullable=False)
""",
    "seed.py": """
        from config import app, db
        from models import User

        with app.app_context():
            User.query.delete()
            user = User(name="Example User")
            db.session.add(user)
            db.session.commit()
""",
    "requirements.txt": """
        flask
        flask-restful
        sqlalchemy
        flask-sqlalchemy
        flask-cors
        flask-migrate
        sqlalchemy-serializer
        python-dotenv
        pymysql
"""
}

def info(msg: str):
    print(f"[INFO] {msg}")

def warn(msg: str):
    print(f"[WARN] {msg}")

def fail(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)

def require(cmd: str, display_name: str = None):
    if shutil.which(cmd) is None:
        fail(f"Required tool not found on PATH: {display_name or cmd}")

def run(args, cwd=None, env=None, allow_fail=False):
    if isinstance(args, str):
        fail("run() expects a list of args, not a string.")
    info(f"Running: {' '.join(args)}")
    try:
        subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            check=True
        )
        return 0
    except subprocess.CalledProcessError as e:
        if allow_fail:
            warn(f"Command failed (allowed): exit {e.returncode}")
            return e.returncode
        fail(f"Command failed with exit code {e.returncode}: {' '.join(args)}")

def write_file(path: Path, content: str, overwrite: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    path.write_text(content, encoding="utf-8")
    return True

def venv_paths(root: Path):
    venv_dir = root / ".venv"
    if IS_WINDOWS:
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
    return venv_dir, py, pip

def ensure_root_package_json(root: Path):
    """
    Optional: creates a root package.json with dev scripts to run client+server.
    Only created if missing.
    """
    pkg = root / "package.json"
    if pkg.exists():
        return

    data = {
        "name": root.name,
        "private": True,
        "version": "0.1.0",
        "scripts": {
            "dev": "concurrently \"npm run dev --prefix client\" \"python server/app.py\"",
            "dev:server": "python server/app.py",
            "dev:client": "npm run dev --prefix client"
        },
        "devDependencies": {
            "concurrently": "^9.0.0"
        }
    }
    pkg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    info("Created root package.json (optional monorepo runner).")

def main():
    if len(sys.argv) < 2:
        fail("Usage: python scaffold.py <project_dir> [--force] [--root-npm]")

    project_dir = Path(sys.argv[1]).resolve()
    force = "--force" in sys.argv
    root_npm = "--root-npm" in sys.argv

    info(f"Detected OS: {OS_NAME}")
    info(f"Using Python: {sys.executable}")

    # Tool checks
    require("node", "Node.js")
    require("npm", "npm")

    # Create root
    project_dir.mkdir(parents=True, exist_ok=True)
    server_dir = project_dir / "server"
    client_dir = project_dir / "client"
    server_dir.mkdir(parents=True, exist_ok=True)

    # Write server files (skip unless --force)
    info("Writing server template files")
    for filename, content in SERVER_FILES.items():
        created = write_file(server_dir / filename, content, overwrite=force)
        if created:
            info(f"  wrote {server_dir / filename}")
        else:
            info(f"  kept  {server_dir / filename}")

    # Misc files
    write_file(project_dir / "README.md", f"# {project_dir.name}\n", overwrite=False)
    write_file(
        project_dir / ".gitignore",
        "__pycache__/\n.env\n.venv/\nclient/node_modules/\nserver/__pycache__/\n",
        overwrite=False
    )

    # Optional root package.json
    if root_npm:
        ensure_root_package_json(project_dir)
        # Ensure its devDependencies are installed (safe to rerun)
        run(["npm", "install"], cwd=project_dir)

    # Client scaffolding with Vite (skip if already exists)
    if (client_dir / "package.json").exists():
        info("Client already exists (client/package.json found). Skipping client scaffold.")
    else:
        info("Creating React client with Vite")
        # npm create vite@latest client -- --template react
        run(["npm", "create", "--yes", "vite@latest", "client", "--", "--template", "react", "--no-interactive", "--no-immediate"], cwd=project_dir)
        run(["npm", "install"], cwd=client_dir)



    # Root venv
    venv_dir, venv_py, venv_pip = venv_paths(project_dir)
    if venv_dir.exists() and venv_py.exists():
        info("Root venv already exists. Skipping venv creation.")
    else:
        info("Creating root virtual environment (.venv)")
        run([sys.executable, "-m", "venv", str(venv_dir)], cwd=project_dir)

    if not venv_py.exists():
        fail(f"Venv python not found at: {venv_py}")

    # Install python deps into root venv
    info("Installing Python dependencies into root venv")
    run([str(venv_pip), "install", "--upgrade", "pip"], cwd=project_dir)
    run([str(venv_pip), "install", "-r", str(server_dir / "requirements.txt")], cwd=project_dir)

    # Flask-Migrate init/migrate/upgrade
    # Use venv python to run flask commands and set cwd=server so imports resolve.
    env = os.environ.copy()
    env["FLASK_APP"] = "app"  # server/app.py has `app` variable

    migrations_dir = server_dir / "migrations"
    if not migrations_dir.exists():
        info("Initializing migrations (flask db init)")
        run([str(venv_py), "-m", "flask", "db", "init"], cwd=server_dir, env=env)
    else:
        info("Migrations already initialized (server/migrations exists).")

    info("Creating migration (flask db migrate) and upgrading (flask db upgrade)")
    # migrate may legitimately produce "No changes..." and still exit 0; allow_fail not needed.
    run([str(venv_py), "-m", "flask", "db", "migrate", "-m", "Auto migration"], cwd=server_dir, env=env, allow_fail=True)
    run([str(venv_py), "-m", "flask", "db", "upgrade"], cwd=server_dir, env=env)

    info("✅ Scaffold complete.")
    info(f"Project location: {project_dir}")
    info("Next steps:")
    print(f"  - Server:  {venv_py} server/app.py")
    print(f"  - Client:  cd client && npm run dev")
    if root_npm:
        print(f"  - Both:    npm run dev  (from project root)")

if __name__ == "__main__":
    main()
