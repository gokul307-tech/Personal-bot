const savedPreferences = () => {
  try {
    return {responseStyle:'balanced',answerLength:'medium',defaultExamMode:'5',beginnerFriendly:true,preferUploadedMaterials:true,showSources:true,enterToSend:state.enterToSend,showTimestamps:true,autoTitles:true,keepAttachmentContext:true,studyStyle:'focused blocks',quizDifficulty:'medium',displayName:localStorage.getItem('sage-display-name')||'Student',...JSON.parse(localStorage.getItem('sage-preferences')||'{}')};
  } catch {
    return {responseStyle:'balanced',answerLength:'medium',defaultExamMode:'5',beginnerFriendly:true,preferUploadedMaterials:true,showSources:true,enterToSend:state.enterToSend,showTimestamps:true,autoTitles:true,keepAttachmentContext:true,studyStyle:'focused blocks',quizDifficulty:'medium',displayName:'Student'};
  }
};
let preferences = savedPreferences();
let pendingAttachment = null;
let themeMediaQuery;
let currentStudyPlans = [];
const fileTypes = new Set(['pdf','docx','txt','md','csv','py']);
const baseSendMessage = sendMessage;
const baseRenderMessage = renderMessage;
const baseRenderWorkspace = renderWorkspace;
const baseRenderDocumentList = renderDocumentList;

function savePreferences(){localStorage.setItem('sage-preferences',JSON.stringify(preferences));}
function formatBytes(bytes){if(bytes<1024)return `${bytes} B`;if(bytes<1024*1024)return `${(bytes/1024).toFixed(0)} KB`;return `${(bytes/1024/1024).toFixed(1)} MB`;}
function startPrompt(prompt){showView('chat');input.value=prompt;input.focus();input.dispatchEvent(new Event('input',{bubbles:true}));}

function renderExplore(){
  const actions=[
    ['Explain a topic','Build a clear explanation with an example.','Explain [topic] step by step, then give a simple example.'],
    ['Exam answer','Prepare a structured answer for an exam.','Write an exam-ready answer about [topic] with clear headings.'],
    ['Summarize notes','Turn study material into revision points.','Summarize these notes into the key ideas and terms: '],
    ['Quiz me','Check recall with questions and an answer key.','Quiz me on [topic]. Ask one question at a time and check my answer.'],
    ['Flashcards','Make question-and-answer cards for review.','Create concise question-and-answer flashcards for [topic].'],
    ['Study plan','Turn a goal into a practical schedule.','Create a study plan for [subject] over [timeframe].'],
    ['Ask my documents','Answer from the uploaded study library.','Answer using my uploaded study materials: '],
    ['Practice questions','Generate targeted practice questions.','Create practice questions on [topic], from basic to challenging.'],
    ['Simplify an explanation','Make a difficult idea easier to follow.','Explain this in beginner-friendly language, keeping the important ideas: ']
  ];
  page('Explore','Choose a study action to start in your SAGE chat.',`<div class="upgrade-grid">${actions.map(([title,copy,prompt])=>`<article class="upgrade-card"><h3>${title}</h3><p>${copy}</p><button type="button" data-explore-prompt="${escapeHtml(prompt)}">Start</button></article>`).join('')}</div>`);
  document.querySelectorAll('[data-explore-prompt]').forEach(button=>button.onclick=()=>startPrompt(button.dataset.explorePrompt));
}

function renderTemplates(){
  const templates=[
    ['Explain simply','Explain [topic] in plain language and give one example.'],
    ["Explain like I'm a beginner","Explain [topic] from the basics, define unfamiliar terms, and use a simple example."],
    ['2-mark answer','Write a concise 2-mark answer about [topic].'],
    ['5-mark answer','Write a structured 5-mark answer about [topic], with key points.'],
    ['10-mark answer','Write a detailed 10-mark answer about [topic], with headings and examples.'],
    ['16-mark answer','Write a comprehensive 16-mark answer about [topic], with an introduction and conclusion.'],
    ['Important points','List the most important points to remember about [topic].'],
    ['Short revision notes','Make short revision notes for [topic] using clear headings and bullets.'],
    ['Summary','Summarize [topic or pasted material] into its key ideas.'],
    ['Quiz','Create a quiz about [topic] and put the answer key separately.'],
    ['Flashcards','Create question-and-answer flashcards for [topic].'],
    ['Compare two concepts','Compare [concept A] and [concept B] in a clear table, then explain the key difference.'],
    ['Give an example','Give a practical example of [concept] and explain why it fits.'],
    ['Last-minute revision','Create a last-minute revision sheet for [topic] with formulas, definitions, and likely exam points.']
  ];
  page('Templates','Pick a starting point, then edit the prompt in chat.',`<div class="upgrade-grid">${templates.map(([title,prompt])=>`<article class="upgrade-card"><h3>${title}</h3><p>${escapeHtml(prompt)}</p><button type="button" data-template-prompt="${escapeHtml(prompt)}">Use</button></article>`).join('')}</div>`);
  document.querySelectorAll('[data-template-prompt]').forEach(button=>button.onclick=()=>startPrompt(button.dataset.templatePrompt));
}

let selectedNote = null;
async function renderNotes(){
  page('Notes','Create, organize, and use your saved study notes.',`<div class="upgrade-toolbar"><button class="upgrade-action" id="note-create">New note</button><input id="note-search" type="search" placeholder="Search title, subject, or note" aria-label="Search notes"></div><div id="note-form-slot"></div><div class="upgrade-list" id="notes-list"><div class="upgrade-empty">Loading notes...</div></div><div class="upgrade-card note-detail" id="note-detail"><h3>Select a note</h3><p>Open a note to read it, edit it, or ask SAGE about it.</p></div>`);
  $('note-create').onclick=()=>showNoteEditor();
  $('note-search').oninput=()=>renderNotesList($('note-search').value);
  await renderNotesList('');
}
async function renderNotesList(query){
  const list=$('notes-list');if(!list)return;list.innerHTML='<div class="upgrade-empty">Loading notes...</div>';
  try{
    const notes=await api(`/api/notes${query?`?q=${encodeURIComponent(query)}`:''}`);
    if(!notes.length){list.innerHTML=`<div class="upgrade-empty">${query?'No notes match your search.':'No notes yet. Create a note to keep useful study material here.'}</div>`;return;}
    list.innerHTML=notes.map(note=>`<article class="upgrade-row"><div class="upgrade-row-main"><strong>${escapeHtml(note.title)}</strong><small>${escapeHtml(note.subject||'General')} · ${formatDate(note.created_at)}</small><p>${escapeHtml(note.content.slice(0,180))}${note.content.length>180?'…':''}</p></div><div class="upgrade-row-actions"><button data-note-view="${note.id}">View</button><button data-note-ask="${note.id}">Ask SAGE</button><button data-note-edit="${note.id}">Edit</button><button data-note-delete="${note.id}">Delete</button></div></article>`).join('');
    list.querySelectorAll('[data-note-view]').forEach(button=>button.onclick=()=>viewNote(notes.find(note=>note.id===Number(button.dataset.noteView))));
    list.querySelectorAll('[data-note-ask]').forEach(button=>button.onclick=()=>{const note=notes.find(item=>item.id===Number(button.dataset.noteAsk));startPrompt(`Use this saved note to help answer my question.\n\nNote: ${note.title}\n${note.content}\n\nQuestion: `)});
    list.querySelectorAll('[data-note-edit]').forEach(button=>button.onclick=()=>showNoteEditor(notes.find(note=>note.id===Number(button.dataset.noteEdit))));
    list.querySelectorAll('[data-note-delete]').forEach(button=>button.onclick=async()=>{if(!confirm('Delete this note?'))return;button.disabled=true;try{await api(`/api/notes/${button.dataset.noteDelete}`,{method:'DELETE'});if(selectedNote?.id===Number(button.dataset.noteDelete))selectedNote=null;toast('Note deleted.');await renderNotesList(query);if(!selectedNote)viewNote(null)}catch{button.disabled=false;toast('SAGE could not delete this note.')}});
  }catch{list.innerHTML='<div class="upgrade-empty">Notes could not be loaded. Check your connection and try again.</div>';toast('SAGE could not load notes.');}
}
function viewNote(note){selectedNote=note||null;const detail=$('note-detail');if(!detail)return;if(!note){detail.innerHTML='<h3>Select a note</h3><p>Open a note to read it, edit it, or ask SAGE about it.</p>';return;}detail.innerHTML=`<h3>${escapeHtml(note.title)}</h3><p>${escapeHtml(note.subject||'General')} · ${formatDate(note.created_at)}</p><p>${escapeHtml(note.content).replace(/\n/g,'<br>')}</p>`;}
function showNoteEditor(note=null){
  const slot=$('note-form-slot');if(!slot)return;slot.innerHTML=`<section class="upgrade-card"><h3>${note?'Edit note':'New note'}</h3><form class="upgrade-form" id="note-editor"><label>Title<input name="title" required maxlength="255" value="${escapeHtml(note?.title||'')}"></label><label>Subject<input name="subject" maxlength="100" value="${escapeHtml(note?.subject||'')}"></label><label>Note<textarea name="content" required maxlength="50000">${escapeHtml(note?.content||'')}</textarea></label><div class="upgrade-toolbar"><button class="upgrade-action">Save note</button><button type="button" class="upgrade-action secondary" id="note-cancel">Cancel</button></div></form></section>`;
  $('note-cancel').onclick=()=>slot.replaceChildren();
  $('note-editor').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));try{await api(note?`/api/notes/${note.id}`:'/api/notes',{method:note?'PATCH':'POST',body:JSON.stringify(data)});slot.replaceChildren();toast(note?'Note updated.':'Note saved.');await renderNotesList($('note-search').value);}catch{toast('SAGE could not save this note.');}};
}

function taskSection(title,tasks){return `<section class="task-section"><h2>${title} <span class="priority-pill">${tasks.length}</span></h2>${tasks.length?`<div class="upgrade-list">${tasks.map(task=>`<article class="upgrade-row"><div class="upgrade-row-main"><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.subject||'General')} · ${task.scheduled_at?formatDate(task.scheduled_at):'No due date'} · <span class="priority-pill ${task.priority==='high'?'high':''}">${escapeHtml(task.priority||'medium')} priority</span></small><p>${escapeHtml(task.description||'')}</p></div><div class="upgrade-row-actions"><button data-task-complete="${task.id}">${task.completed?'Reopen':'Complete'}</button><button data-task-edit="${task.id}">Edit</button><button data-task-delete="${task.id}">Delete</button></div></article>`).join('')}</div>`:'<div class="upgrade-empty">Nothing here yet.</div>'}</section>`;}
async function renderPlans(){
  page('Study Plan','Plan your next study blocks and track progress.',`<div class="upgrade-toolbar"><button class="upgrade-action" id="task-create">Create task</button><input id="plan-request" placeholder="I have 3 days to prepare for OS" aria-label="Describe your study goal"><button class="upgrade-action secondary" id="plan-generate">Ask SAGE</button></div><div id="task-form-slot"></div><div id="plan-status" role="status"></div><div id="plan-progress"></div><div id="plan-groups"><div class="upgrade-empty">Loading your study plan...</div></div>`);
  $('task-create').onclick=()=>showTaskEditor();$('plan-generate').onclick=createPlanFromRequest;await refreshPlans();
}
async function refreshPlans(){
  const groups=$('plan-groups');if(!groups)return;groups.innerHTML='<div class="upgrade-empty">Loading your study plan...</div>';
  try{
    currentStudyPlans=await api('/api/study-plans');
    const completed=currentStudyPlans.filter(task=>task.completed),active=currentStudyPlans.filter(task=>!task.completed);
    const today=new Date().toISOString().slice(0,10);
    const todayTasks=active.filter(task=>task.scheduled_at?.slice(0,10)===today);
    const overdue=active.filter(task=>task.scheduled_at&&task.scheduled_at.slice(0,10)<today);
    const upcoming=active.filter(task=>!task.scheduled_at||task.scheduled_at.slice(0,10)>today);
    const progress=currentStudyPlans.length?Math.round(completed.length/currentStudyPlans.length*100):0;
    $('plan-progress').innerHTML=`<div class="upgrade-message">${completed.length} of ${currentStudyPlans.length} tasks complete · ${progress}%</div><div class="upgrade-progress"><span style="width:${progress}%"></span></div>`;
    groups.innerHTML=taskSection('Overdue tasks',overdue)+taskSection("Today's tasks",todayTasks)+taskSection('Upcoming tasks',upcoming)+taskSection('Completed tasks',completed);
    groups.querySelectorAll('[data-task-complete]').forEach(button=>button.onclick=async()=>{try{await api(`/api/study-plans/${button.dataset.taskComplete}?completed=${button.textContent==='Reopen'?'false':'true'}`,{method:'PATCH'});await refreshPlans();toast('Study task updated.')}catch{toast('SAGE could not update this task.')}});
    groups.querySelectorAll('[data-task-edit]').forEach(button=>button.onclick=()=>showTaskEditor(currentStudyPlans.find(task=>task.id===Number(button.dataset.taskEdit))));
    groups.querySelectorAll('[data-task-delete]').forEach(button=>button.onclick=async()=>{if(!confirm('Delete this study task?'))return;try{await api(`/api/study-plans/${button.dataset.taskDelete}`,{method:'DELETE'});await refreshPlans();toast('Study task deleted.')}catch{toast('SAGE could not delete this task.')}});
  }catch{groups.innerHTML='<div class="upgrade-empty">Study tasks could not be loaded. Check your connection and try again.</div>';toast('SAGE could not load study plans.');}
}
function showTaskEditor(task=null){
  const slot=$('task-form-slot');if(!slot)return;const due=task?.scheduled_at?new Date(task.scheduled_at).toISOString().slice(0,16):'';
  slot.innerHTML=`<section class="upgrade-card"><h3>${task?'Edit task':'New study task'}</h3><form class="upgrade-form" id="task-editor"><label>Task<input name="title" required maxlength="255" value="${escapeHtml(task?.title||'')}"></label><label>Subject or topic<input name="subject" maxlength="100" value="${escapeHtml(task?.subject||'')}"></label><label>Notes<textarea name="description" maxlength="50000">${escapeHtml(task?.description||'')}</textarea></label><label>Due date<input name="scheduled_at" type="datetime-local" value="${due}"></label><label>Priority<select name="priority"><option value="low" ${task?.priority==='low'?'selected':''}>Low</option><option value="medium" ${!task||task.priority==='medium'?'selected':''}>Medium</option><option value="high" ${task?.priority==='high'?'selected':''}>High</option></select></label><div class="upgrade-toolbar"><button class="upgrade-action">Save task</button><button type="button" id="task-cancel" class="upgrade-action secondary">Cancel</button></div></form></section>`;
  $('task-cancel').onclick=()=>slot.replaceChildren();
  $('task-editor').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));if(!data.scheduled_at)data.scheduled_at=null;try{await api(task?`/api/study-plans/${task.id}`:'/api/study-plans',{method:task?'PATCH':'POST',body:JSON.stringify(data)});slot.replaceChildren();await refreshPlans();toast(task?'Study task updated.':'Study task saved.');}catch{toast('SAGE could not save this task.');}};
}
async function createPlanFromRequest(){
  const request=$('plan-request').value.trim();if(!request)return toast('Describe your study goal first.');
  const button=$('plan-generate');button.disabled=true;$('plan-status').textContent='SAGE is preparing and saving your study plan...';
  try{
    const result=await api('/api/study-plans/from-request',{method:'POST',body:JSON.stringify({request,priority:'medium'})});
    $('plan-status').textContent=`Saved ${result.tasks.length} ${result.tasks.length===1?'task':'tasks'} to your study plan.`;toast('Study plan saved.');await refreshPlans();
  }catch{$('plan-status').textContent='SAGE could not create the study task. Try again.';}
  finally{button.disabled=false;}
}

async function renderMemory(){
  page('Memory','SAGE can keep study preferences and goals you choose to save.',`<div class="upgrade-toolbar"><button class="upgrade-action" id="memory-create">Add memory</button><input id="memory-search" type="search" placeholder="Search saved context" aria-label="Search memories"><select id="memory-category" aria-label="Filter memory category"><option value="">All categories</option></select></div><div class="upgrade-message">Saved memory is used to make future study help more relevant. You can review or remove it here.</div><div id="memory-list" class="upgrade-list"><div class="upgrade-empty">Loading saved memories...</div></div>`);
  $('memory-create').onclick=showMemoryEditor;$('memory-search').oninput=renderMemoryList;$('memory-category').onchange=renderMemoryList;await renderMemoryList();
}
let allMemories=[];
async function renderMemoryList(){
  const list=$('memory-list');if(!list)return;list.innerHTML='<div class="upgrade-empty">Loading saved memories...</div>';
  try{
    const query=$('memory-search').value.trim();const selectedCategory=$('memory-category').value;allMemories=await api(`/api/memories${query?`?q=${encodeURIComponent(query)}`:''}`);
    const categories=[...new Set(allMemories.map(item=>item.memory_type))];$('memory-category').innerHTML='<option value="">All categories</option>'+categories.map(category=>`<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join('');
    $('memory-category').value=categories.includes(selectedCategory)?selectedCategory:'';
    const category=$('memory-category').value;const entries=allMemories.filter(item=>!category||item.memory_type===category);
    list.innerHTML=entries.length?entries.map(item=>`<article class="upgrade-row"><div class="upgrade-row-main"><strong>${escapeHtml(item.memory_type)}</strong><small>${formatDate(item.created_at)} · Importance ${item.importance}</small><p>${escapeHtml(item.content)}</p></div><div class="upgrade-row-actions"><button data-memory-delete="${item.id}">Delete</button></div></article>`).join(''):'<div class="upgrade-empty">No saved memories match this view.</div>';
    list.querySelectorAll('[data-memory-delete]').forEach(button=>button.onclick=async()=>{try{await api(`/api/memories/${button.dataset.memoryDelete}`,{method:'DELETE'});toast('Memory deleted.');await renderMemoryList();}catch{toast('SAGE could not delete this memory.')}});
  }catch{list.innerHTML='<div class="upgrade-empty">Memory could not be loaded. Check your connection and try again.</div>';toast('SAGE could not load memory.');}
}
function showMemoryEditor(){
  const list=$('memory-list');if(!list)return;const form=document.createElement('section');form.className='upgrade-card';form.innerHTML='<h3>Add a memory</h3><form class="upgrade-form" id="memory-editor"><label>Category<input name="memory_type" maxlength="50" value="study"></label><label>What should SAGE remember?<textarea name="content" required maxlength="10000"></textarea></label><label>Importance<input name="importance" type="number" min="0" max="10" step="0.5" value="1"></label><button class="upgrade-action">Save memory</button></form>';list.before(form);
  $('memory-editor').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));data.importance=Number(data.importance);try{await api('/api/memories',{method:'POST',body:JSON.stringify(data)});form.remove();toast('Memory saved.');await renderMemoryList();}catch{toast('SAGE could not save this memory.');}};
}

function settingSelect(label,key,options,value){return `<label class="setting-control"><span>${label}</span><select data-pref="${key}">${options.map(([option,title])=>`<option value="${option}" ${value===option?'selected':''}>${title}</option>`).join('')}</select></label>`;}
function settingToggle(label,key,value){return `<label class="setting-control"><span>${label}</span><input type="checkbox" data-pref="${key}" ${value?'checked':''}></label>`;}
function applyThemeMode(mode){
  const effective=mode==='system'?(themeMediaQuery?.matches?'dark':'light'):mode;state.theme=effective;document.documentElement.dataset.theme=effective;localStorage.setItem('sage-theme',effective);localStorage.setItem('sage-theme-mode',mode);$('theme-label').textContent=effective==='dark'?'Light mode':'Dark mode';
}
function renderSettings(){
  preferences=savedPreferences();const themeMode=localStorage.getItem('sage-theme-mode')||state.theme;
  page('Settings','Set how SAGE looks and supports your study sessions.',`<section class="settings-section"><h2>Appearance</h2><div class="settings-grid">${settingSelect('Theme','themeMode',[['light','Light'],['dark','Dark'],['system','System']],themeMode)}${settingSelect('Chat density','density',[['comfortable','Comfortable'],['compact','Compact']],localStorage.getItem('sage-density')||'comfortable')}</div></section><section class="settings-section"><h2>AI and study preferences</h2><div class="settings-grid">${settingSelect('Response style','responseStyle',[['simple','Simple'],['balanced','Balanced'],['detailed','Detailed']],preferences.responseStyle)}${settingSelect('Answer length','answerLength',[['short','Short'],['medium','Medium'],['detailed','Detailed']],preferences.answerLength)}${settingSelect('Default exam answer','defaultExamMode',[['2','2 marks'],['5','5 marks'],['10','10 marks'],['16','16 marks']],preferences.defaultExamMode)}${settingToggle('Beginner-friendly explanations','beginnerFriendly',preferences.beginnerFriendly)}${settingToggle('Prefer uploaded materials','preferUploadedMaterials',preferences.preferUploadedMaterials)}${settingToggle('Name sources when available','showSources',preferences.showSources)}</div></section><section class="settings-section"><h2>Chat</h2><div class="settings-grid">${settingToggle('Enter to send','enterToSend',preferences.enterToSend)}${settingToggle('Show timestamps','showTimestamps',preferences.showTimestamps)}${settingToggle('Generate conversation titles','autoTitles',preferences.autoTitles)}${settingToggle('Keep attachment context in this conversation','keepAttachmentContext',preferences.keepAttachmentContext)}</div></section><section class="settings-section"><h2>Study</h2><div class="settings-grid">${settingSelect('Default study style','studyStyle',[['focused blocks','Focused blocks'],['short sessions','Short sessions'],['deep work','Deep work']],preferences.studyStyle)}${settingSelect('Quiz difficulty','quizDifficulty',[['easy','Easy'],['medium','Medium'],['hard','Hard']],preferences.quizDifficulty)}</div><p class="upgrade-message">Study-plan reminders are available through SAGE, but browser notifications are not configured in this workspace.</p></section><section class="settings-section"><h2>Data and profile</h2><div class="upgrade-form"><label>Display name<input id="display-name" maxlength="100" value="${escapeHtml(preferences.displayName)}"></label><div class="upgrade-toolbar"><button class="upgrade-action secondary" id="settings-export">Export workspace data</button><button class="upgrade-action secondary" id="settings-clear-completed">Clear completed tasks</button><button class="upgrade-action secondary" id="settings-clear-history">Clear conversation history</button></div></div></section>`);
  $('view-workspace').onchange=event=>{const control=event.target.closest('[data-pref]');if(!control)return;const key=control.dataset.pref;if(key==='themeMode'){applyThemeMode(control.value);return}if(key==='density'){localStorage.setItem('sage-density',control.value);document.documentElement.dataset.density=control.value;return}preferences[key]=control.type==='checkbox'?control.checked:control.value;if(key==='enterToSend')state.enterToSend=preferences.enterToSend;savePreferences();document.documentElement.dataset.showTimestamps=String(preferences.showTimestamps);};
  $('display-name').onchange=event=>{preferences.displayName=event.target.value.trim()||'Student';localStorage.setItem('sage-display-name',preferences.displayName);savePreferences();const name=document.querySelector('.profile-copy strong');if(name)name.textContent=preferences.displayName;};
  $('settings-export').onclick=exportWorkspaceData;
  $('settings-clear-history').onclick=()=>$('clear-history').click();
  $('settings-clear-completed').onclick=clearCompletedTasks;
  document.documentElement.dataset.density=localStorage.getItem('sage-density')||'comfortable';document.documentElement.dataset.showTimestamps=String(preferences.showTimestamps);
}
async function exportWorkspaceData(){
  try{const [conversations,notes,plans,memories,documents]=await Promise.all([api('/api/conversations'),api('/api/notes'),api('/api/study-plans'),api('/api/memories'),api('/api/documents')]);const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),conversations,notes,study_plans:plans,memories,documents},null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='sage-workspace-export.json';link.click();URL.revokeObjectURL(link.href);toast('Workspace data exported.');}catch{toast('SAGE could not export workspace data.');}
}
async function clearCompletedTasks(){try{const plans=await api('/api/study-plans');await Promise.all(plans.filter(task=>task.completed).map(task=>api(`/api/study-plans/${task.id}`,{method:'DELETE'})));toast('Completed tasks cleared.');if(state.view==='study')await refreshPlans();}catch{toast('SAGE could not clear completed tasks.');}}
function agentPreferences(){return {response_style:preferences.responseStyle,answer_length:preferences.answerLength,default_exam_mode:preferences.defaultExamMode,beginner_friendly:preferences.beginnerFriendly,prefer_uploaded_materials:preferences.preferUploadedMaterials,show_sources:preferences.showSources,study_style:preferences.studyStyle,quiz_difficulty:preferences.quizDifficulty};}

function attachmentFromContent(content){
  const marker='\n\n<!--sage-attachments:';const index=content.lastIndexOf(marker);if(index<0||!content.endsWith('-->'))return {content,attachments:[]};
  try{return {content:content.slice(0,index),attachments:JSON.parse(content.slice(index+marker.length,-3))};}catch{return {content,attachments:[]};}
}
renderMessage=function(message){
  const parsed=typeof message.content==='string'?attachmentFromContent(message.content):{content:message.content,attachments:[]};
  baseRenderMessage({...message,content:parsed.content});
  const attachments=message.attachments||parsed.attachments;if(!attachments.length)return;
  const body=messages.lastElementChild?.querySelector('.message-body');if(!body)return;
  const row=document.createElement('div');row.className='message-attachments';row.innerHTML=attachments.map(item=>`<span class="message-attachment-chip"><span>📎 ${escapeHtml(item.filename)}<small>${escapeHtml(String(item.file_type||'file').toUpperCase())} · ${formatBytes(Number(item.size)||0)}</small></span></span>`).join('');
  body.insertBefore(row,body.querySelector('.message-time'));
};

function renderAttachmentPreview(status='Ready to send'){
  const preview=$('chat-attachments');if(!preview)return;preview.hidden=!pendingAttachment;if(!pendingAttachment){preview.innerHTML='';return;}
  const file=pendingAttachment;preview.innerHTML=`<div class="chat-attachment-chip"><span>📎 ${escapeHtml(file.name)}<small>${escapeHtml(file.name.split('.').pop().toUpperCase())} · ${formatBytes(file.size)} · ${status}</small></span><button type="button" id="remove-chat-attachment" aria-label="Remove ${escapeHtml(file.name)}" title="Remove attachment">×</button></div>`;
  $('remove-chat-attachment').onclick=()=>{pendingAttachment=null;$('file-input').value='';renderAttachmentPreview();};
}
$('attach-btn').onclick=()=>$('file-input').click();
$('file-input').onchange=event=>{
  const file=event.target.files[0];if(!file)return;const extension=file.name.split('.').pop().toLowerCase();
  if(!fileTypes.has(extension)){toast('Choose PDF, DOCX, TXT, Markdown, CSV, or Python.');event.target.value='';return;}
  if(file.size>10*1024*1024){toast('Attachments must be 10 MB or smaller.');event.target.value='';return;}
  pendingAttachment=file;renderAttachmentPreview();
};
sendMessage=async function(text){
  if(!pendingAttachment)return baseSendMessage(text);
  if(state.loading||!text.trim()){if(!text.trim())toast('Add a question before sending the attachment.');return;}
  const file=pendingAttachment;state.loading=true;state.abort=new AbortController();$('stop-btn').hidden=false;$('welcome').hidden=true;
  renderMessage({role:'user',content:text,created_at:Date.now(),attachments:[{filename:file.name,file_type:file.name.split('.').pop(),size:file.size}]});
  const waiting=document.createElement('article');waiting.className='message assistant';waiting.innerHTML='<div class="message-avatar"><img src="/assets/sage-logo.png" alt="SAGE"></div><div class="message-body typing">Reading attachment and preparing an answer...</div>';messages.appendChild(waiting);
  renderAttachmentPreview('Processing...');input.value='';input.style.height='auto';
  const form=new FormData();form.append('message',text);form.append('file',file);if(state.activeId)form.append('conversation_id',state.activeId);form.append('preferences',JSON.stringify(agentPreferences()));form.append('auto_title',String(preferences.autoTitles));
  try{
    const result=await api('/api/chat/attachments',{method:'POST',body:form,signal:state.abort.signal});state.activeId=result.conversation_id;waiting.remove();renderMessage({role:'assistant',content:result.response,created_at:Date.now()});const detail=await api(`/api/conversations/${state.activeId}`);$('conversation-title').textContent=detail.title;pendingAttachment=null;$('file-input').value='';renderAttachmentPreview();await loadHistory();messages.scrollTop=messages.scrollHeight;
  }catch(error){waiting.remove();if(error.name!=='AbortError')toast('SAGE could not process this attachment. Try again.');renderAttachmentPreview('Not sent');}
  finally{state.loading=false;state.abort=null;$('stop-btn').hidden=true;input.focus();}
};
$('composer').onsubmit=event=>{event.preventDefault();sendMessage(input.value);};

renderDocumentList=async function(query){
  await baseRenderDocumentList(query);
  document.querySelectorAll('[data-document-delete]').forEach(remove=>{const actions=remove.parentElement;if(!actions||actions.querySelector('[data-document-open]'))return;const ask=actions.querySelector('[data-ask-document]');const filename=ask?.dataset.askDocument;if(!filename)return;const open=document.createElement('button');open.type='button';open.dataset.documentOpen='true';open.textContent='View';open.title='Open this study material';open.onclick=()=>window.open(`/api/documents/${encodeURIComponent(filename)}/open`,'_blank','noopener');actions.prepend(open);});
};

renderSettingsPreferences=function(){};
themeMediaQuery=window.matchMedia('(prefers-color-scheme: dark)');
themeMediaQuery.addEventListener?.('change',()=>{if(localStorage.getItem('sage-theme-mode')==='system')applyThemeMode('system');});
toggleTheme=function(){const effective=state.theme==='dark'?'light':'dark';applyThemeMode(effective);if(state.view==='settings')renderSettings();};
document.documentElement.dataset.density=localStorage.getItem('sage-density')||'comfortable';
document.documentElement.dataset.showTimestamps=String(preferences.showTimestamps);
const displayName=document.querySelector('.profile-copy strong');if(displayName)displayName.textContent=preferences.displayName;
state.enterToSend=preferences.enterToSend;

renderWorkspace=function(view){
  if(view==='explore')return renderExplore();
  if(view==='templates')return renderTemplates();
  if(view==='notes')return renderNotes();
  if(view==='study')return renderPlans();
  if(view==='memory')return renderMemory();
  if(view==='settings')return renderSettings();
  return baseRenderWorkspace(view);
};

if(localStorage.getItem('sage-theme-mode')==='system')applyThemeMode('system');