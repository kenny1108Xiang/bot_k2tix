from __future__ import annotations
from typing import Optional, Dict, Any
import datetime as _dt
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import time as _time
from js_scripts import get_presearch_script, get_refresh_timer_script, get_refresh_timer_script_for_cdp, get_autofill_script

try:
    import numpy as _np  # type: ignore
except Exception:
    _np = None  # type: ignore


# --- 小工具：檢查元素是否可見（不靠 Selenium EC，直接用 JS 更精準） ---
def _is_el_visible(driver, el) -> bool:
    """以 JS 判斷元素是否真的可見。"""
    try:
        return bool(driver.execute_script(
            """
            const e = arguments[0];
            if (!e) return false;
            const s = window.getComputedStyle(e);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = e.getBoundingClientRect();
            return (r.width > 0 && r.height > 0);
            """,
            el
        ))
    except Exception:
        return False


# --- 找到並回傳「立刻成為 KKTIX 會員」的 guest modal（且必須可見），否則回 None ---
def _find_visible_guest_modal(driver):
    """找 guest modal 且必須可見。"""
    try:
        return driver.execute_script(
            """
            const modals = document.querySelectorAll('.modal.ng-isolate-scope, .modal.ng-scope');
            for (const m of modals) {
                const body = m.querySelector('.modal-body');
                if (!body) continue;
                const text = (body.textContent || '').toLowerCase();
                if (text.includes('立刻成為') || text.includes('kktix 會員') || text.includes('會員登入') || text.includes('sign in')) {
                    const cs = window.getComputedStyle(m);
                    if (cs.display !== 'none' && cs.visibility !== 'hidden') {
                        const rect = m.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return m;
                        }
                    }
                }
            }
            return null;
            """
        )
    except Exception:
        return None


# --- 以「是否出現 guest modal」作為【未登入】判斷 ---
def is_signed_in_by_guest_modal(driver) -> bool:
    """
    若頁面出現了 guest modal（且可見），代表【未登入】，回傳 False。
    若沒有 guest modal，代表【已登入】或【無須登入】，回傳 True。
    """
    return _find_visible_guest_modal(driver) is None


# --- 在 guest modal 裡，點擊「登入」的 <a>，然後結束（不做刷新、不做後續） ---
def click_login_in_guest_modal(driver, wait_after_click_seconds: int = 5) -> bool:
    """
    在 guest modal 裡找「登入」連結並點擊。
    回傳 True = 成功點擊；False = 沒找到或失敗。
    """
    modal = _find_visible_guest_modal(driver)
    if not modal:
        return False

    try:
        # 在 modal 裡找「登入」連結
        login_link = modal.find_element(By.XPATH, ".//a[contains(text(), '登入')]")
        if _is_el_visible(driver, login_link):
            login_link.click()
            _time.sleep(wait_after_click_seconds)
            return True
    except Exception:
        pass
    return False


# --- 等待文件 readyState 至少為 interactive ---
def _wait_document_ready(driver, timeout_seconds: float = 10.0) -> None:
    """等待頁面至少載入到 interactive 狀態。"""
    try:
        WebDriverWait(driver, timeout_seconds).until(
            lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"]
        )
    except Exception:
        pass


# --- 以 numpy 模擬打字速度（含相對抖動） ---
def _type_with_numpy(element, text: str, cps_min: float = 14.1, cps_max: float = 18.5) -> None:
    """使用 numpy 模擬人類打字速度（含相對抖動）。"""
    if not _np:
        element.send_keys(text)
        return

    try:
        element.clear()
        for char in text:
            element.send_keys(char)
            
            # 基礎延遲
            cps = _np.random.uniform(cps_min, cps_max)
            base_delay = 1.0 / cps
            
            # 相對抖動：±10% 的基礎延遲
            jitter = _np.random.uniform(-0.1, 0.1) * base_delay
            delay = max(0.01, base_delay + jitter)
            
            _time.sleep(delay)
            
            # 5% 機率微停頓（50-150ms）
            if _np.random.random() < 0.05:
                _time.sleep(_np.random.uniform(0.05, 0.15))
    except Exception:
        element.send_keys(text)


# --- 判斷是否在登入頁面 ---
def _is_login_page(driver) -> bool:
    """檢查當前是否在登入頁面。"""
    try:
        current_url = str(driver.current_url or "").lower()
        if "/users/sign_in" in current_url or "/login" in current_url:
            return True
        # 也可以檢查是否有登入表單
        form = driver.find_element(By.ID, "new_user")
        return form is not None
    except Exception:
        return False


# --- 解析 ISO8601 時間字串 ---
def _parse_sale_time_iso8601(sale_time_str: str) -> Optional[int]:
    """將 ISO8601 時間字串轉換為毫秒時間戳。"""
    if not sale_time_str:
        return None
    try:
        dt_obj = _dt.datetime.fromisoformat(sale_time_str.replace("Z", "+00:00"))
        return int(dt_obj.timestamp() * 1000)
    except Exception:
        return None


# --- 預先搜尋目標票券 ---
def _presearch_target(driver, user_data) -> None:
    """預先快取目標票券資訊，使用實際 DOM 結構的選擇器。

    儲存到 localStorage.kk_presearch：
      {
        want: { name1, name2, seatText, priceInt, qty },
        selectors: { ... },
        hint: { index, unitId },
        armed: true
      }
    """
    import time
    
    # 參數提取
    name1 = str((user_data or {}).get("TicketName1", "") or "").strip()
    name2 = str((user_data or {}).get("TicketName2", "") or "").strip()
    price = str((user_data or {}).get("TicketPrice", "") or "").strip()
    qty = str((user_data or {}).get("TicketQuantity", "1") or "1").strip()
    is_auto = bool((user_data or {}).get("IsAutoAllocation", True))
    
    # 執行預搜尋腳本
    driver.execute_script(get_presearch_script(), name1, name2, price, qty, is_auto)
    
    # 結果驗證
    try:
        result = driver.execute_script("return localStorage.getItem('kk_presearch');")
        if result:
            import json
            result_obj = json.loads(result)
            matched = result_obj.get('hint', {}).get('index', -1) >= 0
    except Exception as e:
        pass


# --- 極簡入口：與 main.py 簽名相容，只使用上面兩個工具 ---
def run_flow(driver: WebDriver, user_data: Dict[str, Any], user_dir, chrome_major: Optional[int]) -> None:
    """
    正確流程：
    1) 進入 target_url
    2) 檢查登入狀態
    3) 如果未登入，進行登入流程，登入後會自動回到原始 URL
    4) 登入完成後，才注入腳本並開始搶票流程
    """
    # 1) 先進入 target_url
    target_url = str((user_data or {}).get("TicketUrl", "") or "").strip()
    if target_url:
        try:
            driver.get(target_url)
            _wait_document_ready(driver, 10)
            _time.sleep(1)
        except Exception:
            pass

    # 2) 判斷是否登入（用 guest modal）
    is_signed_in = is_signed_in_by_guest_modal(driver)
    
    if not is_signed_in:
        # 未登入：點擊 modal 裡的「登入」連結
        click_login_in_guest_modal(driver, wait_after_click_seconds=3)
        
        # 3) 等待登入頁面載入，填寫帳密
        try:
            # 等待登入表單出現
            wait = WebDriverWait(driver, 10)
            login_input = wait.until(lambda d: d.find_element(By.ID, "user_login"))
            password_input = driver.find_element(By.ID, "user_password")
            
            # 填寫帳號密碼
            username = str((user_data or {}).get("Username", "") or "").strip()
            password = str((user_data or {}).get("Password", "") or "").strip()
            
            if username and password:
                _type_with_numpy(login_input, username)
                _time.sleep(0.5)
                _type_with_numpy(password_input, password)
                _time.sleep(0.5)
                
                # 找到並點擊登入按鈕
                try:
                    submit_btn = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"][value="登入"]')
                    submit_btn.click()
                    
                    # 等待登入完成並自動跳轉回原始 URL
                    _time.sleep(5)  # 給足夠時間讓頁面跳轉
                    _wait_document_ready(driver, 10)
                    
                except Exception as e:
                    # 備用：用表單提交
                    password_input.submit()
                    _time.sleep(5)
                    _wait_document_ready(driver, 10)
                    
        except Exception as e:
            pass

    # 4) 登入完成後，進行預搜尋
    try:
        import time
        presearch_start = time.time()
        _presearch_target(driver, user_data)
        presearch_end = time.time()
        presearch_duration = presearch_end - presearch_start
    except Exception as e:
        presearch_end = time.time()
        presearch_duration = presearch_end - presearch_start if 'presearch_start' in locals() else 0

    # 5) 注入腳本並開始搶票流程
    try:
        sale_time_str = str((user_data or {}).get('SaleTime', '') or '').strip()
        target_ms = _parse_sale_time_iso8601(sale_time_str)
        if target_ms is not None:
            # 以頁面時間與本機時間估計 offset
            try:
                page_now = int(driver.execute_script("return Date.now();") or 0)
            except Exception:
                page_now = 0
            local_now = int(_time.time() * 1000)
            offset = page_now - local_now if page_now and local_now else 0

            # 先註冊 autofill 腳本
            autofill_source = get_autofill_script()
            try:
                driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', { 'source': autofill_source })
            except Exception:
                pass

            # 清除之前的執行標記，允許新的腳本執行
            try:
                driver.execute_script("""
                    localStorage.removeItem('kk_refresh_timer_executed');
                    localStorage.removeItem('kk_autofill_ever_completed');
                    localStorage.removeItem('kk_payment_page_reached');
                    window.__kk_payment_page_reached = false;
                    window.__kk_payment_page_confirmed = false;
                    console.log('已清除所有執行標記，準備新的搶票流程');
                """)
            except Exception:
                pass
            
            # 註冊計時刷新腳本 - 優先使用 CDP 注入
            cdp_success = False
            refresh_script_cdp = get_refresh_timer_script_for_cdp(int(target_ms), int(offset))
            
            # 測試：先在當前頁面執行 CDP 腳本驗證語法
            try:
                driver.execute_script(refresh_script_cdp)
                cdp_success = True
            except Exception:
                cdp_success = False
            
            try:
                driver.execute_cdp_cmd(
                    'Page.addScriptToEvaluateOnNewDocument',
                    { 'source': refresh_script_cdp }
                )
                cdp_success = True
            except Exception:
                cdp_success = False
            
            # 無論 CDP 是否成功，都在當前頁面執行一次刷新腳本作為備用
            try:
                js_source = get_refresh_timer_script()
                driver.execute_script(js_source, int(target_ms), int(offset))
            except Exception:
                pass

            # Python 端同步等待至到點，但給 JavaScript 腳本足夠的執行空間
            try:
                aim_page_ms = int(target_ms) + int(offset)
                
                while True:
                    try:
                        now_page = int(driver.execute_script("return Date.now();") or 0)
                    except Exception:
                        now_page = int(_time.time() * 1000) + int(offset)
                    remain = aim_page_ms - now_page
                    
                    if remain <= -5000:  # 超過5秒後停止等待
                        break
                    
                    # 動態睡眠：越接近越短，但不要太頻繁以免影響瀏覽器
                    if remain > 5000:
                        _time.sleep(min(1.0, max(0.1, remain/10000.0)))
                    elif remain > 1000:
                        _time.sleep(0.1)
                    else:
                        _time.sleep(0.05)  # 最後1秒內減少干擾
                
                # 等待5秒看是否自動刷新
                for i in range(50):  # 檢查5秒
                    _time.sleep(0.1)
                    try:
                        current_url = driver.current_url
                        # 檢查 localStorage 中的刷新標記
                        fire_status = driver.execute_script("return localStorage.getItem('kk_pre_fire');")
                        timer_executed = driver.execute_script("return localStorage.getItem('kk_refresh_timer_executed');")
                        
                        if fire_status == '1' or timer_executed == 'true':
                            break
                    except Exception:
                        pass
                else:
                    # 如果沒有自動刷新，手動刷新
                    try:
                        # 先嘗試執行刷新腳本
                        js_source = get_refresh_timer_script()
                        driver.execute_script(js_source, int(target_ms), int(offset))
                        _time.sleep(2)  # 給腳本時間執行
                        
                        # 如果腳本執行後還是沒刷新，直接手動刷新
                        fire_status_after = driver.execute_script("return localStorage.getItem('kk_pre_fire');")
                        if fire_status_after != '1':
                            driver.execute_script("localStorage.setItem('kk_pre_fire','1');")
                            driver.refresh()
                    except Exception:
                        # 最後手段：直接刷新
                        try:
                            driver.refresh()
                        except Exception:
                            pass
                
                while True:
                    _time.sleep(1)  # 無限循環，防止程式結束
            except KeyboardInterrupt:
                pass
            except Exception:
                # 即使出錯也要持續運行
                while True:
                    _time.sleep(1)
    except Exception:
        pass