import shutil
from pathlib import Path

from jinja2 import FileSystemLoader, Environment


def main() -> None:
    templates_dir = Path("frontend")

    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=True,
        auto_reload=False,
        enable_async=False,
    )
    template = env.get_template("index.jinja2")

    dist = Path("frontend-dist")
    dist.mkdir(parents=True, exist_ok=True)

    with open(dist / "index.html", "w") as f:
        f.write(template.render(
            app_type="MCSR Ranked",
            is_draftout=False,
        ))

    with open(dist / "draftout.html", "w") as f:
        f.write(template.render(
            app_type="Draftout",
            is_draftout=True,
        ))

    for file_to_copy in ("main.js", "faq.html", "robots.txt", "sitemap.xml"):
        shutil.copy(templates_dir / file_to_copy, dist / file_to_copy)


if __name__ == "__main__":
    main()
