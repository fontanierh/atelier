// The board app. React renders the panes inside the page's #app container; the playful layer (board-fx.js) and the
// meadow scene (board-scene.js) load after this script and find the DOM already there.
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {App} from './ui/Shell';
import {startPolling} from './store/board';
import {standalone} from './lib/media';

document.documentElement.classList.toggle('standalone', standalone);
const root = createRoot(document.getElementById('app')!);
flushSync(() => root.render(<App />));
startPolling();
