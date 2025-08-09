# js_scripts.py
# JavaScript 腳本集合，供 methods.py 使用

def get_presearch_script():
    """預搜尋票券的 JavaScript 腳本"""
    return r"""
        (function(name1, name2, price, qty, isAuto){
          try{
            const list = document.querySelector('.ticket-list');
            const units = list ? Array.from(list.querySelectorAll('.ticket-unit.ng-scope')) : [];
            
            const want = {
              name1: (name1||'').trim(),
              name2: (name2||'').trim(),
              seatText: (isAuto? '電腦配位' : '自行選位'),
              priceInt: (price? parseInt(price,10) : null),
              qty: String(qty||'1'),
              // 檢查標記：確定哪些欄位需要驗證
              checkName1: !!(name1||'').trim(),
              checkName2: !!(name2||'').trim(), 
              checkPrice: !!(price||'').trim(),
              checkSeat: true // 座位類型總是檢查（基於 IsAutoAllocation）
            };
            
            function baseText(el){ return (el? (el.textContent||'') : '').replace(/\s+/g,' ').trim(); }
            function digitsInt(el){ const s = baseText(el); const m = s.replace(/[^0-9]/g,''); return m? parseInt(m,10) : null; }
            
            let hintIndex = -1, hintId = null;
            for (let i=0;i<units.length;i++){
              const u = units[i];
              // 分別抓取主票名和副票名
              const nameEl = u.querySelector('.ticket-name.ng-binding');
              const name2El = u.querySelector('.small.text-muted.ng-binding.ng-scope');
              
              // 主票名：只取直接文字節點，排除子元素
              let nm1 = '';
              if(nameEl){
                for(const node of nameEl.childNodes){
                  if(node.nodeType === 3){ // TEXT_NODE
                    nm1 += node.textContent;
                  }
                }
                nm1 = nm1.replace(/\s+/g,' ').trim();
              }
              
              // 副票名：直接取文字
              const nm2 = baseText(name2El);
              const seat = baseText(u.querySelector('.ticket-seat.ng-binding.ng-scope'));
              const priceEl = u.querySelector('span[ng-if="ticket.price.cents > 0"].ng-binding.ng-scope');
              const pr = digitsInt(priceEl);
              
              // 嚴格檢查每個有設定的欄位
              const ok1 = want.checkName1 ? (nm1 === want.name1) : true;
              const ok2 = want.checkName2 ? (nm2 === want.name2) : true;
              const okSeat = want.checkSeat ? (seat === want.seatText) : true;
              const okPrice = want.checkPrice ? (pr === want.priceInt) : true;
              
              if (ok1 && ok2 && okSeat && okPrice){
                hintIndex = i;
                const disp = u.querySelector('.display-table[id]');
                hintId = disp ? disp.id : null;
                break;
              }
            }
            
            const stash = {
              want: want,
              selectors: {
                unit: '.ticket-unit.ng-scope',
                name: '.ticket-name.ng-binding',
                name2: '.small.text-muted.ng-binding.ng-scope',
                seat: '.ticket-seat.ng-binding.ng-scope',
                price: 'span[ng-if="ticket.price.cents > 0"].ng-binding.ng-scope',
                qtyInput: 'input[ng-model="ticketModel.quantity"]',
                agree: '#person_agree_terms',
                nextBtn: '.register-new-next-button-area button'
              },
              hint: { index: hintIndex, unitId: hintId },
              armed: true
            };
            
            localStorage.setItem('kk_presearch', JSON.stringify(stash));
          }catch(e){ 
            try{ localStorage.setItem('kk_presearch', JSON.stringify({err:String(e)})); }catch(_){} 
          }
        })(arguments[0], arguments[1], arguments[2], arguments[3], arguments[4]);
        """


def get_refresh_timer_script():
    """定時刷新的 JavaScript 腳本"""
    return """
        (function(targetMs, offset){
          try{
            console.log('刷新腳本開始執行，目標時間:', targetMs, '偏移:', offset);
            
            // 【全域檢查】如果已經到達付款頁面，停止刷新腳本
            if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){
              console.log('🛑 付款頁面已到達，刷新腳本停止執行');
              return;
            }
            
            // 使用 localStorage 防止重複執行，即使頁面刷新也能保持
            const timerKey = 'kk_refresh_timer_executed';
            if(localStorage.getItem(timerKey) === 'true') {
              console.log('刷新腳本已經執行過，跳過重複執行');
              return;
            }
            
            if(window.__kk_sale_timer_armed) {
              console.log('刷新腳本已經武裝，跳過重複執行');
              return;
            }
            window.__kk_sale_timer_armed = true;
            
            const aim = Number(targetMs) + Number(offset||0);
            
            function hardRefresh(){
              try{ 
                localStorage.setItem('kk_pre_fire','1'); 
                localStorage.setItem(timerKey, 'true'); // 標記刷新腳本已執行
                // 清除 autofill 完成標記，允許刷新後重新執行
                localStorage.removeItem('kk_autofill_ever_completed');
              }catch(_){}
              try{ location.reload(); }catch(e){ 
                try{ location.replace(location.href); }catch(_e){} 
              }
            }
            
            function spin(){
              // 在每次 spin 檢查時確認是否已到達付款頁面
              if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){
                console.log('🛑 spin 檢查中發現付款頁面已到達，停止刷新倒計時');
                return;
              }
              
              const r = aim - Date.now();
              if (r <= 3){ 
                while(Date.now() < aim){
                  // 精確等待
                } 
                hardRefresh(); 
                return; 
              }
              requestAnimationFrame(spin);
            }
            
            const pre = Math.max(0, aim - Date.now() - 2000);
            
            if (pre <= 0){ 
              try{ requestAnimationFrame(spin); }catch(_){ 
                hardRefresh(); 
              } 
              return; 
            }
            
            setTimeout(function(){ 
              try{ requestAnimationFrame(spin); }catch(_){ 
                hardRefresh(); 
              } 
            }, pre);
          }catch(e){
            console.log('刷新腳本執行錯誤:', e);
          }
        })(arguments[0], arguments[1]);
        """


def get_refresh_timer_script_for_cdp(target_ms, offset):
    """為 CDP 注入創建不依賴 arguments 的刷新腳本"""
    return f"""
        (function(){{
          try{{
            const targetMs = {target_ms};
            const offset = {offset};
            
            console.log('CDP刷新腳本開始執行，目標時間:', targetMs, '偏移:', offset);
            
            // 【全域檢查】如果已經到達付款頁面，停止 CDP 刷新腳本
            if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){{
              console.log('🛑 付款頁面已到達，CDP 刷新腳本停止執行');
              return;
            }}
            
            // 使用 localStorage 防止重複執行，即使頁面刷新也能保持
            const timerKey = 'kk_refresh_timer_executed';
            if(localStorage.getItem(timerKey) === 'true') {{
              console.log('CDP刷新腳本已經執行過，跳過重複執行');
              return;
            }}
            
            if(window.__kk_sale_timer_armed) {{
              console.log('刷新腳本已經武裝，跳過重複執行');
              return;
            }}
            window.__kk_sale_timer_armed = true;
            
            const aim = Number(targetMs) + Number(offset||0);
            
            function hardRefresh(){{
              try{{ 
                localStorage.setItem('kk_pre_fire','1'); 
                localStorage.setItem(timerKey, 'true'); // 標記刷新腳本已執行
                // 清除 autofill 完成標記，允許刷新後重新執行
                localStorage.removeItem('kk_autofill_ever_completed');
              }}catch(_){{}}
              try{{ location.reload(); }}catch(e){{ 
                try{{ location.replace(location.href); }}catch(_e){{}} 
              }}
            }}
            
            function spin(){{
              // 在每次 spin 檢查時確認是否已到達付款頁面
              if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){{
                console.log('🛑 CDP spin 檢查中發現付款頁面已到達，停止刷新倒計時');
                return;
              }}
              
              const r = aim - Date.now();
              if (r <= 3){{ 
                while(Date.now() < aim){{
                  // 精確等待
                }} 
                hardRefresh(); 
                return; 
              }}
              requestAnimationFrame(spin);
            }}
            
            const pre = Math.max(0, aim - Date.now() - 2000);
            
            if (pre <= 0){{ 
              try{{ requestAnimationFrame(spin); }}catch(_){{ 
                hardRefresh(); 
              }} 
              return; 
            }}
            
            setTimeout(function(){{ 
              try{{ requestAnimationFrame(spin); }}catch(_){{ 
                hardRefresh(); 
              }} 
            }}, pre);
          }}catch(e){{
            console.log('刷新腳本執行錯誤:', e);
          }}
        }})();
        """


def get_autofill_script():
    """自動填寫的 JavaScript 腳本"""
    return r"""
(function(){
  console.log('=== AUTOFILL 腳本載入 ===', new Date().toISOString());
  try{
    // 【全域檢查】如果已經到達付款頁面，完全停止腳本執行
    if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){
      console.log('🛑 付款頁面已到達，腳本完全停止執行');
      return; // 立即退出，不執行任何邏輯
    }
    
    const sleep = (ms)=> new Promise(r=>setTimeout(r, ms));
    
    function btnEnabled(btn){
      if(!btn) return false;
      if(btn.disabled) return false;
      const cs=getComputedStyle(btn);
      if(cs.display==='none'||cs.visibility==='hidden') return false;
      const cls=(btn.className||'')+' '+(btn.getAttribute('class')||'');
      if(/btn-disabled|btn-disabled-alt|disabled|ng-disabled/.test(cls)) return false;
      return true;
    }
    
    function baseText(el){ return (el? (el.textContent||'') : '').replace(/\s+/g,' ').trim(); }
    function digitsInt(el){ const s = baseText(el); const m = s.replace(/[^0-9]/g,''); return m? parseInt(m,10) : null; }
    
    // 檢查是否在付款確認頁面
    function isPaymentPage(){
      // 如果已經確認過是付款頁面，直接返回 true，避免重複檢測
      if(window.__kk_payment_page_confirmed){
        return true;
      }
      
      console.log('=== 檢查是否為付款確認頁面 ===');
      console.log('當前 URL:', location.href);
      
      // 檢查是否有付款確認頁面的特徵元素：「確認表單資料」按鈕
      const confirmOrderBtn = document.querySelector('.form-actions.plain.align-center.ng-scope a.btn.btn-primary.btn-lg.ng-binding.ng-isolate-scope[ng-click="confirmOrder()"]');
      const confirmOrderBtnAlt = document.querySelector('a[ng-click="confirmOrder()"]');
      
      console.log('確認表單資料按鈕檢查:');
      console.log('- 完整選擇器按鈕:', !!confirmOrderBtn);
      console.log('- 簡化選擇器按鈕:', !!confirmOrderBtnAlt);
      
      if(confirmOrderBtn || confirmOrderBtnAlt){
        console.log('✅ 發現「確認表單資料」按鈕 - 判定為付款頁面');
        // 設置標記，避免重複檢測
        window.__kk_payment_page_confirmed = true;
        return true;
      }
      
      // 備用檢查：檢查是否有其他付款相關元素
      const paymentIndicators = [
        '.form-actions.plain.align-center',
        'a[ng-click*="confirm"]',
        'button[ng-click*="confirm"]',
        '.payment-form',
        '.checkout-form',
        '.order-summary'
      ];
      
      console.log('備用付款元素檢查:');
      for(const selector of paymentIndicators){
        const element = document.querySelector(selector);
        if(element){
          const text = element.textContent || '';
          console.log(`- ${selector}: 存在，內容: "${text.trim()}"`);
          if(text.includes('確認') || text.includes('付款') || text.includes('結帳')){
            console.log('✅ 發現付款相關元素 - 判定為付款頁面');
            // 設置標記，避免重複檢測
            window.__kk_payment_page_confirmed = true;
            return true;
          }
        } else {
          console.log(`- ${selector}: 不存在`);
        }
      }
      
      console.log('❌ 未發現付款頁面特徵 - 判定為非付款頁面');
      return false;
    }
    
    // 檢查是否在搶票頁面
    function isTicketPurchasePage(){
      console.log('=== 檢查當前頁面類型 ===');
      console.log('當前 URL:', location.href);
      
      // 先檢查是否為付款頁面
      if(isPaymentPage()){
        console.log('判定為付款頁面 - 不是搶票頁面');
        return false;
      }
      
      // 檢查是否有搶票頁面的特徵元素
      const ticketList = document.querySelector('.ticket-list');
      const ticketUnits = document.querySelectorAll('.ticket-unit.ng-scope');
      
      console.log('搶票頁面檢查結果:');
      console.log('- 票券列表存在:', !!ticketList);
      console.log('- 票券單位數量:', ticketUnits.length);
      
      if(ticketList) {
        console.log('- 票券列表元素:', ticketList);
      }
      if(ticketUnits.length > 0) {
        console.log('- 第一個票券單位:', ticketUnits[0]);
      }
      
      // 只要有票券列表和票券單位，就是搶票頁面（不管是否開賣）
      if(!ticketList || ticketUnits.length === 0){
        console.log('❌ 缺少搶票頁面特徵元素 - 判定為非搶票頁面');
        return false;
      }
      
      console.log('✅ 確認為搶票頁面');
      return true;
    }
    
    // 刷新網頁的函數
    function refreshPage(){
      try{ localStorage.setItem('kk_pre_fire','1'); }catch(_){}
      try{ location.reload(); }catch(e){ try{ location.replace(location.href); }catch(_e){} }
    }
    
    function pickUnit(cfg){
      const selUnit = (cfg.selectors&&cfg.selectors.unit) || '.ticket-unit.ng-scope';
      const units = Array.from(document.querySelectorAll(selUnit));
      
      // 先用 hint
      const hint = cfg.hint && Number(cfg.hint.index);
      if(Number.isInteger(hint) && units[hint]){
        return units[hint];
      }
      
      // 或用 unitId
      if(cfg.hint && cfg.hint.unitId){
        const byId = document.getElementById(cfg.hint.unitId);
        if(byId){
          const unit = byId.closest(selUnit);
          if(unit) return unit;
        }
      }
      
      // 全文重配對
      const selName = (cfg.selectors&&cfg.selectors.name) || '.ticket-name.ng-binding';
      const selName2 = (cfg.selectors&&cfg.selectors.name2) || '.small.text-muted.ng-binding.ng-scope';
      const selSeat = (cfg.selectors&&cfg.selectors.seat) || '.ticket-seat.ng-binding.ng-scope';
      const selPrice = (cfg.selectors&&cfg.selectors.price) || 'span[ng-if="ticket.price.cents > 0"].ng-binding.ng-scope';
      
      for(const u of units){
        // 使用相同的票名提取邏輯
        const nameEl = u.querySelector(selName);
        let nm1 = '';
        if(nameEl){
          for(const node of nameEl.childNodes){
            if(node.nodeType === 3){ // TEXT_NODE
              nm1 += node.textContent;
            }
          }
          nm1 = nm1.replace(/\s+/g,' ').trim();
        }
        
        const nm2 = baseText(u.querySelector(selName2));
        const seat = baseText(u.querySelector(selSeat));
        const pr = digitsInt(u.querySelector(selPrice));
        
        // 使用相同的嚴格檢查邏輯
        const ok1 = (cfg.want&&cfg.want.checkName1) ? (nm1 === (cfg.want.name1||'')) : true;
        const ok2 = (cfg.want&&cfg.want.checkName2) ? (nm2 === (cfg.want.name2||'')) : true;
        const okSeat = (cfg.want&&cfg.want.checkSeat) ? (seat === (cfg.want.seatText||'')) : true;
        const okPrice = (cfg.want&&cfg.want.checkPrice) ? (pr === (cfg.want.priceInt||0)) : true;
        
        if (ok1 && ok2 && okSeat && okPrice) return u;
      }
      return null;
    }

    async function typeQty(input, s){
      try{ input.focus(); input.value=''; input.dispatchEvent(new Event('input',{bubbles:true})); }catch(e){}
      for (const ch of String(s)){
        try{ input.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:ch})); }catch(e){}
        try{ input.value += ch; input.dispatchEvent(new Event('input',{bubbles:true})); }catch(e){}
        try{ input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:ch})); }catch(e){}
        await Promise.resolve();
      }
      try{ input.dispatchEvent(new Event('change',{bubbles:true})); input.blur(); }catch(e){}
    }
    
    async function run(){
      console.log('=== AUTOFILL RUN 函數開始執行 ===', new Date().toISOString());
      console.log('頁面 URL:', location.href);
      console.log('頁面標題:', document.title);
      console.log('文檔狀態:', document.readyState);
      
      // 過濾掉不需要處理的頁面
      if(location.href === 'about:blank' || location.href.includes('data:') || location.href.includes('chrome-extension:')){
        console.log('跳過非目標頁面:', location.href);
        return;
      }
      
      // 確保是 KKTIX 相關頁面
      if(!location.href.includes('kktix.com')){
        console.log('非 KKTIX 頁面，跳過執行:', location.href);
        return;
      }
      
      // 清除付款頁面確認標記，讓每次頁面載入都重新檢測
      window.__kk_payment_page_confirmed = false;
      
      // 【最優先檢查】如果已經在付款頁面，立即停止所有腳本執行
      if(isPaymentPage()){
        console.log('🎉 偵測到付款頁面，立即停止所有 JS 腳本執行！');
        // 設置全域標記，防止任何腳本繼續執行
        window.__kk_payment_page_reached = true;
        localStorage.setItem('kk_payment_page_reached', 'true');
        localStorage.setItem('kk_pre_fire','done'); 
        localStorage.setItem('kk_autofill_ever_completed', 'true');
        console.log('✅ 已進入付款頁面，所有自動化腳本已停止');
        return; // 立即退出，不執行任何後續邏輯
      }
      
      // 生成當前頁面的執行標記（基於 URL 路徑）
      const executionKey = 'kk_autofill_completed_' + location.pathname + '_' + Date.now().toString().slice(-6);
      const globalExecutionKey = 'kk_autofill_ever_completed';
      
      // 【再次檢查】確保在執行過程中沒有到達付款頁面
      if(localStorage.getItem('kk_payment_page_reached') === 'true' || window.__kk_payment_page_reached){
        console.log('🛑 執行過程中檢測到付款頁面已到達，立即停止');
        return;
      }
      
      // 檢查是否已經完成過自動填寫（全域檢查）
      const globalCompleted = localStorage.getItem(globalExecutionKey);
      console.log('全域完成標記檢查:', globalCompleted);
      
      // 如果已經完成並且當前已經在付款頁面，直接返回
      if(globalCompleted === 'true' && isPaymentPage()){
        console.log('❌ 已經在付款頁面且 Autofill 已完成，跳過執行');
        // 設置付款頁面到達標記
        window.__kk_payment_page_reached = true;
        localStorage.setItem('kk_payment_page_reached', 'true');
        return;
      }
      
      // 檢查是否是刷新後的執行（有刷新標記但沒有完成標記，說明是新的搶票流程）
      const fired = (localStorage.getItem('kk_pre_fire')||'');
      const refreshExecuted = localStorage.getItem('kk_refresh_timer_executed') === 'true';
      
      if(globalCompleted === 'true' && !fired && !refreshExecuted){
        console.log('❌ Autofill 已完成過且非刷新流程，跳過執行');
        return; // 已經完成過了，不再執行
      }
      
      if(globalCompleted === 'true' && (fired || refreshExecuted)){
        console.log('⚠️ 檢測到之前的完成標記，但這是刷新後的新流程，清除舊標記並繼續');
        try{
          localStorage.removeItem(globalExecutionKey);
        }catch(e){}
      }
      
      console.log('✅ 全域完成標記檢查通過，繼續執行');
      
      console.log('檢查 kk_pre_fire 標記:', fired);
      console.log('刷新腳本是否已執行:', refreshExecuted);
      
      if(!fired || fired==='done'){
        // 嘗試手動檢查是否有刷新跡象
        if(window.performance && window.performance.navigation && window.performance.navigation.type === 1){
          console.log('檢測到頁面刷新，繼續執行 autofill');
          // 頁面被刷新，繼續執行
        } else if(refreshExecuted) {
          console.log('雖然沒有刷新標記，但刷新腳本已執行，繼續執行 autofill');
          // 刷新腳本已執行，可能是通過其他方式刷新的
        } else {
          console.log('未檢測到刷新標記或刷新跡象，跳過執行');
          return;
        }
      } else {
        console.log('檢測到刷新標記，繼續執行 autofill');
      }
      
      // 等待 DOM 載入完成
      let attempts = 0;
      const maxAttempts = 100; // 10秒最大等待時間
      while(attempts < maxAttempts && document.readyState !== 'complete' && document.readyState !== 'interactive'){
        await sleep(100);
        attempts++;
      }
      
      // 頁面類型已在函數開始時檢查過，這裡不需要重複檢查
      
      // 【關鍵檢查】首先檢查是否已經在付款頁面
      if(isPaymentPage()){
        console.log('已經在付款頁面，autofill 任務完成！');
        // 標記自動填寫已完成
        try{ 
          localStorage.setItem('kk_pre_fire','done'); 
          localStorage.setItem(globalExecutionKey, 'true');
          localStorage.setItem(executionKey, 'true');
          console.log('✅ 自動填寫流程完成，已在付款頁面');
        }catch(e){
          console.log('設置完成標記時發生錯誤:', e);
        }
        return; // 已經成功到達付款頁面，結束腳本
      }
      
      console.log('讀取預搜尋配置...');
      const cfg = JSON.parse(localStorage.getItem('kk_presearch')||'{}');
      console.log('預搜尋配置:', cfg);
      
      if(!cfg || cfg.armed!==true) {
        console.log('預搜尋配置無效或未武裝，跳過執行');
        return;
      }
      
      const qtySel = (cfg.selectors&&cfg.selectors.qtyInput) || 'input[ng-model="ticketModel.quantity"]';
      const agreeSel = (cfg.selectors&&cfg.selectors.agree) || '#person_agree_terms';
      const nextSel = (cfg.selectors&&cfg.selectors.nextBtn) || '.register-new-next-button-area button';
      
      // 無限等待直到找到目標票券和數量輸入框
      console.log('開始尋找目標票券...');
      let unit=null, qty=null;
      let searchAttempts = 0;
      
      while(true){
        searchAttempts++;
        
        // 在搜尋過程中也檢查是否跳轉到付款頁面
        if(searchAttempts % 50 === 0) { // 每3秒檢查一次，減少頻率
          if(isPaymentPage()){
            console.log('🎉 搜尋過程中檢測到已跳轉至付款頁面，立即停止所有腳本！');
            // 設置付款頁面到達標記，停止所有後續腳本
            window.__kk_payment_page_reached = true;
            localStorage.setItem('kk_payment_page_reached', 'true');
            localStorage.setItem('kk_pre_fire','done'); 
            localStorage.setItem(globalExecutionKey, 'true');
            localStorage.setItem(executionKey, 'true');
            console.log('🛑 付款頁面已到達，所有自動化腳本已完全停止');
            return;
          }
        }
        
        unit = pickUnit(cfg);
        if(unit){
          console.log('找到目標票券單位，嘗試尋找數量輸入框...');
          qty = unit.querySelector(qtySel);
          if(qty) {
            console.log('找到數量輸入框，準備填寫');
            break;
          } else {
            console.log('未找到數量輸入框，繼續等待...');
          }
        } else {
          if(searchAttempts % 50 === 0) { // 每3秒輸出一次
            console.log('尚未找到目標票券，繼續搜尋... (嘗試次數:', searchAttempts, ')');
          }
        }
        await sleep(60);
      }
      
      console.log('開始填寫票數:', (cfg.want&&cfg.want.qty)||'1');
      if(qty){
        await typeQty(qty, String((cfg.want&&cfg.want.qty)||'1'));
        console.log('票數填寫完成');
      }
      
      // 同意條款
      console.log('檢查並勾選同意條款...');
      try{
        const agree = document.querySelector(agreeSel);
        if(agree) {
          if(!agree.checked){
            console.log('勾選同意條款');
            agree.click();
            agree.dispatchEvent(new Event('change',{bubbles:true}));
          } else {
            console.log('同意條款已經勾選');
          }
        } else {
          console.log('未找到同意條款元素');
        }
      }catch(e){
        console.log('處理同意條款時發生錯誤:', e);
      }
      
      // 下一步按鈕 - 無限等待直到可點擊
      console.log('等待下一步按鈕可點擊...');
      let btn=null;
      let btnAttempts = 0;
      while(true){
        btnAttempts++;
        btn = document.querySelector(nextSel);
        if(btn && btnEnabled(btn)) {
          console.log('下一步按鈕已可點擊');
          break;
        }
        if(btnAttempts % 25 === 0) { // 每秒輸出一次
          console.log('等待下一步按鈕... (嘗試次數:', btnAttempts, ')');
          if(btn) {
            console.log('按鈕存在但不可點擊，狀態:', {
              disabled: btn.disabled,
              className: btn.className,
              style: btn.style.display
            });
          } else {
            console.log('按鈕不存在');
          }
        }
        await sleep(40);
      }
      
      console.log('點擊下一步按鈕...');
      if(btn){
        try{ 
          btn.click(); 
          console.log('下一步按鈕點擊成功');
          
          // 【關鍵修復】點擊後等待頁面載入，然後檢查是否進入付款頁面
          await sleep(1000); // 等待頁面跳轉
          
          if(isPaymentPage()){
            console.log('🎉【成功】已進入付款頁面，立即停止所有腳本！');
            // 設置付款頁面到達標記，完全停止所有腳本
            window.__kk_payment_page_reached = true;
            localStorage.setItem('kk_payment_page_reached', 'true');
            localStorage.setItem('kk_pre_fire','done'); 
            localStorage.setItem(globalExecutionKey, 'true');
            localStorage.setItem(executionKey, 'true');
            console.log('🛑 付款頁面已到達，所有自動化腳本已完全停止');
            return; // 成功完成，退出腳本
          }
          
        }catch(e){ 
          console.log('第一次點擊失敗，嘗試事件觸發:', e);
          try{ 
            btn.dispatchEvent(new MouseEvent('click',{bubbles:true})); 
            console.log('事件觸發點擊成功');
            
            // 同樣在事件觸發點擊後檢查
            await sleep(1000);
            if(isPaymentPage()){
              console.log('🎉【成功】已進入付款頁面，立即停止所有腳本！');
              // 設置付款頁面到達標記，完全停止所有腳本
              window.__kk_payment_page_reached = true;
              localStorage.setItem('kk_payment_page_reached', 'true');
              localStorage.setItem('kk_pre_fire','done'); 
              localStorage.setItem(globalExecutionKey, 'true');
              localStorage.setItem(executionKey, 'true');
              console.log('🛑 付款頁面已到達，所有自動化腳本已完全停止');
              return;
            }
            
          }catch(_e){
            console.log('事件觸發點擊也失敗:', _e);
          } 
        }
      }
      
      // 標記自動填寫已完成（全域標記，防止在其他頁面重複執行）
      console.log('設置完成標記...');
      try{ 
        localStorage.setItem('kk_pre_fire','done'); 
        localStorage.setItem(globalExecutionKey, 'true');
        localStorage.setItem(executionKey, 'true');
        console.log('自動填寫流程完成');
      }catch(e){
        console.log('設置完成標記時發生錯誤:', e);
      }
    }
    
    console.log('=== AUTOFILL 腳本準備觸發 ===');
    console.log('當前文檔狀態:', document.readyState);
    console.log('當前時間:', new Date().toISOString());
    
    if(document.readyState==='complete' || document.readyState==='interactive'){
      console.log('文檔已就緒，立即執行 run 函數');
      setTimeout(()=>{ run(); }, 100); // 稍微延遲以確保頁面完全載入
    } else {
      console.log('文檔未就緒，等待 DOMContentLoaded 事件');
      document.addEventListener('DOMContentLoaded', ()=>{ 
        console.log('DOMContentLoaded 事件觸發，執行 run 函數');
        run(); 
      }, {once:true});
    }
  }catch(e){}
})();
"""
