# dev

Dev mode: a free camera for exploring the world and taking notes on what is wrong with it. Turn it on and off from
the pause screen, or with the backquote key, left of 1. The player waits where they were; leaving dev mode stands them on
whatever is under the camera.

| | keyboard and mouse | controller |
|---|---|---|
| fly | W A S D, along where the camera looks | left stick |
| up, down | E or Space, Q or C | right trigger, left trigger |
| fast | hold Shift | hold the left bumper |
| speed | scroll | |
| look around | drag, or the arrow keys | right stick |
| take a note | N, then type it | North (Y on Xbox, Triangle on PlayStation) |
| export the notes | X | |

A note keeps a screenshot, the camera's place and heading, the point it looks at, a `#start=` link that stands the
player there, and the text typed for it. Exporting downloads `hakuba-notes.zip` (`notes.md` with every note, and
its screenshots), and sends the same zip to `notes/` beside the page, where a server can keep it. On the desktop the
zip is written to the current folder instead.

- `lib.rs` turns dev mode on and off, flies the camera and shows the keys.
- `notes.rs` takes the notes and exports them.
- `zip.rs` writes the zip.
