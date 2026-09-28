# 前端依赖本地副本

答辩现场断网或内网拦截 CDN 时，页面必须仍能启动，因此把三个库随仓库分发。
`console/server.py` 的 `/vendor/{name}` 以白名单方式提供它们；`index.html` 先加载本地副本，
只有本地加载失败时才回退到公网 CDN。

| 文件 | 版本 | 大小 | 来源 URL | SHA-256 |
|---|---|---|---|---|
| `echarts.min.js` | 5.5.1 | 1006.7 KB | https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js | `e84270bd0cd5bdf6…` |
| `three.min.js` | 0.128.0 | 589.3 KB | https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js | `9274bbcec8d96168…` |
| `vue.global.prod.js` | 3.5.13 | 154.2 KB | https://unpkg.com/vue@3.5.13/dist/vue.global.prod.js | `c459ba7cc8db65c9…` |

## 为什么钉死版本

改造前用的是 `vue@3` / `echarts@5` 这类浮动大版本，上游发新版会静默改变 UI 行为，
答辩当天属于风险最高的一行。这里全部钉到具体版本号。

## 更新方式

1. 从上面的 URL 下载新版本，覆盖同名文件；
2. 同步更新本表的版本与 SHA-256，以及 `index.html` 中 `__cdnFallback(...)` 的回退 URL；
3. 跑 `run_tests.bat`，并在浏览器 Network 面板确认三个库均由 `/vendor/` 提供。

## 许可

三者均为 MIT 许可的开源库；本目录只保留官方构建产物，未做任何修改。
