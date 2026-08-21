import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const bool = (v) => v ? 'TRUE' : 'FALSE';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const API_BASE = (window.EES_API_BASE_URL || 'http://localhost:8001').replace(/\/$/, '');

function log(type, message, cls='') {
  const row = document.createElement('div');
  row.className = `event ${cls}`;
  row.innerHTML = `<time>${new Date().toLocaleTimeString([], {hour12:false})}</time><b>${type}</b><span>${message}</span>`;
  $('log').prepend(row);
  while ($('log').children.length > 60) $('log').lastElementChild.remove();
}

async function api(path, options={}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options,
  });
  let body = {};
  try { body = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(body.detail || body.message || `API ${response.status}`);
  return body;
}

class Parking3D {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x06101a);
    this.scene.fog = new THREE.Fog(0x06101a, 65, 170);
    this.camera = new THREE.PerspectiveCamera(45, 1, .1, 300);
    this.camera.position.set(62, 62, 72);
    this.renderer = new THREE.WebGLRenderer({antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0,0,0);
    this.controls.maxPolarAngle = Math.PI/2.05;
    this.controls.minDistance = 28;
    this.controls.maxDistance = 145;
    this.spots=[]; this.carMap=new Map(); this.animations=[];
    this.build(); this.resize();
    addEventListener('resize',()=>this.resize());
    this.renderer.setAnimationLoop(()=>this.render());
  }
  mat(color, emissive=0, intensity=0){return new THREE.MeshStandardMaterial({color,roughness:.56,metalness:.32,emissive,emissiveIntensity:intensity});}
  add(geo,mat,pos){const m=new THREE.Mesh(geo,mat);m.position.copy(pos);m.castShadow=true;m.receiveShadow=true;this.scene.add(m);return m;}
  build(){
    this.scene.add(new THREE.HemisphereLight(0xa9e5ff,0x18202a,2.3));
    const sun=new THREE.DirectionalLight(0xffffff,3.7);sun.position.set(45,70,38);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-70;sun.shadow.camera.right=70;sun.shadow.camera.top=70;sun.shadow.camera.bottom=-70;this.scene.add(sun);
    const glow=new THREE.PointLight(0x29cfff,55,95);glow.position.set(-42,15,-20);this.scene.add(glow);
    this.add(new THREE.BoxGeometry(82,.8,80),this.mat(0x202a34),new THREE.Vector3(0,-.5,0));
    const curb=this.mat(0x697680);
    this.add(new THREE.BoxGeometry(84,.7,1),curb,new THREE.Vector3(0,0,-40));
    this.add(new THREE.BoxGeometry(84,.7,1),curb,new THREE.Vector3(0,0,40));
    this.add(new THREE.BoxGeometry(1,.7,81),curb,new THREE.Vector3(-42,0,0));
    this.add(new THREE.BoxGeometry(1,.7,81),curb,new THREE.Vector3(42,0,0));
    this.buildSpots();
    this.entryGate=this.gate(-17,36.2,'ENTRY');
    this.exitGate=this.gate(17,36.2,'EXIT');
  }
  buildSpots(){
    const line=new THREE.MeshBasicMaterial({color:0x59d0ff});
    const rowLetters='ABCDEFG';
    for(let r=0;r<7;r++){
      for(let c=0;c<10;c++){
        const x=-27+c*6;
        const z=-30+r*9.3;
        const number=`${rowLetters[r]}${String(c+1).padStart(2,'0')}`;
        const g=new THREE.Mesh(new THREE.PlaneGeometry(4.6,7.2),new THREE.MeshStandardMaterial({color:0x11364c,emissive:0x1ca9e0,emissiveIntensity:.25,transparent:true,opacity:.48}));
        g.rotation.x=-Math.PI/2;g.position.set(x,.02,z);this.scene.add(g);
        [-2.35,2.35].forEach(dx=>{const l=new THREE.Mesh(new THREE.BoxGeometry(.09,.03,7.3),line);l.position.set(x+dx,.05,z);this.scene.add(l);});
        this.spots.push({x,z,rot:r%2===0?0:Math.PI,glow:g,occupied:false,number});
      }
    }
  }
  gate(x,z,label){
    const group=new THREE.Group();group.position.set(x,0,z);
    const post=new THREE.Mesh(new THREE.BoxGeometry(1.1,3,1.1),this.mat(0x263b4c,0x117aa7,.25));post.position.y=1.5;group.add(post);
    const pivot=new THREE.Group();pivot.position.set(0,2.55,0);
    const arm=new THREE.Mesh(new THREE.BoxGeometry(7,.26,.34),this.mat(0xf5f7f9));arm.position.x=x<0?3.5:-3.5;pivot.add(arm);
    for(let i=0;i<6;i++){const s=new THREE.Mesh(new THREE.BoxGeometry(.62,.28,.36),this.mat(0xff3659,0xff193f,.65));s.position.x=(x<0?1:-1)*(.65+i*1.1);pivot.add(s);}
    group.add(pivot);this.scene.add(group);return {group,pivot,target:0,label};
  }
  car(color, visitor=false){
    const g=new THREE.Group();
    const body=new THREE.Mesh(new THREE.BoxGeometry(2.5,.72,4.5),this.mat(color));body.position.y=.72;g.add(body);
    const cab=new THREE.Mesh(new THREE.BoxGeometry(1.9,.68,2.2),new THREE.MeshStandardMaterial({color:visitor?0xffd58a:0x8edfff,transparent:true,opacity:.74,roughness:.18,metalness:.4}));cab.position.set(0,1.4,-.15);g.add(cab);
    [[-1.15,.45,1.4],[1.15,.45,1.4],[-1.15,.45,-1.4],[1.15,.45,-1.4]].forEach(p=>{const w=new THREE.Mesh(new THREE.CylinderGeometry(.36,.36,.28,16),this.mat(0x080b0e));w.rotation.z=Math.PI/2;w.position.set(...p);g.add(w);});return g;
  }
  colorFor(id, visitor=false){if(visitor)return 0xffa93f;let h=0;for(const ch of id)h=(h*31+ch.charCodeAt(0))>>>0;const colors=[0x2e7cff,0x40f6a1,0xffca55,0x9b7dff,0x38c3c8,0xf07dc4,0x8ac24a,0xd8e1ea];return colors[h%colors.length];}
  spot(number){return this.spots.find(s=>s.number===number);}
  async gateTo(g,open){g.target=open?(g.group.position.x<0?-Math.PI/2:Math.PI/2):0;await sleep(650);}
  move(obj,points,duration){return new Promise(resolve=>{const start=performance.now(),path=[obj.position.clone(),...points];this.animations.push(now=>{const p=Math.min(1,(now-start)/duration),n=path.length-1,s=p*n,i=Math.min(n-1,Math.floor(s)),t=s-i,e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;obj.position.lerpVectors(path[i],path[i+1],e);if(p>=1){resolve();return true}return false});});}
  parkImmediate(session){
  if(this.carMap.has(session.vehicle_identifier)) return;

  // Production API returns `space_number`.
  // Keep `spot_number` as a compatibility fallback for entry-animation responses.
  const spaceNumber = String(
    session.space_number ?? session.spot_number ?? ""
  ).trim().toUpperCase();

  if(!spaceNumber) {
    console.warn(
      "Parking session missing space assignment:",
      session.vehicle_identifier,
      session
    );
    return;
  }

  const spot = this.spot(spaceNumber);

  if(!spot) {
    console.warn(
      `Parking space ${spaceNumber} was not found in the Three.js lot`,
      session
    );
    return;
  }

  const visitor = session.occupant_type === "VISITOR";
  const car = this.car(
    this.colorFor(session.vehicle_identifier, visitor),
    visitor
  );

  car.position.set(spot.x, 0, spot.z);
  car.rotation.y = spot.rot;

  this.scene.add(car);

  spot.occupied = true;
  spot.glow.material.color.setHex(
    visitor ? 0x5b3510 : 0x173c26
  );
  spot.glow.material.emissive.setHex(
    visitor ? 0xffa62b : 0x40f6a1
  );

  this.carMap.set(session.vehicle_identifier, {
    mesh: car,
    spot,
    visitor
  });
}
  syncSessions(sessions){
    const active=new Set(sessions.map(s=>s.vehicle_identifier));
    for(const [id,item] of this.carMap){if(!active.has(id)){this.scene.remove(item.mesh);item.spot.occupied=false;item.spot.glow.material.color.setHex(0x11364c);item.spot.glow.material.emissive.setHex(0x1ca9e0);this.carMap.delete(id);}}
    sessions.forEach(s=>this.parkImmediate(s));
  }
  async enter(vehicleId, spotNumber, occupantType){
    if(this.carMap.has(vehicleId))return;
    const spot=this.spot(spotNumber);if(!spot)return;
    await this.gateTo(this.entryGate,true);
    const visitor=occupantType==='VISITOR';const car=this.car(this.colorFor(vehicleId,visitor),visitor);car.position.set(-17,0,45);this.scene.add(car);
    await this.move(car,[new THREE.Vector3(-17,0,28),new THREE.Vector3(-17,0,0),new THREE.Vector3(spot.x,0,spot.z)],2600);
    car.rotation.y=spot.rot;spot.occupied=true;spot.glow.material.color.setHex(visitor?0x5b3510:0x173c26);spot.glow.material.emissive.setHex(visitor?0xffa62b:0x40f6a1);this.carMap.set(vehicleId,{mesh:car,spot,visitor});
    await this.gateTo(this.entryGate,false);
  }
  async exit(vehicleId){
    const item=this.carMap.get(vehicleId);if(!item)return;
    await this.gateTo(this.exitGate,true);
    await this.move(item.mesh,[new THREE.Vector3(17,0,0),new THREE.Vector3(17,0,30),new THREE.Vector3(17,0,47)],2400);
    this.scene.remove(item.mesh);item.spot.occupied=false;item.spot.glow.material.color.setHex(0x11364c);item.spot.glow.material.emissive.setHex(0x1ca9e0);this.carMap.delete(vehicleId);await this.gateTo(this.exitGate,false);
  }
  cameraView(v){const views={overview:[[62,62,72],[0,0,0]],entry:[[-34,14,52],[-17,2,29]],exit:[[34,14,52],[17,2,29]]};const [p,t]=views[v]||views.overview;this.camera.position.set(...p);this.controls.target.set(...t);this.controls.update();}
  resize(){const w=this.container.clientWidth,h=this.container.clientHeight;this.camera.aspect=w/Math.max(h,1);this.camera.updateProjectionMatrix();this.renderer.setSize(w,h,false);}
  render(){const now=performance.now();this.animations=this.animations.filter(fn=>!fn(now));[this.entryGate,this.exitGate].forEach(g=>{if(g)g.pivot.rotation.z+=(g.target-g.pivot.rotation.z)*.12});this.controls.update();this.renderer.render(this.scene,this.camera);}
}

class SecurePLC {
  constructor(scene){
    this.scene=scene;this.scanCount=0;this.estop=false;this.busy=false;this.entryGate=false;this.exitGate=false;
    this.tags={Vehicle_Detected:false,Employee_Vehicle:false,Visitor_Vehicle:false,Vehicle_Authorized:false,Security_Approval:false};
    this.status={capacity:70,occupied:0,employees:0,visitors:0,remaining:70,full:false,empty:true,visitor_pool_available:0,active_sessions:[]};
    setInterval(()=>this.scan(),100);this.scan();
  }
  scan(){this.scanCount++;$('scan-count').textContent=this.scanCount.toLocaleString();$('entry-gate').textContent=this.entryGate?'OPEN':'CLOSED';$('exit-gate').textContent=this.exitGate?'OPEN':'CLOSED';$('t-entry-gate').textContent=bool(this.entryGate);$('t-exit-gate').textContent=bool(this.exitGate);$('t-detected').textContent=bool(this.tags.Vehicle_Detected);$('t-employee').textContent=bool(this.tags.Employee_Vehicle);$('t-visitor').textContent=bool(this.tags.Visitor_Vehicle);$('t-authorized').textContent=bool(this.tags.Vehicle_Authorized);$('t-security').textContent=bool(this.tags.Security_Approval);}
  clearDecisionTags(){this.tags.Vehicle_Detected=false;this.tags.Employee_Vehicle=false;this.tags.Visitor_Vehicle=false;this.tags.Vehicle_Authorized=false;this.tags.Security_Approval=false;}
  async animateEntry(result){this.busy=true;this.entryGate=true;this.scan();await this.scene.enter(result.vehicle_identifier,result.spot_number,result.occupant_type);this.entryGate=false;this.busy=false;this.clearDecisionTags();this.scan();}
  async animateExit(result){this.busy=true;this.exitGate=true;this.scan();await this.scene.exit(result.vehicle_identifier);this.exitGate=false;this.busy=false;this.clearDecisionTags();this.scan();}
  toggleEstop(){this.estop=!this.estop;if(this.estop){this.entryGate=false;this.exitGate=false;log('ALARM','Emergency stop activated. Gate authorization outputs inhibited.','alarm');}else log('RESET','Emergency stop released.');$('estop').classList.toggle('active',this.estop);this.scan();}
}

const scene=new Parking3D($('scene'));
const plc=new SecurePLC(scene);
let pendingRequest=null;
let demoIdentifiers=null;
let occupancyFilter='ALL';

function employeeExceptionFor(vehicleIdentifier){
  const vehicle=String(vehicleIdentifier||'').trim().toUpperCase();
  const item=(demoIdentifiers?.denied_examples||[]).find(row=>String(row.vehicle_identifier||'').toUpperCase()===vehicle);
  if(!item)return null;

  let reason='Employee access exception requires Security review';
  if(String(item.employment_status||'').toUpperCase()==='LEAVE')reason='Employee is currently on leave';
  else if(String(item.employment_status||'').toUpperCase()==='INACTIVE')reason='Employee record is inactive';
  else if(!item.parking_authorized)reason='Parking authorization is suspended';

  return {...item,classification:'EMPLOYEE_ACCESS_EXCEPTION',reason};
}

async function loadDemoIdentifiers(){
  const container=$('demo-vehicles');
  try{
    const data=await api('/api/demo/identifiers');
    demoIdentifiers=data;
    if(!container)return;
    const authorized=(data.authorized||[]).slice(0,3);
    const denied=(data.denied_examples||[]).filter(x=>x.vehicle_identifier);
    const visitor=(data.unknown_visitor_examples||[])[0]||'VISITOR-DEMO-01';
    const buttons=[];
    authorized.forEach((item,index)=>buttons.push(
      `<button data-vehicle="${item.vehicle_identifier}" title="Authorized employee: ${item.display_name}">${item.employee_number || `Employee ${index+1}`}</button>`
    ));
    denied.forEach(item=>{
      let reason='Security review';
      if(String(item.employment_status||'').toUpperCase()==='LEAVE')reason='On Leave';
      else if(String(item.employment_status||'').toUpperCase()==='INACTIVE')reason='Inactive';
      else if(!item.parking_authorized)reason='Parking Suspended';
      buttons.push(`<button data-vehicle="${item.vehicle_identifier}" title="${item.display_name}: ${reason}">${item.employee_number} · ${reason}</button>`);
    });
    buttons.push(`<button data-vehicle="${visitor}" title="Unknown visitor vehicle; Security will assign ${data.next_available_visitor_code || 'the next available visitor ID'}">Visitor Demo</button>`);
    container.innerHTML=buttons.join('');
    container.querySelectorAll('[data-vehicle]').forEach(b=>b.addEventListener('click',()=>{$('vehicle-id').value=b.dataset.vehicle;}));
    if($('next-visitor-code'))$('next-visitor-code').textContent=data.next_available_visitor_code || 'NONE AVAILABLE';
    log('DEMO',`Loaded live demo identifiers from ees_data_platform${data.next_available_visitor_code?`; next visitor ID ${data.next_available_visitor_code}`:''}.`);
  }catch(err){
    if(container)container.innerHTML='<span class="demo-load-error">Demo IDs unavailable</span>';
    log('ERROR',`Unable to load demo identifiers: ${err.message}`,'alarm');
  }
}

function formatParkedSince(value){
  if(!value)return 'Entry time unavailable';
  const d=new Date(value);
  return Number.isNaN(d.getTime())?'Entry time unavailable':`Since ${d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
}
function occupantDisplayName(session){
  if(session.occupant_type==='EMPLOYEE')return session.display_name || session.employee_number || session.vehicle_identifier;
  return session.visitor_code ? `Visitor ${session.visitor_code}` : session.vehicle_identifier;
}
function renderOccupancyRoster(filter=occupancyFilter){
  occupancyFilter=filter || 'ALL';
  const all=plc.status.active_sessions || [];
  const rows=occupancyFilter==='ALL'?all:all.filter(s=>s.occupant_type===occupancyFilter);
  const title=occupancyFilter==='EMPLOYEE'?'Employees Currently Parked':occupancyFilter==='VISITOR'?'Visitors Currently Parked':'Everyone Currently Parked';
  if($('occupancy-modal-title'))$('occupancy-modal-title').textContent=title;
  if($('occupancy-roster-summary'))$('occupancy-roster-summary').textContent=`${rows.length} ${rows.length===1?'vehicle':'vehicles'} currently in the lot · ${plc.status.remaining} spaces available`;
  const roster=$('occupancy-roster');
  if(!roster)return;
  if(!rows.length){roster.innerHTML='<div class="occupancy-roster-empty">No matching vehicles are currently parked.</div>';return;}
  roster.innerHTML=rows.map(session=>`<div class="occupancy-roster-row ${session.occupant_type==='VISITOR'?'visitor':''}">
    <div><strong>${occupantDisplayName(session)}</strong><small>${session.employee_number || session.visitor_code || session.vehicle_identifier}</small></div>
    <span>${session.vehicle_identifier}</span>
    <span>Space ${session.space_number}</span>
    <span class="occupant-badge">${session.occupant_type}</span>
    <small>${formatParkedSince(session.entry_time)}</small>
  </div>`).join('');
}
function openOccupancyRoster(filter){
  renderOccupancyRoster(filter);
  $('occupancy-modal')?.classList.remove('hidden');
}
function closeOccupancyRoster(){$('occupancy-modal')?.classList.add('hidden');}
async function restartDemo(){
  if(plc.busy)return;
  const active=plc.status.occupied || 0;
  const ok=window.confirm(`Restart the parking demo? This will close ${active} active parking session${active===1?'':'s'}, clear pending Security reviews, return visitor IDs to the available pool, and reset the live lot to 0/70. Audit history will be preserved.`);
  if(!ok)return;
  const button=$('restart-demo');
  if(button)button.disabled=true;
  setBusy(true);
  try{
    const result=await api('/api/admin/reset-demo',{method:'POST'});
    plc.clearDecisionTags();plc.entryGate=false;plc.exitGate=false;plc.scan();
    hidePending();
    closeOccupancyRoster();
    $('vehicle-id').value='';
    setAccessResult('granted','DEMO RESTARTED',result.message || 'Parking lot returned to empty demo state.');
    $('state-text').textContent='Demo reset — ready for vehicle detection';
    log('RESET',`Demo restarted; ${result.closed_sessions||0} active session(s) closed.`,'warning');
    await refreshStatus();await refreshSecurity();await loadDemoIdentifiers();
  }catch(err){setAccessResult('denied','RESET FAILED',err.message);log('ERROR',err.message,'alarm');}
  finally{setBusy(false);if(button)button.disabled=false;}
}

function setAccessResult(state,title,message){const el=$('access-result');el.className=`access-result ${state||''}`;el.querySelector('strong').textContent=title;el.querySelector('p').textContent=message;}
function vehicleId(){return $('vehicle-id').value.trim().toUpperCase();}
function setBusy(value){plc.busy=value;$('detect-entry').disabled=value;$('detect-exit').disabled=value;$('approve-visitor').disabled=value;$('deny-visitor').disabled=value;}
function updateStatus(s){
  plc.status=s;$('count').textContent=s.occupied;$('employee-count').textContent=s.employees;$('visitor-count').textContent=s.visitors;$('remaining').textContent=`${s.remaining} ${s.remaining===1?'space':'spaces'} available`;$('meter-fill').style.width=`${Math.min(100,s.occupied/s.capacity*100)}%`;$('full').textContent=bool(s.full);$('empty').textContent=bool(s.empty);$('t-count').textContent=s.occupied;$('t-remaining').textContent=s.remaining;$('visitor-pool').textContent=String(s.visitor_pool_available);
  $('lot-state').textContent=s.full?'LOT FULL':s.empty?'LOT EMPTY':'SECURE ACCESS';$('lot-state').style.color=s.full?'var(--red)':s.empty?'var(--green)':'var(--cyan)';
  scene.syncSessions(s.active_sessions||[]);
  if($('occupancy-modal') && !$('occupancy-modal').classList.contains('hidden'))renderOccupancyRoster(occupancyFilter);
}
async function refreshStatus(){try{const s=await api('/api/parking/status');updateStatus(s);$('db-state').textContent='ONLINE';$('api-chip').textContent='● API + DB ONLINE';$('api-chip').className='chip api-online';}catch(err){$('db-state').textContent='OFFLINE';$('api-chip').textContent='● API OFFLINE';$('api-chip').className='chip api-offline';}}
async function health(){try{const h=await api('/api/health');$('api-chip').textContent=`● ${h.database} ONLINE`;$('api-chip').className='chip api-online';$('db-state').textContent='ONLINE';log('DB',`Connected to PostgreSQL database ${h.database}.`);await refreshStatus();await refreshSecurity();}catch(err){$('api-chip').textContent='● API OFFLINE';$('api-chip').className='chip api-offline';$('db-state').textContent='OFFLINE';setAccessResult('denied','API OFFLINE',`Start the FastAPI service at ${API_BASE}.`);log('ERROR',err.message,'alarm');}}
async function detectEntry(){
  const id=vehicleId();if(!id)return setAccessResult('denied','IDENTIFIER REQUIRED','Enter or select a vehicle identifier.');if(plc.estop)return setAccessResult('denied','E-STOP ACTIVE','Release emergency stop before processing access.');
  setBusy(true);plc.tags.Vehicle_Detected=true;$('state-text').textContent='Checking vehicle against ees_data_platform…';log('DETECT',`${id} detected at employee-lot entrance.`);
  try{
    const result=await api('/api/access/entry',{method:'POST',body:JSON.stringify({vehicle_identifier:id})});
    if(result.decision==='GRANTED'){
      plc.tags.Employee_Vehicle=result.occupant_type==='EMPLOYEE';plc.tags.Visitor_Vehicle=result.occupant_type==='VISITOR';plc.tags.Vehicle_Authorized=true;setAccessResult('granted','ACCESS GRANTED',`${result.occupant_type} assigned ${result.spot_number}. Gate opening automatically.`);$('state-text').textContent=`Access granted — ${result.spot_number}`;log('GRANTED',`${id} authorized for ${result.spot_number}.`);setBusy(false);await plc.animateEntry(result);await refreshStatus();
    }else if(result.decision==='SECURITY_REVIEW'){
      const employeeException=employeeExceptionFor(id) || (result.review_type==='EMPLOYEE_EXCEPTION'?{employee_number:result.employee_number,display_name:result.display_name,reason:result.review_reason}:null);
      pendingRequest=result;
      if(employeeException){
        plc.tags.Employee_Vehicle=true;
        plc.tags.Visitor_Vehicle=false;
        plc.tags.Vehicle_Authorized=false;
        setAccessResult('pending','EMPLOYEE ACCESS EXCEPTION',`${employeeException.employee_number} · ${employeeException.display_name}: ${employeeException.reason}. Routed to Security for review; gate remains closed.`);
        $('state-text').textContent=`Employee review — ${employeeException.reason}`;
        log('EMPLOYEE REVIEW',`${id}: ${employeeException.reason}. Security review required.`,'warning');
      }else{
        plc.tags.Employee_Vehicle=false;
        plc.tags.Visitor_Vehicle=true;
        setAccessResult('pending','VISITOR / UNKNOWN',`Unknown vehicle. Request ${result.security_request_id} sent to Security; gate remains closed.`);
        $('state-text').textContent='Visitor waiting for Security approval';
        log('VISITOR',`${id} requires Security approval.`,'warning');
      }
      setBusy(false);
      showPending(result);
      await refreshSecurity();
    }
  }catch(err){setBusy(false);plc.clearDecisionTags();setAccessResult('denied','ACCESS ERROR',err.message);$('state-text').textContent='Access request failed';log('ERROR',err.message,'alarm');}
}
async function detectExit(){
  const id=vehicleId();if(!id)return setAccessResult('denied','IDENTIFIER REQUIRED','Enter or select the exiting vehicle identifier.');if(plc.estop)return setAccessResult('denied','E-STOP ACTIVE','Release emergency stop before processing exit.');
  setBusy(true);plc.tags.Vehicle_Detected=true;$('state-text').textContent='Closing parking session…';log('EXIT',`${id} detected at exit.`);
  try{const result=await api('/api/access/exit',{method:'POST',body:JSON.stringify({vehicle_identifier:id})});setAccessResult('granted','EXIT AUTHORIZED',result.visitor_pass_code?`${result.visitor_pass_code} quarantined until ${new Date(result.reusable_after).toLocaleString()}.`:'Parking session closed. Exit gate opening.');$('state-text').textContent='Exit authorized';setBusy(false);await plc.animateExit(result);log('EXIT',`${id} exited; ${result.spot_number} released.`);await refreshStatus();}
  catch(err){setBusy(false);plc.clearDecisionTags();setAccessResult('denied','EXIT DENIED',err.message);$('state-text').textContent='Exit lookup failed';log('ERROR',err.message,'alarm');}
}
function showPending(req){
  $('security-empty').classList.add('hidden');
  $('security-request').classList.remove('hidden');
  const employeeException=employeeExceptionFor(req.vehicle_identifier);
  if(employeeException){
    $('security-vehicle').textContent=`${employeeException.employee_number} · ${employeeException.display_name}`;
    $('security-request-id').textContent=`Employee Review · Request ${req.security_request_id} · ${employeeException.reason}`;
    if($('next-visitor-code'))$('next-visitor-code').textContent='EMPLOYEE OVERRIDE — NO VISITOR ID';
    if($('approve-visitor')){
      $('approve-visitor').textContent='Approve Employee Override + Open Gate';
      $('approve-visitor').disabled=false;
    }
    if($('deny-visitor'))$('deny-visitor').textContent='Deny Employee Access';
    $('pending-count').textContent='1 EMPLOYEE REVIEW';
  }else{
    $('security-vehicle').textContent=req.vehicle_identifier;
    $('security-request-id').textContent=`Visitor Request ${req.security_request_id}`;
    if($('next-visitor-code'))$('next-visitor-code').textContent=req.next_visitor_code || demoIdentifiers?.next_available_visitor_code || 'CHECKING';
    if($('approve-visitor')){
      $('approve-visitor').textContent=`Buzz In + Issue ${req.next_visitor_code || demoIdentifiers?.next_available_visitor_code || 'Visitor ID'}`;
      $('approve-visitor').disabled=false;
    }
    if($('deny-visitor'))$('deny-visitor').textContent='Deny Visitor';
    $('pending-count').textContent='1 VISITOR PENDING';
  }
}
function hidePending(){
  pendingRequest=null;
  $('security-empty').classList.remove('hidden');
  $('security-request').classList.add('hidden');
  $('pending-count').textContent='0 PENDING';
  if($('approve-visitor')){
    $('approve-visitor').textContent='Buzz In + Issue Visitor ID';
    $('approve-visitor').disabled=false;
  }
  if($('deny-visitor'))$('deny-visitor').textContent='Deny Visitor';
}
async function refreshSecurity(){try{const data=await api('/api/security/requests?status=PENDING');$('pending-count').textContent=`${data.length} PENDING`;if(data.length){pendingRequest=data[0];showPending(data[0]);}else hidePending();}catch(_) {}}
async function approveVisitor(){
  if(!pendingRequest)return;
  const employeeException=employeeExceptionFor(pendingRequest.vehicle_identifier) || (pendingRequest.review_type==='EMPLOYEE_EXCEPTION'?{employee_number:pendingRequest.employee_number,display_name:pendingRequest.display_name,reason:pendingRequest.review_reason}:null);
  if(plc.estop)return setAccessResult('denied','E-STOP ACTIVE','Release emergency stop before Security approval.');
  setBusy(true);
  try{
    const notes=employeeException?`Temporary employee access override approved. Original exception: ${employeeException.reason}`:'Visitor approved from simulator HMI';
    const result=await api(`/api/security/requests/${pendingRequest.security_request_id}/approve`,{method:'POST',body:JSON.stringify({security_user:'SECURITY-DEMO',notes})});
    plc.tags.Security_Approval=true;
    plc.tags.Employee_Vehicle=result.occupant_type==='EMPLOYEE';
    plc.tags.Visitor_Vehicle=result.occupant_type==='VISITOR';
    plc.tags.Vehicle_Authorized=true;
    $('vehicle-id').value=result.vehicle_identifier;
    if(result.approval_type==='EMPLOYEE_OVERRIDE'){
      setAccessResult('granted','EMPLOYEE OVERRIDE APPROVED',`${result.employee_number} · ${result.display_name} authorized by Security for temporary plant access. Assigned ${result.spot_number}. No visitor pass issued.`);
      log('SECURITY',`${result.employee_number} override approved; ${result.vehicle_identifier} assigned ${result.spot_number}.`,'warning');
    }else{
      setAccessResult('granted','VISITOR APPROVED',`${result.visitor_pass_code} issued. Visitor assigned ${result.spot_number}.`);
      log('SECURITY',`${result.vehicle_identifier} approved; ${result.visitor_pass_code} issued.`);
    }
    hidePending();
    setBusy(false);
    await plc.animateEntry(result);
    await refreshStatus();
    await refreshSecurity();
    await loadDemoIdentifiers();
  }catch(err){
    setBusy(false);
    setAccessResult('denied','APPROVAL FAILED',err.message);
    log('ERROR',err.message,'alarm');
  }
}
async function denyVisitor(){if(!pendingRequest)return;const employeeException=employeeExceptionFor(pendingRequest.vehicle_identifier);setBusy(true);try{await api(`/api/security/requests/${pendingRequest.security_request_id}/deny`,{method:'POST',body:JSON.stringify({security_user:'SECURITY-DEMO',notes:employeeException?`Employee access exception: ${employeeException.reason}`:'Denied from simulator HMI'})});setAccessResult('denied',employeeException?'EMPLOYEE ACCESS DENIED':'VISITOR ACCESS DENIED',employeeException?`${employeeException.employee_number} · ${employeeException.display_name}: ${employeeException.reason}. Security denied the temporary employee override; gate remains closed.`:`${pendingRequest.vehicle_identifier} denied by Security.`);log('SECURITY',employeeException?`${employeeException.employee_number} review closed: ${employeeException.reason}.`:`${pendingRequest.vehicle_identifier} denied.`,'warning');hidePending();plc.clearDecisionTags();setBusy(false);await refreshSecurity();}catch(err){setBusy(false);log('ERROR',err.message,'alarm');}}

$('detect-entry').addEventListener('click',detectEntry);$('detect-exit').addEventListener('click',detectExit);$('approve-visitor').addEventListener('click',approveVisitor);$('deny-visitor').addEventListener('click',denyVisitor);$('estop').addEventListener('click',()=>plc.toggleEstop());$('clear-vehicle').addEventListener('click',()=>{$('vehicle-id').value='';$('vehicle-id').focus();});$('clear-log').addEventListener('click',()=>{$('log').innerHTML='';log('SYSTEM','Event buffer cleared.');});
$('restart-demo')?.addEventListener('click',restartDemo);$('employee-occupancy')?.addEventListener('click',()=>openOccupancyRoster('EMPLOYEE'));$('visitor-occupancy')?.addEventListener('click',()=>openOccupancyRoster('VISITOR'));$('close-occupancy-modal')?.addEventListener('click',closeOccupancyRoster);$('occupancy-modal')?.addEventListener('click',e=>{if(e.target===$('occupancy-modal'))closeOccupancyRoster();});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeOccupancyRoster();});
document.querySelectorAll('[data-camera]').forEach(b=>b.addEventListener('click',()=>scene.cameraView(b.dataset.camera)));
$('vehicle-id').addEventListener('keydown',e=>{if(e.key==='Enter')detectEntry();});

log('SYSTEM','Secure parking PLC initialized with 70-space digital twin.');log('SYSTEM',`API endpoint: ${API_BASE}`);health();loadDemoIdentifiers();setInterval(refreshStatus,10000);setInterval(refreshSecurity,12000);
