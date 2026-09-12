export type ImportedAsset = {
  id: string;
  trackId: string;
  kind: "images" | "motion";
  slot: number;
  name: string;
  blob: Blob;
  created?: number;
};
function open() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("sound-vision-video", 1);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore("assets", {
        keyPath: "id",
      });
      store.createIndex("trackId", "trackId");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
export async function loadAssets(trackId: string): Promise<ImportedAsset[]> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("assets", "readonly");
    const request = tx.objectStore("assets").index("trackId").getAll(trackId);
    tx.oncomplete = () => {
      db.close();
      resolve(request.result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
    tx.onabort = () => {
      db.close();
      reject(tx.error || new Error("Media storage was interrupted."));
    };
  });
}
export async function saveAssets(assets: ImportedAsset[]) {
  const db = await open();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction("assets", "readwrite");
    assets.forEach((asset) => tx.objectStore("assets").put(asset));
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
    tx.onabort = () => {
      db.close();
      reject(
        tx.error ||
          new Error("Media could not be saved. Browser storage may be full."),
      );
    };
  });
}
export async function removeAsset(id: string) {
  const db = await open();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction("assets", "readwrite");
    tx.objectStore("assets").delete(id);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
    tx.onabort = () => {
      db.close();
      reject(tx.error || new Error("Media removal was interrupted."));
    };
  });
}
