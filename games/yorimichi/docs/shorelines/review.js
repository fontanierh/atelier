'use strict';
function item(tag, text, parent, className) {
 const element = document.createElement(tag);
 if (text) element.textContent = text;
 if (className) element.className = className;
 if (parent) parent.append(element);
 return element;
}
fetch('assets/runtime-review.json', {cache:'no-cache'}).then(response => {
 if (!response.ok) throw Error('Review unavailable');
 return response.json();
}).then(data => {
 document.querySelector('#review-state').textContent = data.state;
 document.querySelector('#review-summary').textContent = data.summary;
 document.querySelector('#review-scope').textContent = data.scope;
 for (const text of data.checks || []) item('li', text, document.querySelector('#review-checks'));
 for (const text of data.limits || []) item('li', text, document.querySelector('#review-limits'));
 for (const shot of data.stills || []) {
  const figure = item('figure', '', document.querySelector('#still-grid'));
  const link = item('a', '', figure); link.href = shot.src;
  const image = item('img', '', link); image.src=shot.src; image.alt=shot.title; image.loading='lazy'; image.width=1600; image.height=900;
  item('figcaption', shot.title, figure);
 }
 document.querySelector('#review-stills').hidden = !(data.stills || []).length;
 for (const film of data.films || []) {
  const figure = item('figure', '', document.querySelector('#film-grid'));
  const video = item('video', '', figure); video.controls=true; video.preload='none'; video.playsInline=true; video.src=film.src;
  if (film.poster) video.poster=film.poster;
  item('figcaption', film.title, figure);
 }
 document.querySelector('#review-films').hidden = !(data.films || []).length;
 for (const source of data.links || []) {
  const paragraph = item('p', '', document.querySelector('#review-links'));
  const link = item('a', source.title+' ↗', paragraph); link.href=source.href;
 }
 if (data.revision) document.querySelector('#review-revision').textContent='Captured revision '+data.revision+(data.date?' · '+data.date:'');
}).catch(() => {
 document.querySelector('#review-state').textContent='Implementation in review';
 document.querySelector('#review-summary').textContent='The latest evidence could not load. The original proposal and its ten location briefs remain available.';
});
