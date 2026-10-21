(function(){
"use strict";
const $ = id => document.getElementById(id);
const KINDS = ["water","landuse","roads","railways","buildings"];
const LIMIT_KM2 = 30;
const DEFAULT_BBOX = [121.41216481,41.91485205,121.47245519,41.95986786];
const styles = {
 water:[{type:"fill",paint:{"fill-color":"#54b5dd","fill-opacity":.45}},
        {type:"line",paint:{"line-color":"#1888c7","line-width":2}}],
 landuse:[{type:"fill",paint:{"fill-color":"#76c773","fill-opacity":.22}}],
 roads:[{type:"line",paint:{"line-color":"#d65e26","line-width":2.5}}],
 railways:[{type:"line",paint:{"line-color":"#7e22ce","line-width":1.6,"line-dasharray":[3,2]}}],
 buildings:[{type:"fill",paint:{"fill-color":"#475569","fill-opacity":.58,"fill-outline-color":"#1e293b"}}]
};
let map, bbox=DEFAULT_BBOX.slice(), pendingPoint=null, drawing=false, pollTimer=null, activeJob=null;
const mounted = [];
function message(txt,isError=false){
 const box=document.createElement("div");box.className="note"+(isError?" error":"");
 box.textContent=txt; $("messages").prepend(box);
 while($("messages").children.length>8)$("messages").lastElementChild.remove();
}
function state(txt,good=false){$("state").textContent=txt;$("state").className="status"+(good?" good":"");}
function showMapError(txt){$("map-error").textContent=txt;$("map-error").style.display="block";}
function area(b){const mid=(b[1]+b[3])/2*Math.PI/180;const w=(b[2]-b[0])*111.32*Math.cos(mid), h=(b[3]-b[1])*111.32;return {w,h,km2:w*h};}
function check(b){
 if(!Array.isArray(b)||b.length!==4||b.some(v=>!Number.isFinite(v)))return "坐标必须是有限数字";
 if(!(-180<=b[0]&&b[0]<b[2]&&b[2]<=180&&-85<=b[1]&&b[1]<b[3]&&b[3]<=85))return "选区的西/南边界必须小于东/北边界";
 const a=area(b);
 if(a.w<.1||a.h<.1)return "最小选区宽高均为 100 米";
 if(a.km2>LIMIT_KM2)return "选区过大，最大支持 "+LIMIT_KM2+" km²，请缩小范围";
 return null;
}
async function api(url,opts={}){
 const resp=await fetch(url,{...opts,headers:{"Content-Type":"application/json",...(opts.headers||{})},cache:"no-store"});
 let data;
 try{data=await resp.json();}catch(e){throw Error("服务器未返回 JSON（HTTP "+resp.status+"）");}
 if(!resp.ok)throw Error(typeof data.detail==="string"?data.detail:"HTTP "+resp.status);
 return data;
}
function selectionPolygon(b){
 return {type:"Feature",properties:{},geometry:{type:"Polygon",coordinates:[[
 [b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[b[0],b[1]]
 ]]}};
}
function drawBox(b){
 if(map && map.getSource("selected-bbox"))map.getSource("selected-bbox").setData(selectionPolygon(b));
}
function inputsFromBox(b){
 ["west","south","east","north"].forEach((key,i)=>$(key).value=b[i].toFixed(7));
}
function clearLayers(){
 if(!map)return;
 for(const entry of mounted.reverse()){
  if(map.getLayer(entry))map.removeLayer(entry);
 }
 mounted.length=0;
 for(const kind of KINDS){
  if(map.getSource("data-"+kind))map.removeSource("data-"+kind);
  $("c-"+kind).textContent="未准备";
 }
 $("quality").hidden=true;
}
function setBBox(next,fit=false){
 bbox=next.map(v=>Number(v.toFixed(7)));
 inputsFromBox(bbox);drawBox(bbox);
 const issue=check(bbox), a=area(bbox);
 $("selection").textContent=issue||("约 "+a.w.toFixed(2)+" × "+a.h.toFixed(2)+" km · "+a.km2.toFixed(2)+" km²");
 $("selection").className=issue?"error":"";
 $("prepare").disabled=Boolean(issue||activeJob);
 if(fit && map)map.fitBounds([[bbox[0],bbox[1]],[bbox[2],bbox[3]]],{padding:55,duration:400});
 return !issue;
}
function stopDrawing(){
 drawing=false;pendingPoint=null;
 $("draw").classList.remove("selected");
 $("draw").textContent="在地图上选区";
 $("draw-hint").textContent="点击“在地图上选区”，依次点击矩形两个对角点；也可在下方直接输入坐标。按 Esc 退出选区。";
 if(map)map.getCanvas().style.cursor="";
}
function selectClick(event){
 if(!drawing)return;
 const p=[event.lngLat.lng,event.lngLat.lat];
 if(!pendingPoint){pendingPoint=p;$("draw-hint").textContent="已选第一个角点，请点击矩形对角点；Esc 可取消。";return}
 const b=[Math.min(p[0],pendingPoint[0]),Math.min(p[1],pendingPoint[1]),
          Math.max(p[0],pendingPoint[0]),Math.max(p[1],pendingPoint[1])];
 stopDrawing();
 if(!setBBox(b,true))message("请重新选择范围："+check(b),true);
 else {clearLayers();state("选区已更改。点击“准备选区数据”开始获取真实地理图层。");}
}
function paintFeatureLayer(kind,data){
 map.addSource("data-"+kind,{type:"geojson",data});
 for(let i=0;i<styles[kind].length;i++){
  const layerId="lyr-"+kind+"-"+i;
  map.addLayer({id:layerId,source:"data-"+kind,...styles[kind][i]},"selection");
  mounted.push(layerId);
  map.setLayoutProperty(layerId,"visibility",document.querySelector('[data-layer="'+kind+'"]').checked?"visible":"none");
 }
 $("c-"+kind).textContent=data.features.length+" 个";
}
async function showPackage(packageId){
 const manifest=await api("/api/gis/packages/"+encodeURIComponent(packageId));
 clearLayers();
 for(const kind of KINDS){
  try{
   const data=await api("/api/gis/packages/"+encodeURIComponent(packageId)+"/layers/"+kind);
   if(!Array.isArray(data.features)||data.type!=="FeatureCollection")throw Error("返回数据不是 GeoJSON 集合");
   paintFeatureLayer(kind,data);
  }catch(e){message(kind+" 图层加载失败："+e.message,true);}
 }
 const q=manifest.quality||{};
 $("quality").hidden=false;
 $("quality").textContent="地图包 "+packageId+" · "+manifest.tiles+" 个数据块 · "+
   "未解析的 way "+(q.invalid_ways||0)+" · 未知建筑高度 "+(q.unknown_building_heights||0)+
   " · 未处理 multipolygon relations · 仿真可用性：否";
 state("已准备固定版本的 OSM 图层（仅供预览；不能直接当作无人机避障数据）",true);
 message("选区地图包："+packageId+"，已加载数据图层。");
}
function statusJob(job){
 $("progress").style.display="block";
 const total=Math.max(1,job.total_tiles||1),done=job.completed_tiles||0;
 $("progressbar").max=total;$("progressbar").value=done;
 $("progress-text").textContent=job.status+" · "+done+"/"+total+" 块 · "+(job.message||"");
 $("cancel").hidden=!["queued","downloading","processing"].includes(job.status);
}
function clearPolling(){
 if(pollTimer){clearInterval(pollTimer);pollTimer=null}
 activeJob=null;
 sessionStorage.removeItem("swarmbalance_gis_job");
 $("prepare").disabled=Boolean(check(bbox));
 $("cancel").hidden=true;
}
let polling=false;
async function poll(){
 if(!activeJob||polling)return;polling=true;
 try{
  const job=await api("/api/gis/import-jobs/"+activeJob);
  statusJob(job);
  if(["complete","failed","cancelled","interrupted"].includes(job.status)){
   clearPolling();
   if(job.status==="complete"&&job.package_id){
    await showPackage(job.package_id);
    message("本次使用缓存块："+(job.cache_hits||0)+"/"+job.total_tiles);
   }else{
    state("任务状态："+job.status+"。"+job.message);
    message(job.message||"未完成地图准备",true);
   }
  }
 }catch(e){
  clearPolling();state("状态查询失败："+e.message);message(e.message,true);
 }finally{polling=false}
}
async function start(){
 if(activeJob)return;
 const issue=check(bbox);if(issue){message(issue,true);return}
 $("prepare").disabled=true;state("正在创建地图准备任务…");
 try{
  const job=await api("/api/gis/import-jobs",{method:"POST",body:JSON.stringify({bbox,force_refresh:$("force").checked})});
  activeJob=job.id;
  sessionStorage.setItem("swarmbalance_gis_job",activeJob);
  statusJob(job);
  state("已提交后台任务；按区域分块处理，网络中断时显示错误，不会下载整省。");
  if(pollTimer)clearInterval(pollTimer);
  pollTimer=setInterval(poll,1200);await poll();
 }catch(e){clearPolling();state("无法开始数据准备："+e.message);message(e.message,true)}
}
async function cancel(){
 if(!activeJob)return;
 $("cancel").disabled=true;
 try{
  await api("/api/gis/import-jobs/"+activeJob+"/cancel",{method:"POST"});
  message("已请求取消，当前网络请求结束后生效。");
 }catch(e){message("取消失败："+e.message,true)}
 finally{$("cancel").disabled=false}
}
function handleInputs(){
 const b=["west","south","east","north"].map(k=>Number($(k).value));
 if(["west","south","east","north"].some(k=>$(k).value.trim()===""))return;
 if(setBBox(b,false)){clearLayers();state("研究范围已修改。需要重新准备地图数据。");}
}
function setup(){
 $("draw").addEventListener("click",()=>{
  if(drawing){stopDrawing();return}
  drawing=true;pendingPoint=null;
  $("draw").classList.add("selected");$("draw").textContent="取消选区";
  $("draw-hint").textContent="请在地图上连续点击两个对角点，确定新的矩形范围。";
  map.getCanvas().style.cursor="crosshair";
 });
 $("viewport").addEventListener("click",()=>{
  stopDrawing();
  const r=map.getBounds();
  const b=[r.getWest(),r.getSouth(),r.getEast(),r.getNorth()];
  if(!setBBox(b,false))message("当前视野不满足数据源面积限制，请缩放后再选择",true);
  else{clearLayers();state("已选择当前视野，请点击准备选区数据。")}
 });
 $("back").addEventListener("click",()=>{
  stopDrawing();setBBox(DEFAULT_BBOX,true);clearLayers();
  state("已恢复佛寺镇试验区；如需真实图层请点击准备选区数据。");
 });
 for(const id of ["west","south","east","north"])$(id).addEventListener("change",handleInputs);
 $("prepare").addEventListener("click",start);
 $("cancel").addEventListener("click",cancel);
 document.addEventListener("keydown",event=>{if(event.key==="Escape")stopDrawing()});
 for(const kind of KINDS){
  document.querySelector('[data-layer="'+kind+'"]').addEventListener("change",event=>{
   for(let i=0;i<styles[kind].length;i++){
    const id="lyr-"+kind+"-"+i;
    if(map.getLayer(id))map.setLayoutProperty(id,"visibility",event.target.checked?"visible":"none");
   }
  });
 }
 map.on("click",selectClick);
}
if(!window.maplibregl){
 state("无法加载 MapLibre，请检查浏览器联网情况。");
 showMapError("地图脚本未加载，请检查 CDN；原仿真不受影响。");
 return;
}
map=new maplibregl.Map({
 container:"map",center:[121.44231,41.93736],zoom:12.5,attributionControl:true,
 style:{version:8,
 sources:{osm:{type:"raster",tiles:["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],tileSize:256,attribution:"© OpenStreetMap contributors"}},
 layers:[{id:"bg",type:"background",paint:{"background-color":"#eaf0f0"}},{id:"basemap",type:"raster",source:"osm"}]}
});
map.addControl(new maplibregl.NavigationControl(),"top-right");
map.on("error",e=>showMapError("在线底图加载异常："+(e.error?.message||"网络失败")));
map.on("move",()=>{const c=map.getCenter();$("center").textContent=c.lng.toFixed(5)+"°E · "+c.lat.toFixed(5)+"°N";});
map.on("load",async()=>{
 map.addSource("selected-bbox",{type:"geojson",data:selectionPolygon(bbox)});
 map.addLayer({id:"selection",type:"line",source:"selected-bbox",paint:{"line-color":"#2563eb","line-width":3,"line-dasharray":[2,2]}});
 setup();
 try{
  const result=await api("/api/map-lab/status");
  if(result.region?.bbox_wgs84_lonlat)setBBox(result.region.bbox_wgs84_lonlat,true);
  state("在线底图可用；可框选区域并按需准备真实 GIS 图层。");
 }catch(e){setBBox(DEFAULT_BBOX,true);state("区域配置读取失败："+e.message)}
 const saved=sessionStorage.getItem("swarmbalance_gis_job");
 if(saved&&/^[0-9a-f]{32}$/.test(saved)){
  activeJob=saved;$("prepare").disabled=true;
  pollTimer=setInterval(poll,1200);poll();
 }
});
})();
