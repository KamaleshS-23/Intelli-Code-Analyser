import os
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

# backend/ must be on sys.path so flat imports (scanner.*, debt_analyzer.*) resolve
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth.deps import extract_token, optional_user, require_user
from auth.service import (
    get_scan_history_item,
    list_login_history,
    list_scan_history,
    login_user,
    logout_user,
    register_user,
    save_scan_history,
)
from ai_assistant.config import get_ai_settings
from ai_assistant.context_builder import build_project_context
from ai_assistant.orchestrator import AIChatOrchestrator
from debt_analyzer.comparison import compare_debt_reports
from reports.comparison_report import generate_comparison_report
from refactor.optimization_service import OptimizationService
from scanner.scanner_service import ScannerService
from scanner.stack_detector import detect_stack
from stacks import STACK_PROFILES, normalize_stack as normalize_stack_id


SUPPORTED_STACKS = list(STACK_PROFILES)


def normalize_stack(stack_value):
    try:
        return normalize_stack_id(stack_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class AuthRequest(BaseModel):
    email: str
    password: str


class AIChatRequest(BaseModel):
    project_id: str | None = None
    scan_id: str | None = None
    conversation_id: str | None = None
    message: str
    context: dict | None = None


class RefactorGenerateRequest(BaseModel):
    project_path: str = Field(min_length=1)
    baseline_scan: dict
    issue_keys: list[str] | None = None
    select_all: bool = False
    stack: str = "java"
    max_issues: int = Field(default=20, ge=0)


class CompareReportsRequest(BaseModel):
    baseline_debt_report: dict
    current_debt_report: dict


class ComparisonReportRequest(BaseModel):
    baseline_scan: dict
    optimized_scan: dict
    comparison: dict
    optimization_meta: dict


app = FastAPI(
    title="AI Technical Debt Agent API",
    description="API for scanning Java projects and calculating technical debt metrics",
    version="1.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
scanner_service = ScannerService()
ai_orchestrator = AIChatOrchestrator()

# Find the absolute path of backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BACKEND_DIR / "static"
UPLOAD_TEMP_DIR = BACKEND_DIR / "scanner" / "uploads" / "temp"
UPLOAD_WORKDIR = BACKEND_DIR / "scanner" / "uploads" / "workdir"

# Create directories if they do not exist
STATIC_DIR.mkdir(exist_ok=True)
UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_WORKDIR.mkdir(parents=True, exist_ok=True)


def _persist_scan(user, result, source: str):
    if not user:
        return
    try:
        save_scan_history(user, result, source)
    except Exception:
        pass


@app.get("/api/health")
def health():
    mongo_ok = True
    mongo_error = None
    try:
        from db.mongo import ping

        ping()
    except Exception as exc:
        mongo_ok = False
        mongo_error = str(exc)
    return {"ok": True, "mongodb": mongo_ok, "mongodb_error": mongo_error}


@app.post("/api/auth/register")
def api_register(payload: AuthRequest):
    try:
        return register_user(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/auth/login")
def api_login(payload: AuthRequest):
    try:
        return login_user(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/auth/logout")
def api_logout(authorization: Optional[str] = Header(default=None)):
    logout_user(extract_token(authorization))
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(user=Depends(require_user)):
    return {
        "id": str(user["_id"]),
        "email": user["email"],
    }


@app.get("/api/history")
def api_history(user=Depends(require_user)):
    return {
        "logins": list_login_history(user),
        "scans": list_scan_history(user),
    }


@app.get("/api/history/scans/{item_id}")
def api_history_item(item_id: str, user=Depends(require_user)):
    item = get_scan_history_item(user, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found.")
    return item


@app.get("/api/stacks")
def api_stacks():
    return {
        "supported": SUPPORTED_STACKS,
        "options": [
            {
                "id": stack_id,
                "label": profile["label"],
                "description": profile["description"],
                "languages": profile["languages"],
            }
            for stack_id, profile in STACK_PROFILES.items()
        ],
        "default": "java",
    }


@app.get("/api/sample")
def scan_sample(
    stack: str = Query("java"),
    user=Depends(optional_user),
):
    """Scans a pre-packaged project for the chosen stack."""
    stack_name = normalize_stack(stack)
    sample_dir_name = {
        "java": "SampleProject",
        "python": "SamplePythonProject",
        "web": "SampleWebProject",
        "django": "SampleDjangoProject",
        "nodejs": "SampleNodeProject",
    }[stack_name]
    sample_path = BACKEND_DIR / "scanner" / "uploads" / sample_dir_name
    if not sample_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Sample project not found at {sample_path}"
        )

    try:
        stack_name = detect_stack(str(sample_path))
        result = scanner_service.scan(
            str(sample_path), save_output=True, stack=stack_name
        )
        result["stack"] = stack_name
        ai_orchestrator.register_scan(result)
        _persist_scan(user, result, "sample")
        return result
    except (ValueError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan-path")
def scan_path(
    path: str = Query(..., description="Absolute path to the project directory to scan"),
    stack: str = Query("java"),
    user=Depends(optional_user),
):
    """Scans a local directory on the server."""
    target_path = Path(path)
    if not target_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"The specified path is not a project directory: {path}"
        )

    normalize_stack(stack)
    try:
        stack_name = detect_stack(str(target_path))
        result = scanner_service.scan(
            str(target_path), save_output=True, stack=stack_name
        )
        result["stack"] = stack_name
        ai_orchestrator.register_scan(result)
        _persist_scan(user, result, "path")
        return result
    except (ValueError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan-upload")
async def scan_upload(
    file: UploadFile = File(..., description="ZIP archive of the project"),
    stack: str = Form("java"),
    user=Depends(optional_user),
):
    """
    Upload a project ZIP file, extract it, scan it, and clean up.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP file uploads are supported."
        )

    normalize_stack(stack)
    temp_extract_dir = Path(tempfile.mkdtemp(dir=str(UPLOAD_TEMP_DIR)))
    temp_zip_path = temp_extract_dir / file.filename
    workdir_path = None

    try:
        with open(temp_zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        temp_zip_path.unlink()

        scan_target = temp_extract_dir
        subdirs = [d for d in temp_extract_dir.iterdir() if d.is_dir()]

        if len(subdirs) == 1 and not any(f.is_file() for f in temp_extract_dir.iterdir()):
            scan_target = subdirs[0]

        stack_name = detect_stack(str(scan_target))
        workdir_path = UPLOAD_WORKDIR / uuid.uuid4().hex
        shutil.copytree(scan_target, workdir_path)

        result = scanner_service.scan(
            str(workdir_path), save_output=True, stack=stack_name
        )
        ai_orchestrator.register_scan(result)
        _persist_scan(user, result, "upload")
        return {
            **result,
            "workdir_path": str(workdir_path.resolve()),
            "stack": stack_name,
        }

    except (ValueError, NotADirectoryError) as exc:
        if workdir_path and workdir_path.exists():
            shutil.rmtree(workdir_path, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        if workdir_path and workdir_path.exists():
            shutil.rmtree(workdir_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        try:
            shutil.rmtree(temp_extract_dir)
        except Exception:
            pass


@app.post("/api/refactor/generate")
def api_generate_optimized_project(
    payload: RefactorGenerateRequest,
    user=Depends(optional_user),
):
    del user
    stack_name = normalize_stack(payload.stack)
    if stack_name not in {"java", "python", "web", "django", "nodejs"}:
        raise HTTPException(status_code=400, detail="Unsupported refactoring stack.")

    baseline_debt_report = payload.baseline_scan.get("debt_report")
    if not isinstance(baseline_debt_report, dict):
        raise HTTPException(
            status_code=400,
            detail="baseline_scan must include a debt_report object.",
        )
    if not isinstance(baseline_debt_report.get("issues"), list):
        raise HTTPException(
            status_code=400,
            detail="baseline_scan.debt_report must include an issues list.",
        )

    project_dir = Path(payload.project_path)
    if not project_dir.is_dir():
        raise HTTPException(status_code=400, detail="project_path must be a directory.")

    try:
        result = OptimizationService().generate_optimized_project(
            baseline_scan=payload.baseline_scan,
            project_path=str(project_dir),
            issue_keys=payload.issue_keys,
            stack=stack_name,
            max_issues=payload.max_issues,
            select_all=payload.select_all,
        )
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Optimized project generation failed: {exc}",
        ) from exc

    download_path = Path(result["download_zip_path"])
    result["download_filename"] = download_path.name
    result["download_url"] = (
        f"/api/refactor/download?file={quote(download_path.name)}"
    )
    return result


@app.get("/api/refactor/download")
def api_download_optimized_project(file: str = Query(..., min_length=1)):
    optimized_root = (
        BACKEND_DIR / "scanner" / "output" / "optimized"
    ).resolve()
    candidate = (optimized_root / file).resolve()
    try:
        candidate.relative_to(optimized_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid download path.") from exc

    if candidate.suffix.lower() != ".zip" or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Optimized ZIP file not found.")
    return FileResponse(
        path=candidate,
        media_type="application/zip",
        filename=candidate.name,
    )


@app.post("/api/compare/reports")
def api_compare_debt_reports(payload: CompareReportsRequest):
    return compare_debt_reports(
        payload.baseline_debt_report,
        payload.current_debt_report,
    )


@app.post("/api/report/comparison")
def api_comparison_report(payload: ComparisonReportRequest):
    try:
        report_path = generate_comparison_report(
            payload.baseline_scan,
            payload.optimized_scan,
            payload.comparison,
            payload.optimization_meta,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Comparison report could not be generated: {exc}",
        ) from exc
    return FileResponse(
        path=report_path,
        media_type="application/pdf",
        filename=report_path.name,
    )


@app.get("/api/ai/config")
def ai_config():
    settings = get_ai_settings()
    return {
        "provider": settings.provider,
        "model": settings.model,
        "enabled": settings.is_enabled,
        "status": "configured" if settings.is_enabled else "missing-api-key",
        "code_generation_provider": settings.code_generation_provider,
        "code_generation_model": (
            settings.gemini_model
            if settings.code_generation_provider == "gemini"
            else settings.model
        ),
        "code_generation_enabled": (
            bool(settings.gemini_api_key)
            if settings.code_generation_provider == "gemini"
            else settings.is_enabled
        ),
    }


@app.get("/api/ai/context")
def ai_context():
    context = build_project_context(ai_orchestrator.latest_scan)
    return context


@app.post("/api/ai/chat")
def ai_chat(payload: AIChatRequest):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    scan_result = ai_orchestrator._choose_scan(payload.project_id, payload.scan_id)
    if not scan_result:
        raise HTTPException(
            status_code=400,
            detail="No project scan is available yet. Run a scan before using the AI assistant.",
        )

    try:
        return ai_orchestrator.chat(scan_result, payload.message.strip(), payload.context or {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI provider request failed: {exc}",
        ) from exc


class AIValidationRequest(BaseModel):
    code: str
    class_name: Optional[str] = None


@app.post("/api/ai/validate")
def ai_validate(payload: AIValidationRequest):
    """
    Feature 5: Validate Java code syntax and AST integrity.
    """
    from ai_assistant.tools import validate_java_code
    result = validate_java_code(payload.code)
    return result


@app.get("/")
def read_root():
    """
    Serves the main application page.
    """
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return {"message": "Welcome to AI Technical Debt Agent. Frontend not created yet."}
    return FileResponse(index_file)


# Mount static assets directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
