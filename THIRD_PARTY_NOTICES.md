# Third-party notices

Sentinel contains adapted source-code portions from the following projects.
The adaptations change module format, data shape, and integration details.

## God's Eye View

- Project: https://github.com/bilawalsidhu/gods-eye-view
- Upstream files: `src/data/adsbLolFallback.js`,
  `src/layers/earthquakes/index.js`, `src/layers/earthquakes/model.js`, and
  `src/layers/earthquakes/records.js`
- Sentinel files: `sentinel/data/geo.py` (adsb.lol normalizer); the earthquake layer was later re-implemented for globe.gl
- Copyright (c) 2026 Bilawal Sidhu
- License: MIT

## OSIRIS

- Project: https://github.com/simplifaisoul/osiris
- Upstream file: `src/lib/sourceCache.ts`
- Sentinel file: `sentinel/core/cache.py`
- Copyright (c) 2026 simplifaisoul
- License: MIT

## MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Runtime datasets remain subject to their providers' terms, including
adsb.lol's ODbL data terms and USGS source attribution.
