/* Pure, immutable editor operations shared by the browser and Node checks. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  function newProject(defaults) {
    const project = {name: '', algorithm: 'greedy', seed: 101,
      algorithm_parameters: {accept_probability: 1}, simulation: clone(defaults.simulation)};
    project.simulation.environment.num_drones = 3;
    project.simulation.environment.episode_max_steps = 600;
    project.simulation.heterogeneous.enabled = false;
    project.simulation.task_generation.mode = 'realistic';
    project.simulation.task_generation.realistic.total_tasks = 5;
    project.simulation.task_generation.realistic.initial_task_count = 5;
    return project;
  }
  const integers = /(?:seed|num_drones|episode_max_steps|total_tasks|initial_task_count|berths)$/;
  function applyFields(project, fields) {
    const result = clone(project);
    for (const [path, raw] of Object.entries(fields)) {
      const parts = path.split('.');
      let target = result;
      for (const part of parts.slice(0, -1)) target = target[part] ??= {};
      const key = parts.at(-1);
      if (path === 'name' || path === 'algorithm' || path.endsWith('.mode')) {
        target[key] = String(raw).trim();
        if (path === 'name' && !target[key]) throw new Error('项目名称不能为空');
      } else if (typeof raw === 'boolean') target[key] = raw;
      else {
        if (String(raw).trim() === '') throw new Error('数值不能为空，请检查配置字段');
        const number = Number(raw);
        if (!Number.isFinite(number)) throw new Error('请输入有限数值');
        if (integers.test(path) && !Number.isInteger(number)) throw new Error('数量、步数和种子必须为整数');
        if (path.endsWith('accept_probability') && (number < 0 || number > 1)) throw new Error('接受概率必须在 0 到 1 之间');
        target[key] = number;
      }
    }
    const tasks = result.simulation.task_generation;
    if (tasks.mode === 'realistic' && tasks.realistic.initial_task_count > tasks.realistic.total_tasks)
      throw new Error('初始任务数量不能超过任务总量');
    return result;
  }
  function requestGate() {
    let epoch = 0;
    return {next: () => ++epoch, current: token => token === epoch};
  }
  function errorMessage(status, detail) {
    const labels = {400:'配置不符合要求',404:'项目或运行记录不存在',409:'当前状态不允许此操作',422:'提交格式不正确'};
    const message = Array.isArray(detail) ? detail.map(item => `${(item.loc || []).join('.')}: ${item.msg}`).join('；')
      : typeof detail === 'string' ? detail : '请稍后重试';
    return `${labels[status] || `接口错误 (${status})`}：${message}`;
  }
  const effectiveProbability = project => project.algorithm_parameters.accept_probability ?? project.simulation.environment.greedy.accept_probability;
  const taskRows = snapshot => snapshot.task_catalog || snapshot.tasks || [];
  const api = {clone, newProject, applyFields, requestGate, errorMessage, effectiveProbability, taskRows};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.WorkbenchCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
