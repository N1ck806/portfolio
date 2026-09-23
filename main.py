"""
main.py — портфолио-сайт на FastAPI.

Концепция:
    • Каждый проект живёт в templates/new_project/<slug>/index.html
    • index.html полностью автономен (все стили и скрипты внутри)
    • meta.yaml рядом (опционально) описывает карточку на главной
      и метаданные страницы проекта
    • Сайт сканирует templates/new_project/ на каждый запрос главной
    • Добавил папку с проектом → обновил главную → проект в списке

Запуск:
    pip install -r requirements.txt
    uvicorn main:app --reload
    либо
    python main.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ─────────────────────────────────────────────────────────────
#  Пути
# ─────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
PROJECTS_DIR  = TEMPLATES_DIR / "new_project"
STATIC_DIR    = BASE_DIR / "static"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# slug: латиница, цифры, дефис, подчёркивание. Точки и слэши запрещены.
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")

# Значения по умолчанию — согласованы с новой палитрой (тёплый ivory + бронза).
DEFAULT_ICON   = "◆"
DEFAULT_ACCENT = "#a67b3a"     # тёплый бронзовый (не используется напрямую в UI,
                                # но храним как «акцент проекта» на случай
                                # индивидуальных обложек/подсветки).
DEFAULT_ORDER  = 999
DEFAULT_LIMIT  = 6              # reserved: для будущей пагинации

# ─────────────────────────────────────────────────────────────
#  Приложение
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Khorezm Folio",
    description="Персональное портфолио студента: проекты, исследования, цифровые работы.",
    version="2.0.0",
    docs_url=None,       # отключаем публичный /docs
    redoc_url=None,      # и /redoc
    openapi_url=None,    # и /openapi.json
)

# Общая статика сайта (CSS/JS главной и обёртки)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Статика внутри проектов (картинки, шрифты, медиа рядом с index.html).
# Пример ссылки из проекта:
#   <img src="/project-assets/ancient-khorezm/img/palace.jpg">
app.mount(
    "/project-assets",
    StaticFiles(directory=PROJECTS_DIR),
    name="project-assets",
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Проверка на старте: обязательные шаблоны на месте
_REQUIRED_TEMPLATES = ("base.html", "index.html", "project.html")
_missing = [t for t in _REQUIRED_TEMPLATES if not (TEMPLATES_DIR / t).is_file()]
if _missing:
    raise RuntimeError(
        "❌ Не найдены обязательные шаблоны: "
        + ", ".join(_missing)
        + f"\n   Ожидаются в: {TEMPLATES_DIR}"
    )


# ─────────────────────────────────────────────────────────────
#  Парсинг meta.yaml без внешних зависимостей
# ─────────────────────────────────────────────────────────────
def _parse_scalar(raw: str) -> Any:
    """Простой YAML-скаляр: строка, число, bool, inline-список."""
    s = raw.strip()

    if s == "":
        return ""

    # inline-список [a, b, c]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]

    # булевы
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False

    # числа
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)

    # строка (снимаем обрамляющие кавычки, если есть)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _parse_yaml_simple(text: str) -> dict[str, Any]:
    """
    Очень маленький YAML-парсер — только верхний уровень:
        key: value
        key: [a, b, c]
        key: "строка"
        key:
          - a
          - b
    Комментарии (# в начале строки) поддерживаются.
    """
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # Элемент списка
        if stripped.startswith("- "):
            if current_list is None:
                current_list = []
                if current_key is not None:
                    data[current_key] = current_list
            current_list.append(_parse_scalar(stripped[2:]))
            continue

        # Новая пара key: value
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            current_key = key
            current_list = None

            if value == "":
                data[key] = ""
            else:
                data[key] = _parse_scalar(value)
            continue

    return data


def read_meta(project_dir: Path) -> dict[str, Any]:
    """Читает meta.yaml / meta.yml, если есть. Иначе — пустой словарь."""
    for name in ("meta.yaml", "meta.yml"):
        f = project_dir / name
        if not f.is_file():
            continue
        try:
            return _parse_yaml_simple(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ─────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────
def guess_title(slug: str) -> str:
    """my_first_project → My First Project"""
    cleaned = re.sub(r"[_\-]+", " ", slug).strip()
    return cleaned.title() or slug


def is_project_dir(path: Path) -> bool:
    """Папка считается проектом, если внутри есть index.html и имя валидно."""
    if not path.is_dir():
        return False
    if path.name.startswith((".", "_")):
        return False
    if not SLUG_RE.match(path.name):
        return False
    return (path / "index.html").is_file()


def _str(v: Any, default: str = "") -> str:
    """Приводим значение к строке, аккуратно обрабатывая None и числа."""
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip()
    return str(v)


def _tags(meta: dict[str, Any]) -> list[str]:
    raw = meta.get("tags", [])
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return []


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_project(slug: str, meta: dict[str, Any]) -> dict[str, Any]:
    """
    Единая точка формирования словаря проекта.
    Все поля, которые могут понадобиться шаблонам, собраны здесь.
    Значения из meta.yaml имеют приоритет; недостающие — дефолты.
    """
    return {
        # ── базовая карточка ────────────────────────────────
        "slug":         slug,
        "title":        _str(meta.get("title"))       or guess_title(slug),
        "description":  _str(meta.get("description")),
        "icon":         _str(meta.get("icon"))        or DEFAULT_ICON,
        "accent":       _str(meta.get("accent"))      or DEFAULT_ACCENT,
        "tags":         _tags(meta),
        "date":         _str(meta.get("date")),
        "order":        _int(meta.get("order"), DEFAULT_ORDER),

        # ── обложка / визуал ────────────────────────────────
        # если в meta.yaml задан cover — он будет использован на главной
        # и на странице проекта вместо дефолтной SVG-графики
        "cover":        _str(meta.get("cover")),

        # ── метаданные карточки / страницы проекта ──────────
        "category":     _str(meta.get("category")),
        "year":         _str(meta.get("year")),
        "role":         _str(meta.get("role")),
        "stack":        _str(meta.get("stack")),

        # ── страница проекта ────────────────────────────────
        "author":       _str(meta.get("author")),
        "group":        _str(meta.get("group")),
        "format":       _str(meta.get("format")),
        "format_note":  _str(meta.get("format_note")),
        "topic":        _str(meta.get("topic")),
        "period":       _str(meta.get("period")),

        # ── служебное ───────────────────────────────────────
        # первая карточка при выводе может стать крупной — если
        # projects|length >= 2 (см. шаблон)
        "featured":     bool(meta.get("featured", False)),
    }


# ─────────────────────────────────────────────────────────────
#  Сбор проектов
# ─────────────────────────────────────────────────────────────
def collect_projects() -> list[dict[str, Any]]:
    """Сканирует templates/new_project/ и возвращает список проектов."""
    if not PROJECTS_DIR.exists():
        return []

    projects: list[dict[str, Any]] = []

    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not is_project_dir(entry):
            continue
        meta = read_meta(entry)
        projects.append(_normalize_project(entry.name, meta))

    # сортировка: order → date (убыв.) → title
    # пустая дата трактуется как «самая старая», т.е. уходит в конец
    def sort_key(p: dict[str, Any]) -> tuple:
        order = p["order"]
        date = p["date"] or "0000-00-00"
        return (order, _neg_str(date), p["title"].lower())

    projects.sort(key=sort_key)
    return projects


def _neg_str(s: str) -> str:
    """
    Ключ-обёртка: строки сортируются по возрастанию, но для даты
    нам нужно «свежие сверху». Простой трюк: инвертируем символы.
    """
    # ограничим длину, чтобы ключ не разрастался
    s = s[:32]
    return "".join(chr(0x10FFFF - ord(c)) for c in s)


def find_project(slug: str) -> dict[str, Any] | None:
    for p in collect_projects():
        if p["slug"] == slug:
            return p
    return None


# ─────────────────────────────────────────────────────────────
#  Роуты
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, name="index")
async def index(request: Request) -> HTMLResponse:
    """Главная — архив работ."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"projects": collect_projects()},
    )


@app.get("/project/{slug}", response_class=HTMLResponse, name="project")
async def project(request: Request, slug: str) -> HTMLResponse:
    """Страница-обёртка проекта: hero + <iframe> с его index.html."""
    if not SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")

    project_dir = PROJECTS_DIR / slug
    if not is_project_dir(project_dir):
        raise HTTPException(status_code=404, detail="Проект не найден")

    meta = find_project(slug) or _normalize_project(slug, {})

    return templates.TemplateResponse(
        request,
        "project.html",
        {
            "project":      meta,
            "projects":     collect_projects(),
            "project_slug": slug,
        },
    )


@app.get("/project/{slug}/raw", response_class=HTMLResponse, name="project_raw")
async def project_raw(slug: str) -> HTMLResponse:
    """
    Отдаёт index.html проекта «как есть» — для iframe.
    Проект полностью автономен: свои <style> и <script> внутри.
    """
    if not SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")

    index_file = PROJECTS_DIR / slug / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="index.html не найден")

    try:
        html = index_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = index_file.read_text(encoding="utf-8", errors="replace")

    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


# ─────────────────────────────────────────────────────────────
#  Технические роуты
# ─────────────────────────────────────────────────────────────
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Тихий 204 — чтобы не спамить логами 404."""
    return Response(status_code=204)


@app.get("/robots.txt", response_class=Response, include_in_schema=False)
async def robots() -> Response:
    body = "User-agent: *\nAllow: /\n"
    return Response(content=body, media_type="text/plain")


# ─────────────────────────────────────────────────────────────
#  Диагностический роут
# ─────────────────────────────────────────────────────────────
@app.get("/_debug/projects", response_class=HTMLResponse, include_in_schema=False)
async def debug_projects() -> HTMLResponse:
    """Показывает, что сервер видит в templates/new_project/."""

    folder_rows: list[str] = []
    if PROJECTS_DIR.exists():
        for entry in sorted(PROJECTS_DIR.iterdir()):
            is_proj = "✓" if is_project_dir(entry) else "·"
            has_meta = "meta" if (entry / "meta.yaml").is_file() else "—"
            folder_rows.append(
                f"<tr><td>{is_proj}</td><td>{has_meta}</td>"
                f"<td>{entry.name}</td></tr>"
            )

    projects = collect_projects()
    proj_rows = "".join(
        f"<tr>"
        f"<td>{p['order']}</td>"
        f"<td>{p['icon']}</td>"
        f"<td>{p['title']}</td>"
        f"<td><code>{p['slug']}</code></td>"
        f"<td>{p['date'] or '—'}</td>"
        f"<td>{', '.join(p['tags']) or '—'}</td>"
        f"</tr>"
        for p in projects
    )

    html = f"""<!doctype html><html lang="ru"><head>
    <meta charset="utf-8"><title>debug · projects</title>
    <style>
      :root {{
        --bg: #f6f1e7;
        --ink: #1b1c1e;
        --ink-mute: #6b6d73;
        --ink-dim: #9a9ca3;
        --rule: rgba(27,28,30,.08);
        --bronze: #a67b3a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        background: var(--bg);
        color: var(--ink);
        font: 14px/1.55 'Inter', system-ui, -apple-system, sans-serif;
        padding: 48px clamp(20px, 4vw, 64px);
        margin: 0;
      }}
      h1 {{
        font-family: 'Cormorant Garamond', serif;
        font-weight: 400;
        font-size: 2rem;
        margin: 0 0 8px;
      }}
      h2 {{
        font-family: 'Cormorant Garamond', serif;
        font-weight: 400;
        font-size: 1.4rem;
        margin: 40px 0 12px;
      }}
      p  {{ color: var(--ink-mute); max-width: 72ch; }}
      code {{ font-family: 'JetBrains Mono', ui-monospace, monospace; color: var(--bronze); }}
      table {{
        border-collapse: collapse;
        margin: 12px 0 8px;
        width: 100%;
        max-width: 900px;
      }}
      td, th {{
        border-bottom: 1px solid var(--rule);
        padding: 10px 14px;
        text-align: left;
        font-size: .92rem;
      }}
      th {{
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: .7rem;
        letter-spacing: .18em;
        text-transform: uppercase;
        color: var(--ink-dim);
        font-weight: 500;
      }}
      td:first-child, th:first-child {{ padding-left: 0; }}
      tr:first-child th {{ border-bottom-color: rgba(27,28,30,.22); }}
    </style>
    </head><body>
      <h1>Debug · projects</h1>
      <p>Служебная страница. Показывает, что сервер видит в
         <code>templates/new_project/</code>, и как собирает карточки.</p>

      <h2>Папки</h2>
      <table>
        <thead><tr><th>project</th><th>meta</th><th>folder</th></tr></thead>
        <tbody>{''.join(folder_rows) or '<tr><td colspan="3">пусто</td></tr>'}</tbody>
      </table>

      <h2>Собранные проекты</h2>
      <table>
        <thead><tr>
          <th>order</th><th>icon</th><th>title</th>
          <th>slug</th><th>date</th><th>tags</th>
        </tr></thead>
        <tbody>{proj_rows or '<tr><td colspan="6">пусто</td></tr>'}</tbody>
      </table>

      <p>Сканируемая папка: <code>{PROJECTS_DIR}</code></p>
    </body></html>"""
    return HTMLResponse(html)


# ─────────────────────────────────────────────────────────────
#  Обработчики ошибок — спокойные, в духе сайта
# ─────────────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    html = f"""<!doctype html><html lang="ru"><head>
    <meta charset="utf-8"><title>404 · Khorezm Folio</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid; place-items: center;
        background: #f6f1e7;
        color: #1b1c1e;
        font-family: 'Inter', system-ui, sans-serif;
        padding: 32px;
      }}
      .wrap {{ max-width: 520px; text-align: center; }}
      .num {{
        font-family: 'Cormorant Garamond', serif;
        font-size: clamp(4rem, 12vw, 8rem);
        line-height: 1;
        color: #a67b3a;
        margin-bottom: 8px;
      }}
      h1 {{
        font-family: 'Cormorant Garamond', serif;
        font-weight: 400;
        font-size: 1.6rem;
        margin: 0 0 14px;
      }}
      p {{ color: #6b6d73; margin: 0 0 24px; }}
      a {{
        display: inline-block;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: .74rem;
        letter-spacing: .22em;
        text-transform: uppercase;
        color: #1b1c1e;
        text-decoration: none;
        border-bottom: 1px solid #1b1c1e;
        padding-bottom: 4px;
        transition: color .2s, border-color .2s;
      }}
      a:hover {{ color: #a67b3a; border-color: #a67b3a; }}
    </style></head><body>
      <div class="wrap">
        <div class="num">404</div>
        <h1>Страница не найдена</h1>
        <p>Возможно, проект был перемещён или ссылка устарела.</p>
        <a href="/">← Вернуться в архив</a>
      </div>
    </body></html>"""
    return HTMLResponse(html, status_code=404)


# ─────────────────────────────────────────────────────────────
#  Локальный запуск
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)