import sys
import time
import os
import subprocess
from pathlib import Path
import types
import re
from typing import Optional, Tuple, List
import shutil

# ------------------------------
# Python 3.12+ distutils 相容層
# ------------------------------
def _ensure_distutils_shim() -> None:
    """為 Python 3.12+ 準備 distutils 相容層（原生→setuptools→最小 stub）。"""
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

    # 最小 stub（提供 version.LooseVersion，滿足 uc 的匯入需求）
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
        sys.stderr.write(
            "未安裝 undetected-chromedriver，請先執行: pip install undetected-chromedriver\n"
        )
        sys.exit(1)

# Selenium 例外（用於偵測版本不符時的 fallback）
try:
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
except Exception:
    SessionNotCreatedException = type("SessionNotCreatedException", (Exception,), {})  # type: ignore
    WebDriverException = Exception  # type: ignore

# Windows registry
try:
    import winreg  # type: ignore
except Exception:
    winreg = None  # type: ignore


def main() -> None:
    driver = None
    try:
        base_dir = Path(__file__).resolve().parent
        user_dir = base_dir / "user" / "chrome-profile"
        user_dir.mkdir(parents=True, exist_ok=True)

        # 可選：啟動前清掉既有 Chrome 行程，避免 profile 被占用（不預設執行）
        if os.environ.get("KILL_CHROME", "").strip() in ("1", "true", "True"):
            _kill_running_chrome()

        # 先把 PATH 裡含 chromedriver 的目錄暫時移除，避免撿到錯版驅動
        removed_from_path = _strip_path_entries_with_chromedriver()
        if removed_from_path:
            print("[PATH] 已移除含 chromedriver 的目錄：")
            for d in removed_from_path:
                print("    -", d)

        # 清 uc 快取（避免沿用錯版）
        purged = _purge_uc_cache()
        if purged:
            print("[UC Cache] 已清除：")
            for p in purged:
                print("    -", p)

        # ===== 不執行 chrome.exe：改用登錄檔偵測版本與路徑 =====
        chrome_path = _detect_chrome_path_from_registry()
        chrome_major = _detect_chrome_major_from_registry()

        # options factory：每次都建立「新的」 ChromeOptions
        def options_factory() -> "uc.ChromeOptions":
            opts = uc.ChromeOptions()
            opts.add_argument(f"--user-data-dir={str(user_dir)}")     # 獨立資料夾
            opts.add_argument("--profile-directory=Default")
            opts.add_argument("--lang=zh-TW")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--disable-save-password-bubble")
            # 盡量避免顯示「擴充功能錯誤」徽章
            opts.add_argument("--disable-extensions")
            opts.add_argument("--disable-component-update")
            # 可選：無頭模式
            if os.environ.get("HEADLESS", "").strip() in ("1", "true", "True"):
                opts.add_argument("--headless=new")
            # 偏好設定
            opts.add_experimental_option(
                "prefs",
                {
                    "credentials_enable_service": False,
                    "profile.password_manager_enabled": False,
                    "intl.accept_languages": "zh-TW,zh",
                },
            )
            # 指定可執行檔（若登錄檔有抓到）
            if chrome_path:
                try:
                    opts.binary_location = str(chrome_path)
                except Exception:
                    pass
            return opts

        # 第一次嘗試（使用偵測到的主版號）
        driver = _try_launch_uc(options_factory, chrome_major)

        # 若第一次仍因版本不合失敗，再次清 cache 並重試一次
        if driver is None:
            print("[Retry] 偵測到可能的驅動版本不相容，重新清除快取並重試……")
            _purge_uc_cache()
            driver = _try_launch_uc(options_factory, chrome_major)

        if driver is None:
            raise RuntimeError("無法啟動 undetected-chromedriver：請確認已安裝 Google Chrome，或檢查防毒/權限設定。")

        # 防偵測腳本（最佳努力）
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

        # 開站 + 顯示版本資訊
        driver.get("https://kktix.com/events/akkrsd-01/registrations/new")
        try:
            caps = getattr(driver, "capabilities", {}) or {}
            browser_ver = caps.get("browserVersion") or caps.get("version")
            cd_ver = (caps.get("chrome", {}) or {}).get("chromedriverVersion") or caps.get("chromedriverVersion")
            if chrome_major is not None:
                print(f"已啟動 UC（偵測 Chrome 主版號 {chrome_major}）")
            else:
                print("已啟動 UC（未能偵測 Chrome 主版號，改用預設流程）")
            print("Browser version    =", browser_ver)
            print("ChromeDriver ver.  =", cd_ver)
        except Exception:
            pass

        print("使用者資料夾：", str(user_dir))
        print("10 秒後自動關閉……")
        time.sleep(10)

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _try_launch_uc(options_factory, chrome_major: Optional[int]):
    """
    每次呼叫都用 options_factory() 取一個「新的」 ChromeOptions。
    若拋出 'session not created' 且訊息包含版本不合，回傳 None 讓上層決定重試。
    """
    try:
        opts = options_factory()
        if chrome_major is not None:
            return uc.Chrome(options=opts, version_main=chrome_major)
        return uc.Chrome(options=opts)
    except SessionNotCreatedException as e:
        msg = str(e)
        if "only supports Chrome version" in msg or "Current browser version is" in msg:
            return None
        raise
    except WebDriverException as e:
        msg = str(e)
        if "only supports Chrome version" in msg or "Current browser version is" in msg:
            return None
        raise


# ------------------------------
# 清除 uc 快取與 PATH 汙染
# ------------------------------
def _purge_uc_cache() -> List[str]:
    """刪除 uc 可能使用的快取目錄，回傳實際刪除的路徑清單。"""
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
    """將目前行程的 PATH 中，含有 chromedriver(.exe) 的資料夾移除，回傳被移除的清單。"""
    path = os.environ.get("PATH", "")
    if not path:
        return []
    dirs = path.split(os.pathsep)
    kept: List[str] = []
    removed: List[str] = []
    for d in dirs:
        try:
            pd = Path(d)
            if pd.is_dir() and (pd / "chromedriver.exe").exists():
                removed.append(d)
            elif pd.is_dir() and (pd / "chromedriver").exists():
                removed.append(d)
            else:
                kept.append(d)
        except Exception:
            kept.append(d)
    os.environ["PATH"] = os.pathsep.join(kept)
    return removed


# ------------------------------
# Windows：不執行 chrome.exe 的偵測
# ------------------------------
def _detect_chrome_path_from_registry() -> Optional[Path]:
    """
    優先從登錄檔抓 Chrome 可執行檔路徑：
      HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe
    找不到再用常見安裝路徑嘗試存在性（不啟動）。
    """
    # 1) App Paths
    try:
        if winreg:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                try:
                    path, _ = winreg.QueryValueEx(k, None)  # (Default)
                    p = Path(path)
                    if p.exists():
                        return p
                except Exception:
                    pass
    except Exception:
        pass

    # 2) 常見安裝路徑（不執行，只檢查檔案是否存在）
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

    # 3) PATH 上的 chrome 路徑（只回傳檔案，不執行）
    chrome_on_path = _which("chrome")
    if chrome_on_path:
        p = Path(chrome_on_path)
        if p.exists():
            return p

    return None


def _detect_chrome_major_from_registry() -> Optional[int]:
    """
    從登錄檔 BLBeacon 讀 Chrome 版本：
      HKCU\Software\Google\Chrome\BLBeacon\version
      HKLM\Software\Google\Chrome\BLBeacon\version
    僅解析主版號，不執行 chrome.exe。
    """
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
    ]
    for hive, subkey in keys:
        try:
            if not winreg:
                break
            with winreg.OpenKey(hive, subkey) as k:
                ver, _ = winreg.QueryValueEx(k, "version")
                m = re.search(r"^(\d+)\.", str(ver))
                if m:
                    return int(m.group(1))
        except Exception:
            continue
    return None


def _which(cmd: str) -> Optional[str]:
    try:
        from shutil import which as _which_impl
    except Exception:
        return None
    return _which_impl(cmd)


def _kill_running_chrome() -> None:
    """可選：強制結束所有 chrome.exe，避免既有執行個體干擾。"""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
