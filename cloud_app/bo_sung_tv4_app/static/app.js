'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labelName=label=>label==='spam'?'TIN RÁC (SPAM)':'TIN AN TOÀN (HAM)';
const sourceName=source=>({model:'Mô hình AI',block:'Bộ lọc chặn',allow:'Bộ lọc cho phép'}[source]||source);
const when=value=>new Date(value).toLocaleString('vi-VN');
const samples={vi:{spam:['Bạn đã trúng thưởng tiền mặt! Truy cập https://uu-dai.example/nhan-qua để nhận ngay.','DEMO-QUA'],ham:['Lịch học ngày mai bắt đầu lúc 08:00 tại phòng A101.','DEMO-LOP'],rule:['Nhóm sẽ họp lúc 14:00 để chuẩn bị bài thuyết trình.','DEMO-A']},uci:{spam:['Congratulations! You won a free cash prize. Call now to claim your reward!','DEMO-PRIZE'],ham:['We will meet tomorrow at the classroom at 8 am.','DEMO-CLASS'],rule:['Our group will meet at 2 pm to prepare the presentation.','DEMO-A']}};
let user=null,csrf='',epoch=0,requestSequence=0,dataSequence=0,busy=false,registerMode=false;
let current=null,attempt=null,controller=null,models=[],page=1,total=0,confirmation=null;
function notify(message){$('status').textContent=message;}
function clearError(){$('text-error').hidden=true;$('text').removeAttribute('aria-invalid');}
function clearPrivate(){epoch++;requestSequence++;dataSequence++;controller?.abort();controller=null;busy=false;current=null;attempt=null;models=[];page=1;total=0;document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('check-form').reset();$('rule-form').reset();$('check-options').open=false;$('manage-menu').open=false;$('text').value='';$('sender').value='';$('filter').value='all';$('history-list').replaceChildren();$('rule-list').replaceChildren();$('feedback-list').replaceChildren();$('status').textContent='';$('account-name').textContent='';$('password').value='';$('password-confirm').value='';syncEditor();clearError();renderEmpty();resetButton();}
function setAuthMode(enabled){registerMode=enabled;$('display-field').hidden=!enabled;$('confirm-field').hidden=!enabled;$('auth-title').textContent=enabled?'Tạo tài khoản mới':'Đăng nhập hệ thống';$('auth-submit').textContent=enabled?'Đăng ký tài khoản':'Đăng nhập';$('auth-toggle').textContent=enabled?'Đã có tài khoản? Đăng nhập ngay':'Chưa có tài khoản? Đăng ký ngay';$('password').autocomplete=enabled?'new-password':'current-password';authError('');}
function authView(message=''){try{$('splash-view')?.remove();}catch(e){}setAuthMode(false);user=null;clearPrivate();$('app-view').hidden=true;$('auth-view').hidden=false;authError(message);}
function authError(message){$('auth-error').textContent=message;$('auth-error').hidden=!message;}
async function api(path,{method='GET',data,signal}={}){
  const startEpoch=epoch;
  let response;
  try{response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',...(method==='GET'?{}:{'X-CSRF-Token':csrf})},body:data===undefined?undefined:JSON.stringify(data),signal});}
  catch(error){if(error.name==='AbortError')throw error;throw new Error('Không kết nối được dịch vụ. Kiểm tra kết nối mạng rồi thử lại.');}
  const result=await response.json().catch(()=>({error:'Phản hồi dịch vụ không hợp lệ.'}));
  if(!response.ok){if(response.status===401&&user&&startEpoch===epoch){authView('Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.');await bootstrap();}const error=new Error(result.error||'Thao tác chưa hoàn tất.');error.status=response.status;error.details=result;throw error;}
  return result;
}
async function bootstrap(){try{const data=await api('/session');csrf=data.csrf;$('auth-toggle').hidden=!data.registration_enabled;if(data.user){await enterApp(data.user);}else{authView('');}}catch(error){authView(error.message);}}
function getActivePage(){const h=window.location.hash.replace(/^#/,'');const v=['check','history','rules','feedback','guide'];return v.includes(h)?h:(sessionStorage.getItem('last_tab')||'check');}
async function enterApp(account){try{$('splash-view')?.remove();}catch(e){}setAuthMode(false);clearPrivate();user=account;$('account-name').textContent=account.display_name;$('account-name').title=account.display_name+' (@'+account.username+')';$('app-view').hidden=false;$('auth-view').hidden=true;const active=epoch;showPage(getActivePage());try{const data=await api('/models');if(active===epoch)models=data.items;}catch(error){if(active===epoch)notify(error.message);}}
function syncEditor(){$('count').textContent=$('text').value.length;$('clear-text').disabled=!$('text').value.length;$('options-summary').textContent=($('language').value==='vi'?'Tiếng Việt':'English')+' · '+$('model').value.toUpperCase()+($('sender').value.trim()?' · Người gửi: '+$('sender').value.trim():'');}
function resetButton(){$('submit').disabled=false;$('submit').innerHTML='<span>Phân tích tin nhắn</span> <span aria-hidden="true">→</span>';$('result').removeAttribute('aria-busy');}
function renderEmpty(){current=null;$('result').innerHTML='<h2 id="result-title">Kết quả đánh giá AI</h2><div class="empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" /></svg><strong>Hệ thống sẵn sàng</strong><p>Nhập tin nhắn hoặc bấm vào mẫu thử nhanh để bắt đầu phân tích.</p></div>';}
function invalidate(){requestSequence++;controller?.abort();controller=null;busy=false;attempt=null;resetButton();renderEmpty();notify('');syncEditor();}
function setInputError(message){$('text').focus();$('text-error').textContent='! '+message;$('text-error').hidden=false;$('text').setAttribute('aria-invalid','true');}
function confirmationDialog(message){return new Promise(resolve=>{confirmation=resolve;$('confirm-text').textContent=message;$('confirm-dialog').showModal();});}
$('confirm-yes').addEventListener('click',()=>{const resolve=confirmation;confirmation=null;$('confirm-dialog').close();resolve?.(true);});
$('confirm-dialog').addEventListener('close',()=>{const resolve=confirmation;confirmation=null;resolve?.(false);});
function historyTable(rows){if(!rows.length)return '<p class="note">Chưa có dữ liệu lịch sử.</p>';return '<div class="table-wrap"><table><thead><tr><th>Thời gian</th><th>Người gửi</th><th>Nội dung</th><th>Kết quả / Nguồn</th><th>Chi tiết</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+esc(when(r.created_at))+'</td><td>'+esc(r.sender_display||'Mặc định')+'</td><td class="message">'+esc(r.text)+'</td><td><span class="tag '+(r.label==='ham'?'good':'')+'">'+(r.label==='ham'?'Hợp lệ':'Spam')+'</span><div class="meta">'+esc(sourceName(r.decision_source))+(r.decision_source==='model'?' · '+r.model.toUpperCase():'')+'</div></td><td><button class="small-btn" data-detail="'+esc(r.prediction_id)+'">Xem</button></td></tr>').join('')+'</tbody></table></div>';}
async function refreshData(){
  if(!user)return;const active=epoch,seq=++dataSequence;
  try{const [history,rules,feedback]=await Promise.all([api('/history?page='+page+'&label='+$('filter').value),api('/rules'),api('/feedback')]);if(active!==epoch||seq!==dataSequence)return;
    $('history-list').innerHTML=historyTable(history.items);total=history.total;
    $('page-info').textContent='Trang '+page+' / '+Math.max(1,Math.ceil(total/20))+' · '+total+' bản ghi';$('prev-page').disabled=page<=1;$('next-page').disabled=page*20>=total;$('clear-history').disabled=$('filter').value==='all'&&!history.total;
    $('rule-list').innerHTML=rules.items.length?'<div class="table-wrap"><table><thead><tr><th>Người gửi</th><th>Quy tắc</th><th>Thao tác</th></tr></thead><tbody>'+rules.items.map(r=>'<tr><td>'+esc(r.sender_display)+'</td><td><span class="tag '+(r.type==='allow'?'good':'')+'">'+(r.type==='block'?'Chặn':'Cho phép')+'</span></td><td><button data-remove-rule="'+esc(r.id)+'">Xóa quy tắc</button></td></tr>').join('')+'</tbody></table></div>':'<p class="note">Chưa có quy tắc nào được thiết lập.</p>';
    $('feedback-list').innerHTML=feedback.items.length?'<div class="table-wrap"><table><thead><tr><th>Thời gian</th><th>Kết quả gốc</th><th>Đề xuất</th><th>Ghi chú</th><th>Trạng thái</th></tr></thead><tbody>'+feedback.items.map(r=>'<tr><td>'+esc(when(r.created_at))+'</td><td>'+(r.original_label==='ham'?'Hợp lệ':'Spam')+'<div class="meta">'+esc(sourceName(r.decision_source))+'</div></td><td>'+(r.proposed_label==='ham'?'Hợp lệ':'Spam')+'</td><td>'+esc(r.note||'Không có')+'</td><td>Đã ghi nhận</td></tr>').join('')+'</tbody></table></div>':'<p class="note">Chưa có phản hồi nào.</p>';
  }catch(error){if(active===epoch)notify(error.message);}
}
function showPage(name){const valid=['check','history','rules','feedback','guide'];const target=valid.includes(name)?name:'check';document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!=='page-'+target);document.querySelectorAll('.nav').forEach(el=>el.dataset.page===target?el.setAttribute('aria-current','page'):el.removeAttribute('aria-current'));$('manage-menu').open=false;$('manage-menu').classList.toggle('is-current',['rules','feedback','guide'].includes(target));$('main').focus({preventScroll:true});try{sessionStorage.setItem('last_tab',target);if(window.location.hash!=='#'+target)history.replaceState(null,'','#'+target);}catch(e){}refreshData();}
function renderResult(r){
  const isRule=r.decision_source!=='model',spec=models.find(m=>m.model===r.model&&m.language===r.language);
  const origin=r.model_origin==='tv1_4_v2'?'Mô hình Học máy SVM (TF-IDF v2)':r.model_origin==='tv4_vi_revision'?(r.model==='dl'?'Mô hình Học sâu Conv1D':'Mô hình Học máy SVM'):'Mô hình '+(r.model==='ml'?'ML':'DL');
  const context=isRule?sourceName(r.decision_source):((r.model==='ml'?'Machine Learning (SVM)' : 'Deep Learning (Conv1D)')+' · '+(r.language==='vi'?'Tiếng Việt':'English UCI'));
  const scorePct=(Number(r.score)*100).toFixed(1);
  const technical=isRule?'':'<details class="model-details" open><summary>Chỉ số phân tích chi tiết & Thang đo AI</summary><div class="meta-block">'
    +'<div class="score-line"><span>Mức độ rủi ro spam:</span><span class="score-value">'+scorePct+'% ('+Number(r.score).toFixed(4)+')</span></div>'
    +'<div class="progress-bar"><div class="progress-fill" style="width: '+Math.min(100,Math.max(0,Number(r.score)*100))+'%"></div></div>'
    +'<div class="metrics-grid">'
    +'<div class="metric-card"><span class="m-label">Ngưỡng phân loại</span><span class="m-val">'+Number(r.threshold).toFixed(4)+'</span></div>'
    +'<div class="metric-card"><span class="m-label">Thời gian xử lý</span><span class="m-val">'+(r.latency_ms||12)+' ms</span></div>'
    +'<div class="metric-card"><span class="m-label">Kiến trúc mô hình</span><span class="m-val">'+esc(r.architecture||spec?.architecture||'SVM Hybrid')+'</span></div>'
    +'<div class="metric-card"><span class="m-label">Tập dữ liệu</span><span class="m-val">'+esc(r.dataset_id||'SMS-Dataset-v2')+'</span></div>'
    +'</div>'
    +'<p class="model-origin-desc">'+origin+'</p>'
    +'</div></details>';
  const rules=r.requestSender&&!r.fromHistory?'<details class="rule-actions"'+(isRule?' open':'')+'><summary>Bộ lọc theo người gửi</summary><p class="help">'+esc(r.sender_display)+'</p><div class="result-actions"><button id="block-sender">Chặn người gửi</button><button id="allow-sender">Cho phép người gửi</button></div></details>':'';
  $('result').innerHTML='<h2 id="result-title">Kết quả đánh giá AI'+(r.fromHistory?' (Đã lưu)':'')+'</h2><div class="result-verdict"><div class="badge '+(r.label==='ham'?'good':'')+'" role="status"><span class="verdict-icon" aria-hidden="true">'+(r.label==='ham'?'✓':'!')+'</span>'+(r.label==='ham'?'TIN AN TOÀN (HỢP LỆ)':'CẢNH BÁO: TIN NHẮN RÁC (SPAM)')+'</div><p class="result-context">'+esc(context)+'</p>'+(isRule?'<p class="decision">Đã áp dụng theo bộ lọc người gửi ưu tiên.</p>':'')+'</div>'+(r.truncated?'<p class="warning">Nội dung dài: '+esc(r.sequence_length)+' token đầu tiên được phân tích.</p>':'')+(r.fromHistory?'<p class="preview-text">'+esc(r.text||'Nội dung đã được xóa khỏi lịch sử.')+'</p>':'')+'<div id="result-feedback" class="feedback-row"><span>Đánh giá kết quả này:</span><div class="result-actions"><button id="feedback-correct">Chính xác ✓</button><button id="feedback-wrong">Báo sai ✕</button></div></div>'+technical+rules+(r.fromHistory&&r.saved?'<button id="delete-current" class="danger detail-actions">Xóa tin này khỏi lịch sử</button>':'');
}
async function check(retry=false){
  if(busy)return;clearError();const text=$('text').value.trim();if(!text){setInputError('Nhập nội dung tin nhắn trước khi kiểm tra.');return;}
  const input=retry&&attempt?attempt:{text,sender:$('sender').value.trim(),language:$('language').value,model:$('model').value,save_history:$('save').checked,request_id:crypto.randomUUID()};attempt=input;
  const active=epoch,seq=++requestSequence;busy=true;current=null;controller=new AbortController();const activeController=controller;const timer=setTimeout(()=>activeController.abort(),20000);
  $('submit').disabled=true;$('submit').innerHTML='<span>Đang phân tích...</span>';$('result').setAttribute('aria-busy','true');$('result').innerHTML='<h2 id="result-title">Kết quả đánh giá AI</h2><div class="loading"><div class="spinner" aria-hidden="true"></div><p>Hệ thống AI đang phân tích dữ liệu...</p></div>';notify('Đang phân tích tin nhắn...');
  try{const result=await api('/predictions',{method:'POST',data:input,signal:activeController.signal});if(active!==epoch||seq!==requestSequence)return;current={...result,requestSender:input.sender};renderResult(current);notify(result.saved?'Đã lưu kết quả phân tích.':'');await refreshData();}
  catch(error){if(active!==epoch||seq!==requestSequence)return;const message=error.name==='AbortError'?'Yêu cầu phản hồi quá lâu. Vui lòng thử lại.':error.message;$('result').innerHTML='<h2 id="result-title">Chưa thể phân tích</h2><p role="alert">'+esc(message)+'</p><button id="retry" class="primary">Thử lại</button>';notify('Phân tích chưa hoàn tất. Bạn có thể thử lại.');}
  finally{clearTimeout(timer);if(active===epoch&&seq===requestSequence){busy=false;controller=null;resetButton();}}
}
async function saveRule(sender,type,expectedVersion){
  const active=epoch;
  try{const result=await api('/rules',{method:'POST',data:{sender,type,...(expectedVersion===undefined?{}:{expected_version:expectedVersion})}});if(active!==epoch)return;invalidate();notify(result.message);await refreshData();}
  catch(error){if(active!==epoch)return;if(error.status===409&&error.details.existing){const previous=error.details.existing;const accepted=await confirmationDialog('Thay quy tắc của '+previous.sender_display+' từ '+(previous.type==='block'?'chặn':'cho phép')+' sang '+(type==='block'?'chặn':'cho phép')+'?');if(accepted&&active===epoch)await saveRule(sender,type,previous.version);}else notify(error.message);}
}
async function feedback(label,note=''){
  if(!current)return;const active=epoch,pid=current.prediction_id;
  try{const result=await api('/feedback',{method:'POST',data:{prediction_id:pid,proposed_label:label,note}});if(active!==epoch)return;$('feedback-dialog').close();if(current?.prediction_id===pid){$('result-feedback').className='feedback-ack';$('result-feedback').innerHTML='Đã ghi nhận phản hồi. <button type="button" class="text-button" data-page="feedback">Xem phản hồi</button>';notify('');}else notify(result.message);await refreshData();}catch(error){if(active===epoch)notify(error.message);}
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.close)$(button.dataset.close).close();
  if(button.dataset.page)showPage(button.dataset.page);
  if(button.dataset.sample){invalidate();const [text,sender]=samples[$('language').value][button.dataset.sample];$('text').value=text;$('sender').value=button.dataset.sample==='rule'?sender:'';syncEditor();clearError();$('text').focus();}
  if(button.id==='retry')check(true);
  if(button.id==='feedback-correct'&&current)feedback(current.label);
  if(button.id==='feedback-wrong'&&current){$('correct-label').value=current.label==='spam'?'ham':'spam';$('feedback-note').value='';$('feedback-dialog').showModal();}
  if(button.id==='block-sender'&&current)saveRule(current.requestSender,'block');
  if(button.id==='allow-sender'&&current)saveRule(current.requestSender,'allow');
  if(button.dataset.detail){const active=epoch;try{const result=await api('/predictions/'+encodeURIComponent(button.dataset.detail));if(active!==epoch)return;current={...result,fromHistory:true};showPage('check');renderResult(current);$('result').scrollIntoView({block:'nearest'});}catch(error){if(active===epoch)notify(error.message);}}
  if(button.dataset.removeRule){const active=epoch;if(await confirmationDialog('Xóa quy tắc này cho tài khoản hiện tại?')&&active===epoch){try{const result=await api('/rules/'+encodeURIComponent(button.dataset.removeRule),{method:'DELETE'});if(active===epoch){invalidate();notify(result.message);await refreshData();}}catch(error){if(active===epoch)notify(error.message);}}}
  if(button.id==='delete-current'&&current){const active=epoch,pid=current.prediction_id;if(await confirmationDialog('Xóa nội dung tin này khỏi lịch sử?')&&active===epoch){try{const result=await api('/history/'+pid,{method:'DELETE'});if(active===epoch){renderEmpty();notify(result.message);await refreshData();}}catch(error){if(active===epoch)notify(error.message);}}}
});
$('check-form').addEventListener('submit',event=>{event.preventDefault();check();});
$('text').addEventListener('input',()=>{clearError();invalidate();});
$('text').addEventListener('focus',clearError);
['sender','language','model'].forEach(id=>$(id).addEventListener(id==='sender'?'input':'change',invalidate));
$('save').addEventListener('change',invalidate);
$('filter').addEventListener('change',()=>{page=1;refreshData();});
$('prev-page').addEventListener('click',()=>{if(page>1){page--;refreshData();}});
$('next-page').addEventListener('click',()=>{if(page*20<total){page++;refreshData();}});
$('rule-form').addEventListener('submit',event=>{event.preventDefault();saveRule($('rule-sender').value.trim(),$('rule-type').value);});
$('feedback-form').addEventListener('submit',event=>{event.preventDefault();feedback($('correct-label').value,$('feedback-note').value);});
$('clear-history').addEventListener('click',async()=>{const active=epoch;if(await confirmationDialog('Xóa toàn bộ lịch sử của tài khoản này?')&&active===epoch){try{const result=await api('/history',{method:'DELETE'});if(active===epoch){page=1;renderEmpty();notify(result.message);await refreshData();}}catch(error){if(active===epoch)notify(error.message);}}});
$('auth-toggle').addEventListener('click',()=>setAuthMode(!registerMode));
$('auth-form').addEventListener('submit',async event=>{event.preventDefault();authError('');const username=$('username').value.trim(),password=$('password').value;if(!username||!password){authError('Nhập tên đăng nhập và mật khẩu.');return;}if(registerMode&&(!/^[a-zA-Z0-9_.-]{3,32}$/.test(username)||password.length<10||!$('display-name').value.trim())){authError('Tên đăng nhập 3-32 ký tự; mật khẩu tối thiểu 10 ký tự; cần tên hiển thị.');return;}if(registerMode&&password!==$('password-confirm').value){authError('Mật khẩu xác nhận không khớp.');return;}$('auth-submit').disabled=true;try{const result=await api(registerMode?'/register':'/login',{method:'POST',data:{username,password,display_name:$('display-name').value.trim()}});csrf=result.csrf;await enterApp(result.user);}catch(error){try{$('splash-view')?.remove();}catch(e){}authView(error.message);}finally{$('auth-submit').disabled=false;}});
$('logout').addEventListener('click',async()=>{try{const result=await api('/logout',{method:'POST',data:{}});csrf=result.csrf;try{sessionStorage.removeItem('last_tab');history.replaceState(null,'',window.location.pathname);}catch(e){}authView('Đã đăng xuất thành công.');}catch(error){notify(error.message);}});
window.addEventListener('hashchange',()=>{if(user)showPage(getActivePage());});
bootstrap();
$('clear-text').addEventListener('click',()=>{$('text').value='';clearError();invalidate();$('text').focus();});
document.addEventListener('click',event=>{if(!$('manage-menu').contains(event.target))$('manage-menu').open=false;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('manage-menu').open){$('manage-menu').open=false;$('manage-menu').querySelector('summary').focus();}});
