// Offline answer queue backed by IndexedDB.
//
// Stores `{ question_id, user_answer, answered_at, definition_id }` rows
// when the user is offline. On reconnect (or background-sync flush), the
// hook drains the queue via the regular `submit_answer` endpoint and removes
// rows on success.

const DB_NAME = "pycil-offline";
const STORE = "answer_queue";
const DB_VERSION = 1;

export type OfflineAnswer = {
  id?: number;
  question_id: number;
  user_answer: string;
  answered_at: number;
  definition_id: number;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueueAnswer(answer: OfflineAnswer): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).add(answer);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    const reg = await navigator.serviceWorker.ready;
    if ("sync" in reg) {
      try {
        // Background Sync API is not in the standard lib DOM types.
        const syncReg = reg as ServiceWorkerRegistration & {
          sync: { register: (tag: string) => Promise<void> };
        };
        await syncReg.sync.register("pycil-answer-queue");
      } catch {
        // background sync registration is best-effort
      }
    }
  }
}

export async function listPending(): Promise<OfflineAnswer[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result as OfflineAnswer[]);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteAnswer(id: number): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function flushQueue(
  submit: (a: OfflineAnswer) => Promise<void>,
): Promise<{ flushed: number; failed: number }> {
  const pending = await listPending();
  let flushed = 0;
  let failed = 0;
  for (const ans of pending) {
    try {
      await submit(ans);
      if (typeof ans.id === "number") await deleteAnswer(ans.id);
      flushed++;
    } catch {
      failed++;
    }
  }
  return { flushed, failed };
}
