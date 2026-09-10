(() => {
  const $ = id => document.getElementById(id);
  const startBtn = $('startScanner');
  const stopBtn = $('stopScanner');
  const video = $('scannerVideo');
  const screen = $('scannerScreen');
  const status = $('scannerStatus');
  const resultBox = $('scannerResult');
  const form = $('barcodeForm');
  const input = $('barcodeInput');
  if (!startBtn || !video || !resultBox || !form || !input) return;

  let controls = null;
  let scanning = false;
  let busy = false;
  let lastCode = '';
  let lastReadAt = 0;

  const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  const norm = s => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const clean = s => String(s || '').replace(/\D/g,'').slice(0,18);
  const setStatus = s => { status.textContent = s; };

  function mentionsMorocco(value){
    const text = norm(Array.isArray(value) ? value.join(' ') : value);
    return ['morocco','marruecos','maroc','marokko','marocco','المغرب'].some(x => text.includes(norm(x)));
  }

  function localVerified(code){
    if (window.OM_VERIFIED_BARCODES?.[code]) return window.OM_VERIFIED_BARCODES[code];
    const rows = Array.isArray(window.data) ? window.data : [];
    return rows.find(x => String(x.barcode || '') === code || (Array.isArray(x.barcodes) && x.barcodes.map(String).includes(code))) || null;
  }

  function prefix611(code){ return code.startsWith('611'); }

  async function fetchProduct(code){
    const fields = ['code','product_name','brands','origins','origins_tags','manufacturing_places','manufacturing_places_tags','image_front_small_url'].join(',');
    const endpoint = `https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(code)}?product_type=all&fields=${encodeURIComponent(fields)}`;
    const r = await fetch(endpoint, {headers:{Accept:'application/json'}});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return {json:await r.json(), page:`https://world.openfoodfacts.org/product/${encodeURIComponent(code)}`};
  }

  function show(kind, {code,title,message,chips=[],image='',url='',archive=''}){
    const cfg = {
      verified:['!','Marruecos confirmado en nuestro archivo'],
      declared:['!','Marruecos declarado en la base consultada'],
      hint:['?','Indicio relacionado con Marruecos'],
      clear:['✓','Sin evidencia marroquí en los datos consultados'],
      unknown:['?','No hay datos suficientes']
    }[kind] || ['?','Resultado'];

    resultBox.className = `scanner-result ${kind}`;
    resultBox.innerHTML = `
      <div class="result-mark">${cfg[0]}</div>
      <div>
        <span class="result-eyebrow">${esc(cfg[1])}</span>
        <h3>${esc(title)}</h3>
        <p>${message}</p>
        ${image ? `<img src="${esc(image)}" alt="" style="width:74px;height:74px;object-fit:contain;background:#fff;border:1px solid #aaa;margin-top:12px">` : ''}
        <div class="result-meta"><span class="result-chip">EAN / GTIN ${esc(code)}</span>${chips.filter(Boolean).map(x=>`<span class="result-chip">${esc(x)}</span>`).join('')}</div>
        <div class="result-actions">
          ${url ? `<a class="primary" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Abrir fuente ↗</a>` : ''}
          ${archive ? `<button type="button" data-archive="${esc(archive)}">Buscar en el archivo</button>` : ''}
        </div>
      </div>`;

    resultBox.querySelector('[data-archive]')?.addEventListener('click', e => {
      const search = $('search');
      if (!search) return;
      search.value = e.currentTarget.dataset.archive;
      search.dispatchEvent(new Event('input',{bubbles:true}));
      $('productos')?.scrollIntoView({behavior:'smooth',block:'start'});
    });
  }

  async function check(raw){
    const code = clean(raw);
    input.value = code;
    if (code.length < 8){ setStatus('El código parece incompleto.'); return; }
    if (busy) return;
    busy = true;
    setStatus(`Consultando ${code}…`);

    try{
      const verified = localVerified(code);
      if (verified && ['confirmed','processed'].includes(verified.status)){
        show('verified', {
          code,
          title:verified.product || `Código ${code}`,
          message:`<strong>${esc(verified.evidence || 'Ficha verificada por ORIGEN MARRUECOS.')}</strong>${verified.status === 'processed' ? ' La relación documentada es de elaboración o envasado en Marruecos; la materia prima puede proceder de otro país.' : ''}`,
          chips:[verified.brand, verified.status === 'processed' ? 'Elaborado / envasado' : 'Origen confirmado'],
          url:verified.url,
          archive:verified.product || verified.brand
        });
        setStatus('Coincidencia en la base verificada de ORIGEN MARRUECOS.');
        return;
      }

      let external;
      try { external = await fetchProduct(code); }
      catch (e){
        if (prefix611(code)){
          show('hint',{code,title:`Código ${code}`,message:'El código comienza por <strong>611</strong>, prefijo asignado por GS1 Marruecos. <strong>No demuestra el país de fabricación.</strong> La consulta externa no está disponible ahora, así que hay que revisar la etiqueta.',chips:['Prefijo GS1 Marruecos','Origen no confirmado']});
          setStatus('Consulta externa no disponible. Se muestra solo el indicio GS1.');
        } else {
          show('unknown',{code,title:`Código ${code}`,message:'No hemos podido consultar la base externa y no existe una coincidencia local verificada. No se puede determinar el origen con rigor.',chips:['Sin resultado']});
          setStatus('No se pudo completar la consulta externa.');
        }
        return;
      }

      const payload = external.json;
      const p = payload?.product;
      const found = Boolean(p && (payload.status === 1 || p.code || p.product_name || p.brands));
      const is611 = prefix611(code);

      if (!found){
        show(is611 ? 'hint' : 'unknown', {
          code,
          title:'Producto no identificado',
          message:is611 ? 'No aparece una ficha del producto. El prefijo <strong>611</strong> es un indicio de asignación GS1 Marruecos, pero <strong>no equivale a fabricado en Marruecos</strong>. Revisa el país de origen o fabricación en la etiqueta.' : 'No aparece en la base consultada ni existe todavía una ficha verificada por ORIGEN MARRUECOS. El código de barras por sí solo no permite determinar el país de origen.',
          chips:is611 ? ['Prefijo GS1 Marruecos','Producto sin ficha'] : ['Producto sin ficha'],
          url:external.page
        });
        setStatus('Producto no encontrado en la base consultada.');
        return;
      }

      const originMA = mentionsMorocco(p.origins) || mentionsMorocco(p.origins_tags);
      const madeMA = mentionsMorocco(p.manufacturing_places) || mentionsMorocco(p.manufacturing_places_tags);
      const title = p.product_name || p.brands || `Código ${code}`;
      const chips = [p.brands, originMA ? 'Origen: Marruecos' : '', madeMA ? 'Fabricación: Marruecos' : '', is611 ? 'Prefijo GS1 611' : ''];

      if (originMA || madeMA){
        const what = originMA && madeMA ? 'origen y fabricación' : originMA ? 'origen' : 'lugar de fabricación';
        show('declared',{code,title,message:`Open Food Facts contiene una declaración que vincula el <strong>${what}</strong> con Marruecos. Es una base colaborativa, por lo que la mostramos como evidencia externa y no con el mismo nivel que una ficha oficial verificada por nosotros.`,chips,image:p.image_front_small_url,url:external.page,archive:p.product_name || p.brands});
        setStatus('Encontrada una declaración relacionada con Marruecos.');
        return;
      }

      if (is611){
        show('hint',{code,title,message:'El producto está identificado, pero su ficha <strong>no declara Marruecos como origen ni como lugar de fabricación</strong>. Como el EAN empieza por 611, lo marcamos para revisar la etiqueta, no como origen marroquí confirmado.',chips,image:p.image_front_small_url,url:external.page,archive:p.product_name || p.brands});
        setStatus('Producto identificado con prefijo 611, sin origen marroquí declarado.');
        return;
      }

      const originText = String(p.origins || '').trim();
      const madeText = String(p.manufacturing_places || '').trim();
      const hasOriginData = originText || (Array.isArray(p.origins_tags) && p.origins_tags.length);
      const hasMadeData = madeText || (Array.isArray(p.manufacturing_places_tags) && p.manufacturing_places_tags.length);

      if (hasOriginData || hasMadeData){
        show('clear',{code,title,message:'La ficha consultada contiene información de origen o fabricación y <strong>no señala Marruecos</strong>. Esto no sustituye la comprobación del envase, porque un mismo EAN puede mantenerse aunque cambien lotes o cadenas de suministro.',chips:[p.brands,originText ? `Origen: ${originText}` : '',madeText ? `Fabricación: ${madeText}` : ''],image:p.image_front_small_url,url:external.page,archive:p.product_name || p.brands});
        setStatus('Producto identificado sin relación marroquí en los campos consultados.');
      } else {
        show('unknown',{code,title,message:'El producto existe en la base, pero <strong>faltan datos de país de origen y lugar de fabricación</strong>. No sería serio clasificarlo como marroquí ni descartarlo. Hay que revisar la etiqueta.',chips:[p.brands,'Origen sin datos'],image:p.image_front_small_url,url:external.page,archive:p.product_name || p.brands});
        setStatus('Producto identificado, pero sin datos suficientes de origen.');
      }
    } finally {
      busy = false;
    }
  }

  async function start(){
    if (scanning) return;
    if (!window.ZXingBrowser){ setStatus('No se ha cargado el lector. Puedes introducir el EAN manualmente.'); return; }
    startBtn.disabled = true;
    setStatus('Solicitando permiso para usar la cámara…');
    try{
      const reader = new ZXingBrowser.BrowserMultiFormatReader(undefined,{delayBetweenScanAttempts:180,delayBetweenScanSuccess:1200});
      controls = await reader.decodeFromConstraints({audio:false,video:{facingMode:{ideal:'environment'}}},video,result=>{
        if (!result || busy) return;
        const code = clean(result.getText ? result.getText() : result.text);
        const now = Date.now();
        if (!code || (code === lastCode && now-lastReadAt < 2500)) return;
        lastCode = code; lastReadAt = now; check(code);
      });
      scanning = true;
      screen.classList.add('active');
      stopBtn.disabled = false;
      startBtn.textContent = 'Cámara activa';
      setStatus('Cámara activa. Centra el código de barras dentro del recuadro.');
    } catch (e){
      console.error(e);
      startBtn.disabled = false;
      startBtn.textContent = 'Activar cámara';
      setStatus('No se pudo abrir la cámara. Comprueba los permisos del navegador o usa la entrada manual.');
    }
  }

  function stop(){
    try { controls?.stop(); } catch(e) {}
    controls = null; scanning = false;
    screen.classList.remove('active');
    stopBtn.disabled = true;
    startBtn.disabled = false;
    startBtn.textContent = 'Activar cámara';
    setStatus('Cámara detenida.');
  }

  startBtn.addEventListener('click',start);
  stopBtn.addEventListener('click',stop);
  form.addEventListener('submit',e=>{e.preventDefault();check(input.value);});
  input.addEventListener('input',()=>{input.value=clean(input.value);});
  window.addEventListener('pagehide',()=>{if(scanning) stop();});
})();

// Preproducción: usa los assets locales del repositorio para que las fichas no dependan
// de hosts externos y para mantener un lienzo de producto uniforme.
(() => {
  const logoPaths = {
    'Mercadona':'assets/logos/mercadona.svg',
    'Carrefour':'assets/logos/carrefour.svg',
    'Alcampo':'assets/logos/alcampo.png',
    'Lidl':'assets/logos/lidl.svg',
    'Aldi':'assets/logos/aldi.svg',
    'DIA':'assets/logos/dia.svg'
  };
  let activeDetailId = '';
  let scheduled = false;

  const rowById = id => (Array.isArray(window.data) ? window.data.find(x => x.id === id) : null);

  function localizeLogos(root=document){
    root.querySelectorAll?.('img[alt^="Logo "]').forEach(img => {
      const chain = img.alt.slice(5).trim();
      const src = logoPaths[chain];
      if (!src || img.dataset.omLocalLogo === '1') return;
      img.dataset.omLocalLogo = '1';
      img.src = src;
      img.removeAttribute('referrerpolicy');
    });
  }

  function productFigure(id, product){
    const fig = document.createElement('div');
    fig.className = 'product-photo';
    fig.dataset.productImage = id;
    const img = document.createElement('img');
    img.src = `assets/products/${encodeURIComponent(id)}.webp?v=2`;
    img.alt = product ? `Imagen de ${product}` : 'Imagen del producto';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.addEventListener('error', () => fig.remove(), {once:true});
    fig.appendChild(img);
    return fig;
  }

  function enhanceCards(){
    document.querySelectorAll('.product-card').forEach(card => {
      const detail = card.querySelector('[data-detail]');
      const id = detail?.dataset.detail;
      if (!id || card.querySelector(`.product-photo[data-product-image="${CSS.escape(id)}"]`)) return;
      const row = rowById(id);
      const top = card.querySelector('.product-top');
      if (!top) return;
      top.insertAdjacentElement('afterend', productFigure(id, row?.product));
    });
  }

  function enhanceDetail(){
    if (!activeDetailId) return;
    const body = document.getElementById('detailBody');
    if (!body || body.querySelector('.modal-product-photo')) return;
    const row = rowById(activeDetailId);
    if (!row) return;
    const fig = productFigure(activeDetailId, row.product);
    fig.classList.add('modal-product-photo');
    const status = body.querySelector('.status');
    if (status) status.insertAdjacentElement('afterend', fig);
    else body.prepend(fig);
  }

  function runEnhancements(){
    scheduled = false;
    localizeLogos();
    enhanceCards();
    enhanceDetail();
  }

  function schedule(){
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(runEnhancements);
  }

  document.addEventListener('click', e => {
    const button = e.target.closest?.('[data-detail]');
    if (!button) return;
    activeDetailId = button.dataset.detail || '';
    setTimeout(schedule, 0);
  }, true);

  const observer = new MutationObserver(schedule);
  observer.observe(document.body, {childList:true, subtree:true});
  window.addEventListener('load', schedule);
  schedule();
})();
