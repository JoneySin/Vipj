"""🗂️ PERMANENT GROUP UI — group card, master thumbnail, admin modal, Group Mode.

`web/web_assets.py` की तरह ही **एकमात्र source**: CSS, `GROUP_CARD_TEMPLATE`,
`GROUP_JS` (renderer — सभी pages पर `SITE_JS` में) और admin-only
`GROUP_ADMIN_HTML` / `GROUP_ADMIN_JS` (सिर्फ़ `/search` पर admin को)।

Standing constraints बरकरार:
  * `.vcard`/`.vgrid`/`vcardHTML()` shared video-card single-source — group के
    अंदर की हर variant बिल्कुल वही card है (`window.cardHTML(v)` से)।
  * Filter dropdown `FILTER_CSS`/`FILTER_JS` unchanged; Group Mode अपना FAB है।
  * Thumbnail के अंदर Edit/Delete overlay (`.vadmin`) file cards पर वैसा ही;
    group card की अपनी `.gadmin` overlay उसी poster के अंदर रहती है।
  * कोई primary/cloud/archive/section pill, कोई नया player tab।
"""

import json

GROUP_CSS = r"""
/* ═══════════════════════════════════════════════════════════════════
   🗂️ SHARED GROUP CARD — master thumbnail + quality chips + variants
   ═══════════════════════════════════════════════════════════════════ */
.gcard{display:block;position:relative;overflow:hidden;background:var(--card);
border:1px solid var(--line);border-radius:10px;color:var(--txt);cursor:pointer;
transition:transform .22s,border-color .22s,box-shadow .28s}
.gcard:focus-visible{outline:2px solid var(--red);outline-offset:2px}
@media(hover:hover){.gcard:not(.open):hover{transform:translateY(-4px);
border-color:rgba(229,9,20,.65);box-shadow:0 14px 34px rgba(0,0,0,.45)}}
.gcard.open{grid-column:1/-1;box-shadow:0 8px 28px rgba(0,0,0,.45);cursor:default}
.gposter{position:relative;aspect-ratio:16/9;overflow:hidden;
background:linear-gradient(90deg,var(--bg3) 0,#2b2b3a 50%,var(--bg3) 100%);
background-size:200% 100%;animation:sh 1.5s infinite linear}
.gposter.no-thumb{animation:none;background:none}
.gposter.no-thumb .vph{display:flex}
.gcard:hover .gposter .vimg.on{transform:scale(1.05)}
.gbottom{position:absolute;left:0;right:0;bottom:0;z-index:3;display:flex;
flex-wrap:wrap;gap:5px;padding:24px 8px 8px;
background:linear-gradient(transparent,rgba(0,0,0,.88));pointer-events:none}
.gqchip{background:#082f49;color:#7dd3fc;border:1px solid #0ea5e9;border-radius:5px;
font-size:10px;font-weight:800;padding:2px 8px;line-height:1.5}
.gqchip i{font-style:normal;color:#e0f2fe;margin-left:2px}
.gqchip.more{background:#3f3f46;color:#e4e4e7;border-color:#71717a}
/* 🎞️ एक फाइल की qualities  ⇄  📺 सीरीज के episodes */
.gkind{background:rgba(0,0,0,.78);backdrop-filter:blur(6px);border-radius:5px;
padding:3px 7px;font-size:10px;font-weight:800;border:1px solid rgba(255,255,255,.14)}
.gkind.quality{color:#fde68a;border-color:rgba(253,230,138,.45)}
.gkind.series{color:#c4b5fd;border-color:rgba(196,181,253,.5)}
.gqchip.ep{background:#3b0764;color:#e9d5ff;border-color:#a855f7}
.gmkind{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.gmkind button{border:1.5px solid var(--line);background:var(--bg3);color:var(--txt);
border-radius:9px;padding:10px 8px;font-size:12px;font-weight:800;cursor:pointer;
font-family:inherit;line-height:1.45;text-align:center}
.gmkind button small{display:block;font-size:10px;font-weight:600;color:var(--mut);margin-top:3px}
.gmkind button.on{border-color:var(--red);background:rgba(229,9,20,.13);color:var(--txt)}
.gmkind button:hover{border-color:var(--red)}
.gmep{width:96px;flex:0 0 auto;background:var(--bg);border:1px solid var(--line);
color:var(--txt);border-radius:6px;padding:4px 7px;font-size:11px;font-weight:800;
font-family:inherit;outline:none;text-align:center}
.gmep:focus{border-color:var(--red)}
.gmcount{font-size:11px;font-weight:800;color:#c4b5fd;margin-top:6px}
.gbody{padding:10px 11px 12px;display:flex;align-items:flex-start;gap:8px}
.gtitle{flex:1;min-width:0;color:var(--txt);font-size:12.5px;font-weight:600;
line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.gcard.open .gtitle{-webkit-line-clamp:unset}
.gtitle:hover{color:var(--red);text-decoration:underline;text-underline-offset:2px}
.gopenbtn{flex:0 0 auto;border:1px solid var(--line);background:var(--bg3);
color:var(--mut);border-radius:6px;padding:4px 8px;font-size:11px;font-weight:800;
cursor:pointer;font-family:inherit}
.gopenbtn:hover{border-color:var(--red);color:var(--txt)}
.gvariants{display:none;border-top:1px solid var(--line);gap:12px;padding:10px;
grid-template-columns:1fr}
.gcard.open .gvariants{display:grid}
@media(min-width:620px){.gcard.open .gvariants{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(min-width:1024px){.gcard.open .gvariants{grid-template-columns:repeat(3,minmax(0,1fr))}}
.gvariants .vcard:hover{transform:none}
.vgrid.mode-text .gposter{display:none}
.gadmin{position:absolute;left:0;right:0;bottom:0;z-index:6;display:flex;gap:5px;
flex-wrap:wrap;padding:8px;background:rgba(0,0,0,.86);opacity:0;visibility:hidden;
transform:translateY(8px);transition:opacity .18s,transform .18s,visibility .18s;pointer-events:none}
.gcard.gactive .gadmin{opacity:1;visibility:visible;transform:translateY(0);pointer-events:all}
.gcard.gactive .gbottom{display:none}
.gadmin button{flex:1 1 42%;min-width:90px;padding:8px 6px;border-radius:6px;
font-size:11px;font-weight:800;color:#fff;border:1px solid var(--line);
background:rgba(42,42,48,.92);cursor:pointer;font-family:inherit}
.gadmin button:hover{background:var(--red);border-color:var(--red)}
.gadmin .ga-del:hover{background:#a00808;border-color:var(--red)}
.gadmin button:active{transform:scale(.95)}
.gcard.gactive .gposter::after{content:'';position:absolute;inset:0;z-index:5;background:rgba(0,0,0,.35)}
/* ☑️ Group Mode: select files → permanent group */
.gfab{position:fixed;right:16px;bottom:18px;z-index:140;background:var(--red);color:#fff;
border:0;border-radius:999px;padding:11px 16px;font-size:12px;font-weight:800;
cursor:pointer;box-shadow:0 6px 20px rgba(229,9,20,.45);font-family:inherit}
.gselbar{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:150;
background:var(--bg2);border:1.5px solid var(--line);border-radius:14px;padding:9px 12px;
display:flex;align-items:center;gap:8px;box-shadow:0 8px 30px rgba(0,0,0,.55);max-width:96vw}
.gselbar span{font-size:12px;font-weight:700;color:var(--txt);white-space:nowrap}
.gselbar button{border:0;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:800;
cursor:pointer;color:#fff;background:var(--red);font-family:inherit}
.gselbar button.alt{background:var(--bg3);color:var(--txt)}
.gselbar button:disabled{opacity:.5}
.gsel-mode .vcard{cursor:pointer}
.gsel-mode .vcard::after{content:'';position:absolute;top:8px;right:8px;width:22px;height:22px;
border-radius:50%;border:2px solid #fff;background:rgba(0,0,0,.55);z-index:7;display:flex;
align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:900}
.gsel-mode .vcard.gsel::after{content:'✓';background:#22c55e;border-color:#22c55e}
.vcard.gsel{outline:2px solid #22c55e;outline-offset:-2px}
/* 🛠️ Group modal */
.gmodal{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.88);display:none;
align-items:center;justify-content:center;padding:14px}
.gmodal.open{display:flex}
.gmcard{background:var(--bg2);border:1px solid var(--line);border-radius:14px;width:100%;
max-width:560px;max-height:92vh;overflow-y:auto;padding:18px;box-sizing:border-box}
.gmhead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}
.gmhead h3{margin:0;font-size:16px;font-weight:900;color:var(--txt)}
.gmclose{background:none;border:0;color:var(--mut);font-size:22px;cursor:pointer;line-height:1}
.gmlabel{font-size:11px;font-weight:800;color:var(--mut);letter-spacing:.5px;margin:14px 0 6px}
.gminput{width:100%;background:var(--bg3);border:1.5px solid var(--line);color:var(--txt);
padding:10px 12px;border-radius:8px;font-size:13px;font-family:inherit;outline:none;box-sizing:border-box}
.gminput:focus{border-color:var(--red)}
.gmresults{max-height:150px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;margin-top:6px}
.gmres{display:flex;align-items:center;gap:8px;padding:9px 11px;font-size:12px;color:var(--txt);
cursor:pointer;border-bottom:1px solid var(--line)}
.gmres:last-child{border-bottom:0}
.gmres:hover,.gmres.on{background:var(--bg3);color:var(--red)}
.gmres b{color:#38bdf8;font-size:11px;min-width:40px}
.gmchosen{margin-top:8px;font-size:12px;font-weight:800;color:#22c55e}
.gmthumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px}
.gmth{position:relative;border:2px solid var(--line);border-radius:8px;overflow:hidden;
cursor:pointer;background:var(--bg3);aspect-ratio:16/9}
.gmth.on{border-color:#22c55e}
.gmth img{width:100%;height:100%;object-fit:cover;display:block}
.gmth em{position:absolute;left:0;right:0;bottom:0;font-style:normal;font-size:10px;
font-weight:800;color:#7dd3fc;background:rgba(0,0,0,.78);padding:2px 5px;text-align:center}
.gmauto{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:var(--mut)}
.gmmem{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--line);
font-size:12px;color:var(--txt)}
.gmmem span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gmmem button{border:0;background:none;color:var(--mut);font-size:14px;cursor:pointer}
.gmmem button:hover{color:var(--red)}
.gmeprow{display:flex;align-items:center;gap:8px;padding:7px 0;
border-bottom:1px solid var(--line);font-size:12px;color:var(--txt)}
.gmeprow span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gmrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px}
.gmbtn{border:0;border-radius:8px;padding:10px 14px;font-size:12px;font-weight:800;cursor:pointer;
color:#fff;background:var(--red);font-family:inherit}
.gmbtn.alt{background:var(--bg3);color:var(--txt);border:1px solid var(--line)}
.gmbtn.danger{background:#a00808}
.gmbtn:disabled{opacity:.5}
.gmnote{font-size:11px;color:var(--mut);line-height:1.5;margin-top:10px}
.gmtoast{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:400;
background:var(--bg2);border:1.5px solid var(--line);border-radius:10px;padding:10px 16px;
font-size:12px;font-weight:800;color:var(--txt);opacity:0;pointer-events:none;
transition:opacity .2s;box-shadow:0 8px 24px rgba(0,0,0,.5)}
.gmtoast.show{opacity:1}
.gmtoast.err{border-color:var(--red);color:#fca5a5}
.gmprogress{font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5}
@media(max-width:520px){.gselbar{left:8px;right:8px;transform:none;justify-content:center;flex-wrap:wrap}
.gfab{right:10px;bottom:76px}.gadmin button{flex:1 1 100%}}
"""

# Group card का markup — JS `GROUP_CARD_TEMPLATE` से, ठीक VCARD_TEMPLATE की तरह।
GROUP_CARD_TEMPLATE = (
    '<div class="gcard{CARD_CLASS}" role="button" tabindex="0" '
    'data-gkey="{GKEY}" data-gid="{GID}" aria-label="{NAME} — {COUNT} files">'
    '<div class="gmaster">'
    '<div class="gposter" onclick="gPoster(this,event)">'
    '<img class="vimg" {IMG_ATTRS} alt="" loading="lazy" '
    'onload="this.classList.add(\'on\')" onerror="{IMG_ERROR}">'
    '<div class="vph"><b>▶</b><span>NO THUMBNAIL</span></div>'
    '<div class="vchips">{TOPCHIPS}</div>'
    '<div class="gbottom">{QCHIPS}</div>{ADMIN}'
    '</div>'
    '<div class="gbody"><div class="gtitle" onclick="event.stopPropagation();gToggle(this)">{NAME}</div>'
    '<button class="gopenbtn" onclick="event.stopPropagation();gToggle(this)">▾ Files</button></div>'
    '</div>'
    '<div class="gvariants">{VARIANTS}</div></div>'
)

_GROUP_JS_TPL = r"""/* 🗂️ SHARED GROUP CARD — template web/group_assets.py से (Python → JS) */
(function(){
  var TPL=__GROUP_CARD_TEMPLATE__, GD={};
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  /* inline onclick="...'VALUE'..." के लिए: HTML entity + JS quote/backslash escape */
  function js1(s){return String(s==null?'':s)
    .replace(/\\/g,'\\\\').replace(/'/g,"\\'")
    .replace(/&/g,'&amp;').replace(/"/g,'&quot;')
    .replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function fill(t){return TPL.replace(/\{([A-Z_]+)\}/g,function(m,k){
    return Object.prototype.hasOwnProperty.call(t,k)?String(t[k]):'';});}
  function html(g,imgAttrs,imgError){
    if(!g||!g.group)return '';
    GD[String(g.key)]=g;
    var isEp=g.kind==='episodes';
    var n=isEp?(g.episodes||g.count||0):(g.qualities||g.count||0);
    var list=g.chips||[], MAX=6;
    var chips=list.slice(0,MAX).map(function(c){
      return '<span class="gqchip'+(isEp?' ep':'')+'">'+esc(c.label)+
        (c.count>1?' <i>x'+c.count+'</i>':'')+'</span>';
    }).join('');
    if(list.length>MAX)chips+='<span class="gqchip more">+'+esc(list.length-MAX)+'</span>';
    /* ⚠️ group card पर किसी एक फाइल का size/duration नहीं दिखाते — group में
       अलग-अलग size (और episodes में अलग duration) होते हैं। ये chips सिर्फ़
       GROUP-LEVEL हैं: #number, कितनी qualities / कितने episodes, type. */
    var top='<span class="vtag blue">'+(g.manual?'#'+esc(g.num)+' GROUP':'GROUP')+'</span>'+
            '<span class="vtag gold">'+esc(n)+(isEp?' EPISODES':' QUALITIES')+'</span>'+
            '<span class="gkind '+(isEp?'series':'quality')+'">'+
              (isEp?'📺 SERIES':'🎞️ SINGLE TITLE')+'</span>'+
            (g.type?'<span class="vtag">'+esc(g.type)+'</span>':'');
    var adm='';
    if(window.IS_GROUP_ADMIN){
      var k=js1(g.key), gd=js1(g.gid||'');
      adm='<div class="gadmin">'+
        '<button onclick="event.stopPropagation();gEdit(\''+k+'\')">'+
          (g.manual?'✏️ Edit Group #'+esc(g.num):'💾 Save as Group')+'</button>'+
        '<button onclick="event.stopPropagation();gSelectGroup(\''+k+'\')">☑️ Select files</button>'+
        (g.manual?'<button onclick="event.stopPropagation();gMerge(\''+k+'\')">🔀 Merge</button>'+
                  '<button class="ga-del" onclick="event.stopPropagation();gUngroup(\''+gd+'\')">🗑️ Ungroup</button>':'')+
      '</div>';
    }
    var variants=(g.variants||[]).map(function(v){
      return window.cardHTML?window.cardHTML(v):'';
    }).join('');
    return fill({
      CARD_CLASS:'', GKEY:esc(g.key), GID:esc(g.gid||''),
      NAME:esc(g.name), COUNT:esc(g.count||0),
      IMG_ATTRS:imgAttrs||'', IMG_ERROR:imgError||'thumbFail(this)',
      TOPCHIPS:top, QCHIPS:chips,
      ADMIN:adm, VARIANTS:variants
    });
  }
  window.groupHTML=html;
  window.gJs=js1;
  window.groupGet=function(k){return GD[String(k)];};
  window.gToggle=function(node){
    var c=node&&node.closest?node.closest('.gcard'):null;if(!c)return;
    c.classList.toggle('open');
  };
  window.gPoster=function(el,e){
    if(e)e.stopPropagation();
    var c=el.closest('.gcard');if(!c)return;
    if(!window.IS_GROUP_ADMIN){c.classList.toggle('open');return;}
    var was=c.classList.contains('gactive');
    Array.prototype.forEach.call(document.querySelectorAll('.gcard.gactive'),
      function(x){x.classList.remove('gactive');});
    if(!was)c.classList.add('gactive');
  };
  document.addEventListener('click',function(e){
    if(e.target&&e.target.closest&&e.target.closest('.gadmin'))return;
    Array.prototype.forEach.call(document.querySelectorAll('.gcard.gactive'),
      function(x){x.classList.remove('gactive');});
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape')Array.prototype.forEach.call(
      document.querySelectorAll('.gcard.gactive'),function(x){x.classList.remove('gactive');});
    if((e.key==='Enter'||e.key===' ')&&document.activeElement){
      var c=document.activeElement.closest&&document.activeElement.closest('.gcard');
      if(c&&document.activeElement===c){e.preventDefault();c.classList.toggle('open');}
    }
  });
})();
"""
GROUP_JS = _GROUP_JS_TPL.replace("__GROUP_CARD_TEMPLATE__",
                                 json.dumps(GROUP_CARD_TEMPLATE))


GROUP_ADMIN_HTML = r"""<div class="gmtoast" id="gmToast"></div>
<div class="gmodal" id="gmModal">
  <div class="gmcard">
    <div class="gmhead"><h3 id="gmTitle">🗂️ Permanent Group</h3>
      <button class="gmclose" onclick="gClose()" aria-label="Close">✕</button></div>
    <div id="gmBody"></div>
  </div>
</div>
<button class="gfab" id="gFab" onclick="gSelectMode()">☑️ Group Mode</button>
"""


GROUP_ADMIN_JS = r"""<script>
/* 🛠️ ADMIN GROUP ACTIONS — permanent groups, merge, scan, master thumbnail */
(function(){
  var SEL={}, selMode=false, mode='save', current=null, targetGid='',
      thumbFid='', currentKind='qualities', scanTimer=null;
  function q(s){return document.querySelector(s);}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  var jse=window.gJs||function(s){return String(s==null?'':s).replace(/'/g,"\\'");};
  var LIST=[];
  function toast(msg,err){var t=q('#gmToast');if(!t)return;
    t.textContent=msg;t.classList.toggle('err',!!err);t.classList.add('show');
    clearTimeout(t._tm);t._tm=setTimeout(function(){t.classList.remove('show');},3200);}
  function post(url,body){
    return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body||{}),credentials:'same-origin'}).then(function(r){
        return r.json().then(function(d){if(!r.ok||d.ok===false)
          throw new Error(d.error||('HTTP '+r.status));return d;});});
  }
  function refresh(){if(window.load)window.load(true);}
  function open(title,body){q('#gmTitle').textContent=title;q('#gmBody').innerHTML=body;
    q('#gmModal').classList.add('open');}
  window.gClose=function(){var m=q('#gmModal');if(m)m.classList.remove('open');
    current=null;targetGid='';thumbFid='';};
  function itemsFrom(g){
    return (g.variants||[]).map(function(v){return {id:v.file_id,name:v.name};});
  }
  function membersHtml(items,gid){
    return items.map(function(it){
      return '<div class="gmmem"><span>'+esc(it.name||it.id)+'</span>'+
        (gid?'<button title="Group से हटाओ" onclick="gRemove(\''+jse(gid)+'\',\''+jse(it.id)+'\')">✕</button>':'')+
        '</div>';
    }).join('');
  }
  function kindHtml(g){
    var isQ=currentKind!=='episodes';
    return '<div class="gmlabel">GROUP TYPE — क्या इस group में qualities हैं या episodes?</div>'+
      '<div class="gmkind">'+
        '<button type="button" data-kind="qualities" class="'+(isQ?'on':'')+'" '+
          'onclick="gPickKind(\'qualities\')">🎞️ Qualities'+
          '<small>एक ही फाइल / मूवी के अलग-अलग quality</small></button>'+
        '<button type="button" data-kind="episodes" class="'+(isQ?'':'on')+'" '+
          'onclick="gPickKind(\'episodes\')">📺 Episodes'+
          '<small>एक सीरीज के अलग-अलग एपिसोड</small></button>'+
      '</div>';
  }
  function episodesHtml(g){
    var rows=(g.variants||[]).map(function(v){
      return '<div class="gmeprow"><span>'+esc(v.name||v.file_id)+'</span>'+
        '<input class="gmep" data-fid="'+esc(v.file_id)+'" maxlength="24" '+
        'value="'+esc(v.el||'')+'" aria-label="Episode label" title="Episode label बदलें"></div>';
    }).join('');
    return '<div id="gmEpisodes" style="display:'+(currentKind==='episodes'?'block':'none')+'">'+
      '<div class="gmlabel">📺 EPISODE LABELS — चाहें तो हर file का episode नंबर बदलें</div>'+
      rows+'<div class="gmcount">इस group में '+(g.episodes||(g.variants||[]).length)+
      ' episodes / '+(g.variants||[]).length+' files</div></div>';
  }
  window.gPickKind=function(k){
    currentKind=(k==='episodes')?'episodes':'qualities';
    Array.prototype.forEach.call(document.querySelectorAll('.gmkind button'),function(b){
      b.classList.toggle('on',b.getAttribute('data-kind')===currentKind);});
    var ep=q('#gmEpisodes');if(ep)ep.style.display=(currentKind==='episodes'?'block':'none');
  };
  function groupMetric(x){
    x=x||{};
    if(x.kind==='episodes')return (x.episodes||x.count||0)+' episodes';
    return (x.qualities||x.count||0)+' qualities';
  }
  function collectEpisodes(){
    /* Type बदलकर वापस आने पर custom labels न मिटें — इसलिए inputs हमेशा
       पढ़ते हैं, चाहे episode editor इस वक्त hidden ही क्यों न हो। */
    var out={};
    Array.prototype.forEach.call(document.querySelectorAll('#gmEpisodes .gmep'),function(inp){
      var v=String(inp.value||'').trim();
      if(v)out[inp.getAttribute('data-fid')]=v.slice(0,24);
    });
    return out;
  }
  function thumbsHtml(g){
    var out='<div class="gmth'+(thumbFid?'':' on')+'" onclick="gPickThumb(\'\')">'+
      '<div class="gmauto" style="height:100%">⚡ AUTO<br>(highest quality)</div><em>AUTO</em></div>';
    (g.variants||[]).forEach(function(v){
      out+='<div class="gmth'+(thumbFid===v.file_id?' on':'')+'" onclick="gPickThumb(\''+esc(v.file_id)+'\')">'+
        (v.thumb?'<img src="'+esc(v.thumb)+'" alt="">':'<div class="gmauto" style="height:100%">no thumb</div>')+
        '<em>'+esc(v.ql||v.quality||'?')+'</em></div>';
    });
    return out;
  }

  /* ── Save / Edit modal ─────────────────────────────────────── */
  window.gEdit=function(k){
    var g=window.groupGet(k);if(!g)return;
    current=g;mode='save';targetGid=g.manual?String(g.gid):'';
    thumbFid=g.manual&&g.thumb_fid?String(g.thumb_fid):'';
    currentKind=(g.kind==='episodes')?'episodes':'qualities';
    var items=itemsFrom(g);
    open(g.manual?'✏️ Edit Group #'+g.num:'💾 Save as Permanent Group',
      '<div class="gmlabel">GROUP NAME</div>'+
      '<input class="gminput" id="gmName" value="'+esc(g.name)+'" placeholder="Movie / series का नाम">'+
      '<div class="gmlabel">मौजूदा GROUP में जोड़ो (नाम या #number)</div>'+
      '<input class="gminput" id="gmFind" placeholder="खोजें… जैसे #12 या naam" oninput="gFind(this.value)">'+
      '<div class="gmresults" id="gmResults"></div>'+
      '<div class="gmchosen" id="gmChosen">'+(targetGid?'✓ Group #'+esc(targetGid):'')+'</div>'+
      kindHtml(g)+episodesHtml(g)+
      '<div class="gmlabel">MASTER THUMBNAIL</div><div class="gmthumbs" id="gmThumbs">'+thumbsHtml(g)+'</div>'+
      '<div class="gmrow"><label class="gmbtn alt" style="cursor:pointer">📸 Custom upload'+
      '<input type="file" accept="image/*" id="gmFile" style="display:none" onchange="gUpload(this)"></label>'+
      (g.manual?'<button class="gmbtn alt" onclick="gClearCustom()">↩️ Custom हटाओ</button>':'')+'</div>'+
      '<div class="gmlabel">FILES ('+items.length+')</div>'+membersHtml(items,g.manual?String(g.gid):'')+
      '<div class="gmrow"><button class="gmbtn" id="gmSave" onclick="gSave()">'+
        (g.manual?'💾 Save Changes (नाम / type / thumbnail / files)':'💾 Save Group')+'</button>'+
      (g.manual?'<button class="gmbtn danger" onclick="gUngroup(\''+jse(g.gid)+'\')">🗑️ Ungroup</button>':'')+
      '<button class="gmbtn alt" onclick="gClose()">Cancel</button></div>'+
      '<div class="gmnote"><b>GROUP NAME</b> बदलकर Save करने पर उसी group का नाम DB में update होता है '+
      '(#number वही रहता है)। <b>GROUP TYPE</b> से तय करें कि इसमें एक फाइल की qualities हैं या सीरीज के '+
      'episodes — card पर <i>3 QUALITIES</i> या <i>12 EPISODES</i> उसी हिसाब से दिखेगा, और किसी एक फाइल का '+
      'size/duration group पर नहीं दिखेगा। Same-title की नई quality auto_keys से अपने-आप जुड़ जाएगी।</div>');
    if(targetGid)gFind('#'+targetGid);
  };
  window.gFind=function(v){
    var box=q('#gmResults');if(!box)return;
    fetch('/api/group/list?q='+encodeURIComponent(v||''),{credentials:'same-origin'})
      .then(function(r){return r.json();}).then(function(d){
        LIST=d.groups||[];
        box.innerHTML=LIST.map(function(x){
          return '<div class="gmres'+(String(x.id)===targetGid?' on':'')+'" onclick="gChoose(\''+jse(x.id)+'\')">'+
            '<b>#'+esc(x.num)+'</b><span>'+esc(x.name)+' · '+groupMetric(x)+'</span></div>';
        }).join('')||'<div class="gmres" style="color:var(--mut)">कोई group नहीं मिला</div>';
      }).catch(function(){});
  };
  window.gChoose=function(gid){
    targetGid=String(gid);
    var item=LIST.filter(function(x){return String(x.id)===targetGid;})[0]||{};
    var c=q('#gmChosen');if(c)c.textContent='✓ Group #'+(item.num||gid)+' — '+(item.name||'')+' में files जुड़ेंगी';
    var n=q('#gmName');if(n&&item.name)n.value=item.name;   /* .value = safe, कोई HTML नहीं */
    gFind('#'+gid);
  };
  window.gPickThumb=function(fid){thumbFid=String(fid||'');
    var g=current;if(!g)return;var box=q('#gmThumbs');if(box)box.innerHTML=thumbsHtml(g);};
  window.gClearCustom=function(){
    if(!current||!current.gid){toast('पहले group save करें',true);return;}
    post('/api/group/update',{group_id:current.gid,clear_custom:true})
      .then(function(){toast('↩️ Custom thumbnail हटाया');window.gClose();refresh();})
      .catch(function(e){toast(e.message,true);});
  };
  window.gUpload=function(input){
    var f=input.files&&input.files[0];if(!f)return;
    if(!current||!current.gid){toast('पहले group save करें',true);return;}
    var fd=new FormData();fd.append('group_id',current.gid);fd.append('image',f);
    fetch('/api/group/upload_thumb',{method:'POST',body:fd,credentials:'same-origin'})
      .then(function(r){return r.json();}).then(function(d){
        if(d.ok===false)throw new Error(d.error||'upload fail');
        toast('📸 Custom master thumbnail save');window.gClose();refresh();
      }).catch(function(e){toast(e.message,true);});
  };
  window.gSave=function(){
    var g=current;if(!g)return;
    var name=String((q('#gmName')||{}).value||'').trim();
    if(!targetGid&&!name){toast('Group का नाम लिखिए',true);return;}
    var btn=q('#gmSave');if(btn)btn.disabled=true;
    var emap=collectEpisodes();
    var body={items:itemsFrom(g),name:name,kind:currentKind,episode_map:emap};
    if(targetGid)body.group_id=targetGid;
    post('/api/group/save',body).then(function(d){
      var gid=d.group_id||targetGid||'';
      /* ✏️ नाम बदलना save-members से अलग काम है — `/api/group/update` पर
         साफ़ तौर पर भेजो (और master thumbnail भी उसी call में)। */
      var upd={group_id:gid,kind:currentKind,episode_map:emap};
      if(name)upd.name=name;
      if(thumbFid)upd.thumb_file_id=thumbFid;
      if(!gid)return d;
      return post('/api/group/update',upd).then(function(){return d;});
    }).then(function(d){
      /* तुरंत card का नाम बदलो — reload आने का इंतज़ार नहीं, और अगर fetch
         fail हो जाए तब भी UI में नया नाम दिखे। अगर कोई दूसरा target group
         चुना है तो यहाँ rename न दिखाएँ; refresh सही state लाएगा। */
      var sameGroup=!targetGid||String(targetGid)===String(g.gid||'');
      if(name&&sameGroup){
        Array.prototype.forEach.call(document.querySelectorAll('.gcard'),function(c){
          if(c.getAttribute('data-gid')===String(d.group_id||targetGid||'')||
             c.getAttribute('data-gkey')===String(g.key||'')){
            var t=c.querySelector('.gtitle');if(t)t.textContent=name;
          }
        });
        var gd=window.groupGet(g.key);if(gd)gd.name=name;
      }
      /* group type/episode labels तुरंत card पर भी दिखें (refresh से पहले) */
      var gd2=window.groupGet(g.key);
      if(gd2&&sameGroup){gd2.kind=currentKind;gd2.episode_map=emap;}
      toast('🗂️ Group #'+d.num+' save हो गया · '+
        (currentKind==='episodes'?'📺 episodes':'🎞️ qualities'));
      window.gClose();refresh();
    }).catch(function(e){toast(e.message,true);if(btn)btn.disabled=false;});
  };
  window.gRemove=function(gid,fid){
    if(!confirm('इस file को group से हटाएँ?'))return;
    post('/api/group/remove_file',{group_id:gid,file_id:fid})
      .then(function(){toast('File group से हटी');window.gClose();refresh();})
      .catch(function(e){toast(e.message,true);});
  };
  window.gUngroup=function(gid){
    if(!gid||!confirm('Group हटाएँ? Files DELETE नहीं होंगी, बस ungroup होंगी।'))return;
    post('/api/group/delete',{group_id:gid})
      .then(function(){toast('🗑️ Ungroup हो गया');window.gClose();refresh();})
      .catch(function(e){toast(e.message,true);});
  };

  /* ── Merge modal ───────────────────────────────────────────── */
  window.gMerge=function(k){
    var g=window.groupGet(k);if(!g||!g.manual)return;
    current=g;
    open('🔀 Merge Group #'+g.num,
      '<div class="gmlabel">TARGET GROUP NUMBER</div>'+
      '<input class="gminput" id="gmTarget" placeholder="जैसे 12 या #12" oninput="gFindMerge(this.value)">'+
      '<div class="gmnote">Source group #'+esc(g.num)+' की सारी files + auto_keys target group में '+
      'चली जाएँगी, source हट जाएगा। Files delete नहीं होतीं।</div>'+
      '<div class="gmresults" id="gmMergeResults"></div>'+
      '<div class="gmlabel">FILES ('+(g.variants||[]).length+')</div>'+membersHtml(itemsFrom(g),'')+
      '<div class="gmrow"><button class="gmbtn" onclick="gDoMerge()">🔀 Merge</button>'+
      '<button class="gmbtn alt" onclick="gClose()">Cancel</button></div>');
    gFindMerge('');
  };
  window.gFindMerge=function(v){
    var box=q('#gmMergeResults');if(!box)return;
    fetch('/api/group/list?q='+encodeURIComponent(v||''),{credentials:'same-origin'})
      .then(function(r){return r.json();}).then(function(d){
        box.innerHTML=(d.groups||[]).filter(function(x){return String(x.id)!==String(current.gid);})
          .map(function(x){return '<div class="gmres" onclick="gPickMerge(\''+jse(x.id)+'\')">'+
            '<b>#'+esc(x.num)+'</b><span>'+esc(x.name)+' · '+groupMetric(x)+'</span></div>';}).join('')||
          '<div class="gmres" style="color:var(--mut)">कोई दूसरा group नहीं मिला</div>';
      }).catch(function(){});
  };
  window.gPickMerge=function(gid){var t=q('#gmTarget');if(t)t.value=String(gid);};
  window.gDoMerge=function(){
    var t=(q('#gmTarget')||{}).value||'';
    if(!t.trim()){toast('Target group number लिखिए',true);return;}
    post('/api/group/merge',{source:String(current.gid),target:t.trim()})
      .then(function(d){toast('🔀 Group #'+d.num+' में merge हो गया');window.gClose();refresh();})
      .catch(function(e){toast(e.message,true);});
  };

  /* ── ☑️ Group Mode — अलग-अलग cards चुनकर group बनाओ ─────────── */
  function renderBar(){
    var fab=q('#gFab');if(fab)fab.style.display=selMode?'none':'block';
    var bar=q('#gSelBar');
    if(!selMode){if(bar)bar.remove();return;}
    if(!bar){bar=document.createElement('div');bar.id='gSelBar';bar.className='gselbar';
      document.body.appendChild(bar);}
    var keys=Object.keys(SEL),n=keys.length;
    bar.innerHTML='<span>'+n+' selected</span>'+
      '<button onclick="gOpenSelected()"'+(n>=2?'':' disabled')+'>🗂️ Group</button>'+
      '<button class="alt" onclick="gScanAll()">⚙️ Scan all</button>'+
      '<button class="alt" onclick="gSelectMode()">Cancel</button>';
  }
  window.gSelectMode=function(){
    selMode=!selMode;SEL={};
    var grid=q('#grid');if(grid)grid.classList.toggle('gsel-mode',selMode);
    Array.prototype.forEach.call(document.querySelectorAll('.vcard.gsel'),
      function(c){c.classList.remove('gsel');});
    renderBar();
  };
  document.addEventListener('click',function(e){
    if(!selMode)return;
    var c=e.target&&e.target.closest&&e.target.closest('.vcard[data-fid]');
    if(!c)return;
    e.preventDefault();e.stopPropagation();
    var fid=c.dataset.fid;if(!fid)return;
    try{fid=decodeURIComponent(fid);}catch(x){}
    if(SEL[fid])delete SEL[fid];else SEL[fid]={id:fid,name:c.dataset.name||fid};
    c.classList.toggle('gsel',!!SEL[fid]);renderBar();
  },true);
  window.gSelectGroup=function(k){
    var g=window.groupGet(k);if(!g)return;
    SEL={};(g.variants||[]).forEach(function(v){SEL[v.file_id]={id:v.file_id,name:v.name};});
    selMode=true;var grid=q('#grid');if(grid)grid.classList.add('gsel-mode');
    renderBar();toast('☑️ '+Object.keys(SEL).length+' files select — और जोड़ने के लिए cards पर click करें');
  };
  window.gOpenSelected=function(){
    var items=Object.keys(SEL).map(function(k){return SEL[k];});
    if(items.length<2){toast('कम-से-कम 2 files चुनिए',true);return;}
    var fake={group:true,manual:false,gid:'',num:'',name:'',count:items.length,
      key:'sel:'+Date.now(),variants:items.map(function(it){
        return {file_id:it.id,name:it.name,thumb:'',size:'',quality:'',duration:'',type:'VIDEO'};
      }),chips:[],type:'VIDEO',duration:'',size:''};
    window.groupHTML(fake,'');                 /* GD में register करो */
    selMode=false;SEL={};var grid=q('#grid');if(grid)grid.classList.remove('gsel-mode');renderBar();
    window.gEdit(fake.key);
  };

  /* ── ⚙️ Scan all + progress ────────────────────────────────── */
  window.gScanAll=function(){
    if(!confirm('पूरी library scan करके permanent groups बनाएँ? (बड़ी library में कुछ मिनट लग सकते हैं)'))return;
    post('/api/group/scan_all',{}).then(function(d){
      toast(d.started?'⚙️ Scan शुरू हो गया…':'⚙️ Scan पहले से चल रहा है');
      clearInterval(scanTimer);
      scanTimer=setInterval(function(){
        fetch('/api/group/scan_status',{credentials:'same-origin'}).then(function(r){return r.json();})
          .then(function(s){
            if(s.running){toast('⚙️ '+s.phase+' ('+s.scanned+'/'+s.total+')');}
            else{clearInterval(scanTimer);
              if(s.error)toast('Scan error: '+s.error,true);
              else{toast('✅ Scan complete: '+s.created+' नये groups, '+s.added+' files जुड़ीं');refresh();}}
          }).catch(function(){});
      },3000);
    }).catch(function(e){toast(e.message,true);});
  };
  q('#gmModal').addEventListener('click',function(e){if(e.target===this)window.gClose();});
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&q('#gmModal').classList.contains('open'))window.gClose();
  });
  renderBar();
})();
</script>"""
