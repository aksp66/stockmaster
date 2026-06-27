/**
 * StockMaster PWA — client API + helpers d'installation et de synchronisation.
 * La file d'attente hors ligne (mouvements créés sans connexion) est gérée par
 * le Service Worker (sw.js) via IndexedDB + Background Sync : ce fichier n'a
 * donc qu'à appeler l'API normalement et à réagir aux messages du SW.
 */
const API_BASE = '/api/v1';
let token = localStorage.getItem('access_token');

async function apiCall(endpoint, method = 'GET', body) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401) {
    window.location = '/comptes/connexion/';
    return null;
  }
  return resp.json();
}

window.StockMasterAPI = { apiCall };

// ── Installation de la PWA (bouton "Installer") ────────────────────────────
let deferredInstallPrompt = null;

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  document.getElementById('btn-installer-pwa')?.classList.remove('hidden');
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  document.getElementById('btn-installer-pwa')?.classList.add('hidden');
});

window.PWAInstaller = {
  isAvailable: () => !!deferredInstallPrompt,
  async installer() {
    if (!deferredInstallPrompt) return 'unavailable';
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    return outcome; // 'accepted' ou 'dismissed'
  },
};

// ── Synchronisation différée : notifie l'utilisateur quand le SW a rejoué
//    la file de mouvements mise en attente hors ligne ────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', (event) => {
    if (event.data?.type === 'SYNC_COMPLETE') {
      const { succes, echecs, message } = event.data;
      const toast = document.createElement('div');
      toast.className = `toast ${echecs > 0 ? 'warning' : 'success'}`;
      toast.innerHTML = `<i class="fas fa-cloud-arrow-up"></i><span>${message}</span>`;
      let wrap = document.getElementById('tw');
      if (!wrap) {
        wrap = document.createElement('div');
        wrap.id = 'tw';
        wrap.className = 'toast-w';
        document.body.appendChild(wrap);
      }
      wrap.appendChild(toast);
      setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 400); }, 4000);
    }
  });
}

// ── Capacité de scan caméra (détection, utilisée par les pages de scan) ───
window.StockMasterScanner = {
  isSupported: () => 'BarcodeDetector' in window,
};
