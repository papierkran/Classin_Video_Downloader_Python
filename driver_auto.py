import os
import sys
import subprocess


def _get_base_dir():
    """获取程序所在目录，兼容 PyInstaller 打包后的 exe"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def which(cmd: str):
    """跨平台 which。Windows 下也尽量工作。"""
    try:
        if os.name == 'nt':
            p = subprocess.run(["where", cmd], capture_output=True, text=True)
            out = (p.stdout or "").strip().splitlines()
            return out[0].strip() if out else None
        p = subprocess.run(["bash", "-lc", f"command -v {cmd}"], capture_output=True, text=True)
        out = (p.stdout or "").strip()
        return out if out else None
    except Exception:
        return None


def _windows_candidate_paths():
    pf = os.environ.get('ProgramFiles', r'C:\\Program Files')
    pfx86 = os.environ.get('ProgramFiles(x86)', r'C:\\Program Files (x86)')
    lad = os.environ.get('LocalAppData')

    edge = [
        os.path.join(pfx86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(pf, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    if lad:
        edge.append(os.path.join(lad, 'Microsoft', 'Edge', 'Application', 'msedge.exe'))

    chrome = [
        os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(pfx86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]
    if lad:
        chrome.append(os.path.join(lad, 'Google', 'Chrome', 'Application', 'chrome.exe'))

    return edge, chrome


def detect_browser_preference():
    """返回 (browser, binary_path)；browser in {'edge','chrome'}。

    Windows：优先用常见安装路径，其次 where。
    Linux/macOS：用 command -v。
    """
    if os.name == 'nt':
        edge_paths, chrome_paths = _windows_candidate_paths()
        for p in edge_paths:
            if p and os.path.exists(p):
                return 'edge', p
        for p in chrome_paths:
            if p and os.path.exists(p):
                return 'chrome', p

        # fallback: where
        for c in ('msedge', 'microsoft-edge', 'msedge.exe'):
            p = which(c)
            if p:
                return 'edge', p
        for c in ('chrome', 'google-chrome', 'chrome.exe'):
            p = which(c)
            if p:
                return 'chrome', p
        return None, None

    # 非 Windows：优先 Edge，再 Chrome
    for c in ("microsoft-edge", "microsoft-edge-stable"):
        p = which(c)
        if p:
            return "edge", p
    for c in ("google-chrome", "chromium-browser", "chromium"):
        p = which(c)
        if p:
            return "chrome", p
    return None, None


def _copy_to_program_dir(src_path: str, program_dir: str, dest_name: str):
    """把下载出来的 driver 复制到程序目录（exe 同级），便于 PyInstaller 场景使用。"""
    import shutil

    if not src_path or not os.path.exists(src_path):
        return src_path
    os.makedirs(program_dir, exist_ok=True)
    dest = os.path.join(program_dir, dest_name)
    try:
        shutil.copy2(src_path, dest)
        # 确保可执行
        try:
            os.chmod(dest, 0o755)
        except Exception:
            pass
        return dest
    except Exception:
        # 复制失败则退回原路径
        return src_path


def ensure_driver(browser: str, base_dir: str = None):
    """自动下载匹配 driver 到 base_dir，并尽量复制一份到程序目录返回。

    目的：Windows + PyInstaller 下，driver 固定落在 exe 同级，方便可视化获取 cookie。
    """
    base_dir = base_dir or _get_base_dir()
    os.makedirs(base_dir, exist_ok=True)

    if browser == "edge":
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
        src = EdgeChromiumDriverManager(path=base_dir).install()
        # Windows 固定叫 msedgedriver.exe；非 Windows 也用 msedgedriver
        dest_name = 'msedgedriver.exe' if os.name == 'nt' else 'msedgedriver'
        return _copy_to_program_dir(src, base_dir, dest_name)

    if browser == "chrome":
        from webdriver_manager.chrome import ChromeDriverManager
        src = ChromeDriverManager(path=base_dir).install()
        dest_name = 'chromedriver.exe' if os.name == 'nt' else 'chromedriver'
        return _copy_to_program_dir(src, base_dir, dest_name)

    raise ValueError(f"Unsupported browser: {browser}")


def create_webdriver(browser: str, driver_path: str, headless: bool = False, binary_path: str = None):
    """创建 Selenium WebDriver。"""
    if browser == "edge":
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service

        options = webdriver.EdgeOptions()
        if binary_path:
            options.binary_location = binary_path
        if headless:
            try:
                options.add_argument('--headless=new')
            except Exception:
                options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1280,720')

        service = Service(executable_path=driver_path)
        return webdriver.Edge(service=service, options=options)

    if browser == "chrome":
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service

        options = webdriver.ChromeOptions()
        if binary_path:
            options.binary_location = binary_path
        if headless:
            # Chrome headless
            try:
                options.add_argument('--headless=new')
            except Exception:
                options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1280,720')

        service = Service(executable_path=driver_path)
        return webdriver.Chrome(service=service, options=options)

    raise ValueError(f"Unsupported browser: {browser}")
