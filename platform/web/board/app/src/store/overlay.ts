// What sits over the board: the photo lightbox, the document reader and the confirmation sheet.
import {api, message} from '../api/client';
import type {File as BoardFile} from '../api/schema';
import {Store} from './store';

export interface Overlay {
  photo: BoardFile | null;
  reader: {file: BoardFile; html: string | null; status: string} | null;
  sheet: {title: string; text: string; action: string; resolve: (ok: boolean) => void} | null;
}

export const overlay = new Store<Overlay>({photo: null, reader: null, sheet: null});

export const openPhoto = (file: BoardFile) => overlay.set({photo: file});
export const closePhoto = () => overlay.set({photo: null});

export async function openReader(file: BoardFile): Promise<void> {
  overlay.set({reader: {file, html: null, status: 'Opening…'}});
  try {
    const doc = await api.document(file.id);
    if (overlay.get().reader?.file.id === file.id) overlay.set({reader: {file, html: doc.html, status: ''}});
  } catch (error) {
    if (overlay.get().reader?.file.id === file.id) {
      overlay.set({reader: {file, html: null, status: message(error, 'This file could not be opened.')}});
    }
  }
}
export const closeReader = () => overlay.set({reader: null});

/** An action sheet that answers whether the person confirmed. */
export function confirmSheet(title: string, text: string, action: string): Promise<boolean> {
  overlay.get().sheet?.resolve(false);
  return new Promise((resolve) => overlay.set({sheet: {title, text, action, resolve}}));
}
