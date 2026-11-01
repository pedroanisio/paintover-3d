"""The README's Python runs, in order, as one script: what a reader copies has to work."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_the_readme_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    blocks = re.findall(r"```python\n(.*?)```", (ROOT / "README.md").read_text(), re.S)
    assert len(blocks) >= 6
    scope = {"__name__": "readme"}
    sys.modules["readme"] = type(sys)("readme")  # a dataclass looks its module up while it is being made
    exec(compile("\n".join(blocks), "README.md", "exec"), scope)
    del sys.modules["readme"]
    assert sorted(path.name for path in (tmp_path / "renders").iterdir()) == [
        "flat-blocking.png", "flat-engraved.png", "flat-loft.png", "flat-notes.png", "flat-shaded.png", "flat-toon.png", "flat-wireframe.png"]
    assert "acme.crate" in scope["registry"].prefabs and "studio.sofa" in scope["other"].registry.prefabs
