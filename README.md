# S.A.D. Realtime

By [freekieaudio.uk](https://freekieaudio.uk)

A live calculator for subwoofer array delay, gain and polarity, built on
the array math from Merlijn van Veen's S.A.D. (Subwoofer Array Designer)
spreadsheet ([merlijnvanveen.nl](https://www.merlijnvanveen.nl/)), plus
some extensions of its own. It gives the three per-sub values only: there
is no polar or SPL prediction, so check the result in a prediction tool or
on site.

**100% vibe coded. Use at your own risk and check all calculations before
use.**

There are two versions, and both run the same math file (`shared/array_math.py`):

- **Web app:** https://mrfreekie.github.io/sad-realtime-osc/ runs in a laptop
  browser, needs no install, and works offline at venues after one online
  visit. It has a results table with Copy and CSV export, and no OSC.
- **Desktop app** (`realtime_app/`): Python + Tkinter, and it streams the
  values over OSC as you move the controls. See
  [realtime_app/README.md](realtime_app/README.md) for setup, the full user
  guide and credits.

Project files (`.sadrt`) open in either app.

☕ Free to use. If it saves you time on a show, you can
[buy me a coffee](https://buymeacoffee.com/fohengineer).

## Checks

Every push runs [`.github/workflows/pages.yml`](.github/workflows/pages.yml),
which does three things:

1. It runs 115 snapshot cases through the math in desktop Python and again
   in Pyodide, the Python build the web app uses.
2. It runs the desktop app without a screen beside the web app's logic and
   checks that every readout and saved file matches.
3. If the checks pass on `master`, it publishes the web app.

To run the same checks locally:

```bash
python tests/check_parity.py
python tests/check_web_model.py
```
