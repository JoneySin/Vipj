"""🖼️/📄 POSTER ↔ TEXT VIEW MODE — **इकलौता source** (यही फाइल)।

यहाँ Poster/Text का पूरा behaviour एक बार लिखा है; `/search`, `/posts`,
`/actors`, group cards, group variants — सब इसी को इस्तेमाल करते हैं।
**दोनों modes का markup/code बिल्कुल एक ही है**, सिर्फ़ Text mode में
 thumbnail image (`vm-img`) और image-only सजावट (`vm-ph`/`vm-overlay`)
CSS से छिप जाती है। कोई अलग HTML branch / अलग render path नहीं।
Text mode की grid भी यहीं: GitHub reference (v5 `.res-grid`) जैसी
📱 1 / 📟 2 / 🖥️ 3 cards-per-row, हर card compact (नाम + chips + actions)।

┌── CHANGE IN ONE PLACE → EVERYWHERE ──────────────────────────────────┐
│ • नया mode label/chip/option बदलना हो   → `VIEW_MODE_OPTIONS`          │
│ • Text mode का layout/रंग/spacing बदलना → `MODE_CSS`                   │
│ • mode state / persistence / img src    → `MODE_JS` (`window.ViewMode`)│
│ • डिफ़ॉल्ट mode (अभी Text) बदलना हो   → `MODE_JS` का `DEFAULT`       │
│ • कोई नया page/card mode-aware करना हो  → नीचे वाले `VM_*` classes      │
│   markup में जोड़ो (`vm-grid`, `vm-card`, `vm-img`, …); किसी CSS/JS    │
│   फाइल में कोई नया नियम लिखने की ज़रूरत नहीं।                          │
└──────────────────────────────────────────────────────────────────────┘

📐 CLASS CONTRACT (mode-agnostic — कोई भी surface opt-in कर सकती है)::

    vm-grid      grid जिस पर Poster/Text लागू हो   (.vgrid, .cat-grid)
    vm-card      एक card                          (.vcard, .gcard, .cat-card)
    vm-master    अंदरूनी wrapper, अगर हो           (.gmaster)
    vm-poster    image + details वाला box         (.vposter, .gposter, .cat-poster-wrap)
    vm-img       thumbnail `<img>`                (.vimg, .cat-poster)
    vm-ph        "NO THUMBNAIL" placeholder       (.vph, .cat-ph)
    vm-overlay   सिर्फ़ image पर दिखने वाली सजावट (.vplay, .cat-grad)
    vm-details   chips/badges का container        (.vchips, .gbottom)
    vm-chip      एक अकेला badge/chip              (.cat-badge)
    vm-size      size badge                      (.vsize)
    vm-actions   admin Edit/Delete box           (.vadmin, .gadmin, .cat-actions)
    vm-always    (vm-actions के साथ) Text mode में हमेशा दिखे — सिर्फ़
                 admin को render होने वाली actions पर लगाओ
    vm-body      नाम / meta वाला हिस्सा           (.vbody, .gbody, .cat-meta)
    vm-title     नाम                             (.vtitle, .gtitle, .cat-meta-main)

`MODE_JS` में `ViewMode.imgAttrs(url)` सिर्फ़ `src` ⇄ `data-src` चुनता है,
इसलिए Text mode में thumbnail request जाती ही नहीं; Poster mode पर लौटते
ही `data-src` → `src` लग जाता है। Select पर `data-vm-select="1"` लगाओ तो
state, localStorage और styled dropdown label अपने-आप sync हो जाते हैं।
"""

# ── 🎛️ Dropdown options — labels/captions भी यहीं (filter specs इसी को पढ़ते हैं)
VIEW_MODE_OPTIONS = (("poster", "🖼️ Poster"), ("text", "📄 Text"))


# ── 🎨 CSS — `mode-text` का इकलौता नियम-सेट ─────────────────────────────
# ⚠️ SITE_CSS में ये सबसे आख़िर में append होता है, इसलिए `.vgrid`,
#    `.cat-grid`, `.vposter`, `.cat-poster-wrap` जैसे page-specific base
#    rules से specificity/order दोनों में ऊपर रहता है। नए page के लिए
#    सिर्फ़ `vm-*` classes जोड़ो, यहाँ कुछ बदलने की ज़रूरत नहीं।
MODE_CSS = r"""
/* ═══════════════ 🖼️📄 POSTER / TEXT — web/mode_assets.py ═══════════════
   Text mode: सिर्फ़ thumbnail + image-only decoration छिपता है।
   बाकी सब कुछ (नाम, chips, size, duration, group meta, admin actions)
   Poster mode जैसा ही, बस compact card में।
   📐 GitHub reference (v5 `.res-grid`) जैसी responsive grid — 📱 1 card/row,
   📟 2, 🖥️ 3 (Poster mode वाले `.vgrid` breakpoints से मेल खाते हैं)। */
.vm-grid.mode-text{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;
align-items:start}
@media(min-width:620px){.vm-grid.mode-text{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}
@media(min-width:1024px){.vm-grid.mode-text{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.vm-grid.mode-text>.state,.vm-grid.mode-text>.vempty,
.vm-grid.mode-text>.cat-vempty{grid-column:1/-1}
.vm-grid.mode-text .vm-card{display:flex;flex-direction:column;align-items:stretch;
gap:6px;padding:10px 11px;margin:0;border-radius:8px;min-width:0;max-width:100%}
.vm-grid.mode-text > .vm-card > .vm-master{display:flex;flex-direction:column;
align-items:stretch;gap:6px;padding:0}
.vm-grid.mode-text .vm-body{order:-1;display:flex;flex-direction:column;
align-items:stretch;gap:3px;padding:0;flex:0 0 auto;width:100%;min-width:0}
.vm-grid.mode-text .vm-title{display:block;flex:1;min-width:0;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis;-webkit-line-clamp:1}
/* ⚠️ Text mode में सिर्फ़ यही छिपता है — thumbnail से जुड़ी चीज़ें */
.vm-grid.mode-text .vm-img,
.vm-grid.mode-text .vm-ph,
.vm-grid.mode-text .vm-overlay{display:none!important}
/* poster box → compact inline details strip (chips/size इसी के अंदर हैं) */
.vm-grid.mode-text .vm-poster{position:static;display:flex;flex-wrap:wrap;
align-items:center;gap:5px;aspect-ratio:auto;width:100%;flex:0 0 auto;
min-width:0;padding:0;overflow:visible;background:none;animation:none;cursor:pointer}
.vm-grid.mode-text .vm-details{position:static;top:auto;left:auto;right:auto;
bottom:auto;display:flex;flex-wrap:wrap;gap:5px;padding:0;background:none;
pointer-events:none}
.vm-grid.mode-text .vm-chip{position:static;top:auto;left:auto;display:inline-flex;
align-items:center}
.vm-grid.mode-text .vm-size{position:static;right:auto;bottom:auto;
display:inline-block;pointer-events:none}
.vm-grid.mode-text .vm-actions{position:static;top:auto;left:auto;right:auto;
bottom:auto;gap:5px;padding:0;background:none;flex:0 0 auto;flex-wrap:wrap}
.vm-grid.mode-text .vm-actions button{flex:0 0 auto;min-width:0;padding:6px 9px}
/* catalog की admin actions सिर्फ़ ADMIN को render होती हैं ⇒ हमेशा दिखाओ;
   `.vadmin`/`.gadmin` poster-click पर खुलने वाली ही रहती हैं। */
.vm-grid.mode-text .vm-actions.vm-always{opacity:1;visibility:visible;
transform:none;pointer-events:all}
/* image पर लगने वाले dim pseudo-overlay बंद, details chips हमेशा रहें */
.vm-grid.mode-text .vm-card.admin-active .vm-poster::after,
.vm-grid.mode-text .vm-card.gactive .vm-poster::after{display:none}
.vm-grid.mode-text .vm-card.gactive .vm-details{display:flex}
@media(hover:hover){.vm-grid.mode-text .vm-card:hover{transform:translateX(3px)}}
"""


# ── ⚙️ JS — mode state का इकलौता engine ──────────────────────────────────
MODE_JS = r"""/* 🖼️📄 POSTER / TEXT — single source web/mode_assets.py (SITE_JS में) */
window.ViewMode=(function(){
  /* ⭐ DEFAULT_VIEW_MODE — डिफ़ॉल्ट बदलना हो तो बस ये एक लाइन बदलो।
     हर page (/search, /posts, /actors) खाली localStorage पर इसी से शुरू होगा। */
  var DEFAULT='text', RESET_FLAG='ff_mode_default_v2';
  var VALID=['poster','text'], cur=DEFAULT, cfg={}, bound=[];
  function norm(v){return VALID.indexOf(v)>=0?v:DEFAULT;}
  /* storage key भी यहीं — search / posts / actors अलग-अलग याद रखते हैं */
  function storageFor(kind){return kind?'ff_cat_mode_'+kind:'ff_view_mode';}
  /* पुराने browsers में 'poster' save था ⇒ नया डिफ़ॉल्ट एक बार लागू करो:
     सिर्फ़ mode वाली पुरानी keys हटाते हैं, इसके बाद user की नई पसंद याद रहती है. */
  function resetOnce(){
    try{
      if(localStorage.getItem(RESET_FLAG))return;
      for(var i=localStorage.length-1;i>=0;i--){
        var n=localStorage.key(i);
        if(n==='ff_view_mode'||n.indexOf('ff_cat_mode_')===0)localStorage.removeItem(n);
      }
      localStorage.setItem(RESET_FLAG,'1');
    }catch(e){}
  }
  function key(){return cfg.storage||storageFor(cfg.kind);}
  function get(){return cur;}
  function isText(){return cur==='text';}
  /* URL पहले से HTML-safe हो; सिर्फ़ src ⇄ data-src चुनते हैं।
     Text mode में किसी thumbnail की network request नहीं जाती। */
  function imgAttrs(url){
    var u=String(url==null?'':url);
    return (isText()?'data-src="'+u+'"':'src="'+u+'"')+
           ' data-thumb="'+u+'" data-retry="0"';
  }
  function apply(){
    Array.prototype.forEach.call(document.querySelectorAll('.vm-grid'),function(g){
      g.classList.toggle('mode-text',isText());
    });
    /* styled dropdown का label/value sync — change dispatch नहीं करते,
       नहीं तो नीचे वाला listener खुद को दोबारा चलाएगा। */
    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-vm-select]'),function(s){
        s.value=cur;
        if(window.ddSet)window.ddSet(s,cur,false);
      });
    if(!isText()){
      Array.prototype.forEach.call(
        document.querySelectorAll('.vm-grid img.vm-img[data-src]'),function(img){
          if(!img.getAttribute('src'))img.src=img.dataset.src;
        });
    }
  }
  function set(v){
    cur=norm(v);
    try{localStorage.setItem(key(),cur);}catch(e){}
    apply();                       /* CSS-only toggle — कोई re-render नहीं */
  }
  function bind(){
    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-vm-select]'),function(s){
        if(bound.indexOf(s)>=0)return;bound.push(s);
        s.addEventListener('change',function(){set(s.value);});
      });
  }
  function init(o){
    cfg=o||{};
    resetOnce();                 /* सिर्फ़ पहली बार — पुरानी Poster preference हटे */
    var v=null;try{v=localStorage.getItem(key());}catch(e){}
    cur=norm(v||DEFAULT);       /* कोई पसंद न हो ⇒ Text mode */
    bind();apply();
  }
  return {init:init,set:set,get:get,isText:isText,apply:apply,
          imgAttrs:imgAttrs,storageFor:storageFor,options:VALID.slice(),
          defaultMode:DEFAULT};
})();
/* पुराने inline handlers / tests के लिए छोटा alias — logic सिर्फ़ ViewMode में */
window.setMode=function(v){window.ViewMode.set(v);};
"""
