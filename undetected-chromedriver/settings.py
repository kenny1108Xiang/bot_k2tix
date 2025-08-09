import os
import re
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, asdict
import json
import types
import tempfile
import atexit

# 全域變數用於保持 driver 實例
_global_driver_instance = None

# ------------------------------
# Python 3.12+ distutils 相容層
# ------------------------------
def _ensure_distutils_shim() -> None:
    try:
        import distutils.version  # type: ignore
        return
    except Exception:
        pass

    try:
        import setuptools._distutils as _du  # type: ignore
    except Exception:
        _du = None  # type: ignore

    if _du is not None:
        sys.modules.setdefault("distutils", _du)
        sys.modules.setdefault("distutils.version", _du.version)
        return

    # 最小 stub：提供 version.LooseVersion
    distutils_module = types.ModuleType("distutils")
    version_module = types.ModuleType("distutils.version")

    class LooseVersion:
        def __init__(self, vstring: str | int | float = "") -> None:
            self.vstring: str = str(vstring)
            self.version: list[object] = self.parse(self.vstring)

        @staticmethod
        def parse(vstring: str) -> list[object]:
            tokens = re.split(r"[\._-]+", vstring)
            parsed: list[object] = []
            for token in tokens:
                if not token:
                    continue
                if token.isdigit():
                    parsed.append(int(token))
                else:
                    parsed.append(token)
            return parsed

        def _compare(self, other: "LooseVersion | str | int | float") -> int:
            if not isinstance(other, LooseVersion):
                other = LooseVersion(other)
            a = list(self.version)
            b = list(other.version)
            max_len = max(len(a), len(b))
            a.extend([0] * (max_len - len(a)))
            b.extend([0] * (max_len - len(b)))
            for left, right in zip(a, b):
                if isinstance(left, int) and isinstance(right, int):
                    if left != right:
                        return -1 if left < right else 1
                else:
                    sl, sr = str(left), str(right)
                    if sl != sr:
                        return -1 if sl < sr else 1
            return 0

        def __lt__(self, other: object) -> bool:  # type: ignore[override]
            return self._compare(other) < 0  # type: ignore[arg-type]

        def __le__(self, other: object) -> bool:  # type: ignore[override]
            return self._compare(other) <= 0  # type: ignore[arg-type]

        def __eq__(self, other: object) -> bool:  # type: ignore[override]
            try:
                return self._compare(other) == 0  # type: ignore[arg-type]
            except Exception:
                return False

        def __ne__(self, other: object) -> bool:  # type: ignore[override]
            return not self.__eq__(other)

        def __gt__(self, other: object) -> bool:  # type: ignore[override]
            return self._compare(other) > 0  # type: ignore[arg-type]

        def __ge__(self, other: object) -> bool:  # type: ignore[override]
            return self._compare(other) >= 0  # type: ignore[arg-type]

        def __repr__(self) -> str:
            return f"LooseVersion({self.vstring!r})"

    version_module.LooseVersion = LooseVersion  # type: ignore[attr-defined]
    distutils_module.version = version_module  # type: ignore[attr-defined]
    sys.modules["distutils"] = distutils_module
    sys.modules["distutils.version"] = version_module


# ------------------------------
# 匯入 uc（缺 distutils 時自動補）
# ------------------------------
try:
    import undetected_chromedriver as uc
except ModuleNotFoundError as e:  # 可能是 Python 3.12+ 缺 distutils
    if getattr(e, "name", "") == "distutils":
        _ensure_distutils_shim()
        import undetected_chromedriver as uc  # type: ignore[no-redef]
    else:
        # 修正 PyInstaller 環境中 sys.stderr 為 None 的問題
        try:
            if sys.stderr:
                sys.stderr.write(
                    "未安裝 undetected-chromedriver，請先執行: pip install undetected-chromedriver\n"
                )
        except Exception:
            pass
        raise

# Selenium 例外（用於偵測版本不符時的 fallback）
try:
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
except Exception:
    SessionNotCreatedException = type("SessionNotCreatedException", (Exception,), {})  # type: ignore
    WebDriverException = Exception  # type: ignore


# ------------------------------
# Windows registry 與工具
# ------------------------------
try:
    import winreg  # type: ignore
except Exception:
    winreg = None  # type: ignore


def _which(cmd: str) -> Optional[str]:
    try:
        from shutil import which as _which_impl
    except Exception:
        return None
    return _which_impl(cmd)


def _purge_uc_cache() -> List[str]:
    candidates: List[Path] = []
    for env_key in ("LOCALAPPDATA", "TEMP", "TMP"):
        base = os.environ.get(env_key)
        if base:
            candidates.append(Path(base) / "undetected_chromedriver")
    candidates.append(Path.home() / ".cache" / "undetected_chromedriver")

    removed: List[str] = []
    for p in candidates:
        try:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                removed.append(str(p))
        except Exception:
            pass
    return removed


def _strip_path_entries_with_chromedriver() -> List[str]:
    path = os.environ.get("PATH", "")
    if not path:
        return []
    dirs = path.split(os.pathsep)
    kept: List[str] = []
    removed: List[str] = []
    for d in dirs:
        try:
            pd = Path(d)
            if pd.is_dir() and ((pd / "chromedriver.exe").exists() or (pd / "chromedriver").exists()):
                removed.append(d)
            else:
                kept.append(d)
        except Exception:
            kept.append(d)
    os.environ["PATH"] = os.pathsep.join(kept)
    return removed
def _prune_chrome_profile_cache(profile_dir: Path) -> List[str]:
    """刪除 Chrome 使用者資料夾內常見的快取目錄，避免資料夾無限成長。
    僅刪除非必要快取；歷史與 Cookies 等保留。
    """
    removed: List[str] = []
    cache_like_dirs = [
        "Cache",
        "Code Cache",
        "GPUCache",
        "ShaderCache",
        "GrShaderCache",
        "DawnCache",
        os.path.join("Service Worker", "CacheStorage"),
        "Media Cache",
        os.path.join("Default", "Cache"),
        os.path.join("Default", "Code Cache"),
        os.path.join("Default", "GPUCache"),
        os.path.join("Default", "Media Cache"),
        os.path.join("Default", "Service Worker", "CacheStorage"),
    ]
    for rel in cache_like_dirs:
        try:
            p = profile_dir / rel
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                removed.append(str(p))
        except Exception:
            # 忽略個別刪除錯誤
            pass
    return removed


def _detect_chrome_path_from_registry() -> Optional[Path]:
    # 1) App Paths
    try:
        if winreg:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            ) as k:
                try:
                    path, _ = winreg.QueryValueEx(k, None)
                    p = Path(path)
                    if p.exists():
                        return p
                except Exception:
                    pass
    except Exception:
        pass

    # 2) 常見安裝路徑
    for env_key, sub in (
        ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
        ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
    ):
        base = os.environ.get(env_key)
        if base:
            p = Path(base) / sub
            if p.exists():
                return p

    # 3) PATH
    chrome_on_path = _which("chrome")
    if chrome_on_path:
        p = Path(chrome_on_path)
        if p.exists():
            return p
    return None


def _detect_chrome_major_from_registry() -> Optional[int]:
    keys = [
        (getattr(winreg, "HKEY_CURRENT_USER", None), r"Software\Google\Chrome\BLBeacon"),
        (getattr(winreg, "HKEY_LOCAL_MACHINE", None), r"Software\Google\Chrome\BLBeacon"),
    ]
    for hive, subkey in keys:
        try:
            if not winreg or hive is None:
                break
            with winreg.OpenKey(hive, subkey) as k:
                ver, _ = winreg.QueryValueEx(k, "version")
                m = re.search(r"^(\d+)\.", str(ver))
                if m:
                    return int(m.group(1))
        except Exception:
            continue
    return None


def _kill_running_chrome() -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass


def _try_launch_uc(options_factory, chrome_major: Optional[int]):
    """嘗試啟動 UC。若偵測到版本不符或連線被重置等常見錯誤，回傳 None 讓上層重試。"""
    # 延伸可辨識為「可重試」的例外（例如 WinError 10054 連線被重置）
    retryable_error_substrings = (
        "only supports Chrome version",
        "Current browser version is",
        "ConnectionResetError",
        "WinError 10054",
        "Remote end closed connection",
        "Max retries exceeded",
        "Failed to establish a new connection",
        "RemoteDisconnected",
    )

    try:
        opts = options_factory()
        # 先嘗試使用偵測到的 major；若無則交給 UC 自動偵測
        if chrome_major is not None:
            return uc.Chrome(options=opts, version_main=chrome_major)
        return uc.Chrome(options=opts)
    except SessionNotCreatedException as e:
        msg = str(e)
        if any(x in msg for x in retryable_error_substrings):
            return None
        raise
    except WebDriverException as e:
        msg = str(e)
        if any(x in msg for x in retryable_error_substrings):
            return None
        raise
    except Exception as e:  # 捕捉底層 urllib3/http.client 的連線錯誤
        msg = str(e)
        if any(x in msg for x in retryable_error_substrings):
            return None
        raise


def prepare_driver() -> Tuple["uc.Chrome", Path, Optional[int]]:
    base_dir = _get_app_root()  # kktix 專案根

    profile_dir_env = os.environ.get("PROFILE_DIR", "").strip()
    profile_mode = os.environ.get("PROFILE_MODE", "persist").strip().lower()

    if profile_dir_env:
        user_dir = Path(profile_dir_env).expanduser().resolve()
    elif profile_mode == "temp":
        user_dir = Path(tempfile.mkdtemp(prefix="uc-profile-"))
    else:
        user_dir = (base_dir / "undetected-chromedriver" / "user" / "chrome-profile").resolve()

    user_dir.mkdir(parents=True, exist_ok=True)

    # 程序結束時清理策略
    def _on_exit_cleanup() -> None:
        try:
            # 先修剪快取，避免下次啟動前資料爆量
            _prune_chrome_profile_cache(user_dir)
        except Exception:
            pass
        # 臨時模式：嘗試刪除整個 profile
        if profile_mode == "temp":
            try:
                shutil.rmtree(user_dir, ignore_errors=True)
            except Exception:
                pass

    atexit.register(_on_exit_cleanup)
    
    # 用於儲存 driver 實例，防止被垃圾回收
    global _global_driver_instance

    if os.environ.get("KILL_CHROME", "").strip() in ("1", "true", "True"):
        _kill_running_chrome()

    _strip_path_entries_with_chromedriver()
    _purge_uc_cache()

    chrome_path = _detect_chrome_path_from_registry()
    chrome_major = _detect_chrome_major_from_registry()

    def options_factory() -> "uc.ChromeOptions":
        opts = uc.ChromeOptions()
        opts.add_argument(f"--user-data-dir={str(user_dir)}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--lang=zh-TW")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--disable-save-password-bubble")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-component-update")
        # 降低背景節流與被遮蔽視窗的計時不準
        opts.add_argument("--disable-background-timer-throttling")
        opts.add_argument("--disable-renderer-backgrounding")
        opts.add_argument("--disable-backgrounding-occluded-windows")
        opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
        # 確保 Chrome 進程獨立運行，不會因為父進程結束而關閉
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        # 減少磁碟快取
        opts.add_argument("--disk-cache-size=0")
        opts.add_argument("--media-cache-size=0")
        opts.add_argument("--disable-gpu-shader-disk-cache")
        opts.add_argument("--aggressive-cache-discard")
        if os.environ.get("HEADLESS", "").strip() in ("1", "true", "True"):
            opts.add_argument("--headless=new")
        # 設定頁面載入策略：eager（DOM 載完就行，不等資源）
        opts.page_load_strategy = 'eager'
        opts.add_experimental_option(
            "prefs",
            {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "intl.accept_languages": "zh-TW,zh",
            },
        )
        # 注意：detach 選項在較新版本的 Chrome 中不被支援，已移除
        
        if chrome_path:
            try:
                opts.binary_location = str(chrome_path)
            except Exception:
                pass
        return opts

    # 1st：用偵測到的 major（若有）
    # 啟動前可選擇清理快取：CLEAN_PROFILE_CACHE=1
    if os.environ.get("CLEAN_PROFILE_CACHE", "").strip() in ("1", "true", "True"):
        _prune_chrome_profile_cache(user_dir)

    driver = _try_launch_uc(options_factory, chrome_major)
    if driver is None:
        # 小睡讓本機 port 釋放、避免緊湊重試
        try:
            import time as _t
            _t.sleep(0.6)
        except Exception:
            pass
    # 2nd：清空 UC 快取後再嘗試一次（仍以偵測到的 major）
    if driver is None:
        _purge_uc_cache()
        driver = _try_launch_uc(options_factory, chrome_major)
    if driver is None:
        try:
            import time as _t
            _t.sleep(0.6)
        except Exception:
            pass
    # 3rd：若仍失敗，改用 UC 自動偵測（忽略偵測到的 major）
    if driver is None:
        driver = _try_launch_uc(options_factory, None)
    if driver is None:
        try:
            import time as _t
            _t.sleep(0.6)
        except Exception:
            pass
    # 4th：最後再清一次快取後以自動偵測嘗試
    if driver is None:
        _purge_uc_cache()
        driver = _try_launch_uc(options_factory, None)
    if driver is None:
        raise RuntimeError("無法啟動 undetected-chromedriver：請確認已安裝 Google Chrome，或檢查防毒/權限設定。")

    # 反自動化注入（最佳努力）
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    "window.chrome = window.chrome || { runtime: {} };"
                    "Object.defineProperty(navigator, 'languages', {get: () => ['zh-TW','zh']});"
                    "Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});"
                )
            },
        )
    except Exception:
        pass

    # 將 driver 儲存到全域變數，防止被垃圾回收導致 Chrome 關閉
    _global_driver_instance = driver
    
    return driver, user_dir, chrome_major


# ------------------------------
# 讀取 WinUI 產生的 UserConfig.json
# ------------------------------
@dataclass
class UserData:
    Username: str = ""
    Password: str = ""
    TicketName1: str = ""
    TicketName2: str = ""
    TicketPrice: str = ""
    TicketQuantity: str = ""
    TicketUrl: str = ""
    IsAutoAllocation: bool = True
    IsAutoPayment: bool = False
    SaleTime: str = ""


def _get_app_root() -> Path:
    """
    回傳『專案根目錄（kktix）』，無論是 .py 或打包後的 .exe。
    - exe:   .../undetected-chromedriver/dist/py-bot/py-bot.exe → 上上上層 = kktix
    - source:.../kktix/undetected-chromedriver/settings.py      → 上一層 = kktix
    """
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir.parent.parent.parent
    else:
        return Path(__file__).resolve().parent.parent


def _resolve_winui_user_config_path() -> Path:
    # 允許以環境變數覆寫（免改碼、免重打包）
    env = os.environ.get("USER_CONFIG", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    root = _get_app_root()  # 專案根 kktix
    rel = (
        root / "WinUi-3" / "bin" / "x64" / "Debug"
             / "net8.0-windows10.0.19041.0" / "win-x64" / "AppX" / "UserConfig.json"
    )
    return rel.resolve()


def load_user_data() -> Tuple[UserData, Dict[str, Any]]:
    path = _resolve_winui_user_config_path()
    
    # 記錄設定檔路徑資訊
    try:
        from main import write_error_log
        write_error_log(f"嘗試讀取設定檔: {path}", "INFO")
        write_error_log(f"設定檔是否存在: {path.exists()}", "INFO")
    except ImportError:
        pass
    
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
            data = UserData(
                Username=str(raw.get("Username", "")),
                Password=str(raw.get("Password", "")),
                TicketName1=str(raw.get("TicketName1", "")),
                TicketName2=str(raw.get("TicketName2", "")),
                TicketPrice=str(raw.get("TicketPrice", "")),
                TicketQuantity=str(raw.get("TicketQuantity", "")),
                TicketUrl=str(raw.get("TicketUrl", "")),
                IsAutoAllocation=bool(raw.get("IsAutoAllocation", True)),
                IsAutoPayment=bool(raw.get("IsAutoPayment", False)),
                SaleTime=str(raw.get("SaleTime", "")),
            )
            
            try:
                from main import write_error_log
                write_error_log("設定檔讀取成功", "INFO")
                write_error_log(f"票券URL: {data.TicketUrl}", "INFO")
                write_error_log(f"開售時間: {data.SaleTime}", "INFO")
            except ImportError:
                pass
            
            return data, asdict(data)
    except Exception as e:
        try:
            from main import write_error_log
            import traceback
            error_msg = f"讀取設定檔失敗: {str(e)}\n{traceback.format_exc()}"
            write_error_log(error_msg, "ERROR")
        except ImportError:
            pass
        
        empty = UserData()
        return empty, asdict(empty)


# 模組載入時即初始化，確保在開啟 driver 前記憶體已有使用者資料
USER_DATA_OBJ, USER_DATA = load_user_data()

