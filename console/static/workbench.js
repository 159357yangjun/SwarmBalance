/* MVP-01 UI: all project, run and result data comes from /api/mvp. */
(() => {
  'use strict';
  const core = window.WorkbenchCore;
  const $ = id => document.getElementById(id);
  const state = {defaults:null, project:null, dirty:false, busy:false, projects:[], runs:[], run:null, result:null};
  const projectsGate = core.requestGate(), runsGate = core.requestGate(), resultGate = core.requestGate();
  let pollTimer, page = 'projects';
  const active = run => run && ['queued','running','stopping'].includes(run.status);
  const statusText = status => ({queued:'等待启动',running:'运行中',stopping:'正在停止',stopped:'已停止',completed:'已完成',failed:'运行失败',interrupted:'服务重启中断'})[status] || status;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const get = (value, path) => path.split('.').reduce((obj,key) => obj?.[key], value);
  const date = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
  const storage = {get(key){try{return localStorage.getItem('swarm-mvp-'+key);}catch{return null;}},set(key,value){try{localStorage.setItem('swarm-mvp-'+key,value);}catch{/* Private mode still works. */}}};
  function tell(message, error=false) {
    $(error?'error':'notice').textContent = message;
    $(error?'error':'notice').hidden = !message;
    $(error?'notice':'error').hidden = true;
  }
  function connection(online) {
    $('connection').textContent = online ? '本地服务已连接' : '本地服务连接中断';
    $('connection').className = 'connection ' + (online?'online':'offline');
  }
  async function api(path, options={}) {
    const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),20000);
    let response;
    try {
      response = await fetch('/api/mvp'+path, {...options, signal:controller.signal,
        headers:{'Content-Type':'application/json',...options.headers}});
      connection(true);
      const body = await response.json();
      if (!response.ok) throw new Error(core.errorMessage(response.status,body.detail));
      return body;
    } catch(error) {
      if (!response) {
        connection(false);
        throw new Error('无法连接本地服务或请求超时。请确认服务正在运行；输入已保留。可刷新项目与运行记录核对提交是否成功。');
      }
      throw error;
    } finally {clearTimeout(timeout);}
  }
  function summary(project) {
    if (!project) return '请先创建并保存项目。';
    const sim = project.simulation, tasks = sim.task_generation;
    return `${sim.environment.num_drones} 架${sim.heterogeneous.enabled?'异构':'同质'}无人机 · ${sim.environment.episode_max_steps} 步 · ${tasks.mode==='realistic'?tasks.realistic.total_tasks+' 个任务':'持续任务流'} · ${project.algorithm} · seed ${project.seed}`;
  }
  function context() {
    const project = state.project, saved = Boolean(project?.project_id);
    $('context-name').textContent = project?.name || '未命名项目';
    $('save-state').textContent = state.dirty ? '有未保存修改' : saved ? '已保存到本地' : '尚未保存';
    $('save-state').className = 'tag' + (state.dirty?' dirty':'');
    $('run-project-name').textContent = project?.name || '尚未选择项目';
    $('run-config-summary').textContent = summary(project);
    $('unsaved-warning').hidden = !state.dirty;
    $('start-run').disabled = state.busy || !saved || state.dirty || active(state.run);
    $('stop-run').disabled = state.busy || !active(state.run) || state.run?.status==='stopping';
    $('download-result').disabled = !state.result || state.busy;
    $('save-project').disabled = $('save-config').disabled = !project || state.busy;
  }
  function dirty() {state.dirty = true; context();}
  function renderEditor() {
    const project = state.project;
    $('project-name').value = project.name;
    for (const input of document.querySelectorAll('[data-field]')) {
      let value = get(project,input.dataset.field);
      if (input.dataset.field==='algorithm_parameters.accept_probability' && value==null)
        value = core.effectiveProbability(project);
      if (input.type==='checkbox') input.checked = Boolean(value);
      else input.value = value ?? '';
    }
    $('fleet-mix').textContent = '原配比：' + Object.entries(project.simulation.heterogeneous.fleet_mix).map(([key,value])=>`${key} × ${value}`).join(' / ');
    $('nest-fields').innerHTML = project.simulation.charging_stations.map((nest,index)=>`<tr><td>${esc(nest.station_id)}</td>${['x','y','swap_time_seconds'].map(key=>`<td><input aria-label="机巢 ${esc(nest.station_id)} ${key}" data-testid="nest-${index}-${key}" data-nest="${index}" data-key="${key}" type="number" ${key==='swap_time_seconds'?'min="0.001"':''} step="any" required value="${esc(nest[key] ?? project.simulation.nest.swap_time_seconds)}"></td>`).join('')}</tr>`).join('');
    context();
  }
  function collect() {
    if (!$('project-form').checkValidity()) {showPage('projects');$('project-form').reportValidity();throw new Error('请填写有效项目名称。');}
    if (!$('config-form').checkValidity()) {showPage('config');$('config-form').reportValidity();throw new Error('请检查必填字段与数值范围。');}
    const fields = {name:$('project-name').value};
    for (const input of document.querySelectorAll('[data-field]')) fields[input.dataset.field] = input.type==='checkbox'?input.checked:input.value;
    const project = core.applyFields(state.project, fields);
    for (const input of document.querySelectorAll('[data-nest]')) {
      if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error('机巢坐标与换电时长必须是有限数值');
      project.simulation.charging_stations[Number(input.dataset.nest)][input.dataset.key] = Number(input.value);
    }
    return project;
  }
  async function write(operation) {
    if (state.busy) return;
    state.busy = true;
    document.body.inert = true;
    document.body.classList.add('busy');
    const controls = [...document.querySelectorAll('button,input,select')].map(element=>[element,element.disabled]);
    controls.forEach(([element])=>element.disabled=true);
    try {await operation();} catch(error) {tell(error.message,true);}
    finally {
      state.busy = false;document.body.classList.remove('busy');
      document.body.inert = false;
      controls.forEach(([element,disabled])=>{if(element.isConnected)element.disabled=disabled;});
      context();
    }
  }
  async function refreshProjects() {
    state.projects = (await api('/projects')).projects;
    $('project-count').textContent = String(state.projects.length).padStart(2,'0');
    $('project-list').innerHTML = state.projects.length ? state.projects.map(project=>`<article class="project-row ${project.project_id===state.project?.project_id?'selected':''}"><div><h3>${esc(project.name)}</h3><p>${esc(summary(project))}</p></div><time datetime="${esc(project.updated_at)}">${esc(date(project.updated_at))}</time><button class="text-button" data-open-project="${project.project_id}" data-testid="open-project-${project.project_id}" aria-label="打开项目 ${esc(project.name)}">打开 ↗</button></article>`).join('') : '<p class="empty">还没有保存的项目。在上方为第一个项目命名。</p>';
  }
  function cancelRunContext() {
    clearTimeout(pollTimer);runsGate.next();resultGate.next();refreshRuns.sequence++;
    state.run = state.result = null; state.runs=[];
    renderRun();renderRunLists();renderResult(null);
  }
  async function openProject(id, silent=false) {
    if (!silent && state.dirty && !window.confirm('当前有未保存修改，打开其他项目将放弃这些输入。继续吗？')) return;
    const token = projectsGate.next();
    const project = await api('/projects/'+id);
    if (!projectsGate.current(token)) return;
    cancelRunContext();state.project=project;state.dirty=false;
    storage.set('project',id);renderEditor();await refreshRuns();
    if (projectsGate.current(token)) {await refreshProjects();if(!silent)tell('已打开项目：'+project.name);}
  }
  async function saveProject() {
    const project = collect(), id=project.project_id;
    const saved = await api(id?'/projects/'+id:'/projects',{method:id?'PUT':'POST',body:JSON.stringify(project)});
    state.project=saved;state.dirty=false;storage.set('project',saved.project_id);
    renderEditor();await refreshProjects();await refreshRuns();
    tell('项目与完整配置已保存，可在运行区开始仿真。');
  }
  function newProject() {
    if (!state.defaults) {tell('尚未读取默认配置，请先恢复本地服务并刷新页面。',true);return;}
    if (state.dirty && !window.confirm('放弃当前未保存修改并新建项目？')) return;
    projectsGate.next();cancelRunContext();state.project=core.newProject(state.defaults);state.dirty=false;
    storage.set('project','');renderEditor();showPage('projects');tell('填写名称并保存，创建一个真实项目。');
    $('project-name').focus();
  }
  function renderRun() {
    const run=state.run;
    $('run-status').textContent=run?statusText(run.status):'尚未运行';
    $('run-id').textContent=run?.run_id || '无运行记录';
    const progress = run && Number.isFinite(run.progress) ? Math.max(0,Math.min(1,run.progress)):null;
    $('run-progress-number').innerHTML=(progress===null?'—':(progress*100).toFixed(1))+'<span>%</span>';
    $('run-progress').value=progress??0;
    $('run-steps').textContent=run?`${run.step??0} / ${run.total_steps??'—'} 步`:'— / — 步';
    $('run-error').textContent=run?.error || (run?.status==='interrupted'?'上次运行因服务重启中断，请重新启动仿真。':['stopped','stopping'].includes(run?.status)?'停止的运行保留状态与输入记录，不生成完整结果。':'');
    context();
  }
  function renderRunLists() {
    $('run-list').innerHTML=state.runs.length?state.runs.map(run=>`<article class="run-row"><div><p class="mono">${esc(run.run_id)}</p><p class="hint">${esc(date(run.created_at))} · seed ${esc(run.seed)}</p></div><span>${esc(statusText(run.status))}</span><button class="text-button" data-open-run="${run.run_id}" aria-label="查看运行 ${run.run_id}">查看 ↗</button></article>`).join(''):'<p class="empty">此项目还没有运行记录。</p>';
    const selected=$('result-run').value;
    $('result-run').innerHTML='<option value="">选择一条运行记录</option>'+state.runs.map(run=>`<option value="${run.run_id}">${esc(date(run.created_at))} · ${esc(statusText(run.status))} · ${run.run_id.slice(0,10)}</option>`).join('');
    if(state.runs.some(run=>run.run_id===selected))$('result-run').value=selected;
  }
  async function refreshRuns() {
    const id=state.project?.project_id;if(!id)return;
    const contextId=id;
    // Project identity and dedicated request generations prevent late list responses.
    const listToken = ++refreshRuns.sequence;
    const runs=(await api('/projects/'+id+'/runs')).runs;
    if(state.project?.project_id!==contextId || listToken!==refreshRuns.sequence)return;
    state.runs=runs;renderRunLists();
    if (!state.run) {
      const stored=storage.get('run-'+id);
      const selected=runs.find(run=>run.run_id===stored) || runs.find(active) || runs[0];
      if(selected)await watchRun(selected.run_id);
    }
  }
  refreshRuns.sequence=0;
  async function watchRun(id) {
    clearTimeout(pollTimer); const token=runsGate.next(),projectId=state.project?.project_id;
    async function poll() {
      try {
        const run=await api('/runs/'+id);
        if(!runsGate.current(token)||state.project?.project_id!==projectId)return;
        const previous=state.run?.status;
        state.run=run;storage.set('run-'+projectId,id);renderRun();
        if(active(run))pollTimer=setTimeout(poll,650);
        else if(previous!==run.status)await refreshRuns();
      }catch(error){if(runsGate.current(token)){tell(error.message,true);pollTimer=setTimeout(poll,2500);}}
    }
    await poll();
  }
  async function startRun() {
    if(state.dirty)throw new Error('请先保存配置，再开始运行。');
    const id=state.project?.project_id;if(!id)throw new Error('请先保存项目。');
    const run=await api('/projects/'+id+'/runs',{method:'POST'});
    state.run=run;renderRun();await watchRun(run.run_id);await refreshRuns();
    tell('已建立真实运行：'+run.run_id);
  }
  async function stopRun() {
    if(!active(state.run))return;
    state.run=await api('/runs/'+state.run.run_id+'/stop',{method:'POST'});
    renderRun();await watchRun(state.run.run_id);tell('已发送停止请求。');
  }
  function definition(rows) {return rows.map(([key,value])=>`<dt>${esc(key)}</dt><dd>${esc(value??'—')}</dd>`).join('');}
  function renderResult(result) {
    state.result=result;$('result-content').hidden=!result;$('result-state').hidden=Boolean(result);
    context();if(!result)return;
    const stats=result.snapshot.stats;
    const number=value=>Number.isFinite(value)?value.toLocaleString('zh-CN',{maximumFractionDigits:3}):'—';
    const percent=value=>Number.isFinite(value)?(value*100).toFixed(1)+'%':'—';
    const metrics=[['完成任务',`${number(stats.completed)} / ${number(stats.generated)}`,'完成 / 已生成'],['完成率',percent(stats.completion_rate),'引擎统计口径'],['超时率',percent(stats.timeout_rate),'引擎统计口径'],['累计能耗',number(stats.energy),'既有模型单位']];
    $('metrics').innerHTML=metrics.map(([label,value,hint])=>`<div class="metric"><span>${label}</span><strong>${value}</strong><small>${hint}</small></div>`).join('');
    const project=result.project;
    $('result-config').innerHTML=definition([['项目名称',project.name],['机队 / 步数',`${project.simulation.environment.num_drones} / ${project.simulation.environment.episode_max_steps}`],['调度算法',project.algorithm],['随机种子',project.seed],['接受概率',core.effectiveProbability(project)],['任务生成',project.simulation.task_generation.mode]]);
    $('result-evidence').innerHTML=definition([['run_id',result.run_id],['project_id',result.project_id],['完成时间',date(result.finished_at)],['引擎机队',result.engine_input?.num_drones],['引擎接受概率',result.engine_input?.greedy?.accept_probability],['输入指纹',result.engine_input?.project_sha256??result.engine_input?.config_sha256]]);
    const tasks=core.taskRows(result.snapshot);
    $('result-tasks').innerHTML=tasks.length?tasks.map(task=>`<tr><td>${esc(task.id)}</td><td>${esc(({pending:'待分配',assigned:'已分配',in_progress:'执行中',completed:'已完成'})[task.status]||task.status||'—')}</td><td>${esc(task.priority)}</td><td>${esc(task.assigned_drone_id||'—')}</td></tr>`).join(''):'<tr><td colspan="4">本次运行没有可显示的任务目录。</td></tr>';
    $('result-json').textContent=JSON.stringify(result,null,2);
  }
  async function loadResult(id) {
    const token=resultGate.next(),projectId=state.project?.project_id;
    renderResult(null);$('result-state').textContent=id?'正在读取运行结果…':'尚未选择已完成的运行。';
    if(id && !state.runs.some(run=>run.run_id===id && run.project_id===projectId)){
      $('result-state').textContent='所选结果不属于当前项目，或运行记录已不存在。';return;
    }
    // Result browsing is independent of the run watched by the execution workspace.
    if(projectId)storage.set('result-'+projectId,id);
    if(!id)return;
    try {
      const run=await api('/runs/'+id);
      if(!resultGate.current(token)||state.project?.project_id!==projectId)return;
      if(run.project_id!==projectId)throw new Error('运行记录不属于当前项目。');
      if(run.status!=='completed'){
        $('result-state').textContent=`${statusText(run.status)}：${run.error || (active(run)?'运行尚未完成，可到运行区查看真实进度。':'此运行没有完整结果。')}`;return;
      }
      const result=await api('/runs/'+id+'/result');
      if(resultGate.current(token)&&state.project?.project_id===projectId){
        if(result.project_id!==projectId)throw new Error('结果记录不属于当前项目。');
        renderResult(result);
      }
    }catch(error){if(resultGate.current(token)){$('result-state').textContent=error.message;tell(error.message,true);}}
  }
  function showPage(name) {
    page=['projects','config','run','results'].includes(name)?name:'projects';
    document.querySelectorAll('.workspace').forEach(element=>element.hidden=element.id!=='page-'+page);
    document.querySelectorAll('[data-page]').forEach(element=>{element.classList.toggle('active',element.dataset.page===page);element.setAttribute('aria-current',element.dataset.page===page?'page':'false');});
    storage.set('page',page);
  }
  document.querySelectorAll('[data-page]').forEach(button=>button.addEventListener('click',()=>showPage(button.dataset.page)));
  $('project-name').addEventListener('input',()=>{if(state.project)state.project.name=$('project-name').value;dirty();});
  $('config-form').addEventListener('input',dirty);
  $('project-form').addEventListener('submit',event=>{event.preventDefault();write(saveProject);});
  $('save-config').addEventListener('click',()=>write(saveProject));
  $('new-project').addEventListener('click',newProject);
  $('refresh-projects').addEventListener('click',()=>write(refreshProjects));
  $('refresh-runs').addEventListener('click',()=>write(refreshRuns));
  $('start-run').addEventListener('click',()=>write(startRun));
  $('stop-run').addEventListener('click',()=>write(stopRun));
  $('project-list').addEventListener('click',event=>{const button=event.target.closest('[data-open-project]');if(button)write(()=>openProject(button.dataset.openProject));});
  $('run-list').addEventListener('click',event=>{const button=event.target.closest('[data-open-run]');if(!button)return;const run=state.runs.find(item=>item.run_id===button.dataset.openRun);if(run?.status==='completed'){showPage('results');$('result-run').value=run.run_id;loadResult(run.run_id);}else{showPage('run');watchRun(button.dataset.openRun);}});
  $('result-run').addEventListener('change',()=>loadResult($('result-run').value));
  $('download-result').addEventListener('click',()=>{
    if(!state.result)return;const blob=new Blob([JSON.stringify(state.result,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='swarmbalance-'+state.result.run_id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
  async function init() {
    context();
    try {
      state.defaults=await api('/defaults');state.project=core.newProject(state.defaults);renderEditor();
      await refreshProjects();
      const id=storage.get('project');
      if(id && state.projects.some(project=>project.project_id===id))await openProject(id,true);
      showPage(storage.get('page')||'projects');
      if(page==='results' && state.runs.length){
        const selected=storage.get('result-'+state.project.project_id);
        const saved=state.runs.find(run=>run.run_id===selected && run.project_id===state.project.project_id);
        const run=saved || state.runs.find(run=>run.status==='completed') || state.runs[0];
        $('result-run').value=run.run_id;await loadResult(run.run_id);
        if(selected && !saved)tell('上次选择的结果记录已不存在，已打开此项目最近的可用运行。');
      }
    }catch(error){tell(error.message+' 修复服务后刷新页面重试。',true);}
  }
  init();
})();
