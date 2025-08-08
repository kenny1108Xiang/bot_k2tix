import sys
import time


def _ensure_distutils_shim() -> None:
    """為 Python 3.12+ 嘗試以 setuptools._distutils 提供 distutils 相容層。"""
    try:
        import distutils.version  # type: ignore
        return
    except Exception:
        pass

    try:
        import setuptools._distutils as _du  # type: ignore
    except Exception:
        return

    sys.modules.setdefault("distutils", _du)
    sys.modules.setdefault("distutils.version", _du.version)


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


def main() -> None:
    driver = None
    try:
        # 啟動瀏覽器（預設非無頭）
        driver = uc.Chrome()
        driver.get("about:blank")
        print("已啟動 undetected-chromedriver。10 秒後自動關閉……")
        time.sleep(10)
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    main()

