from pathlib import Path
import tempfile
class Context: pass
class Star:
    def __init__(self, context): self.context = context; self._kv = {}
    async def get_kv_data(self, k, d): return self._kv.get(k, d)
    async def put_kv_data(self, k, v): self._kv[k] = v
class StarTools:
    @staticmethod
    def get_data_dir(name): return Path(tempfile.mkdtemp()) / name
def register(*a, **k):
    def deco(cls): return cls
    return deco

async def _html_render(self, tmpl, data, return_url=True, options=None, umo=None):
    from jinja2 import Template
    html = Template(tmpl).render(**data)
    p = tempfile.mktemp(suffix=".html")
    open(p, "w").write(html)
    self.rendered = getattr(self, "rendered", []) + [p]
    return p
Star.html_render = _html_render
