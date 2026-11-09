"""让测试在任意目录下都能以包名 astrbot_plugin_mist_detective 导入插件，并用桩模块代替 AstrBot。"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PKG = Path(tempfile.gettempdir()) / "mist_detective_pkg"
PKG.mkdir(exist_ok=True)
link = PKG / "astrbot_plugin_mist_detective"
if not link.exists():
    os.symlink(ROOT, link, target_is_directory=True)
for p in (str(HERE / "stubs"), str(PKG), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
