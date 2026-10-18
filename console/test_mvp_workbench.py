"""Workbench contracts: served local assets and lossless configuration editing."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class WorkbenchTests(unittest.TestCase):
    def test_result_history_selection_survives_reload_without_changing_watched_run(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js required for UI orchestration regression")
        script = r'''
const assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs');
const config = JSON.parse(fs.readFileSync('./config/simulation.json','utf8'));
const project={project_id:'p1',name:'history',simulation:config,algorithm:'greedy',seed:101,algorithm_parameters:{}};
const otherProject={...project,project_id:'p2',name:'other project'};
const runs=[{run_id:'recent',project_id:'p1',status:'completed',step:600,total_steps:600,progress:1},
            {run_id:'older',project_id:'p1',status:'completed',step:600,total_steps:600,progress:1}];
const data=new Map([['swarm-mvp-project','p1'],['swarm-mvp-page','results'],['swarm-mvp-run-p1','recent']]);
const otherRun={...runs[0],run_id:'other-run',project_id:'p2'};
let delayOlder=false,releaseOlder;
const result = id => ({run_id:id,project_id:id==='other-run'?'p2':'p1',project:id==='other-run'?otherProject:project,engine_input:{},snapshot:{stats:{completed:id==='older'?6:0,generated:6,completion_rate:id==='older'?1:0,timeout_rate:0,energy:id==='older'?1123:0},task_catalog:[]}});
function boot() {
  const nodes=new Map();
  function element(id) {
    if(!nodes.has(id)) {
      const item={value:'',textContent:'',hidden:false,disabled:false,dataset:{},handlers:{},
        classList:{add(){},remove(){},toggle(){}},addEventListener(type,handler){this.handlers[type]=handler;},setAttribute(){}};
      Object.defineProperty(item,'innerHTML',{get(){return this.html||'';},set(value){this.html=value;if(id==='result-run')this.value='';}});
      nodes.set(id,item);
    }
    return nodes.get(id);
  }
  const document={getElementById:element,querySelectorAll:()=>[],body:{classList:{add(){},remove(){}}}};
  const context={document,window:{WorkbenchCore:require('./console/static/workbench-core.js'),addEventListener(){},confirm:()=>true},
    localStorage:{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value)},
    setTimeout,clearTimeout,AbortController,console,
    fetch:async url=>{
      const path=url.replace('/api/mvp','');let value;
      if(path==='/defaults')value={simulation:config};
      else if(path==='/projects')value={projects:[project,otherProject]};
      else if(path==='/projects/p1')value=project;
      else if(path==='/projects/p2')value=otherProject;
      else if(path==='/projects/p1/runs')value={runs};
      else if(path==='/projects/p2/runs')value={runs:[otherRun]};
      else if(path.endsWith('/result'))value=result(path.split('/')[2]);
      else if(path.startsWith('/runs/'))value=[...runs,otherRun].find(run=>run.run_id===path.split('/')[2]);
      else throw new Error('Unexpected request '+path);
      if(delayOlder && path==='/runs/older/result')await new Promise(resolve=>releaseOlder=resolve);
      return {ok:true,json:async()=>structuredClone(value)};
    }};
  vm.runInNewContext(fs.readFileSync('./console/static/workbench.js','utf8'),context);
  return element;
}
async function settle(){for(let i=0;i<25;i++)await new Promise(resolve=>setImmediate(resolve));}
(async()=>{
  let ui=boot();await settle();
  ui('result-run').value='older';ui('result-run').handlers.change();await settle();
  assert.equal(JSON.parse(ui('result-json').textContent).run_id,'older');
  assert.equal(data.get('swarm-mvp-result-p1'),'older','result dropdown must save its own selection');
  assert.equal(data.get('swarm-mvp-run-p1'),'recent','historical result must not replace watched run');
  ui=boot();await settle();
  assert.equal(ui('result-run').value,'older','refresh must restore selected historical run');
  assert.equal(JSON.parse(ui('result-json').textContent).snapshot.stats.completed,6);
  ui('result-run').value='recent';ui('result-run').handlers.change();await settle();
  ui('run-list').handlers.click({target:{closest:()=>({dataset:{openRun:'older'}})}});await settle();
  assert.equal(data.get('swarm-mvp-result-p1'),'older','completed list click must also persist result selection');
  data.set('swarm-mvp-result-p1','missing');ui=boot();await settle();
  assert.equal(ui('result-run').value,'recent','missing result must fall back to an existing project run');
  assert.match(ui('notice').textContent,/不存在/);
  assert.equal(data.get('swarm-mvp-run-p1'),'recent');
  delayOlder=true;ui('result-run').value='older';ui('result-run').handlers.change();await settle();
  assert.equal(typeof releaseOlder,'function');
  ui('project-list').handlers.click({target:{closest:()=>({dataset:{openProject:'p2'}})}});await settle();
  ui('result-run').value='other-run';ui('result-run').handlers.change();await settle();
  releaseOlder();await settle();
  assert.equal(JSON.parse(ui('result-json').textContent).project_id,'p2','late p1 result must not overwrite current p2');
  assert.equal(data.get('swarm-mvp-result-p1'),'older');
  assert.equal(data.get('swarm-mvp-result-p2'),'other-run');
  assert.equal(data.get('swarm-mvp-run-p1'),'recent');
  console.log('history UI: dropdown/list persistence, reload, missing fallback, watched-run and stale-project isolation PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([node, "-e", script], cwd=ROOT, text=True,
                                encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())

    def test_editor_preserves_hidden_config_and_rejects_bad_fields(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js required for browser-independent editor checks")
        script = r'''
const assert = require('node:assert/strict');
const core = require('./console/static/workbench-core.js');
const defaults = {simulation: JSON.parse(require('node:fs').readFileSync('./config/simulation.json', 'utf8')), seed:100};
const draft = core.newProject(defaults);
assert.equal(draft.simulation.environment.num_drones,3);
assert.equal(draft.simulation.heterogeneous.enabled,false);
assert.equal(draft.simulation.environment.episode_max_steps,600);
assert.equal(draft.simulation.task_generation.realistic.total_tasks,5);
assert.equal(defaults.simulation.environment.num_drones,10);
const before = structuredClone(draft);
const edited = core.applyFields(draft, {'name':'  edited  ','simulation.environment.num_drones':'4','seed':'102'});
assert.equal(edited.name,'edited');
assert.equal(edited.simulation.environment.num_drones,4);
assert.equal(edited.seed,102);
assert.deepEqual(edited.simulation.no_fly_zones,before.simulation.no_fly_zones);
assert.deepEqual(edited.simulation.charging_stations,before.simulation.charging_stations);
assert.deepEqual(draft,before);
assert.throws(()=>core.applyFields(draft,{'seed':''}),/不能为空/);
assert.throws(()=>core.applyFields(draft,{'simulation.environment.num_drones':'1.5'}),/整数/);
assert.throws(()=>core.applyFields(draft,{'algorithm_parameters.accept_probability':'2'}),/0.*1/);
assert.throws(()=>core.applyFields(draft,{'simulation.task_generation.realistic.initial_task_count':'6'}),/初始任务/);
const hetero=structuredClone(defaults); hetero.name='hetero'; hetero.algorithm='greedy'; hetero.algorithm_parameters={};
assert.equal(core.applyFields(hetero,{'name':'kept'}).simulation.heterogeneous.enabled,true);
assert.equal(core.effectiveProbability(hetero),1);
hetero.simulation.environment.greedy.accept_probability=.4;
assert.equal(core.effectiveProbability(hetero),.4);
assert.deepEqual(core.taskRows({task_catalog:[{id:'task<&>',status:'completed'}]})[0].id,'task<&>');
const epoch=core.requestGate(); const old=epoch.next(); const current=epoch.next();
assert.equal(epoch.current(old),false); assert.equal(epoch.current(current),true);
assert.equal(core.errorMessage(409,'busy').includes('busy'),true);
assert.equal(core.errorMessage(422,[{loc:['body','name'],msg:'required'}]).includes('required'),true);
console.log('editor: immutable defaults, full config, numeric validation, stale requests, API errors PASS');
'''
        result = subprocess.run([node, "-e", script], cwd=ROOT, text=True,
                                encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())

    def test_real_http_serves_workbench_assets_and_keeps_root(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, SWARM_BALANCE_MVP_DATA=folder, PYTHONUTF8="1")
            with open(os.devnull, "w") as log:
                process = subprocess.Popen([sys.executable, "-m", "uvicorn", "console.server:app",
                                            "--host", "127.0.0.1", "--port", str(port)],
                                           cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    base = f"http://127.0.0.1:{port}"
                    for _ in range(200):
                        try:
                            urlopen(base + "/api/mvp/defaults", timeout=1).close()
                            break
                        except OSError:
                            time.sleep(.1)
                    try:
                        with urlopen(base + "/workbench") as response:
                            html = response.read().decode("utf-8")
                    except HTTPError as error:
                        self.fail(f"workbench should be served, got HTTP {error.code}")
                    self.assertIn('data-testid="project-name"', html)
                    for name in ("workbench.css", "workbench-core.js", "workbench.js"):
                        with urlopen(base + "/workbench/assets/" + name) as response:
                            self.assertEqual(response.status, 200)
                            self.assertNotIn("text/html", response.headers["Content-Type"])
                    with urlopen(base + "/") as response:
                        self.assertEqual(response.status, 200)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + "/workbench/assets/server.py")
                    self.assertEqual(error.exception.code, 404)
                    with urlopen(base + "/api/mvp/projects") as response:
                        self.assertEqual(json.load(response), {"projects": []})
                finally:
                    process.terminate()
                    process.wait(timeout=20)


if __name__ == "__main__":
    unittest.main()
